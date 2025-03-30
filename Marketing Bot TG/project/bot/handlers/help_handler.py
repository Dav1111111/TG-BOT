"""
Обработчик команды /help
"""
import logging
from aiogram import types, F
from aiogram.filters.command import Command

logger = logging.getLogger(__name__)

# Текст справки
HELP_TEXT = """
🤖 <b>Бот-ассистент по маркетингу и бизнесу</b>

Я помогу вам создать маркетинговые материалы и решить бизнес-задачи:

📊 <b>Основные возможности:</b>
• Создание бизнес-планов
• Формирование ценностных предложений
• Маркетинговые советы и рекомендации
• Поиск информации в базе знаний

📝 <b>Доступные команды:</b>
/start - Начать работу с ботом
/business - Создать бизнес-план
/value - Создать ценностное предложение
/help - Помощь по боту
/feedback - Отправить обратную связь

💡 <b>Как использовать:</b>
• Выберите нужную команду из меню
• Следуйте инструкциям бота
• Для быстрого доступа к командам используйте кнопку меню в чате
• Вы можете задать любой вопрос, и бот ответит с использованием доступных знаний
"""

async def help_command(message: types.Message):
    """
    Обработчик команды /help
    """
    # Отправляем сообщение с помощью
    await message.answer(HELP_TEXT, parse_mode="HTML")

    logger.info(f"User {message.from_user.id} requested help")

async def help_button_callback(callback_query: types.CallbackQuery):
    """
    Обработчик нажатия на кнопку помощи
    """
    # Отвечаем на callback query, чтобы убрать часы загрузки
    await callback_query.answer()
    
    # Отправляем сообщение с помощью
    await callback_query.message.answer(HELP_TEXT, parse_mode="HTML")
    
    logger.info(f"User {callback_query.from_user.id} clicked help button")

def register_handlers(dp):
    """
    Регистрация обработчиков команды /help
    """
    dp.message.register(help_command, Command("help"))
    dp.callback_query.register(help_button_callback, F.data == "help_button")
