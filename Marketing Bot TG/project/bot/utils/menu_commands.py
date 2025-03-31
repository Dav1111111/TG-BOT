"""
Модуль для настройки команд и меню бота в Telegram
"""
from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat
from aiogram.types import MenuButtonCommands, MenuButtonDefault, MenuButtonWebApp
from aiogram.types import WebAppInfo

# Список команд бота с описаниями
BOT_COMMANDS = [
    BotCommand(command="start", description="Начать работу с ботом"),
    BotCommand(command="business", description="Создать бизнес-план"),
    BotCommand(command="value", description="Создать ценностное предложение"),
    BotCommand(command="subscribe", description="Оплата"),
    BotCommand(command="help", description="О боте"),
    BotCommand(command="feedback", description="Отправить обратную связь"),

]

# Команды для администраторов
ADMIN_COMMANDS = BOT_COMMANDS + [
    BotCommand(command="stats", description="Статистика использования бота"),
    BotCommand(command="broadcast", description="Отправить сообщение всем пользователям"),
]

async def set_bot_commands(bot: Bot, admin_ids=None):
    """
    Установить команды бота в меню

    Args:
        bot: Экземпляр бота
        admin_ids: Список ID администраторов
    """
    # Устанавливаем основные команды для всех пользователей
    await bot.set_my_commands(BOT_COMMANDS, scope=BotCommandScopeDefault())

    # Устанавливаем расширенные команды для администраторов
    if admin_ids:
        for admin_id in admin_ids:
            try:
                await bot.set_my_commands(
                    ADMIN_COMMANDS,
                    scope=BotCommandScopeChat(chat_id=admin_id)
                )
            except Exception as e:
                print(f"Ошибка при установке команд для админа {admin_id}: {e}")

async def set_menu_button(bot: Bot):
    """
    Установить кнопку меню бота

    Args:
        bot: Экземпляр бота
    """
    # Устанавливаем кнопку меню с командами
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
