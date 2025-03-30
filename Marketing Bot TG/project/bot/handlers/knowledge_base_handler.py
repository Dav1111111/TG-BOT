"""
Обработчик для управления базой знаний (загрузка PDF и поиск)
"""
import os
import logging
import tempfile
from aiogram import types, F
from aiogram.filters.command import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.config import config
from bot.knowledge_base import KnowledgeBaseManager
from bot.states.states import KnowledgeBaseStates

logger = logging.getLogger(__name__)
kb_manager = KnowledgeBaseManager()

# Создаем временную директорию для загрузки файлов
TEMP_DIR = "temp_uploads"
os.makedirs(TEMP_DIR, exist_ok=True)

async def kb_start_command(message: types.Message):
    """
    Обработчик команды /kb - основное меню базы знаний
    """
    user_id = message.from_user.id

    # Проверяем, является ли пользователь администратором
    is_admin = user_id in config.ADMIN_IDS

    menu_text = "🔍 База знаний - здесь собраны документы, которые помогут ответить на ваши вопросы.\n\n"
    
    # Базовые опции, доступные всем пользователям
    menu_text += "Доступные команды:\n"
    menu_text += "📚 /kb_list - показать список документов\n"
    
    # Опции для администратора
    if is_admin:
        menu_text += "📥 /kb_upload - загрузить PDF файл\n"
        menu_text += "🗑 /kb_delete - удалить документ\n"
    
    await message.answer(menu_text)

async def kb_list_docs_command(message: types.Message):
    """
    Обработчик для просмотра списка документов
    """
    # Получаем список документов
    docs = kb_manager.list_knowledge_base_docs()

    if not docs:
        await message.answer("📚 База знаний пуста. Документы еще не загружены.")
        return

    # Формируем сообщение со списком документов
    message_text = "📚 Список документов в базе знаний:\n\n"

    for i, doc in enumerate(docs, 1):
        message_text += f"{i}. {doc['title']} ({doc['filename']})\n"
        message_text += f"   Загружен: {doc['upload_date']}, {doc['num_pages']} страниц\n\n"

    await message.answer(message_text)

async def kb_upload_pdf_command(message: types.Message, state: FSMContext):
    """
    Обработчик для начала процесса загрузки PDF
    """
    user_id = message.from_user.id

    # Проверяем, является ли пользователь администратором
    if user_id not in config.ADMIN_IDS:
        await message.answer("⛔ У вас нет прав для загрузки документов")
        return

    await state.set_state(KnowledgeBaseStates.waiting_for_pdf)

    await message.answer(
        "📤 Пожалуйста, отправьте PDF файл, который вы хотите добавить в базу знаний.\n"
        "Для отмены используйте команду /cancel"
    )

async def process_pdf_upload(message: types.Message, state: FSMContext):
    """
    Обработчик для загрузки PDF файла
    """
    user_id = message.from_user.id

    # Проверяем, является ли пользователь администратором
    if user_id not in config.ADMIN_IDS:
        await message.answer("⛔ У вас нет прав для загрузки документов")
        await state.clear()
        return

    # Проверяем, что сообщение содержит документ
    if not message.document:
        await message.answer("❌ Пожалуйста, отправьте PDF файл. Для отмены используйте команду /cancel")
        return

    # Проверяем формат файла (PDF)
    if not message.document.file_name.lower().endswith('.pdf'):
        await message.answer("❌ Пожалуйста, отправьте файл в формате PDF. Для отмены используйте команду /cancel")
        return

    # Сохраняем имя файла
    await state.update_data(file_name=message.document.file_name)

    # Создаем путь для временного файла
    temp_file_path = os.path.join(TEMP_DIR, message.document.file_name)

    # Загружаем файл
    await message.document.download(destination=temp_file_path)

    # Сохраняем путь к файлу
    await state.update_data(file_path=temp_file_path)

    # Переходим к запросу названия документа
    await state.set_state(KnowledgeBaseStates.waiting_for_title)

    await message.answer(
        "📝 Пожалуйста, введите название для этого документа, которое будет отображаться в списке."
    )

async def process_pdf_title(message: types.Message, state: FSMContext):
    """
    Обработчик для получения названия PDF файла и его обработки
    """
    # Получаем текст сообщения (название документа)
    title = message.text

    # Получаем сохраненные данные
    data = await state.get_data()
    file_path = data.get('file_path')
    file_name = data.get('file_name')

    if not file_path or not file_name:
        await message.answer("❌ Произошла ошибка при обработке файла. Пожалуйста, попробуйте заново.")
        await state.clear()
        return

    # Отправляем сообщение о начале обработки
    processing_msg = await message.answer("⏳ Обрабатываю PDF файл, это может занять некоторое время...")

    try:
        # Добавляем документ в базу знаний
        result = kb_manager.add_document_to_knowledge_base(file_path, title)

        if result['success']:
            await processing_msg.edit_text(
                f"✅ Документ \"{title}\" успешно добавлен в базу знаний!\n"
                f"Обработано {result['num_pages']} страниц."
            )
        else:
            await processing_msg.edit_text(f"❌ Ошибка при обработке документа: {result['error']}")

    except Exception as e:
        logger.error(f"Error processing PDF: {str(e)}")
        await processing_msg.edit_text(f"❌ Произошла ошибка при обработке файла: {str(e)}")

    # Очищаем состояние
    await state.clear()

    # Удаляем временный файл
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        logger.error(f"Error removing temp file: {str(e)}")

async def kb_delete_pdf_command(message: types.Message, state: FSMContext):
    """
    Обработчик для начала процесса удаления PDF
    """
    user_id = message.from_user.id

    # Проверяем, является ли пользователь администратором
    if user_id not in config.ADMIN_IDS:
        await message.answer("⛔ У вас нет прав для удаления документов")
        return

    # Получаем список документов
    docs = kb_manager.list_knowledge_base_docs()

    if not docs:
        await message.answer("📚 База знаний пуста. Нет документов для удаления.")
        return

    # Формируем сообщение со списком документов
    message_text = "🗑 Выберите документ для удаления, отправив его номер:\n\n"

    for i, doc in enumerate(docs, 1):
        message_text += f"{i}. {doc['title']} ({doc['filename']})\n"

    # Сохраняем список документов в контексте
    await state.update_data(docs=docs)
    await state.set_state(KnowledgeBaseStates.waiting_for_delete_choice)

    await message.answer(message_text)

async def process_delete_choice(message: types.Message, state: FSMContext):
    """
    Обработчик для выбора документа для удаления
    """
    # Получаем номер документа
    try:
        doc_index = int(message.text) - 1
    except ValueError:
        await message.answer("❌ Пожалуйста, введите номер документа из списка.")
        return

    # Получаем сохраненные данные
    data = await state.get_data()
    docs = data.get('docs', [])

    # Проверяем корректность индекса
    if doc_index < 0 or doc_index >= len(docs):
        await message.answer("❌ Неверный номер документа. Пожалуйста, введите номер из списка.")
        return

    # Получаем выбранный документ
    doc = docs[doc_index]
    
    try:
        # Удаляем документ из базы знаний
        result = kb_manager.delete_document_from_knowledge_base(doc['doc_id'])
        
        if result['success']:
            await message.answer(f"✅ Документ \"{doc['title']}\" успешно удален из базы знаний!")
        else:
            await message.answer(f"❌ Ошибка при удалении документа: {result['error']}")
            
    except Exception as e:
        logger.error(f"Error deleting document: {str(e)}")
        await message.answer(f"❌ Произошла ошибка при удалении документа: {str(e)}")
    
    # Очищаем состояние
    await state.clear()

async def cancel_command(message: types.Message, state: FSMContext):
    """
    Обработчик для отмены текущей операции
    """
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("❓ Нет активных операций для отмены.")
        return

    # Удаляем временный файл, если он существует
    data = await state.get_data()
    file_path = data.get('file_path')
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            logger.error(f"Error removing temp file: {str(e)}")

    # Очищаем состояние
    await state.clear()
    await message.answer("🛑 Операция отменена.")

def register_handlers(dp):
    """
    Регистрация обработчиков для управления базой знаний
    """
    # Основные команды
    dp.message.register(kb_start_command, Command("kb"))
    dp.message.register(kb_list_docs_command, Command("kb_list"))
    dp.message.register(kb_upload_pdf_command, Command("kb_upload"))
    dp.message.register(kb_delete_pdf_command, Command("kb_delete"))
    dp.message.register(cancel_command, Command("cancel"))

    # Обработчики состояний
    dp.message.register(process_pdf_upload, KnowledgeBaseStates.waiting_for_pdf)
    dp.message.register(process_pdf_title, KnowledgeBaseStates.waiting_for_title)
    dp.message.register(process_delete_choice, KnowledgeBaseStates.waiting_for_delete_choice)

    # Удаляем обработчики колбэков, так как кнопки больше не используются
