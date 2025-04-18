"""
Модуль для обработки платежей и подписок в Telegram боте
"""
import logging
from datetime import datetime, timedelta
from aiogram import types, Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from bot.config import config
from bot.database import DBManager
from bot.utils.yookassa_client import create_payment, check_payment_status

# Инициализируем логгер
logger = logging.getLogger(__name__)

# Инициализируем базу данных
db = DBManager()

# Настройки платежей
CURRENCY = config.PAYMENT_CURRENCY

# Информация о подписке
SUBSCRIPTION = {
    "title": "Премиум подписка",
    "description": "Полный доступ к функциям бота",
    "price": 1,  # В рублях
    "days": 30,  # Срок действия в днях
    "messages_limit": 500  # Лимит сообщений
}

async def subscription_command(message: Message):
    """
    Обработчик команды /subscribe - показывает информацию о подписке
    """
    if not config.YOOKASSA_SHOP_ID or not config.YOOKASSA_SECRET_KEY:
        await message.answer(
            "⚠️ Платежная система временно недоступна. "
            "Пожалуйста, обратитесь к администратору."
        )
        logger.warning("YooKassa credentials not configured")
        return
    
    # Получаем информацию о текущем статусе подписки пользователя
    user_id = message.from_user.id
    subscription_status = db.get_subscription_status(user_id)
    msg_count = db.get_user_message_count(user_id)
    
    # Формируем текст сообщения
    if subscription_status == "premium":
        # Получаем дату окончания подписки
        expiry_date = db.execute_query(
            "SELECT subscription_expiry FROM users WHERE user_id = ?",
            (user_id,),
            True
        )
        
        expiry_str = "Неизвестно"
        if expiry_date and expiry_date[0][0]:
            try:
                # Преобразуем строку даты в объект datetime
                if isinstance(expiry_date[0][0], str):
                    expiry = datetime.fromisoformat(expiry_date[0][0])
                else:
                    expiry = expiry_date[0][0]
                expiry_str = expiry.strftime("%d.%m.%Y")
            except Exception as e:
                logger.error(f"Error parsing expiry date: {e}")
        
        text = (
            f"🔹 <b>Информация о подписке</b>\n\n"
            f"У вас активна <b>Премиум подписка</b>\n"
            f"Действует до: <b>{expiry_str}</b>\n"
            f"Использовано сообщений: <b>{msg_count}/{SUBSCRIPTION['messages_limit']}</b>\n\n"
            f"Хотите продлить подписку?"
        )
    else:
        limit = config.SUBSCRIPTION_LIMITS["free"]
        text = (
            f"🔹 <b>Информация о подписке</b>\n\n"
            f"У вас базовый тариф (бесплатный)\n"
            f"Лимит сообщений: <b>{limit}</b>\n"
            f"Использовано: <b>{msg_count}/{limit}</b>\n\n"
            f"Преимущества Премиум подписки:\n"
            f"✅ Расширенный лимит сообщений: {SUBSCRIPTION['messages_limit']}\n"
            f"✅ Доступ ко всем функциям бота\n"
            f"✅ Приоритетная поддержка\n\n"
            f"Стоимость: <b>{SUBSCRIPTION['price']} {CURRENCY}</b>\n"
            f"Срок: <b>{SUBSCRIPTION['days']} дней</b>"
        )
    
    # Создаем кнопку для оплаты
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(
            text=f"Оформить подписку за {SUBSCRIPTION['price']} {CURRENCY}",
            callback_data="subscribe"
        )]
    ])
    
    # Отправляем сообщение с информацией о подписке
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    
    logger.info(f"Subscription info shown to user {user_id}")

async def subscribe_callback(callback_query: types.CallbackQuery):
    """
    Обработчик нажатия на кнопку подписки
    """
    await callback_query.answer()
    
    user_id = callback_query.from_user.id
    
    # Создаем платеж в ЮKassa
    payment_info = create_payment(
        amount=SUBSCRIPTION["price"],
        description=f"{SUBSCRIPTION['title']} - {SUBSCRIPTION['description']}",
        user_id=user_id,
        subscription_type="premium"
    )
    
    if not payment_info:
        await callback_query.message.answer(
            "❌ Не удалось создать платеж. Пожалуйста, попробуйте позже."
        )
        return
    
    # Сохраняем информацию о платеже в базе данных
    db.save_payment_info(user_id, payment_info["id"], "premium", SUBSCRIPTION["price"])
    
    # Создаем клавиатуру с кнопками оплаты и проверки
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(
            text="Оплатить",
            url=payment_info["confirmation_url"]
        )],
        [types.InlineKeyboardButton(
            text="Проверить оплату",
            callback_data="check_payment"
        )]
    ])
    
    # Отправляем сообщение с ссылкой на оплату
    await callback_query.message.answer(
        f"💳 <b>Оплата подписки</b>\n\n"
        f"Тариф: <b>{SUBSCRIPTION['title']}</b>\n"
        f"Сумма: <b>{SUBSCRIPTION['price']} {CURRENCY}</b>\n"
        f"Длительность: <b>{SUBSCRIPTION['days']} дней</b>\n\n"
        f"Нажмите кнопку ниже, чтобы перейти к оплате. После оплаты вернитесь сюда и нажмите 'Проверить оплату'.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    
    logger.info(f"Payment link sent to user {user_id}")

async def check_payment_callback(callback_query: types.CallbackQuery):
    """
    Обработчик нажатия на кнопку проверки оплаты
    """
    await callback_query.answer()
    
    # Получаем ID пользователя
    user_id = callback_query.from_user.id
    
    # Получаем информацию о последнем платеже пользователя
    payment_info = db.get_last_payment(user_id)
    
    if not payment_info:
        await callback_query.message.answer("⚠️ Информация о платеже не найдена")
        return
    
    payment_id = payment_info[0]
    
    # Проверяем статус платежа
    payment_status = check_payment_status(payment_id)
    
    if not payment_status:
        await callback_query.message.answer(
            "❌ Не удалось проверить статус платежа. Пожалуйста, попробуйте позже."
        )
        return
    
    # Если платеж успешно оплачен
    if payment_status["status"] == "succeeded" and payment_status["paid"]:
        # Обновляем статус подписки пользователя
        update_subscription(user_id, "premium", SUBSCRIPTION["days"])
        update_message_limit(user_id, SUBSCRIPTION["messages_limit"])
        
        # Отправляем сообщение об успешной подписке
        await callback_query.message.answer(
            f"✅ <b>Подписка успешно оформлена!</b>\n\n"
            f"Подписка: {SUBSCRIPTION['title']}\n"
            f"Срок действия: {SUBSCRIPTION['days']} дней\n"
            f"Лимит сообщений: {SUBSCRIPTION['messages_limit']}\n\n"
            f"Благодарим за покупку! Теперь вам доступны расширенные возможности бота.",
            parse_mode="HTML"
        )
        
        logger.info(f"User {user_id} successfully purchased premium subscription")
    else:
        # Отправляем сообщение о статусе платежа
        await callback_query.message.answer(
            f"ℹ️ <b>Статус платежа</b>: {payment_status['status']}\n\n"
            f"Пожалуйста, завершите оплату или попробуйте позже.",
            parse_mode="HTML"
        )

def update_subscription(user_id: int, status: str, days: int):
    """
    Обновляет статус подписки пользователя в базе данных
    """
    try:
        # Вычисляем дату окончания подписки
        expiry_date = datetime.now() + timedelta(days=days)
        
        # Обновляем статус подписки и дату окончания
        db.execute_query(
            "UPDATE users SET subscription_status = ?, subscription_expiry = ? WHERE user_id = ?",
            (status, expiry_date, user_id)
        )
        
        logger.info(f"Updated subscription for user {user_id} to {status} until {expiry_date}")
        return True
    except Exception as e:
        logger.error(f"Error updating subscription for user {user_id}: {e}")
        return False

def update_message_limit(user_id: int, limit: int):
    """
    Обновляет лимит сообщений пользователя в базе данных
    """
    try:
        # Обновляем лимит сообщений для пользователя
        # Сначала сбрасываем счетчик сообщений
        db.execute_query(
            "UPDATE users SET messages_count = 0, message_limit = ? WHERE user_id = ?",
            (limit, user_id)
        )
        
        logger.info(f"Reset message count and set limit to {limit} for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error updating message limit for user {user_id}: {e}")
        return False

def register_handlers(dp: Router):
    """
    Регистрирует обработчики для платежей и подписок
    """
    # Команда для подписки
    dp.message.register(subscription_command, Command("subscribe"))
    
    # Обработчик нажатия на кнопку подписки
    dp.callback_query.register(subscribe_callback, F.data == "subscribe")
    
    # Обработчик проверки оплаты
    dp.callback_query.register(check_payment_callback, F.data == "check_payment")
    
    logger.info("Payment handlers registered") 