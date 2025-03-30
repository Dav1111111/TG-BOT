"""
Module for storing the bot's state classes
"""
from aiogram.fsm.state import State, StatesGroup

class BusinessPlanStates(StatesGroup):
    """Состояния для создания бизнес-плана"""
    waiting_for_info = State()

class ValuePropositionStates(StatesGroup):
    """Состояния для создания ценностного предложения"""
    waiting_for_info = State()

class KnowledgeBaseStates(StatesGroup):
    """Состояния для работы с базой знаний"""
    waiting_for_pdf = State()
    waiting_for_title = State()
    waiting_for_delete_choice = State()
