"""
Обработчик для создания ценностного предложения
"""
import logging
import re
from aiogram import types, F
from aiogram.filters.command import Command
from aiogram.fsm.context import FSMContext
from bot.states.states import ValuePropositionStates
from bot.config.prompts import VALUE_PROPOSITION_PROMPT, VALUE_PROPOSITION_GENERATION_PROMPT
from bot.utils.ai_client import generate_gpt_response
from bot.utils.text_utils import split_message, remove_asterisks

logger = logging.getLogger(__name__)

async def value_proposition_callback(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Обработчик для кнопки "Сформировать ценностное предложение"
    """
    await callback_query.answer()

    # Устанавливаем состояние ожидания информации о бизнесе
    await state.set_state(ValuePropositionStates.waiting_for_info)

    # Отправляем запрос информации
    await callback_query.message.answer(VALUE_PROPOSITION_PROMPT)

    logger.info(f"User {callback_query.from_user.id} started value proposition creation")

async def value_proposition_command(message: types.Message, state: FSMContext):
    """
    Обработчик для команды /value
    """
    # Устанавливаем состояние ожидания информации о бизнесе
    await state.set_state(ValuePropositionStates.waiting_for_info)

    # Отправляем запрос информации
    await message.answer(VALUE_PROPOSITION_PROMPT)

    logger.info(f"User {message.from_user.id} started value proposition creation via command")

async def handle_value_proposition_info(message: types.Message, state: FSMContext):
    """
    Обработчик для получения информации о бизнесе и создания ценностного предложения
    """
    # Получаем информацию о бизнесе
    business_info = message.text

    # Отправляем сообщение о начале генерации
    processing_msg = await message.answer("Генерирую ценностное предложение на основе предоставленной информации...")

    try:
        # Импортируем здесь, чтобы избежать циклических импортов
        from bot.knowledge_base.vector_kb_manager import VectorKnowledgeBaseManager
        
        # Получаем контент из базы знаний по запросу
        kb_manager = VectorKnowledgeBaseManager()
        knowledge_content = kb_manager.get_content_for_query(business_info)
        
        # Добавляем дополнительный контекст из базы знаний, если он найден
        kb_context = ""
        if knowledge_content:
            kb_context = f"\n\nИспользуйте следующую информацию из базы знаний при создании ценностного предложения:\n{knowledge_content}"
        
        # Формируем запрос к GPT
        prompt = VALUE_PROPOSITION_GENERATION_PROMPT.format(business_info=business_info) + kb_context

        # Создаем сообщения для запроса
        messages = [
            {"role": "system", "content": "Ты — эксперт по маркетингу и ценностным предложениям. Твоя задача создать структурированное ценностное предложение на основе информации о бизнесе."},
            {"role": "user", "content": prompt}
        ]

        # Генерируем ценностное предложение
        response = await generate_gpt_response(messages=messages)

        # Убираем форматирование звездочками
        response = remove_asterisks(response)

        # Удаляем сообщение о генерации
        await processing_msg.delete()

        # Отправляем вступительное сообщение
        await message.answer("<b>Ценностное предложение</b>\n\nНиже будут отправлены разделы ценностного предложения:")

        # Поиск ключевых блоков ценностного предложения
        # Ищем заголовки блоков АУДИТОРИЯ и ПРОДУКТ
        audience_match = re.search(r'(?i)АУДИТОРИЯ', response)
        product_match = re.search(r'(?i)ПРОДУКТ', response)
        
        sections = []
        
        if audience_match and product_match:
            # Если найдены оба блока, разделяем их
            audience_start = audience_match.start()
            product_start = product_match.start()
            
            # Получаем блок АУДИТОРИЯ
            audience_text = response[audience_start:product_start].strip()
            
            # Получаем блок ПРОДУКТ
            product_text = response[product_start:].strip()
            
            # Ищем подразделы в блоке АУДИТОРИЯ
            audience_sections = extract_value_proposition_sections(audience_text)
            
            # Ищем подразделы в блоке ПРОДУКТ
            product_sections = extract_value_proposition_sections(product_text)
            
            # Отправляем заголовок блока АУДИТОРИЯ
            await message.answer(f"<b>{audience_match.group(0)}</b>")
            
            # Отправляем подразделы блока АУДИТОРИЯ
            for section in audience_sections:
                await message.answer(section)
            
            # Отправляем заголовок блока ПРОДУКТ
            await message.answer(f"<b>{product_match.group(0)}</b>")
            
            # Отправляем подразделы блока ПРОДУКТ
            for section in product_sections:
                await message.answer(section)
        else:
            # Если структура не соответствует ожидаемой, отправляем по частям
            parts = split_message(response)
            for part in parts:
                await message.answer(part)

        # Очищаем состояние
        await state.clear()

        logger.info(f"Value proposition generated for user {message.from_user.id}")

    except Exception as e:
        logger.error(f"Error generating value proposition: {e}")
        await processing_msg.edit_text("Произошла ошибка при генерации ценностного предложения. Пожалуйста, попробуйте позже.")
        await state.clear()

def extract_value_proposition_sections(text):
    """
    Извлекает разделы ценностного предложения из текста
    
    Ищет разделы типа "Точка A", "Точка B", "Препятствия", "Магниты", "Трансформация", и т.д.
    """
    # Ищем все возможные подзаголовки в ценностном предложении
    section_titles = [
        "Точка A", "Точка B", "Препятствия", "Магниты",
        "Трансформация", "Функции", "Конкуренты", "Немезида", "Уникальность"
    ]
    
    sections = []
    last_pos = 0
    text_length = len(text)
    
    # Ищем подзаголовки в порядке их появления в тексте
    positions = []
    for title in section_titles:
        match = re.search(rf'(?i){re.escape(title)}', text)
        if match:
            positions.append((match.start(), title))
    
    # Сортируем по позиции в тексте
    positions.sort()
    
    # Разделяем текст по найденным подзаголовкам
    for i, (pos, title) in enumerate(positions):
        next_pos = text_length
        if i < len(positions) - 1:
            next_pos = positions[i+1][0]
        
        section_text = text[pos:next_pos].strip()
        # Выделяем заголовок жирным
        section_text = re.sub(rf'(?i)({re.escape(title)})', r'<b>\1</b>', section_text)
        sections.append(section_text)
    
    return sections

def register_handlers(dp):
    """
    Регистрация обработчиков для создания ценностного предложения
    """
    # Регистрируем обработчик кнопки
    dp.callback_query.register(value_proposition_callback, F.data == "value_proposition")

    # Регистрируем обработчик команды /value
    dp.message.register(value_proposition_command, Command("value"))

    # Регистрируем обработчик получения информации о бизнесе
    dp.message.register(handle_value_proposition_info, ValuePropositionStates.waiting_for_info)
