"""
Обработчики для начала работы с ботом (команда /start)
"""
import logging
from aiogram import types
from aiogram.filters.command import Command
from bot.config.prompts import START_TEXT
from bot.database import DBManager

logger = logging.getLogger(__name__)
db = DBManager()

async def start_command(message: types.Message):
    """
    Обработчик команды /start - начало работы с ботом
    """
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    # Обновляем информацию о активности пользователя
    db.update_user_activity(user_id)
    
    # Отправляем приветственное сообщение
    await message.answer(
        START_TEXT,
        parse_mode="HTML"
    )
    
    logger.info(f"User {user_id} started the bot")

def register_handlers(dp):
    """
    Регистрация обработчиков для начала работы с ботом
    """
    # Регистрируем обработчик команды /start
    dp.message.register(start_command, Command("start"))