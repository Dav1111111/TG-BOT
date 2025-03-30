"""
Обработчик для команды /cancel
"""
import logging
from aiogram import types
from aiogram.filters.command import Command
from aiogram.fsm.context import FSMContext
from bot.states.states import BusinessPlanStates, ValuePropositionStates, KnowledgeBaseStates

logger = logging.getLogger(__name__)

async def cancel_command(message: types.Message, state: FSMContext):
    """
    Обработчик команды /cancel - отменяет текущую операцию пользователя
    """
    # Получаем текущее состояние
    current_state = await state.get_state()

    # Если состояния нет, значит нечего отменять
    if current_state is None:
        await message.answer("🤔 У вас нет активных операций для отмены.")
        return

    # Определяем, какая операция отменяется
    cancel_message = "❌ Операция отменена."

    if current_state in [s.state for s in BusinessPlanStates.__states__]:
        cancel_message = "❌ Создание бизнес-плана отменено."
    elif current_state in [s.state for s in ValuePropositionStates.__states__]:
        cancel_message = "❌ Создание ценностного предложения отменено."
    elif current_state in [s.state for s in KnowledgeBaseStates.__states__]:
        cancel_message = "❌ Работа с базой знаний отменена."

    # Очищаем состояние
    await state.clear()

    # Отправляем сообщение об отмене
    await message.answer(cancel_message)

    logger.info(f"User {message.from_user.id} canceled operation in state {current_state}")

def register_handlers(dp):
    """
    Регистрация обработчика команды /cancel
    """
    dp.message.register(cancel_command, Command("cancel"))
