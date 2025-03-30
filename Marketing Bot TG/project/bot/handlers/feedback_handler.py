"""
Обработчик команды /feedback для отправки обратной связи
"""
import logging
from aiogram import types, Bot
from aiogram.filters.command import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

logger = logging.getLogger(__name__)

# ID администратора для получения обратной связи
ADMIN_ID = 780848273

# Определение состояний для FSM
class FeedbackStates(StatesGroup):
    """Состояния для обработки обратной связи"""
    waiting_for_feedback = State()

async def feedback_command(message: types.Message, state: FSMContext):
    """
    Обработчик команды /feedback
    """
    # Устанавливаем состояние ожидания текста обратной связи
    await state.set_state(FeedbackStates.waiting_for_feedback)
    
    # Отправляем сообщение с инструкцией
    await message.answer(
        "Пожалуйста, напишите ваши комментарии, пожелания или замечания по работе бота. "
        "Это сообщение будет отправлено разработчикам."
    )
    
    logger.info(f"User {message.from_user.id} started feedback process")

async def handle_feedback_message(message: types.Message, bot: Bot, state: FSMContext):
    """
    Обработчик получения сообщения с обратной связью
    """
    # Получаем текст обратной связи
    feedback_text = message.text
    
    # Информация о пользователе
    user_id = message.from_user.id
    username = message.from_user.username or "Нет username"
    first_name = message.from_user.first_name or "Неизвестно"
    last_name = message.from_user.last_name or "Неизвестно"
    
    # Формируем текст для администратора
    admin_text = (
        f"📬 <b>Получена обратная связь!</b>\n\n"
        f"👤 <b>От пользователя:</b>\n"
        f"ID: {user_id}\n"
        f"Имя: {first_name} {last_name}\n"
        f"Username: @{username}\n\n"
        f"💬 <b>Сообщение:</b>\n"
        f"{feedback_text}"
    )
    
    try:
        # Отправляем сообщение администратору
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_text,
            parse_mode="HTML"
        )
        
        # Подтверждаем получение обратной связи пользователю
        await message.answer(
            "Спасибо за вашу обратную связь! Ваше сообщение отправлено разработчикам."
        )
        
        logger.info(f"Feedback from user {user_id} sent to admin {ADMIN_ID}")
        
    except Exception as e:
        logger.error(f"Error sending feedback to admin: {e}")
        await message.answer(
            "Произошла ошибка при отправке обратной связи. Пожалуйста, попробуйте позже."
        )
    
    # Очищаем состояние
    await state.clear()

def register_handlers(dp):
    """
    Регистрация обработчиков для обратной связи
    """
    # Регистрируем обработчик команды /feedback
    dp.message.register(feedback_command, Command("feedback"))
    
    # Регистрируем обработчик получения сообщения с обратной связью
    dp.message.register(handle_feedback_message, FeedbackStates.waiting_for_feedback) 