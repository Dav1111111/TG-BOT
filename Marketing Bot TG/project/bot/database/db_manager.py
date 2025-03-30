"""
Database manager module for handling database operations
"""
import sqlite3
import logging
import datetime
from bot.config import config

logger = logging.getLogger(__name__)

class DBManager:
    """Database manager class for handling SQL operations"""

    def __init__(self, db_path=None):
        """Initialize the database manager with a connection to the database"""
        self.db_path = db_path or config.DB_PATH
        self.conn = None
        self.cursor = None
        self._connect()
        self.setup_database()

    def _connect(self):
        """Establish a connection to the database"""
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.cursor = self.conn.cursor()
            logger.info(f"Connected to database: {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    def execute_query(self, query, params=(), fetch=False):
        """Execute an SQL query with error handling and reconnection"""
        try:
            self.cursor.execute(query, params)
            self.conn.commit()
            if fetch:
                return self.cursor.fetchall()
            return True
        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            # Try to reconnect
            try:
                self._connect()
                self.cursor.execute(query, params)
                self.conn.commit()
                if fetch:
                    return self.cursor.fetchall()
                return True
            except sqlite3.Error as e2:
                logger.error(f"Failed to reconnect to database: {e2}")
                return None

    def setup_database(self):
        """Create the database tables if they don't exist"""
        # Table for chat history
        self.execute_query('''
        CREATE TABLE IF NOT EXISTS chat_history (
            user_id INTEGER,
            message TEXT,
            response TEXT,
            timestamp DATETIME,
            PRIMARY KEY (user_id, timestamp)
        )
        ''')

        # Table for user data
        self.execute_query('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            subscription_status TEXT DEFAULT 'free',
            messages_count INTEGER DEFAULT 0,
            message_limit INTEGER DEFAULT NULL,
            last_activity DATETIME,
            subscription_expiry DATETIME DEFAULT NULL
        )
        ''')

        logger.info("Database tables successfully set up")

    def get_chat_history(self, user_id, limit=10):
        """Get the chat history for a specific user"""
        results = self.execute_query(
            """
            SELECT message, response FROM chat_history
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (user_id, limit),
            True
        )
        return results or []

    def save_chat_message(self, user_id, message, response):
        """Save a chat message and response to the database"""
        current_time = datetime.datetime.now()
        return self.execute_query(
            "INSERT INTO chat_history (user_id, message, response, timestamp) VALUES (?, ?, ?, ?)",
            (user_id, message, response, current_time)
        )

    def update_user_activity(self, user_id):
        """Update or create a user's activity timestamp"""
        current_time = datetime.datetime.now()
        return self.execute_query(
            "INSERT OR REPLACE INTO users (user_id, last_activity) VALUES (?, ?)",
            (user_id, current_time)
        )

    def increment_message_count(self, user_id):
        """Increment the message count for a user"""
        return self.execute_query(
            "UPDATE users SET messages_count = messages_count + 1 WHERE user_id = ?",
            (user_id,)
        )

    def get_user_message_count(self, user_id):
        """Get the number of messages a user has sent"""
        result = self.execute_query(
            "SELECT messages_count FROM users WHERE user_id = ?",
            (user_id,),
            True
        )
        return result[0][0] if result and result[0] else 0

    def get_subscription_status(self, user_id):
        """Get a user's subscription status"""
        # Проверяем срок действия подписки
        self.check_subscription_expiry(user_id)
        
        result = self.execute_query(
            "SELECT subscription_status FROM users WHERE user_id = ?",
            (user_id,),
            True
        )
        return result[0][0] if result and result[0] else 'free'
    
    def check_subscription_expiry(self, user_id):
        """Проверяет и обновляет статус подписки, если срок истек"""
        try:
            result = self.execute_query(
                "SELECT subscription_status, subscription_expiry FROM users WHERE user_id = ?",
                (user_id,),
                True
            )
            
            if not result or not result[0]:
                return
            
            status, expiry = result[0]
            
            # Если статус не premium или нет даты окончания, ничего не делаем
            if status != 'premium' or not expiry:
                return
            
            # Преобразуем строку в datetime объект, если это строка
            if isinstance(expiry, str):
                try:
                    expiry = datetime.datetime.fromisoformat(expiry)
                except ValueError:
                    # Если формат даты некорректный, считаем что подписка действительна
                    return
            
            # Проверяем, не истек ли срок подписки
            if expiry and datetime.datetime.now() > expiry:
                # Обновляем статус на бесплатный
                self.execute_query(
                    "UPDATE users SET subscription_status = 'free', message_limit = NULL WHERE user_id = ?",
                    (user_id,)
                )
                logger.info(f"Subscription expired for user {user_id}, changed to free")
        except Exception as e:
            logger.error(f"Error checking subscription expiry for user {user_id}: {e}")
    
    def update_subscription(self, user_id, status, expiry_date=None):
        """Обновляет статус подписки пользователя"""
        try:
            if expiry_date:
                self.execute_query(
                    "UPDATE users SET subscription_status = ?, subscription_expiry = ? WHERE user_id = ?",
                    (status, expiry_date, user_id)
                )
            else:
                self.execute_query(
                    "UPDATE users SET subscription_status = ? WHERE user_id = ?",
                    (status, user_id)
                )
            return True
        except Exception as e:
            logger.error(f"Error updating subscription for user {user_id}: {e}")
            return False
    
    def get_message_limit(self, user_id):
        """Получает лимит сообщений для пользователя"""
        result = self.execute_query(
            "SELECT message_limit FROM users WHERE user_id = ?",
            (user_id,),
            True
        )
        
        # Если у пользователя установлен индивидуальный лимит
        if result and result[0] and result[0][0]:
            return result[0][0]
        
        # Иначе берем лимит из настроек по статусу подписки
        subscription = self.get_subscription_status(user_id)
        return config.SUBSCRIPTION_LIMITS.get(subscription, 50)

    def cleanup_inactive_chats(self, days=None):
        """Delete chat history and users who haven't been active for a while"""
        days = days or config.INACTIVE_CHAT_CLEANUP_DAYS
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)

        try:
            # Delete chat history for inactive users
            self.execute_query(
                "DELETE FROM chat_history WHERE user_id IN (SELECT user_id FROM users WHERE last_activity < ?)",
                (cutoff_date,)
            )
            # Delete inactive users
            self.execute_query(
                "DELETE FROM users WHERE last_activity < ?",
                (cutoff_date,)
            )
            logger.info(f"Cleaned up inactive chats older than {days} days")
            return True
        except Exception as e:
            logger.error(f"Error during cleanup of inactive chats: {e}")
            return False

    def close(self):
        """Close the database connection"""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")
