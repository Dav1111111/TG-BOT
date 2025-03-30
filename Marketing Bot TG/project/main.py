#!/usr/bin/env python3
"""
Main entry point for the Telegram bot
"""
import asyncio
import logging
import sys
import os
import nest_asyncio
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
# Комментируем этот импорт, так как он не найден
# from aiogram.client.default import DefaultBotProperties
from bot.config import config
from bot.handlers import register_handlers
from bot.utils.menu_commands import set_bot_commands, set_menu_button
from bot.knowledge_base.vector_kb_manager import VectorKnowledgeBaseManager
from bot.database import DBManager
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=config.LOG_LEVEL,
    format=config.LOG_FORMAT,
    stream=sys.stdout
)

# Apply nest_asyncio for Google Colab compatibility
nest_asyncio.apply()

def load_knowledge_base():
    """Загружает документ в векторный индекс при запуске бота"""
    try:
        # Сначала пробуем загрузить DOCX файл
        docx_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), config.PDF_STORAGE_PATH, "Positioning That Sells 2.docx")
        
        if os.path.exists(docx_file_path):
            file_path = docx_file_path
            title = "Positioning That Sells 2"
            logging.info(f"Найден DOCX файл, загружаю: {file_path}")
        else:
            # Если DOCX не найден, пробуем загрузить PDF
            pdf_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), config.PDF_STORAGE_PATH, "Positioning That Sells.pdf")
            
            if not os.path.exists(pdf_file_path):
                logging.error(f"Документы не найдены по путям: {docx_file_path}, {pdf_file_path}")
                return False
                
            file_path = pdf_file_path
            title = "Positioning That Sells"
            logging.info(f"Найден PDF файл, загружаю: {file_path}")
        
        logging.info(f"Загрузка документа в векторную базу знаний: {file_path}")
        
        # Инициализация менеджеров
        db_manager = DBManager()
        vector_kb_manager = VectorKnowledgeBaseManager(db_manager)
        
        # Очищаем существующие записи из БД, но НЕ удаляем физические файлы
        # Вместо удаления через manager, удаляем напрямую из базы данных
        db_manager.execute_query("DELETE FROM knowledge_base_content")
        db_manager.execute_query("DELETE FROM knowledge_base_docs")
        logging.info("Существующие записи в базе данных очищены без удаления физических файлов")
        
        # Удаляем старый векторный индекс
        vector_storage_path = Path(config.VECTOR_STORAGE_PATH)
        vector_index_path = vector_storage_path / "faiss_index"
        if os.path.exists(vector_index_path):
            import shutil
            shutil.rmtree(vector_index_path, ignore_errors=True)
            logging.info(f"Удален существующий векторный индекс: {vector_index_path}")
        
        # Загружаем документ напрямую
        result = vector_kb_manager.kb_manager.load_document_directly(file_path, title)
        
        if result['success']:
            logging.info(f"Документ успешно загружен в базу знаний, ID документа: {result['doc_id']}")
            # После успешной загрузки в базу, обновляем векторный индекс
            vector_kb_manager.rebuild_index()
            return True
        else:
            logging.error(f"Ошибка при загрузке документа: {result['error']}")
            return False
    except Exception as e:
        logging.error(f"Ошибка при загрузке документа в базу знаний: {e}")
        return False

async def main():
    """Main function to start the bot"""
    # Загружаем документ в базу знаний при запуске
    load_knowledge_base()
    
    # Initialize bot and dispatcher
    bot = Bot(token=config.TELEGRAM_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher()

    # Set up commands in bot menu
    await set_bot_commands(bot, config.ADMIN_IDS)

    # Set up menu button
    await set_menu_button(bot)

    # Register all handlers
    register_handlers(dp)

    # Start polling
    logging.info("Starting bot")
    await dp.start_polling(bot, close_timeout=5, allowed_updates=["message", "callback_query", "inline_query"], drop_pending_updates=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot stopped by user")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        sys.exit(1)
