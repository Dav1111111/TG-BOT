"""
Модуль для работы с ЮKassa API
"""
import uuid
import logging
from yookassa import Configuration, Payment
from bot.config import config

# Настройка логгера
logger = logging.getLogger(__name__)

# Конфигурация ЮKassa
Configuration.account_id = config.YOOKASSA_SHOP_ID
Configuration.secret_key = config.YOOKASSA_SECRET_KEY

def create_payment(amount: float, description: str, user_id: int, subscription_type: str):
    """
    Создает платеж в ЮKassa и возвращает URL для оплаты
    
    Args:
        amount: Сумма платежа в рублях
        description: Описание платежа
        user_id: ID пользователя Telegram
        subscription_type: Тип подписки
        
    Returns:
        dict: Информация о платеже, включая URL для оплаты
    """
    try:
        # Генерируем уникальный идентификатор платежа
        idempotence_key = str(uuid.uuid4())
        
        # Создаем метаданные платежа
        metadata = {
            "user_id": user_id,
            "subscription_type": subscription_type
        }
        
        # Создаем платеж
        payment = Payment.create({
            "amount": {
                "value": str(amount),
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": f"{config.PAYMENT_RETURN_URL}?user_id={user_id}"
            },
            "capture": True,
            "description": description,
            "metadata": metadata
        }, idempotence_key)
        
        # Возвращаем информацию о платеже
        logger.info(f"Created payment {payment.id} for user {user_id}")
        return {
            "id": payment.id,
            "status": payment.status,
            "confirmation_url": payment.confirmation.confirmation_url
        }
        
    except Exception as e:
        logger.error(f"Error creating payment for user {user_id}: {e}")
        return None

def check_payment_status(payment_id: str):
    """
    Проверяет статус платежа
    
    Args:
        payment_id: ID платежа в ЮKassa
        
    Returns:
        dict: Информация о платеже или None в случае ошибки
    """
    try:
        # Получаем информацию о платеже
        payment = Payment.find_one(payment_id)
        
        # Возвращаем статус
        logger.info(f"Payment {payment_id} status: {payment.status}")
        return {
            "status": payment.status,
            "paid": payment.paid,
            "metadata": payment.metadata
        }
        
    except Exception as e:
        logger.error(f"Error checking payment status for {payment_id}: {e}")
        return None 