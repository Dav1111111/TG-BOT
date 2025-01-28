import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI
from datetime import datetime
from chat_history import ChatHistory
from config import TELEGRAM_TOKEN, OPENAI_API_KEY, SYSTEM_PROMPT

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

class MarketingPalBot:
    def __init__(self):
        self.app = Application.builder().token(TELEGRAM_TOKEN).build()
        self.user_states = {}
        self.chat_history = ChatHistory()
        self.client = OpenAI(api_key=OPENAI_API_KEY)

    async def run(self):
        try:
            # Регистрация обработчиков
            self.app.add_handler(CommandHandler("start", self.start_command))
            self.app.add_handler(CommandHandler("help", self.help_command))
            self.app.add_handler(CommandHandler("newpersona", self.new_persona_command))
            self.app.add_handler(CommandHandler("history", self.show_history_command))
            self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
            
            print("🤖 MarketingPal бот запущен...")
            await self.app.initialize()
            await self.app.start()
            
            # Запуск длительного опроса
            try:
                await self.app.updater.start_polling(drop_pending_updates=True)
                # Ожидание завершения работы бота
                while True:
                    await asyncio.sleep(3600)  # Периодический sleep для поддержания работы
            except asyncio.CancelledError:
                print("Работа бота прервана")
            
        except Exception as e:
            logging.error(f"Ошибка при работе бота: {str(e)}")
            raise
        finally:
            await self.stop()

    async def stop(self):
        try:
            await self.app.stop()
            await self.app.shutdown()
        except Exception as e:
            logging.error(f"Ошибка при остановке бота: {str(e)}")

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        welcome_message = (
            "👋 Привет! Я MarketingPal - ваш ИИ-ассистент по созданию клиентских персон.\n\n"
            "🎯 Я помогу вам:\n"
            "- Создавать детальные портреты целевой аудитории\n"
            "- Анализировать потребности и боли клиентов\n"
            "- Разрабатывать эффективные маркетинговые стратегии\n\n"
            "Используйте команду /newpersona чтобы начать создание новой персоны."
        )
        await update.message.reply_text(welcome_message)
        self.chat_history.add_message(update.effective_user.id, "Команда /start", False)
        self.chat_history.add_message(update.effective_user.id, welcome_message, True)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_message = (
            "🤖 Как использовать MarketingPal:\n\n"
            "1. /start - Начать работу с ботом\n"
            "2. /newpersona - Создать новую клиентскую персону\n"
            "3. /help - Показать это сообщение\n"
            "4. /history - Показать историю сообщений\n\n"
            "Просто отвечайте на мои вопросы, и я помогу вам создать детальный портрет вашей целевой аудитории."
        )
        await update.message.reply_text(help_message)
        self.chat_history.add_message(update.effective_user.id, "Команда /help", False)
        self.chat_history.add_message(update.effective_user.id, help_message, True)

    async def new_persona_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        self.user_states[user_id] = {"stage": "business_info"}

        persona_message = (
            "📊 Давайте создадим новую клиентскую персону!\n\n"
            "Для начала, расскажите о вашем бизнесе:\n"
            "- В какой сфере вы работаете?\n"
            "- Какой продукт или услугу предлагаете?\n"
            "- Кто, по вашему мнению, ваша целевая аудитория?"
        )
        await update.message.reply_text(persona_message)
        self.chat_history.add_message(update.effective_user.id, "Команда /newpersona", False)
        self.chat_history.add_message(update.effective_user.id, persona_message, True)

    async def show_history_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        history = self.chat_history.get_user_history(user_id)

        if not history:
            await update.message.reply_text("У вас пока нет истории сообщений.")
            return

        message = "📝 История ваших сообщений:\n\n"
        for entry in history[-10:]:
            time = datetime.fromisoformat(entry['timestamp']).strftime('%Y-%m-%d %H:%M')
            who = "🤖 Бот" if entry['is_bot'] else "👤 Вы"
            message += f"{time} {who}:\n{entry['message']}\n\n"

        await update.message.reply_text(message)
        self.chat_history.add_message(user_id, "Команда /history", False)
        self.chat_history.add_message(user_id, message, True)

    def get_gpt4mini_response(self, text: str, user_id: int) -> str:
        try:
            stage = self.user_states.get(user_id, {}).get("stage", "general")

            messages = [
                {
                    "role": "system",
                    "content": [{"type": "text", "text": SYSTEM_PROMPT}]
                },
                {
                    "role": "user",
                    "content": [{"type": "text", "text": text}]
                }
            ]

            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.7,
                max_tokens=800,
                top_p=1
            )
            return response.choices[0].message.content
        except Exception as e:
            logging.error(f"Error in GPT-4-mini request: {str(e)}")
            return f"Извините, произошла ошибка при обработке запроса: {str(e)}"

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        message_text = update.message.text

        self.chat_history.add_message(user_id, message_text, False)
        await update.message.chat.send_action(action="typing")
        response = self.get_gpt4mini_response(message_text, user_id)
        self.chat_history.add_message(user_id, response, True)
        await update.message.reply_text(response)