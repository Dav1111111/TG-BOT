"""
Улучшенная версия менеджера базы знаний с использованием LangChain и embeddings
"""
import os
import time
import json
import logging
import tempfile
import pickle
from pathlib import Path
import numpy as np
from typing import List, Dict, Tuple, Optional, Any, Union

# Импорты LangChain
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.docstore.document import Document
from langchain_community.document_loaders import PyPDFLoader

# Импорты проекта
from bot.config import config
from bot.database import DBManager
from bot.knowledge_base.kb_manager import KnowledgeBaseManager

logger = logging.getLogger(__name__)

class VectorKnowledgeBaseManager:
    """
    Улучшенный менеджер базы знаний с использованием векторных embeddings
    для более эффективного семантического поиска
    """

    def __init__(self, db_manager=None):
        """
        Инициализация менеджера векторной базы знаний

        Args:
            db_manager: Экземпляр DBManager для работы с базой данных
        """
        # Используем существующий класс KnowledgeBaseManager для базовых операций с БД
        self.kb_manager = KnowledgeBaseManager(db_manager)

        # Директория для хранения векторных индексов
        self.vector_storage_path = Path(config.VECTOR_STORAGE_PATH)
        os.makedirs(self.vector_storage_path, exist_ok=True)

        # Инициализируем embeddings модель
        try:
            self.embeddings = OpenAIEmbeddings(
                api_key=config.OPENAI_API_KEY,
                model=config.EMBEDDING_MODEL
            )
            logger.info(f"Инициализирована модель эмбеддингов: {config.EMBEDDING_MODEL}")
        except Exception as e:
            logger.error(f"Ошибка при инициализации OpenAI Embeddings: {e}")
            logger.warning("Будет использован обычный поиск без векторных эмбеддингов")
            self.embeddings = None

        # Загружаем существующий векторный индекс, если он есть
        self.vector_index_path = self.vector_storage_path / "faiss_index"
        self.vector_store = self._load_vector_store()

        # Настройки для разделения текста
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
        )

    def _load_vector_store(self) -> Optional[FAISS]:
        """
        Загрузить существующий векторный индекс, если он есть

        Returns:
            FAISS: Векторное хранилище или None
        """
        if self.embeddings is None:
            return None

        try:
            if os.path.exists(self.vector_index_path):
                logger.info(f"Загрузка существующего векторного индекса из {self.vector_index_path}")
                try:
                    vector_store = FAISS.load_local(
                        folder_path=str(self.vector_index_path),
                        embeddings=self.embeddings,
                        allow_dangerous_deserialization=True
                    )
                    return vector_store
                except Exception as load_error:
                    # Проверяем, связана ли ошибка с __fields_set__
                    if '__fields_set__' in str(load_error):
                        logger.warning(f"Обнаружен несовместимый векторный индекс: {load_error}")
                        logger.warning("Удаляю несовместимый индекс для автоматического пересоздания...")
                        
                        # Удаляем несовместимый индекс
                        import shutil
                        try:
                            shutil.rmtree(self.vector_index_path, ignore_errors=True)
                            logger.info(f"Несовместимый индекс успешно удален из {self.vector_index_path}")
                        except Exception as rm_error:
                            logger.error(f"Ошибка при удалении индекса: {rm_error}")
                        
                        return None
                    else:
                        # Если ошибка не связана с __fields_set__, пробрасываем её дальше
                        raise load_error
            else:
                logger.info("Векторный индекс не найден, будет создан новый при добавлении документов")
                return None
        except Exception as e:
            # Подавляем ошибку в логах, чтобы не показывать её пользователям
            if '__fields_set__' in str(e):
                logger.warning("Проблема с совместимостью векторного индекса. Будет создан новый.")
            else:
                logger.error(f"Ошибка при загрузке векторного индекса: {e}")
            return None

    def _save_vector_store(self) -> bool:
        """
        Сохранить векторный индекс на диск

        Returns:
            bool: Успешно ли сохранен индекс
        """
        if self.vector_store is None:
            logger.warning("Нет векторного индекса для сохранения")
            return False

        try:
            self.vector_store.save_local(folder_path=str(self.vector_index_path))
            logger.info(f"Векторный индекс успешно сохранен в {self.vector_index_path}")
            return True
        except Exception as e:
            logger.error(f"Ошибка при сохранении векторного индекса: {e}")
            return False

    def load_pdf_directly(self, pdf_path: str, title: Optional[str] = None) -> Tuple[bool, str]:
        """
        Загрузить PDF файл в базу знаний и векторное хранилище

        Args:
            pdf_path: Путь к PDF файлу
            title: Название документа (если None, используется имя файла без расширения)

        Returns:
            Tuple[bool, str]: (успех, ID документа или сообщение об ошибке)
        """
        # Сначала используем существующий метод для загрузки в базу данных
        success, result = self.kb_manager.load_pdf_directly(pdf_path, title)

        if not success:
            return False, result

        # Если векторная модель не доступна, просто возвращаем результат
        if self.embeddings is None:
            return True, result

        # Добавляем документ в векторное хранилище
        doc_id = result
        try:
            # Загружаем PDF через LangChain для более точной обработки
            loader = PyPDFLoader(pdf_path)
            pages = loader.load()

            # Разделяем текст на чанки для лучшего поиска
            chunks = self.text_splitter.split_documents(pages)

            # Добавляем метаданные каждому чанку
            for i, chunk in enumerate(chunks):
                chunk.metadata["doc_id"] = doc_id
                chunk.metadata["title"] = title or os.path.splitext(os.path.basename(pdf_path))[0]
                chunk.metadata["chunk_id"] = i

            # Создаем или обновляем векторное хранилище
            if self.vector_store is None:
                # Первый документ - создаем новое хранилище
                self.vector_store = FAISS.from_documents(chunks, self.embeddings)
            else:
                # Добавляем к существующему хранилищу
                self.vector_store.add_documents(chunks)

            # Сохраняем обновленный индекс
            self._save_vector_store()

            logger.info(f"Документ {doc_id} успешно добавлен в векторное хранилище")
            return True, doc_id

        except Exception as e:
            logger.error(f"Ошибка при добавлении документа в векторное хранилище: {e}")
            # Если не удалось добавить в векторное хранилище, но в БД добавили,
            # то всё равно считаем операцию успешной
            return True, doc_id

    def remove_pdf_by_id(self, doc_id: Union[int, str]) -> Tuple[bool, str]:
        """
        Удалить PDF файл из обычной базы знаний и векторного хранилища

        Args:
            doc_id: ID документа для удаления

        Returns:
            Tuple[bool, str]: (успех, сообщение)
        """
        # Проверяем, существует ли документ
        try:
            doc_id = int(doc_id)
        except ValueError:
            return False, f"Некорректный ID документа: {doc_id}"

        # Сначала удаляем из обычной базы знаний
        success, message = self.kb_manager.remove_pdf_by_id(doc_id)

        if not success:
            return False, message

        # Если векторного хранилища нет, просто возвращаем результат
        if self.vector_store is None or self.embeddings is None:
            return True, message

        try:
            # Пересоздаем векторное хранилище без удаленного документа
            # Получаем все документы из хранилища
            all_docs = self.vector_store.docstore._dict.values()

            # Отфильтровываем удаленный документ
            filtered_docs = [
                doc for doc in all_docs
                if doc.metadata.get("doc_id") != str(doc_id) and doc.metadata.get("doc_id") != doc_id
            ]

            if filtered_docs:
                # Если остались документы, пересоздаем хранилище
                self.vector_store = FAISS.from_documents(filtered_docs, self.embeddings)
                self._save_vector_store()
                logger.info(f"Документ {doc_id} успешно удален из векторного хранилища")
            else:
                # Если документов не осталось, удаляем хранилище
                if os.path.exists(self.vector_index_path):
                    import shutil
                    shutil.rmtree(self.vector_index_path)
                self.vector_store = None
                logger.info("Удален последний документ, векторное хранилище очищено")

            return True, message

        except Exception as e:
            logger.error(f"Ошибка при удалении документа из векторного хранилища: {e}")
            # Если не удалось удалить из векторного хранилища, но из БД удалили,
            # то всё равно считаем операцию успешной
            return True, message + " (Внимание: возникла ошибка при обновлении векторного индекса)"

    def get_content_for_query(self, query: str, use_vector_search: bool = True) -> Optional[str]:
        """
        Получить релевантный контент из базы знаний для запроса

        Args:
            query: Запрос пользователя
            use_vector_search: Использовать ли векторный поиск (если доступен)

        Returns:
            Optional[str]: Релевантный контент или None
        """
        # Проверяем возможность использования векторного поиска
        if use_vector_search and self.vector_store is not None and self.embeddings is not None:
            try:
                # Выполняем векторный поиск
                docs_with_scores = self.vector_store.similarity_search_with_score(query, k=5)

                if not docs_with_scores:
                    logger.info("Векторный поиск не дал результатов, используем обычный поиск")
                    return self.kb_manager.get_content_for_query(query)

                # Фильтруем документы с низким сходством (порог можно настроить)
                threshold = 0.7  # Порог сходства (1.0 - точное совпадение)
                filtered_docs = [
                    (doc, score) for doc, score in docs_with_scores
                    if score <= threshold  # Меньшее значение = большее сходство
                ]

                if not filtered_docs:
                    logger.info("Все найденные документы ниже порога сходства, используем обычный поиск")
                    return self.kb_manager.get_content_for_query(query)

                # Формируем результат
                relevant_content = []
                for i, (doc, score) in enumerate(filtered_docs, 1):
                    title = doc.metadata.get("title", "Неизвестный документ")
                    page_num = doc.metadata.get("page", 1)
                    doc_id = doc.metadata.get("doc_id", "unknown")

                    relevant_content.append(
                        f"Документ: {title} (ID: {doc_id}, Страница: {page_num}, Релевантность: {1.0 - score:.2f})\n\n{doc.page_content}"
                    )

                return "\n\n---\n\n".join(relevant_content)

            except Exception as e:
                logger.error(f"Ошибка при выполнении векторного поиска: {e}")
                # В случае ошибки, используем обычный поиск
                return self.kb_manager.get_content_for_query(query)
        else:
            # Если векторный поиск недоступен или отключен, используем обычный поиск
            return self.kb_manager.get_content_for_query(query)

    def list_knowledge_base_docs(self, admin_id=None):
        """
        Получить список всех документов в базе знаний

        Args:
            admin_id: Опционально, ID администратора для фильтрации

        Returns:
            list: Список документов
        """
        # Используем существующий метод для получения списка документов
        return self.kb_manager.list_knowledge_base_docs(admin_id)

    def search_in_knowledge_base(self, query: str, limit: int = 10,
                                use_vector_search: bool = True) -> List[Dict[str, Any]]:
        """
        Выполнить поиск в базе знаний

        Args:
            query: Поисковый запрос
            limit: Максимальное количество результатов
            use_vector_search: Использовать ли векторный поиск (если доступен)

        Returns:
            List[Dict]: Список результатов поиска
        """
        # Проверяем возможность использования векторного поиска
        if use_vector_search and self.vector_store is not None and self.embeddings is not None:
            try:
                # Выполняем векторный поиск
                docs_with_scores = self.vector_store.similarity_search_with_score(query, k=limit)

                if not docs_with_scores:
                    logger.info("Векторный поиск не дал результатов, используем обычный поиск")
                    return self.kb_manager.search_in_knowledge_base(query, limit)

                # Преобразуем результаты в нужный формат
                search_results = []
                for doc, score in docs_with_scores:
                    title = doc.metadata.get("title", "Неизвестный документ")
                    page_num = doc.metadata.get("page", 1)
                    doc_id = doc.metadata.get("doc_id", "unknown")

                    # Создаем сниппет из содержимого документа
                    snippet = doc.page_content
                    if len(snippet) > 200:
                        snippet = snippet[:200] + "..."

                    search_results.append({
                        'doc_id': doc_id,
                        'title': title,
                        'page_num': page_num,
                        'snippet': snippet,
                        'score': 1.0 - score  # Преобразуем в оценку от 0 до 1
                    })

                return search_results

            except Exception as e:
                logger.error(f"Ошибка при выполнении векторного поиска: {e}")
                # В случае ошибки, используем обычный поиск
                return self.kb_manager.search_in_knowledge_base(query, limit)
        else:
            # Если векторный поиск недоступен или отключен, используем обычный поиск
            return self.kb_manager.search_in_knowledge_base(query, limit)

    def add_document_to_knowledge_base(self, pdf_path, title=None):
        """
        Добавить PDF файл в базу знаний и обновить векторный индекс

        Args:
            pdf_path: Путь к PDF файлу
            title: Название документа (если None, используется имя файла)

        Returns:
            dict: Результат операции с ключами:
                  - success: True/False
                  - error: Сообщение об ошибке (если есть)
                  - num_pages: Количество обработанных страниц
                  - doc_id: ID документа
        """
        try:
            # Сначала добавляем документ через базовый менеджер
            result = self.kb_manager.add_document_to_knowledge_base(pdf_path, title)
            
            # Если операция была успешной, обновляем векторный индекс
            if result['success'] and self.embeddings is not None:
                doc_id = result['doc_id']
                logger.info(f"Документ добавлен в базу, ID: {doc_id}. Обновляем векторный индекс...")
                
                # Получаем контент документа
                try:
                    # Загружаем документ напрямую с помощью LangChain
                    loader = PyPDFLoader(pdf_path)
                    documents = loader.load()
                    
                    # Разбиваем на чанки
                    text_chunks = self.text_splitter.split_documents(documents)
                    
                    # Добавляем метаданные документа
                    for chunk in text_chunks:
                        if hasattr(chunk, 'metadata'):
                            chunk.metadata['doc_id'] = doc_id
                            chunk.metadata['title'] = title or os.path.basename(pdf_path)
                    
                    # Добавляем в векторный индекс
                    if self.vector_store is None:
                        # Создаем новый индекс, если его еще нет
                        self.vector_store = FAISS.from_documents(text_chunks, self.embeddings)
                    else:
                        # Добавляем к существующему индексу
                        self.vector_store.add_documents(text_chunks)
                    
                    # Сохраняем обновленный индекс
                    self._save_vector_store()
                    logger.info(f"Векторный индекс успешно обновлен для документа {doc_id}")
                except Exception as e:
                    logger.error(f"Ошибка при обновлении векторного индекса: {e}")
                    # Операция всё равно считается успешной, так как документ был добавлен в базу
            
            return result
            
        except Exception as e:
            error_msg = f"Ошибка при добавлении документа в базу знаний: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg
            }

    def delete_document_from_knowledge_base(self, doc_id):
        """
        Удалить документ из базы знаний и обновить векторный индекс

        Args:
            doc_id: ID документа для удаления

        Returns:
            dict: Результат операции с ключами:
                  - success: True/False
                  - error: Сообщение об ошибке (если есть)
        """
        try:
            # Сначала удаляем документ через базовый менеджер
            result = self.kb_manager.delete_document_from_knowledge_base(doc_id)
            
            # Если операция была успешной и у нас есть векторный индекс, обновляем его
            if result['success'] and self.embeddings is not None and self.vector_store is not None:
                logger.info(f"Документ с ID {doc_id} удален из базы. Необходимо пересоздать векторный индекс...")
                
                # Для FAISS мы не можем просто удалить документы из индекса,
                # поэтому нужно полностью пересоздать индекс из оставшихся документов
                try:
                    # Получаем список всех оставшихся документов
                    remaining_docs = self.kb_manager.list_knowledge_base_docs()
                    
                    if not remaining_docs:
                        # Если документов не осталось, просто удаляем индекс
                        if os.path.exists(self.vector_index_path):
                            import shutil
                            shutil.rmtree(self.vector_index_path, ignore_errors=True)
                        self.vector_store = None
                        logger.info("Векторный индекс удален, так как не осталось документов")
                    else:
                        # Пересоздаем индекс из оставшихся документов
                        # Это затратная операция, но для небольшого количества документов приемлемо
                        all_chunks = []
                        
                        for doc in remaining_docs:
                            try:
                                file_path = doc['file_path']
                                if os.path.exists(file_path):
                                    loader = PyPDFLoader(file_path)
                                    documents = loader.load()
                                    text_chunks = self.text_splitter.split_documents(documents)
                                    
                                    for chunk in text_chunks:
                                        if hasattr(chunk, 'metadata'):
                                            chunk.metadata['doc_id'] = doc['doc_id']
                                            chunk.metadata['title'] = doc['title']
                                    
                                    all_chunks.extend(text_chunks)
                            except Exception as e:
                                logger.error(f"Ошибка при обработке документа {doc['title']}: {e}")
                        
                        if all_chunks:
                            # Создаем новый индекс
                            self.vector_store = FAISS.from_documents(all_chunks, self.embeddings)
                            self._save_vector_store()
                            logger.info(f"Векторный индекс успешно пересоздан с {len(all_chunks)} фрагментами")
                        else:
                            self.vector_store = None
                            logger.warning("Не удалось создать векторный индекс из оставшихся документов")
                
                except Exception as e:
                    logger.error(f"Ошибка при обновлении векторного индекса после удаления: {e}")
                    # Операция всё равно считается успешной, так как документ был удален из базы
            
            return result
            
        except Exception as e:
            error_msg = f"Ошибка при удалении документа с ID {doc_id}: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg
            }

    def rebuild_index(self):
        """
        Полное пересоздание векторного индекса для всех документов в базе знаний.
        Используется для ручного обновления индекса, например, при проблемах с ним.

        Returns:
            dict: Результат операции с ключами:
                  - success: True/False
                  - error: Сообщение об ошибке (если есть)
                  - chunks_count: Количество обработанных фрагментов
                  - docs_count: Количество обработанных документов
        """
        if self.embeddings is None:
            return {
                'success': False,
                'error': 'Векторная модель эмбеддингов недоступна'
            }

        try:
            # Получаем список всех документов
            all_docs = self.kb_manager.list_knowledge_base_docs()
            
            if not all_docs:
                # Если документов нет, удаляем индекс, если он существует
                if os.path.exists(self.vector_index_path):
                    import shutil
                    shutil.rmtree(self.vector_index_path, ignore_errors=True)
                self.vector_store = None
                logger.info("База знаний пуста. Векторный индекс очищен.")
                
                return {
                    'success': True,
                    'chunks_count': 0,
                    'docs_count': 0
                }
            
            # Собираем все чанки из всех документов
            all_chunks = []
            processed_docs = 0
            failed_docs = 0
            
            logger.info(f"Начинаю пересоздание индекса для {len(all_docs)} документов...")
            
            for doc in all_docs:
                try:
                    # Получаем содержимое документа из базы данных
                    doc_id = doc['doc_id']
                    title = doc['title']
                    
                    # Получаем текст всех страниц из базы данных
                    content_data = self.kb_manager.db_manager.execute_query(
                        "SELECT page_num, content FROM knowledge_base_content WHERE doc_id = ? ORDER BY page_num",
                        (doc_id,),
                        fetch=True
                    )
                    
                    if not content_data:
                        logger.warning(f"Не найдено содержимое для документа {title} (ID: {doc_id})")
                        failed_docs += 1
                        continue
                    
                    # Преобразуем данные из базы в формат для LangChain Document
                    documents = []
                    for page_num, content in content_data:
                        if content and content.strip():
                            documents.append(Document(
                                page_content=content,
                                metadata={
                                    'source': title,
                                    'page': page_num,
                                    'doc_id': doc_id
                                }
                            ))
                    
                    # Разбиваем на чанки для индексации
                    text_chunks = self.text_splitter.split_documents(documents)
                    
                    # Добавляем метаданные документа к каждому чанку
                    for chunk in text_chunks:
                        if hasattr(chunk, 'metadata'):
                            chunk.metadata['doc_id'] = doc_id
                            chunk.metadata['title'] = title
                    
                    # Добавляем в общий список чанков
                    all_chunks.extend(text_chunks)
                    processed_docs += 1
                    logger.info(f"Обработан документ {title} (ID: {doc_id}), добавлено {len(text_chunks)} фрагментов")
                    
                except Exception as e:
                    logger.error(f"Ошибка при обработке документа {doc.get('title', 'unknown')} (ID: {doc.get('doc_id', 'unknown')}): {e}")
                    failed_docs += 1
            
            # Создаем новый индекс, если есть чанки
            if all_chunks:
                logger.info(f"Создание нового векторного индекса с {len(all_chunks)} фрагментами...")
                
                # Удаляем старый индекс, если он существует
                if os.path.exists(self.vector_index_path):
                    import shutil
                    shutil.rmtree(self.vector_index_path, ignore_errors=True)
                
                # Создаем новый индекс
                self.vector_store = FAISS.from_documents(all_chunks, self.embeddings)
                
                # Сохраняем индекс
                self._save_vector_store()
                
                logger.info(f"Векторный индекс успешно пересоздан с {len(all_chunks)} фрагментами из {processed_docs} документов")
                
                return {
                    'success': True,
                    'chunks_count': len(all_chunks),
                    'docs_count': processed_docs,
                    'failed_docs': failed_docs
                }
            else:
                # Если не удалось создать чанки
                if os.path.exists(self.vector_index_path):
                    import shutil
                    shutil.rmtree(self.vector_index_path, ignore_errors=True)
                self.vector_store = None
                
                error_msg = "Не удалось создать векторный индекс - не найдено содержимое документов"
                logger.warning(error_msg)
                
                return {
                    'success': False,
                    'error': error_msg,
                    'docs_count': processed_docs,
                    'failed_docs': failed_docs
                }
                
        except Exception as e:
            error_msg = f"Ошибка при пересоздании векторного индекса: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg
            }
