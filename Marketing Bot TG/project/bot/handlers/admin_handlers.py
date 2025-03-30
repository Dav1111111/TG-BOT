"""
Обработчики административных команд (только для админов)
"""
import logging
import asyncio
from datetime import datetime, timedelta
from aiogram import types, F
from aiogram.filters.command import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.config import config
from bot.database import DBManager

logger = logging.getLogger(__name__)
db = DBManager()

class BroadcastStates(StatesGroup):
    """Состояния для рассылки сообщений"""
    waiting_for_message = State()
    confirm_broadcast = State()

# Проверка прав администратора
def is_admin(user_id):
    """Проверить, является ли пользователь администратором"""
    return user_id in config.ADMIN_IDS

async def stats_command(message: types.Message):
    """
    Обработчик команды /stats - показывает статистику использования бота
    """
    user_id = message.from_user.id

    # Проверяем, является ли пользователь администратором
    if not is_admin(user_id):
        await message.answer("⛔ У вас нет прав для выполнения этой команды")
        return

    # Получаем статистику из базы данных
    try:
        # Общая статистика
        total_users = db.execute_query("SELECT COUNT(*) FROM users", fetch=True)[0][0]
        active_users = db.execute_query(
            "SELECT COUNT(*) FROM users WHERE last_activity > ?",
            (datetime.now() - timedelta(days=7),),
            fetch=True
        )[0][0]
        total_messages = db.execute_query("SELECT SUM(message_count) FROM users", fetch=True)[0][0] or 0

        # Статистика по PDF файлам
        pdf_count = db.execute_query("SELECT COUNT(*) FROM knowledge_base_docs", fetch=True)[0][0]

        # Формируем сообщение со статистикой
        stats_message = (
            "📊 <b>Статистика использования бота</b>\n\n"
            f"👥 <b>Пользователи:</b>\n"
            f"• Всего пользователей: {total_users}\n"
            f"• Активных за 7 дней: {active_users}\n\n"
            f"💬 <b>Сообщения:</b>\n"
            f"• Всего обработано: {total_messages}\n\n"
            f"📚 <b>База знаний:</b>\n"
            f"• PDF документов: {pdf_count}\n"
        )

        await message.answer(stats_message, parse_mode="HTML")
        logger.info(f"Admin {user_id} requested stats")

    except Exception as e:
        logger.error(f"Error getting statistics: {e}")
        await message.answer("❌ Произошла ошибка при получении статистики")

async def broadcast_command(message: types.Message, state: FSMContext):
    """
    Обработчик команды /broadcast - начинает процесс рассылки сообщений
    """
    user_id = message.from_user.id

    # Проверяем, является ли пользователь администратором
    if not is_admin(user_id):
        await message.answer("⛔ У вас нет прав для выполнения этой команды")
        return

    # Переходим в состояние ожидания сообщения для рассылки
    await state.set_state(BroadcastStates.waiting_for_message)

    await message.answer(
        "📣 <b>Подготовка рассылки сообщений</b>\n\n"
        "Отправьте сообщение, которое нужно разослать всем пользователям.\n"
        "Поддерживается HTML-форматирование.\n\n"
        "Для отмены используйте команду /cancel",
        parse_mode="HTML"
    )

    logger.info(f"Admin {user_id} started broadcast process")

async def process_broadcast_message(message: types.Message, state: FSMContext):
    """
    Обработчик для получения сообщения для рассылки
    """
    # Сохраняем сообщение в состоянии
    await state.update_data(broadcast_message=message.html_text)

    # Переходим в состояние подтверждения рассылки
    await state.set_state(BroadcastStates.confirm_broadcast)

    # Создаем клавиатуру для подтверждения
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_broadcast"),
            types.InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_broadcast")
        ]
    ])

    # Получаем количество пользователей
    total_users = db.execute_query("SELECT COUNT(*) FROM users", fetch=True)[0][0]

    await message.answer(
        f"📣 <b>Подтверждение рассылки</b>\n\n"
        f"Ваше сообщение будет отправлено <b>{total_users}</b> пользователям.\n\n"
        f"<b>Предпросмотр сообщения:</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"{message.html_text}\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
        f"Подтвердите отправку или отмените рассылку.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

async def confirm_broadcast_callback(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Обработчик подтверждения рассылки
    """
    await callback_query.answer()

    # Получаем сообщение из состояния
    state_data = await state.get_data()
    broadcast_message = state_data.get('broadcast_message')

    if not broadcast_message:
        await callback_query.message.edit_text("❌ Ошибка: сообщение для рассылки не найдено")
        await state.clear()
        return

    # Получаем список всех пользователей
    users = db.execute_query("SELECT user_id FROM users", fetch=True)
    total_users = len(users)
    success_count = 0

    # Отправляем сообщение о начале рассылки
    status_message = await callback_query.message.edit_text(
        "📣 <b>Рассылка начата</b>\n\n"
        f"Отправка сообщения {total_users} пользователям...\n"
        "Это может занять некоторое время.",
        parse_mode="HTML"
    )

    # Отправляем сообщения всем пользователям
    for user in users:
        user_id = user[0]
        try:
            await callback_query.bot.send_message(
                chat_id=user_id,
                text=broadcast_message,
                parse_mode="HTML"
            )
            success_count += 1

            # Обновляем статус каждые 10 отправленных сообщений
            if success_count % 10 == 0:
                await status_message.edit_text(
                    "📣 <b>Рассылка выполняется</b>\n\n"
                    f"Отправлено: {success_count}/{total_users}\n"
                    f"Прогресс: {success_count/total_users*100:.1f}%",
                    parse_mode="HTML"
                )

            # Добавляем небольшую задержку, чтобы избежать блокировки API
            await asyncio.sleep(0.1)

        except Exception as e:
            logger.error(f"Error sending broadcast to user {user_id}: {e}")

    # Отправляем сообщение о завершении рассылки
    await status_message.edit_text(
        "✅ <b>Рассылка завершена</b>\n\n"
        f"Отправлено успешно: {success_count}/{total_users}\n"
        f"Процент успешных отправок: {success_count/total_users*100:.1f}%",
        parse_mode="HTML"
    )

    # Очищаем состояние
    await state.clear()

    logger.info(f"Broadcast completed: {success_count}/{total_users} messages sent")

async def cancel_broadcast_callback(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Обработчик отмены рассылки
    """
    await callback_query.answer()
    await callback_query.message.edit_text("❌ Рассылка отменена")
    await state.clear()

    logger.info(f"Broadcast cancelled by admin {callback_query.from_user.id}")

async def cancel_command(message: types.Message, state: FSMContext):
    """
    Обработчик команды /cancel для отмены операций
    """
    current_state = await state.get_state()
    if current_state in [BroadcastStates.waiting_for_message, BroadcastStates.confirm_broadcast]:
        await state.clear()
        await message.answer("❌ Рассылка отменена")
        logger.info(f"Broadcast cancelled by admin {message.from_user.id}")
    else:
        await message.answer("❓ Нет активных операций для отмены")

def register_handlers(dp):
    """
    Регистрация обработчиков административных команд
    """
    # Регистрируем обработчик статистики
    dp.message.register(stats_command, Command("stats"))

    # Регистрируем обработчики для рассылки
    dp.message.register(broadcast_command, Command("broadcast"))
    dp.message.register(process_broadcast_message, BroadcastStates.waiting_for_message)
    dp.callback_query.register(confirm_broadcast_callback, F.data == "confirm_broadcast")
    dp.callback_query.register(cancel_broadcast_callback, F.data == "cancel_broadcast")

    # Регистрируем обработчик отмены
    dp.message.register(cancel_command, Command("cancel"))
