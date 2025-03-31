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

        # Фиксированные заголовки разделов согласно новой структуре (без эмодзи)
        section_titles = [
            "Целевая аудитория",
            "Проблема",
            "Ценность",
            "Уникальность",
            "Существующие решения",
            "Конкуренты",
            "Привлечение первых клиентов",
            "Монетизация",
            "Массовое привлечение",
            "Масштабирование"
        ]

        # Создаем системный промпт с четкими инструкциями о структуре и запрашиваем нумерованные разделы
        system_prompt = """КОНТЕКСТ
Ты — Эксперт по бизнес-планам, специалист в разработке стратегий для малого бизнеса. Ты помогаешь предпринимателям системно прорабатывать их бизнес-идеи, анализировать рынок и находить наиболее эффективные пути развития.

ЦЕЛЬ
Создать четкий, структурированный и применимый бизнес-план для малого бизнеса. Этот документ поможет предпринимателю в развитии продукта, маркетинге, продажах и финансовом планировании.

СТРУКТУРА БИЗНЕС-ПЛАНА
Бизнес-план должен содержать 10 ключевых разделов, каждый из которых отвечает на важный вопрос:
🎯 Целевая аудитория – Кто ваши основные клиенты?
🤔 Проблема – Какую главную боль решает продукт?
💎 Ценность – Какую пользу приносит продукт?
✨ Уникальность – Чем продукт выделяется среди конкурентов?
😈 Существующие решения – Что используют клиенты сейчас?
⚔️ Конкуренты – Кто главные соперники и как с ними конкурировать?
💡 Привлечение первых клиентов – Как получить первых пользователей?
💰 Монетизация – Как зарабатывать деньги?
🚴 Массовое привлечение – Как получить первых 100+ платящих клиентов?
📈 Масштабирование – Как развивать бизнес?

ТРЕБОВАНИЯ К ТЕКСТУ
Простота и ясность – Бизнес-план должен быть понятен даже новичку.
Минимум воды – Только конкретные рекомендации и идеи.
Применимость – Все пункты должны быть практическими и реализуемыми.
Четкая структура – Каждая секция должна быть 1-3 кратких абзаца, список или таблица.

ФОРМАТ ОТВЕТА
Отправляй каждый пункт отдельным сообщением. Ты должен создать 10 ОТДЕЛЬНЫХ И САМОСТОЯТЕЛЬНЫХ разделов, которые будут отправлены мной как отдельные сообщения.
Вместо одного длинного сообщения, раздели сообщение на заголовки.
Каждый раздел должен начинаться с номера и точки (например, "1.", "2.", "3." и т.д.).
Сначала отправь раздел "1. Целевая аудитория", затем "2. Проблема" и так далее до "10. Масштабирование".

Каждый раздел должен начинаться с номера и точки (например, "1. ")."""

        # Создаем сообщения для запроса
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]

        # Генерируем бизнес-план
        response = await generate_gpt_response(messages=messages)

        # Удаляем сообщение о генерации
        await processing_msg.delete()

        # Отправляем сообщение о структуре бизнес-плана
        intro_msg = await message.answer("<b>Бизнес-план</b>\n\nНиже будут отправлены 10 разделов бизнес-плана:")
        
        # Прямой запрос для конкретного формата данных
        # Запрашиваем строго 10 разделов с тегами
        try:
            # Новый подход - ищем разделы по нумерации
            contents = {}
            
            # Используем регулярное выражение для поиска разделов по номеру (например, "1.", "2.", ..., "10.")
            for i, title in enumerate(section_titles):
                current_num = i + 1
                
                # Ищем раздел по номеру и точке в начале строки (с возможными пробелами)
                # Ищем текст от текущего номера до следующего номера или до конца текста
                if current_num < 10:
                    next_num = current_num + 1
                    # Ищем начало текущего раздела и текст до начала следующего
                    pattern = rf"^\s*{current_num}\.\s*(.*?)(?=^\s*{next_num}\.\s*|\Z)"
                else: # Для последнего раздела (10.)
                    pattern = rf"^\s*{current_num}\.\s*(.*)"
                
                # Ищем с флагами MULTILINE и DOTALL
                match = re.search(pattern, response, re.MULTILINE | re.DOTALL)
                
                if match:
                    # Нашли текст раздела (без номера и точки)
                    section_content = match.group(1).strip()
                    # Форматируем заголовок жирным с номером
                    section_text = f"<b>{current_num}. {title}</b>\n\n{section_content}"
                    contents[i] = section_text
                else:
                     logger.warning(f"Не удалось найти раздел {current_num}. с помощью regex.")

            # Если не удалось найти все 10 разделов с помощью regex, пробуем разбить по номерам
            if len(contents) < 10:
                logger.warning(f"Нашли только {len(contents)} разделов с помощью regex, пробуем разбить по номерам.")
                
                # Разбиваем текст по номерам "1.", "2.", ... "10." в начале строки
                split_pattern = r'^\s*(?=\d{1,2}\.\s)'
                all_sections = re.split(split_pattern, response, flags=re.MULTILINE)
                
                # Убираем пустые строки и пробелы
                all_sections = [s.strip() for s in all_sections if s.strip()]

                # Пытаемся сопоставить найденные части с номерами
                temp_sections = {}
                for section_part in all_sections:
                    match_num = re.match(r'^(\d{1,2})\.\s*(.*)', section_part, re.DOTALL)
                    if match_num:
                        num = int(match_num.group(1))
                        content_part = match_num.group(2).strip()
                        if 1 <= num <= 10:
                            idx = num - 1
                            if idx not in contents: # Добавляем только если еще не найден
                                title = section_titles[idx]
                                temp_sections[idx] = f"<b>{num}. {title}</b>\n\n{content_part}"
                
                # Обновляем основной словарь найденных разделов
                contents.update(temp_sections)

            # Если все еще не удалось найти все разделы, попробуем прямую генерацию недостающих разделов
            if len(contents) < 10:
                logger.warning(f"После двух попыток разбора нашли только {len(contents)} разделов, генерируем недостающие.")
                
                # Логируем, какие разделы не найдены
                missing_indices = [i for i in range(10) if i not in contents]
                logger.info(f"Отсутствуют разделы (индексы): {missing_indices}")
                # Логируем ответ от GPT для диагностики
                logger.info(f"Ответ GPT для диагностики: {response[:500]}...")
                
                # Отправляем запрос на генерацию недостающих разделов
                missing_titles_with_nums = [f"{i+1}. {section_titles[i]}" for i in missing_indices]
                if missing_titles_with_nums:
                    try:
                        # Создаем запрос на генерацию только недостающих разделов с нумерацией
                        missing_prompt = f"Создай следующие недостающие разделы бизнес-плана для этого бизнеса, начиная каждый раздел с номера и точки (например, '3. Ценность'):\n" + "\n".join(missing_titles_with_nums)
                        missing_messages = [
                            {"role": "system", "content": system_prompt}, # Используем обновленный system_prompt
                            {"role": "user", "content": prompt},
                            {"role": "assistant", "content": "Я создал некоторые разделы бизнес-плана, но некоторые отсутствуют."},
                            {"role": "user", "content": missing_prompt}
                        ]
                        
                        # Генерируем недостающие разделы
                        missing_response = await generate_gpt_response(messages=missing_messages)
                        logger.info(f"Ответ GPT на запрос недостающих разделов: {missing_response[:500]}...")
                        
                        # Повторяем процесс поиска разделов в новом ответе по нумерации
                        for i in missing_indices:
                            current_num = i + 1
                            if current_num < 10:
                                next_num = current_num + 1
                                pattern = rf"^\s*{current_num}\.\s*(.*?)(?=^\s*{next_num}\.\s*|\Z)"
                            else:
                                pattern = rf"^\s*{current_num}\.\s*(.*)"
                            
                            match = re.search(pattern, missing_response, re.MULTILINE | re.DOTALL)
                            if match:
                                section_content = match.group(1).strip()
                                title = section_titles[i]
                                section_text = f"<b>{current_num}. {title}</b>\n\n{section_content}"
                                contents[i] = section_text
                            else:
                                logger.warning(f"Не удалось найти недостающий раздел {current_num}. в ответе на доп. запрос.")

                    except Exception as gen_error:
                        logger.error(f"Ошибка при генерации недостающих разделов: {gen_error}")

            # Отправляем каждый раздел по порядку
            for i in range(10):
                current_num = i + 1
                title = section_titles[i] # Заголовок без эмодзи

                if i in contents:
                    # Раздел найден и уже отформатирован
                    section_text = contents[i]
                    # Дополнительная проверка на наличие номера и жирного шрифта
                    if not re.match(rf"<b>{current_num}\.", section_text):
                         # Если форматирование неверное, переформатируем
                         content_match = re.search(r'\n\n(.*)', section_text, re.DOTALL)
                         section_content = content_match.group(1) if content_match else section_text # Берем все после \n\n или весь текст
                         section_text = f"<b>{current_num}. {title}</b>\n\n{section_content.strip()}"
                    await message.answer(section_text)
                else:
                    # Раздел не был найден или сгенерирован, генерируем его отдельно
                    logger.warning(f"Раздел {current_num}. не найден, генерируем отдельно.")
                    section_prompt = f"Создай раздел '{current_num}. {title}' для бизнес-плана. Информация о бизнесе: {business_info}"
                    
                    try:
                        # Генерируем содержимое для одного конкретного раздела
                        section_messages = [
                            {"role": "system", "content": f"Ты - эксперт по бизнес-планам. Создай короткий раздел '{current_num}. {title}' для бизнес-плана (3-5 предложений). Начни ответ с '{current_num}.'."},
                            {"role": "user", "content": section_prompt}
                        ]
                        
                        section_content_raw = await generate_gpt_response(messages=section_messages, max_tokens=300)
                        
                        # Убираем номер из начала ответа, если он есть, и форматируем
                        section_content = re.sub(rf"^\s*{current_num}\.\s*", "", section_content_raw).strip()
                        full_text = f"<b>{current_num}. {title}</b>\n\n{section_content}"
                        await message.answer(full_text)
                    except Exception as section_error:
                        logger.error(f"Ошибка при генерации отдельного раздела {current_num}. {title}: {section_error}")
                        # Отправляем заглушку, если генерация не удалась
                        await message.answer(f"<b>{current_num}. {title}</b>\n\nНе удалось сгенерировать этот раздел.")
                
                # Небольшая пауза между сообщениями
                await asyncio.sleep(0.5)
                
        except Exception as parsing_error:
            logger.error(f"Ошибка при разборе разделов: {parsing_error}")
            
            # Запасной вариант - разбиваем на равные секции
            try:
                # Делим на 10 равных частей
                total_len = len(response)
                section_len = total_len // 10
                
                for i in range(10):
                    start = i * section_len
                    end = start + section_len if i < 9 else total_len
                    
                    # Находим ближайший конец предложения
                    if i < 9:
                        next_period = response.find('. ', end - 50, end + 50)
                        if next_period != -1:
                            end = next_period + 1
                    
                    section_text = response[start:end].strip()
                    
                    # Добавляем заголовок
                    full_text = f"<b>{section_titles[i]}</b>\n\n{section_text}"
                    
                    # Отправляем раздел
                    await message.answer(full_text)
                    await asyncio.sleep(0.5)
            except Exception as final_error:
                logger.error(f"Критическая ошибка при обработке бизнес-плана: {final_error}")
                await message.answer("Произошла ошибка при формировании бизнес-плана. Пожалуйста, попробуйте еще раз.")

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
