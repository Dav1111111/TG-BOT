"""
Обработчик для инлайн-режима Telegram
"""
import logging
import uuid
import asyncio
import time
from aiogram import types
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent
from bot.utils.ai_client import generate_gpt_response
from bot.utils.text_utils import remove_asterisks
from bot.knowledge_base.vector_kb_manager import VectorKnowledgeBaseManager
from bot.database import DBManager

logger = logging.getLogger(__name__)
db = DBManager()

# Инициализируем менеджер базы знаний
try:
    kb_manager = VectorKnowledgeBaseManager()
except Exception as e:
    logger.error(f"Error initializing KnowledgeBaseManager for inline mode: {e}")
    kb_manager = None

# Кэш для хранения последних ответов (чтобы не генерировать заново при повторном запросе)
RESPONSE_CACHE = {}
CACHE_EXPIRATION = 600  # Время жизни кэша в секундах (10 минут)
CACHE_TIMESTAMPS = {}  # Время добавления в кэш

# Тип инлайн-ответов
MARKETING_TYPES = [
    {
        "id": "quick_advice",
        "title": "💡 Быстрый совет",
        "description": "Краткий ответ на ваш вопрос по маркетингу",
        "thumb_url": "https://cdn-icons-png.flaticon.com/512/1048/1048953.png"
    },
    {
        "id": "content_idea",
        "title": "📝 Идея контента",
        "description": "Идея для поста в социальных сетях",
        "thumb_url": "https://cdn-icons-png.flaticon.com/512/1048/1048945.png"
    },
    {
        "id": "customer_message",
        "title": "💬 Сообщение клиенту",
        "description": "Профессиональный ответ клиенту",
        "thumb_url": "https://cdn-icons-png.flaticon.com/512/1048/1048950.png"
    }
]

async def clean_cache_task():
    """
    Фоновая задача для периодической очистки кэша
    """
    while True:
        try:
            current_time = time.time()
            keys_to_delete = []

            # Находим устаревшие записи
            for key, timestamp in CACHE_TIMESTAMPS.items():
                if current_time - timestamp > CACHE_EXPIRATION:
                    keys_to_delete.append(key)

            # Удаляем устаревшие записи
            for key in keys_to_delete:
                if key in RESPONSE_CACHE:
                    del RESPONSE_CACHE[key]
                if key in CACHE_TIMESTAMPS:
                    del CACHE_TIMESTAMPS[key]

            if keys_to_delete:
                logger.info(f"Cleaned {len(keys_to_delete)} expired cache entries")

        except Exception as e:
            logger.error(f"Error cleaning cache: {e}")

        # Ждем 5 минут перед следующей проверкой
        await asyncio.sleep(300)

async def inline_query_handler(inline_query: types.InlineQuery):
    """
    Обработчик инлайн-запросов
    """
    query_text = inline_query.query.strip()
    user_id = inline_query.from_user.id

    # Если запрос пустой или слишком короткий, предлагаем примеры
    if len(query_text) < 3:
        results = [
            InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title="✍️ Введите запрос...",
                description="Например: идея для поста о кофейне, как отвечать на негатив, маркетинг для салона красоты",
                input_message_content=InputTextMessageContent(
                    message_text="Чтобы получить ответ, введите запрос длиной не менее 3-х символов."
                ),
                thumb_url="https://cdn-icons-png.flaticon.com/512/1048/1048967.png"
            )
        ]
        await inline_query.answer(results, cache_time=5)
        return

    try:
        # Проверяем кэш
        cache_key = f"{user_id}:{query_text}"
        if cache_key in RESPONSE_CACHE:
            results = RESPONSE_CACHE[cache_key]
            await inline_query.answer(results, cache_time=300)
            return

        # Создаем заглушки для результатов
        placeholder_results = []
        for type_data in MARKETING_TYPES:
            placeholder_results.append(
                InlineQueryResultArticle(
                    id=f"{type_data['id']}_{uuid.uuid4()}",
                    title=f"{type_data['title']} (Генерация...)",
                    description="Подождите, ответ создается...",
                    input_message_content=InputTextMessageContent(
                        message_text=f"🔄 Генерирую {type_data['title'].lower()} на запрос: {query_text}"
                    ),
                    thumb_url=type_data['thumb_url']
                )
            )

        # Отвечаем заглушками сразу, чтобы пользователь видел прогресс
        await inline_query.answer(placeholder_results, cache_time=5)

        # Выполняем фактическую генерацию ответов в фоне
        asyncio.create_task(generate_inline_results(inline_query, query_text, user_id))

    except Exception as e:
        logger.error(f"Error processing inline query: {e}")
        error_results = [
            InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title="❌ Произошла ошибка",
                description=f"Не удалось обработать запрос: {str(e)[:100]}",
                input_message_content=InputTextMessageContent(
                    message_text=f"❌ Не удалось сгенерировать ответ на запрос: {query_text}"
                )
            )
        ]
        await inline_query.answer(error_results, cache_time=5)

async def generate_inline_results(inline_query: types.InlineQuery, query_text: str, user_id: int):
    """
    Генерирует результаты для инлайн-запроса в фоновом режиме

    Args:
        inline_query: Инлайн-запрос
        query_text: Текст запроса
        user_id: ID пользователя
    """
    try:
        # Обновляем активность пользователя
        db.update_user_activity(user_id)

        # Ищем релевантную информацию в базе знаний
        knowledge_content = None
        if kb_manager:
            knowledge_content = kb_manager.get_content_for_query(query_text)

        # Генерируем ответы для разных типов
        results = []

        for type_data in MARKETING_TYPES:
            # Формируем запрос в зависимости от типа
            if type_data["id"] == "quick_advice":
                content = await generate_quick_advice(query_text, knowledge_content)
            elif type_data["id"] == "content_idea":
                content = await generate_content_idea(query_text, knowledge_content)
            elif type_data["id"] == "customer_message":
                content = await generate_customer_message(query_text, knowledge_content)
            else:
                content = "Неизвестный тип запроса"

            # Добавляем в результаты
            results.append(
                InlineQueryResultArticle(
                    id=f"{type_data['id']}_{uuid.uuid4()}",
                    title=type_data['title'],
                    description=content[:100] + "..." if len(content) > 100 else content,
                    input_message_content=InputTextMessageContent(
                        message_text=content,
                        parse_mode="HTML"
                    ),
                    thumb_url=type_data['thumb_url']
                )
            )

        # Сохраняем в кэш
        cache_key = f"{user_id}:{query_text}"
        RESPONSE_CACHE[cache_key] = results
        CACHE_TIMESTAMPS[cache_key] = time.time()  # Обновляем timestamp

        # Отправляем новые результаты
        await inline_query.answer(results, cache_time=300)

        # Увеличиваем счетчик сообщений пользователя
        db.increment_message_count(user_id)

    except Exception as e:
        logger.error(f"Error generating inline results: {e}")

        # Отправляем сообщение об ошибке
        error_results = [
            InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title="❌ Произошла ошибка",
                description=f"Не удалось обработать запрос: {str(e)[:100]}",
                input_message_content=InputTextMessageContent(
                    message_text=f"❌ Не удалось сгенерировать ответ на запрос: {query_text}"
                )
            )
        ]
        await inline_query.answer(error_results, cache_time=5)

async def generate_quick_advice(query_text: str, knowledge_content: str = None) -> str:
    """
    Генерирует быстрый совет по маркетингу

    Args:
        query_text: Текст запроса
        knowledge_content: Информация из базы знаний (опционально)

    Returns:
        str: Готовый ответ
    """
    prompt = f"Дай краткий и конкретный маркетинговый совет по запросу: {query_text}"

    if knowledge_content:
        prompt += f"\n\nИспользуй эту информацию из базы знаний при ответе:\n{knowledge_content}"

    messages = [
        {"role": "system", "content": "Ты — эксперт по маркетингу. Давай краткие, полезные и конкретные советы. Используй максимум 3-4 предложения. Не начинай с фраз типа 'Вот мой совет' или 'Как маркетолог'."},
        {"role": "user", "content": prompt}
    ]

    response = await generate_gpt_response(
        messages=messages,
        max_tokens=500,
        temperature=0.7
    )

    # Форматируем ответ
    response = remove_asterisks(response)
    return f"<b>💡 Совет маркетолога:</b>\n\n{response}"

async def generate_content_idea(query_text: str, knowledge_content: str = None) -> str:
    """
    Генерирует идею контента для социальных сетей

    Args:
        query_text: Текст запроса
        knowledge_content: Информация из базы знаний (опционально)

    Returns:
        str: Готовый ответ
    """
    prompt = f"Предложи креативную идею для поста в социальных сетях по теме: {query_text}"

    if knowledge_content:
        prompt += f"\n\nИспользуй эту информацию из базы знаний при ответе:\n{knowledge_content}"

    messages = [
        {"role": "system", "content": "Ты — креативный SMM-специалист. Предлагай интересные идеи для постов в соцсетях с конкретным форматом, структурой и хештегами. Не начинай с фраз типа 'Вот моя идея' или 'Как SMM-специалист'."},
        {"role": "user", "content": prompt}
    ]

    response = await generate_gpt_response(
        messages=messages,
        max_tokens=800,
        temperature=0.8
    )

    # Форматируем ответ
    response = remove_asterisks(response)
    return f"<b>📝 Идея для поста:</b>\n\n{response}"

async def generate_customer_message(query_text: str, knowledge_content: str = None) -> str:
    """
    Генерирует профессиональное сообщение для клиента

    Args:
        query_text: Текст запроса
        knowledge_content: Информация из базы знаний (опционально)

    Returns:
        str: Готовый ответ
    """
    prompt = f"Напиши профессиональный ответ клиенту на запрос/комментарий: {query_text}"

    if knowledge_content:
        prompt += f"\n\nИспользуй эту информацию из базы знаний при ответе:\n{knowledge_content}"

    messages = [
        {"role": "system", "content": "Ты — профессиональный менеджер по работе с клиентами. Пиши вежливые, эмпатичные и профессиональные ответы клиентам. Не используй шаблонные фразы. Не начинай с обращений 'Уважаемый клиент'."},
        {"role": "user", "content": prompt}
    ]

    response = await generate_gpt_response(
        messages=messages,
        max_tokens=600,
        temperature=0.7
    )

    # Форматируем ответ
    response = remove_asterisks(response)
    return f"<b>💬 Ответ клиенту:</b>\n\n{response}"

def register_handlers(dp):
    """
    Регистрация обработчиков инлайн-режима
    """
    # Запускаем фоновую задачу очистки кэша
    asyncio.create_task(clean_cache_task())

    # Регистрируем обработчик инлайн-запросов
    dp.inline_query.register(inline_query_handler)
