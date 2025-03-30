"""
Модуль для обработки платежей и подписок в Telegram боте
"""
import logging
from datetime import datetime, timedelta
from aiogram import types, Router, F
from aiogram.filters import Command
from aiogram.types import LabeledPrice, PreCheckoutQuery, Message
from aiogram.fsm.context import FSMContext

from bot.config import config
from bot.database import DBManager

# Инициализируем логгер
logger = logging.getLogger(__name__)

# Инициализируем базу данных
db = DBManager()

# Настройки платежей
PAYMENT_PROVIDER_TOKEN = config.PAYMENT_PROVIDER_TOKEN
CURRENCY = "RUB"

# Варианты подписок
SUBSCRIPTION_OPTIONS = {
    "week": {
        "title": "Недельная подписка",
        "description": "Полный доступ к боту на 7 дней",
        "price": 299,  # В минимальных единицах валюты (копейки)
        "days": 7,
        "messages_limit": 100,
    },
    "month": {
        "title": "Месячная подписка",
        "description": "Полный доступ к боту на 30 дней",
        "price": 999,  # В минимальных единицах валюты (копейки)
        "days": 30,
        "messages_limit": 500,
    },
    "year": {
        "title": "Годовая подписка",
        "description": "Полный доступ к боту на 365 дней",
        "price": 5999,  # В минимальных единицах валюты (копейки)
        "days": 365,
        "messages_limit": 5000,
    }
}

async def subscription_command(message: Message):
    """
    Обработчик команды /subscribe - показывает варианты подписки
    """
    if not PAYMENT_PROVIDER_TOKEN:
        await message.answer(
            "⚠️ Платежная система временно недоступна. "
            "Пожалуйста, обратитесь к администратору."
        )
        logger.warning("Payment provider token not configured")
        return
    
    # Создаем клавиатуру с вариантами подписки
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(
            text=f"{SUBSCRIPTION_OPTIONS['week']['title']} - {SUBSCRIPTION_OPTIONS['week']['price'] / 100} {CURRENCY}",
            callback_data="subscribe_week"
        )],
        [types.InlineKeyboardButton(
            text=f"{SUBSCRIPTION_OPTIONS['month']['title']} - {SUBSCRIPTION_OPTIONS['month']['price'] / 100} {CURRENCY}",
            callback_data="subscribe_month"
        )],
        [types.InlineKeyboardButton(
            text=f"{SUBSCRIPTION_OPTIONS['year']['title']} - {SUBSCRIPTION_OPTIONS['year']['price'] / 100} {CURRENCY}",
            callback_data="subscribe_year"
        )]
    ])
    
    # Получаем информацию о текущем статусе подписки пользователя
    user_id = message.from_user.id
    subscription = db.get_subscription_status(user_id)
    msg_count = db.get_user_message_count(user_id)
    
    # Формируем сообщение о текущем статусе и доступных опциях
    await message.answer(
        f"💬 <b>Ваш текущий статус:</b> {subscription.capitalize()}\n"
        f"📊 Использовано сообщений: {msg_count}/{config.SUBSCRIPTION_LIMITS.get(subscription, 50)}\n\n"
        f"📱 <b>Доступные варианты подписки:</b>\n\n"
        f"• <b>Недельная подписка:</b> {SUBSCRIPTION_OPTIONS['week']['price'] / 100} {CURRENCY}\n"
        f"  ✓ {SUBSCRIPTION_OPTIONS['week']['messages_limit']} сообщений\n"
        f"  ✓ Доступ к полной базе знаний\n"
        f"  ✓ Расширенные возможности бота\n\n"
        f"• <b>Месячная подписка:</b> {SUBSCRIPTION_OPTIONS['month']['price'] / 100} {CURRENCY}\n"
        f"  ✓ {SUBSCRIPTION_OPTIONS['month']['messages_limit']} сообщений\n"
        f"  ✓ Доступ к полной базе знаний\n"
        f"  ✓ Расширенные возможности бота\n\n"
        f"• <b>Годовая подписка:</b> {SUBSCRIPTION_OPTIONS['year']['price'] / 100} {CURRENCY}\n"
        f"  ✓ {SUBSCRIPTION_OPTIONS['year']['messages_limit']} сообщений\n"
        f"  ✓ Доступ к полной базе знаний\n"
        f"  ✓ Расширенные возможности бота\n"
        f"  ✓ Приоритетная поддержка\n\n"
        f"Выберите подходящий вариант:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    
    logger.info(f"User {user_id} requested subscription options")

async def subscribe_callback(callback_query: types.CallbackQuery):
    """
    Обработчик нажатия на кнопки подписки
    """
    await callback_query.answer()
    
    # Определяем выбранный план подписки
    sub_type = callback_query.data.split("_")[1]
    if sub_type not in SUBSCRIPTION_OPTIONS:
        await callback_query.message.answer("⚠️ Неверный тип подписки")
        return
    
    # Получаем информацию о выбранной подписке
    subscription = SUBSCRIPTION_OPTIONS[sub_type]
    
    # Создаем счет для оплаты
    await send_invoice(callback_query.message, sub_type, subscription)
    
    logger.info(f"User {callback_query.from_user.id} selected {sub_type} subscription")

async def send_invoice(message: Message, sub_type: str, subscription: dict):
    """
    Отправляет счет для оплаты подписки
    """
    # Формируем счет
    await message.answer_invoice(
        title=subscription["title"],
        description=subscription["description"],
        provider_token=PAYMENT_PROVIDER_TOKEN,
        currency=CURRENCY,
        prices=[LabeledPrice(
            label=subscription["title"],
            amount=subscription["price"]
        )],
        payload=f"subscription_{sub_type}",
        start_parameter="subscribe",
        protect_content=False
    )

async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    """
    Обрабатывает запрос предварительной проверки платежа
    """
    # В реальном приложении здесь может быть логика проверки платежа
    # Например, проверка наличия товара, валидность данных и т.д.
    
    # Для демонстрации просто подтверждаем все платежи
    await pre_checkout_query.answer(ok=True)
    
    logger.info(f"Pre-checkout query {pre_checkout_query.id} from user {pre_checkout_query.from_user.id} confirmed")

async def successful_payment(message: Message):
    """
    Обрабатывает успешный платеж
    """
    payment_info = message.successful_payment
    user_id = message.from_user.id
    
    # Получаем тип подписки
    sub_type = payment_info.invoice_payload.split("_")[1]
    
    # Обновляем статус подписки пользователя
    try:
        # Устанавливаем тип подписки и дату окончания
        subscription_info = SUBSCRIPTION_OPTIONS[sub_type]
        
        # В реальном приложении здесь будет обновление базы данных
        # с типом подписки и датой истечения
        update_subscription(user_id, "premium", subscription_info["days"])
        
        # Обновляем лимит сообщений
        update_message_limit(user_id, subscription_info["messages_limit"])
        
        # Отправляем сообщение об успешной подписке
        await message.answer(
            f"✅ <b>Подписка успешно оформлена!</b>\n\n"
            f"Подписка: {subscription_info['title']}\n"
            f"Срок действия: {subscription_info['days']} дней\n"
            f"Лимит сообщений: {subscription_info['messages_limit']}\n\n"
            f"Благодарим за покупку! Теперь вам доступны расширенные возможности бота.",
            parse_mode="HTML"
        )
        
        logger.info(f"User {user_id} successfully purchased {sub_type} subscription")
    
    except Exception as e:
        logger.error(f"Error processing payment for user {user_id}: {e}")
        await message.answer(
            "❌ Произошла ошибка при обработке платежа. "
            "Пожалуйста, обратитесь к администратору."
        )

def update_subscription(user_id: int, status: str, days: int):
    """
    Обновляет статус подписки пользователя в базе данных
    """
    # Добавляем метод для изменения статуса подписки и даты окончания
    # Этот метод еще должен быть реализован в DBManager
    try:
        # Вычисляем дату окончания подписки
        expiry_date = datetime.now() + timedelta(days=days)
        
        # Обновляем статус подписки и дату окончания
        db.execute_query(
            "UPDATE users SET subscription_status = ?, subscription_expiry = ? WHERE user_id = ?",
            (status, expiry_date, user_id)
        )
        
        logger.info(f"Updated subscription for user {user_id} to {status} until {expiry_date}")
        return True
    except Exception as e:
        logger.error(f"Error updating subscription for user {user_id}: {e}")
        return False

def update_message_limit(user_id: int, limit: int):
    """
    Обновляет лимит сообщений пользователя в базе данных
    """
    try:
        # Обновляем лимит сообщений для пользователя
        # Сначала сбрасываем счетчик сообщений
        db.execute_query(
            "UPDATE users SET messages_count = 0, message_limit = ? WHERE user_id = ?",
            (limit, user_id)
        )
        
        logger.info(f"Reset message count and set limit to {limit} for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error updating message limit for user {user_id}: {e}")
        return False

def register_handlers(dp: Router):
    """
    Регистрирует обработчики для платежей и подписок
    """
    # Команда для подписки
    dp.message.register(subscription_command, Command("subscribe"))
    
    # Обработчик нажатия на кнопки подписки
    dp.callback_query.register(subscribe_callback, F.data.startswith("subscribe_"))
    
    # Обработчики платежей
    dp.pre_checkout_query.register(process_pre_checkout)
    dp.message.register(successful_payment, F.successful_payment)
    
    logger.info("Payment handlers registered") 