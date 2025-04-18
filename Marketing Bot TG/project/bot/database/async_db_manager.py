"""
Asynchronous database manager module for handling database operations with aiosqlite
"""
import aiosqlite
import logging
import datetime
import os
from bot.config import config

logger = logging.getLogger(__name__)

# Синглтон для AsyncDBManager
_instance = None

class AsyncDBManager:
    """Asynchronous database manager class for handling SQL operations, реализован как синглтон"""

    def __new__(cls, db_path=None):
        """Обеспечивает, что существует только один экземпляр класса"""
        global _instance
        if _instance is None:
            logger.info("Creating new AsyncDBManager instance")
            _instance = super(AsyncDBManager, cls).__new__(cls)
            _instance.initialized = False  # Флаг для предотвращения повторной инициализации
        return _instance

    def __init__(self, db_path=None):
        """Initialize the database manager"""
        # Предотвращаем повторную инициализацию
        if getattr(self, "initialized", False):
            return

        # Инициализация атрибутов
        self.db_path = db_path or config.DB_PATH
        self.conn = None
        self.initialized = True
        logger.info(f"AsyncDBManager initialized with database path: {self.db_path}")

    async def connect(self):
        """Establish a connection to the database"""
        if self.conn is not None:
            return

        try:
            # Создаем директорию для БД, если она не существует
            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir)
                logger.info(f"Created directory for database: {db_dir}")
            
            # Устанавливаем соединение
            self.conn = await aiosqlite.connect(self.db_path)
            
            # Включаем режим WAL и другие настройки
            await self.conn.execute("PRAGMA journal_mode=WAL")
            await self.conn.execute("PRAGMA synchronous=NORMAL")
            await self.conn.execute("PRAGMA foreign_keys=ON")
            
            # Настройка соединения для поддержки возврата словарей
            self.conn.row_factory = aiosqlite.Row
            
            logger.info(f"Connected to database: {self.db_path} with WAL mode")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    async def execute_query(self, query, params=(), fetch=False):
        """Execute an SQL query"""
        if self.conn is None:
            await self.connect()
            
        try:
            async with self.conn.execute(query, params) as cursor:
                if fetch:
                    results = await cursor.fetchall()
                    return [dict(row) for row in results]
                await self.conn.commit()
                return True
        except Exception as e:
            logger.error(f"Database error: {e} Query: {query} Params: {params}")
            # Попытка переподключения в случае ошибки
            try:
                await self.close()
                await self.connect()
                logger.warning("Reconnected after error, but query was not re-executed.")
            except Exception as e2:
                logger.error(f"Failed to reconnect after error: {e2}")
            return None

    async def setup_database(self):
        """Create the database tables if they don't exist and ensure columns exist."""
        # Таблица для истории чата
        await self.execute_query('''
        CREATE TABLE IF NOT EXISTS chat_history (
            user_id INTEGER,
            message TEXT,
            response TEXT,
            timestamp DATETIME,
            PRIMARY KEY (user_id, timestamp)
        )
        ''')

        # Таблица для данных пользователя
        await self.execute_query('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            subscription_status TEXT DEFAULT 'free',
            messages_count INTEGER DEFAULT 0,
            message_limit INTEGER DEFAULT NULL,
            last_activity DATETIME,
            subscription_expiry DATETIME DEFAULT NULL
        )
        ''')

        # Проверка и добавление колонок
        await self.check_and_add_column('subscription_expiry', 'DATETIME DEFAULT NULL')
        await self.check_and_add_column('message_limit', 'INTEGER DEFAULT NULL')

        # Таблица для платежей
        await self.execute_query('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            payment_id TEXT NOT NULL,
            subscription_type TEXT NOT NULL,
            amount REAL NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        logger.info("Database tables successfully set up")

    async def check_and_add_column(self, column_name, column_type):
        """Check if a column exists and add it if it doesn't"""
        try:
            # Получаем информацию о таблице
            table_info = await self.execute_query(f"PRAGMA table_info(users)", fetch=True)
            
            # Проверяем наличие колонки
            column_exists = any(col['name'] == column_name for col in table_info)
            
            if not column_exists:
                logger.info(f"Adding missing column '{column_name}' to 'users' table.")
                add_success = await self.execute_query(f"ALTER TABLE users ADD COLUMN {column_name} {column_type};")
                if add_success:
                    logger.info(f"Column '{column_name}' added successfully.")
                else:
                    logger.error(f"Failed to add column '{column_name}'.")
        except Exception as e:
            logger.error(f"Error checking/adding column '{column_name}': {e}")

    async def get_chat_history(self, user_id, limit=10):
        """Get the chat history for a specific user, исключая записи с NULL ответами"""
        results = await self.execute_query(
            """
            SELECT message, response FROM chat_history
            WHERE user_id = ? AND response IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (user_id, limit),
            True
        )
        
        # Преобразуем результат в формат, совместимый с предыдущим форматом
        if results:
            return [(item['message'], item['response']) for item in results]
        return []

    async def save_chat_message(self, user_id, message, response=None):
        """
        Save a chat message and optionally a response to the database.
        Если response=None, сохраняется только сообщение пользователя.
        """
        try:
            current_time = datetime.datetime.now()
            # Используем отдельный SQL запрос в зависимости от наличия ответа
            if response is None:
                return await self.execute_query(
                    "INSERT INTO chat_history (user_id, message, timestamp) VALUES (?, ?, ?)",
                    (user_id, message, current_time)
                )
            else:
                return await self.execute_query(
                    "INSERT INTO chat_history (user_id, message, response, timestamp) VALUES (?, ?, ?, ?)",
                    (user_id, message, response, current_time)
                )
        except Exception as e:
            logger.error(f"Error saving chat message for user {user_id}: {e}")
            return False

    async def update_chat_response(self, user_id, message, response):
        """
        Update the response for a previously saved message.
        Используется для обновления записи, созданной с response=None.
        """
        try:
            if response is None:
                logger.warning(f"Attempted to update chat response with NULL for user {user_id}")
                return False  # Не позволяем устанавливать NULL значения для ответа
                
            # Находим самое последнее сообщение от пользователя без ответа
            result = await self.execute_query(
                """
                SELECT rowid FROM chat_history 
                WHERE user_id = ? AND message = ? AND response IS NULL
                ORDER BY timestamp DESC LIMIT 1
                """,
                (user_id, message),
                True
            )
            
            if not result:
                logger.warning(f"No matching message found to update response for user {user_id}")
                # Если запись не найдена, создаем новую запись с сообщением и ответом
                return await self.save_chat_message(user_id, message, response)
            
            # Обновляем найденную запись
            rowid = result[0]['rowid']
            update_success = await self.execute_query(
                "UPDATE chat_history SET response = ? WHERE rowid = ?",
                (response, rowid)
            )
            
            if update_success:
                logger.debug(f"Successfully updated chat response for message rowid {rowid}")
                return True
            else:
                logger.error(f"Failed to update chat response for message rowid {rowid}")
                # Если обновление не удалось, пробуем создать новую запись
                return await self.save_chat_message(user_id, message, response)
        except Exception as e:
            logger.error(f"Error updating chat response for user {user_id}: {e}")
            # В случае ошибки, пробуем создать новую запись
            try:
                return await self.save_chat_message(user_id, message, response)
            except Exception as e2:
                logger.error(f"Failed to save message after update failure: {e2}")
                return False

    async def update_user_activity(self, user_id):
        """Update or create a user's activity timestamp"""
        current_time = datetime.datetime.now()
        
        # Проверяем, существует ли пользователь
        user = await self.execute_query(
            "SELECT 1 FROM users WHERE user_id = ?",
            (user_id,),
            True
        )
        
        if not user:
            # Если пользователя нет, создаем запись
            return await self.execute_query(
                "INSERT INTO users (user_id, last_activity, subscription_status) VALUES (?, ?, 'free')",
                (user_id, current_time)
            )
        else:
            # Обновляем существующую запись
            return await self.execute_query(
                "UPDATE users SET last_activity = ? WHERE user_id = ?",
                (current_time, user_id)
            )

    async def increment_message_count(self, user_id):
        """
        Increment the message count for a user using INSERT OR REPLACE.
        Также убедимся, что запись пользователя создается, если она не существует.
        """
        try:
            # Определяем, существует ли запись для пользователя
            user_exists = await self.execute_query(
                "SELECT 1 FROM users WHERE user_id = ? LIMIT 1",
                (user_id,),
                True
            )
            current_time = datetime.datetime.now()
            
            # Если записи нет, создаем её с messages_count = 1
            if not user_exists:
                logger.info(f"Creating new user record for user_id {user_id}")
                success = await self.execute_query(
                    """
                    INSERT INTO users 
                    (user_id, messages_count, subscription_status, last_activity) 
                    VALUES (?, 1, 'free', ?)
                    """,
                    (user_id, current_time)
                )
                if success:
                    return True
                else:
                    logger.error(f"Failed to create new user record for user_id {user_id}")
                    return False
            
            # Если запись существует, увеличиваем счетчик
            success = await self.execute_query(
                "UPDATE users SET messages_count = messages_count + 1, last_activity = ? WHERE user_id = ?",
                (current_time, user_id)
            )
            
            if success:
                logger.debug(f"Successfully incremented count for user {user_id}")
                return True
            else:
                logger.error(f"Failed to increment message count for user {user_id}")
                return False
        except Exception as e:
            logger.error(f"Error incrementing message count for user {user_id}: {e}")
            return False

    async def get_user_message_count(self, user_id):
        """
        Get the number of messages a user has sent.
        Если запись в таблице users отсутствует, считаем сообщения из истории чата.
        """
        try:
            # Получаем счетчик из таблицы users
            result = await self.execute_query(
                "SELECT messages_count FROM users WHERE user_id = ?",
                (user_id,),
                True
            )
            
            # Если записи в users нет или счетчик NULL
            if not result or result[0]['messages_count'] is None:
                # Подсчитываем сообщения из истории чата
                count_from_history = await self.execute_query(
                    "SELECT COUNT(*) as count FROM chat_history WHERE user_id = ?",
                    (user_id,),
                    True
                )
                
                count = count_from_history[0]['count'] if count_from_history else 0
                logger.debug(f"Got message count from chat_history for user {user_id}: {count}")
                
                # Создаем запись пользователя или обновляем счетчик, если есть расхождение
                await self.execute_query(
                    """
                    INSERT OR REPLACE INTO users 
                    (user_id, messages_count, subscription_status, last_activity) 
                    VALUES (?, ?, 
                        COALESCE((SELECT subscription_status FROM users WHERE user_id = ?), 'free'), 
                        CURRENT_TIMESTAMP
                    )
                    """,
                    (user_id, count, user_id)
                )
                
                return count
            
            # Возвращаем счетчик из таблицы users
            count = result[0]['messages_count']
            logger.debug(f"Got message count from users table for user {user_id}: {count}")
            return count
        except Exception as e:
            logger.error(f"Error getting message count for user {user_id}: {e}")
            return 0

    async def get_subscription_status(self, user_id):
        """Get a user's subscription status"""
        # Проверяем срок действия подписки
        await self.check_subscription_expiry(user_id)
        
        result = await self.execute_query(
            "SELECT subscription_status FROM users WHERE user_id = ?",
            (user_id,),
            True
        )
        
        if result:
            return result[0]['subscription_status']
        return 'free'
    
    async def check_subscription_expiry(self, user_id):
        """Проверяет и обновляет статус подписки, если срок истек"""
        try:
            result = await self.execute_query(
                "SELECT subscription_status, subscription_expiry FROM users WHERE user_id = ?",
                (user_id,),
                True
            )
            
            if not result:
                return
            
            status = result[0]['subscription_status']
            expiry = result[0]['subscription_expiry']
            
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
                await self.execute_query(
                    "UPDATE users SET subscription_status = 'free', message_limit = NULL WHERE user_id = ?",
                    (user_id,)
                )
                logger.info(f"Subscription expired for user {user_id}, changed to free")
        except Exception as e:
            logger.error(f"Error checking subscription expiry for user {user_id}: {e}")
    
    async def update_subscription(self, user_id, status, expiry_date=None):
        """Обновляет статус подписки пользователя"""
        try:
            if expiry_date:
                await self.execute_query(
                    "UPDATE users SET subscription_status = ?, subscription_expiry = ? WHERE user_id = ?",
                    (status, expiry_date, user_id)
                )
            else:
                await self.execute_query(
                    "UPDATE users SET subscription_status = ? WHERE user_id = ?",
                    (status, user_id)
                )
            return True
        except Exception as e:
            logger.error(f"Error updating subscription for user {user_id}: {e}")
            return False
    
    async def get_message_limit(self, user_id):
        """Получает лимит сообщений для пользователя"""
        result = await self.execute_query(
            "SELECT message_limit FROM users WHERE user_id = ?",
            (user_id,),
            True
        )
        
        # Если у пользователя установлен индивидуальный лимит
        if result and result[0]['message_limit'] is not None:
            return result[0]['message_limit']
        
        # Иначе берем лимит из настроек по статусу подписки
        subscription = await self.get_subscription_status(user_id)
        return config.SUBSCRIPTION_LIMITS.get(subscription, 50)

    async def cleanup_inactive_chats(self, days=None):
        """Delete chat history and users who haven't been active for a while"""
        days = days or config.INACTIVE_CHAT_CLEANUP_DAYS
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)

        try:
            # Delete chat history for inactive users
            await self.execute_query(
                "DELETE FROM chat_history WHERE user_id IN (SELECT user_id FROM users WHERE last_activity < ?)",
                (cutoff_date,)
            )
            # Delete inactive users
            await self.execute_query(
                "DELETE FROM users WHERE last_activity < ?",
                (cutoff_date,)
            )
            logger.info(f"Cleaned up inactive chats older than {days} days")
            return True
        except Exception as e:
            logger.error(f"Error during cleanup of inactive chats: {e}")
            return False

    async def save_payment_info(self, user_id: int, payment_id: str, subscription_type: str, amount: float):
        """
        Сохраняет информацию о платеже в базе данных
        
        Args:
            user_id: ID пользователя
            payment_id: ID платежа в ЮKassa
            subscription_type: Тип подписки
            amount: Сумма платежа
            
        Returns:
            bool: True если успешно, False в случае ошибки
        """
        try:
            await self.execute_query(
                "INSERT INTO payments (user_id, payment_id, subscription_type, amount) VALUES (?, ?, ?, ?)",
                (user_id, payment_id, subscription_type, amount)
            )
            
            logger.info(f"Payment info saved for user {user_id}: payment_id={payment_id}")
            return True
        except Exception as e:
            logger.error(f"Error saving payment info for user {user_id}: {e}")
            return False
            
    async def get_last_payment(self, user_id: int):
        """
        Получает информацию о последнем платеже пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            tuple: (payment_id, subscription_type) или None в случае ошибки
        """
        try:
            result = await self.execute_query(
                "SELECT payment_id, subscription_type FROM payments WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
                (user_id,),
                True
            )
            
            if result:
                return (result[0]['payment_id'], result[0]['subscription_type'])
            else:
                return None
        except Exception as e:
            logger.error(f"Error getting last payment for user {user_id}: {e}")
            return None

    async def close(self):
        """Close the database connection"""
        if self.conn:
            await self.conn.close()
            self.conn = None
            logger.info("Database connection closed") 