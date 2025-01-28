import asyncio
import logging
from bot import MarketingPalBot

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def main():
    bot = None
    try:
        print("🚀 Запуск MarketingPal бота...")
        bot = MarketingPalBot()
        await bot.run()
    except Exception as e:
        logging.error(f"❌ Критическая ошибка: {str(e)}")
        print(f"\n❌ Ошибка: {str(e)}")
    finally:
        if bot:
            try:
                await bot.stop()
            except Exception as stop_error:
                logging.error(f"Ошибка при останове бота: {stop_error}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен пользователем")