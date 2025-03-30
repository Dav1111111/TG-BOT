"""
Обработчики для бизнес-плана
"""
import logging
import asyncio
import re
from aiogram import types, F
from aiogram.filters.command import Command
from aiogram.fsm.context import FSMContext
from bot.utils.ai_client import generate_gpt_response
from bot.states.states import BusinessPlanStates
from bot.utils.text_utils import format_business_plan, split_message, split_response_into_sections
from bot.database import DBManager
from bot.config.prompts import BUSINESS_PLAN_PROMPT, BUSINESS_PLAN_GENERATION_PROMPT

logger = logging.getLogger(__name__)

async def business_plan_callback(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Обработчик для кнопки "Создать бизнес-план"
    """
    await callback_query.answer()

    # Устанавливаем состояние ожидания информации о бизнесе
    await state.set_state(BusinessPlanStates.waiting_for_info)

    # Отправляем запрос информации
    await callback_query.message.answer(BUSINESS_PLAN_PROMPT)

    logger.info(f"User {callback_query.from_user.id} started business plan creation")

async def business_plan_command(message: types.Message, state: FSMContext):
    """
    Обработчик для команды /business
    """
    # Устанавливаем состояние ожидания информации о бизнесе
    await state.set_state(BusinessPlanStates.waiting_for_info)

    # Отправляем запрос информации
    await message.answer(BUSINESS_PLAN_PROMPT)

    logger.info(f"User {message.from_user.id} started business plan creation via command")

async def handle_business_info(message: types.Message, state: FSMContext):
    """
    Обработчик для получения информации о бизнесе и создания бизнес-плана
    """
    # Получаем информацию о бизнесе
    business_info = message.text

    # Отправляем сообщение о начале генерации
    processing_msg = await message.answer("Генерирую бизнес-план на основе предоставленной информации...")

    try:
        # Импортируем здесь, чтобы избежать циклических импортов
        from bot.knowledge_base.vector_kb_manager import VectorKnowledgeBaseManager
        
        # Получаем контент из базы знаний по запросу
        kb_manager = VectorKnowledgeBaseManager()
        knowledge_content = kb_manager.get_content_for_query(business_info)
        
        # Добавляем дополнительный контекст из базы знаний, если он найден
        kb_context = ""
        if knowledge_content:
            kb_context = f"\n\nИспользуйте следующую информацию из базы знаний при создании бизнес-плана:\n{knowledge_content}"
        
        # Формируем запрос к GPT
        prompt = BUSINESS_PLAN_GENERATION_PROMPT.format(business_info=business_info) + kb_context

        # Создаем сообщения для запроса
        messages = [
            {"role": "system", "content": "Ты — эксперт по созданию бизнес-планов для предпринимателей. Твоя задача создать структурированный бизнес-план на основе информации о бизнесе. Ответ должен состоять из 10 ясно разделённых секций, которые я смогу отправить отдельными сообщениями."},
            {"role": "user", "content": prompt}
        ]

        # Генерируем бизнес-план
        response = await generate_gpt_response(messages=messages)

        # Форматируем ответ
        response = format_business_plan(response)

        # Удаляем сообщение о генерации
        await processing_msg.delete()

        # Отправляем сообщение о структуре бизнес-плана
        await message.answer("<b>Бизнес-план</b>\n\nНиже будут отправлены 10 разделов бизнес-плана:")
        
        # Фиксированные заголовки разделов для структурирования
        section_titles = [
            "1. Резюме проекта",
            "2. Описание продукта/услуги",
            "3. Анализ рынка",
            "4. Портрет целевой аудитории",
            "5. Конкурентный анализ",
            "6. Маркетинговая стратегия",
            "7. Бизнес-модель",
            "8. Операционный план",
            "9. Финансовый план",
            "10. Риски и их минимизация"
        ]
        
        # Сначала пытаемся найти все разделы с помощью регулярных выражений
        matches = []
        
        # Ищем с помощью HTML-тегов (после форматирования)
        html_pattern = r'<b>(\d+\.\s+[^<]+)</b>'
        html_matches = list(re.finditer(html_pattern, response))
        
        # Если нашли через HTML-теги
        if len(html_matches) >= 8:  # Ожидаем не менее 8 из 10 разделов для точности
            # Извлекаем позиции начала каждого раздела
            section_starts = [match.start() for match in html_matches]
            section_starts.append(len(response))  # Добавляем конец текста
            
            # Извлекаем каждый раздел
            sections = []
            for i in range(len(section_starts) - 1):
                section_text = response[section_starts[i]:section_starts[i+1]].strip()
                sections.append(section_text)
            
            # Отправляем каждый раздел отдельным сообщением
            for section in sections:
                await message.answer(section)
                
            # Проверяем, если у нас меньше 10 разделов, добавляем оставшиеся
            if len(sections) < 10:
                missing_count = 10 - len(sections)
                logger.info(f"Найдено только {len(sections)} разделов, добавляем {missing_count} пустых")
                
                for i in range(len(sections), 10):
                    await message.answer(f"<b>{section_titles[i]}</b>\n\nРаздел отсутствует в сгенерированном плане.")
                
        else:
            # Если не удалось найти разделы, принудительно делим на 10 частей
            logger.info("Не удалось найти разделы по тегам, делим текст на 10 частей")
            
            # Разделяем текст пополам для лучшего деления
            total_length = len(response)
            first_half = response[:total_length//2]
            second_half = response[total_length//2:]
            
            # Отправляем каждый раздел с соответствующим заголовком
            for i, title in enumerate(section_titles):
                if i < 5:
                    # Первая половина делится на 5 разделов
                    start = i * (len(first_half) // 5)
                    end = (i + 1) * (len(first_half) // 5) if i < 4 else len(first_half)
                    content = first_half[start:end]
                else:
                    # Вторая половина делится на 5 разделов
                    start = (i - 5) * (len(second_half) // 5)
                    end = (i - 4) * (len(second_half) // 5) if i < 9 else len(second_half)
                    content = second_half[start:end]
                
                # Формируем текст раздела с заголовком
                section_text = f"<b>{title}</b>\n\n{content}"
                
                # Отправляем раздел
                await message.answer(section_text)

        # Очищаем состояние
        await state.clear()

        logger.info(f"Business plan generated for user {message.from_user.id}")

    except Exception as e:
        logger.error(f"Error generating business plan: {e}")
        await processing_msg.edit_text("Произошла ошибка при генерации бизнес-плана. Пожалуйста, попробуйте позже.")
        await state.clear()

def register_handlers(dp):
    """
    Регистрация обработчиков для создания бизнес-плана
    """
    # Регистрируем обработчик кнопки
    dp.callback_query.register(business_plan_callback, F.data == "business_plan")

    # Регистрируем обработчик команды /business
    dp.message.register(business_plan_command, Command("business"))

    # Регистрируем обработчик получения информации о бизнесе
    dp.message.register(handle_business_info, BusinessPlanStates.waiting_for_info)