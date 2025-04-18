import os
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration class
class Config:
    # Bot token
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    if not TELEGRAM_TOKEN:
        raise ValueError("No TELEGRAM_TOKEN provided in environment variables")

    # OpenAI API key
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    if not OPENAI_API_KEY:
        raise ValueError("No OPENAI_API_KEY provided in environment variables")

    # Database settings
    DB_PATH = 'bot_database.db'

    # Knowledge base settings
    PDF_STORAGE_PATH = 'knowledge_base_files'
    VECTOR_STORAGE_PATH = 'vector_storage'

    # Embeddings settings
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    USE_VECTOR_SEARCH = os.getenv("USE_VECTOR_SEARCH", "true").lower() in ('true', 'yes', '1', 't')

    # Опциональные ID администраторов для Telegram бота
    # Эти ID нужны только для доступа к загрузке через Telegram бота
    # При использовании программного интерфейса эти проверки не применяются
    ADMIN_IDS = []
    admin_ids_str = os.getenv("ADMIN_IDS", "")
    if admin_ids_str:
        try:
            ADMIN_IDS = [int(id.strip()) for id in admin_ids_str.split(",") if id.strip()]
        except ValueError:
            logging.warning("Invalid ADMIN_IDS format in .env file. Using empty list.")

    # Check if we're running in Google Colab
    try:
        from google.colab import drive
        RUNNING_IN_COLAB = True
        # Uncomment to use Google Drive for database
        # drive.mount('/content/drive')
        # DB_PATH = '/content/drive/MyDrive/Colab_Notebooks/bot_database.db'
        # PDF_STORAGE_PATH = '/content/drive/MyDrive/Colab_Notebooks/knowledge_base_files'
        # VECTOR_STORAGE_PATH = '/content/drive/MyDrive/Colab_Notebooks/vector_storage'
    except ImportError:
        RUNNING_IN_COLAB = False

    # OpenAI model settings
    GPT_MODEL = "gpt-4o"
    GPT_MAX_TOKENS = 3000
    GPT_TEMP = 0.7

    # Subscription limits
    SUBSCRIPTION_LIMITS = {
        'free': 5,
        'premium': 500
    }

    # Payment settings
    PAYMENT_PROVIDER_TOKEN = os.getenv("PAYMENT_PROVIDER_TOKEN", "")
    YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "")
    YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "")
    PAYMENT_RETURN_URL = os.getenv("PAYMENT_RETURN_URL", "https://t.me/your_bot_username")
    PAYMENT_CURRENCY = "RUB"

    # Logging settings
    LOG_LEVEL = logging.INFO
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    # Cleanup settings (in days)
    INACTIVE_CHAT_CLEANUP_DAYS = 90

# Create a config instance
config = Config()
