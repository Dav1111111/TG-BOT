"""
Handlers for general text messages
"""
import logging
import asyncio
from aiogram import types, F
from bot.config import config
from bot.config.prompts import GPT_CONTEXT, KNOWLEDGE_BASE_CONTEXT
from bot.database import DBManager
from bot.utils import remove_asterisks, split_message
from bot.utils.ai_client import generate_gpt_response
from bot.knowledge_base import KnowledgeBaseManager
from aiogram.filters import Filter

logger = logging.getLogger(__name__)
db = DBManager()
kb_manager = KnowledgeBaseManager()

async def handle_message(message: types.Message):
    """Handler for general text messages"""
    user_id = message.from_user.id
    user_message = message.text
    is_reply = False
    reply_to_message_text = None

    # Проверяем, является ли сообщение ответом на другое сообщение
    if message.reply_to_message and message.reply_to_message.from_user.is_bot:
        is_reply = True
        reply_to_message_text = message.reply_to_message.text
        logger.info(f"User {user_id} replied to bot message")

    # Update last activity
    db.update_user_activity(user_id)

    # Send processing message
    processing_msg = await message.answer("Обрабатываю ваш запрос...")

    try:
        # Check message limits
        msg_count = db.get_user_message_count(user_id)
        subscription = db.get_subscription_status(user_id)

        # Get subscription limits - теперь используем метод из DBManager
        limit = db.get_message_limit(user_id)

        if msg_count >= limit:
            # Если пользователь достиг лимита, предлагаем оформить подписку
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(
                    text="💎 Оформить подписку",
                    callback_data="open_subscription"
                )]
            ])
            
            await processing_msg.edit_text(
                "🔒 <b>Достигнут лимит сообщений</b>\n\n"
                f"Вы использовали {msg_count} из {limit} доступных сообщений в вашем тарифе '{subscription}'.\n\n"
                "Для продолжения работы с ботом вы можете:\n"
                "• Оформить платную подписку\n"
                "• Дождаться сброса лимита\n\n"
                "Платная подписка открывает доступ к расширенным функциям и увеличивает лимит сообщений.",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            return

        # Поиск в базе знаний релевантного контента
        knowledge_content = kb_manager.get_content_for_query(user_message)

        # Если это ответ на сообщение бота, добавляем контекст ответа
        if is_reply and reply_to_message_text:
            # Формируем контекстуальный запрос, добавляя информацию о том, на какое сообщение отвечает пользователь
            contextual_message = f"Контекст: Вы отправили сообщение:\n\n{reply_to_message_text}\n\nПользователь ответил: {user_message}"
            # Generate GPT response with additional context
            response = await gpt_request(contextual_message, user_id, knowledge_content)
        else:
            # Generate GPT response with chat history and knowledge base content
            response = await gpt_request(user_message, user_id, knowledge_content)

        # Remove formatting
        response = remove_asterisks(response)

        # Increment message count
        db.increment_message_count(user_id)

        # Save to history
        db.save_chat_message(user_id, user_message, response)

        # Delete processing message
        await processing_msg.delete()

        # Send response (respecting Telegram message limits)
        message_parts = split_message(response)
        for part in message_parts:
            await message.answer(part)

    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        await processing_msg.edit_text(
            "Произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте позже."
        )

async def gpt_request(prompt, user_id, knowledge_content=None, max_retry=2):
    """Generate response from GPT with retry logic"""
    retry_count = 0

    # Get chat history from database
    chat_history = db.get_chat_history(user_id)

    # Determine context based on knowledge content
    system_content = GPT_CONTEXT
    if knowledge_content:
        system_content = KNOWLEDGE_BASE_CONTEXT.format(
            base_context=GPT_CONTEXT,
            knowledge_content=knowledge_content
        )

    # Format messages for the GPT API
    messages = [{"role": "system", "content": system_content}]

    # Add reversed history (chronological order)
    if chat_history:
        for msg, resp in reversed(chat_history):
            messages.append({"role": "user", "content": msg})
            messages.append({"role": "assistant", "content": resp})

    # Add current user message
    messages.append({"role": "user", "content": prompt})

    while retry_count <= max_retry:
        try:
            # Add delay for retries
            if retry_count > 0:
                await asyncio.sleep(1)

            response = await generate_gpt_response(
                messages=messages,
                max_tokens=config.GPT_MAX_TOKENS,
                temperature=config.GPT_TEMP
            )
            return response

        except Exception as e:
            logger.error(f"GPT request error (attempt {retry_count+1}): {e}")
            retry_count += 1

    # If all retries failed
    return "Извините, произошла ошибка при обработке вашего запроса. Наши серверы сейчас перегружены, пожалуйста, попробуйте позже."

async def process_callback(callback_query: types.CallbackQuery):
    """Handle button callbacks"""
    await callback_query.answer()
    
    if callback_query.data == "open_subscription":
        # Открываем окно подписки
        from bot.handlers.payment_handler import subscription_command
        await subscription_command(callback_query.message)
    
    # Другие обработчики коллбэков можно добавить здесь

def register_handlers(dp):
    """Register general message handler"""
    dp.message.register(handle_message, F.text)
    dp.callback_query.register(process_callback, F.data == "open_subscription")
