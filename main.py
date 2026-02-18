"""
RoofNN — Telegram-бот. Приветствие, кнопка «Открыть карту», админ-модерация точек.
"""
import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton

from database import init_db, SessionLocal, Spot, User

# Важно: load_dotenv по умолчанию НЕ перезаписывает уже заданные переменные окружения.
# Если вы меняете `.env`, а в системе уже есть WEBAPP_URL/BOT_TOKEN/ADMIN_ID,
# бот может продолжать брать старые значения. Поэтому override=True.
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env", override=True)

# ID администратора — только он получает уведомления о новых точках и может одобрять/отклонять
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEBAPP_URL = (os.environ.get("WEBAPP_URL", "https://your-domain.com") or "").strip()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def get_webapp_keyboard() -> InlineKeyboardMarkup:
    """Кнопка «Открыть карту» — открывает Mini App."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Открыть карту", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Команда /start: приветствие и кнопка перехода в карту."""
    text = (
        "Привет, экстремал! Нижний как на ладони. "
        "Находи пролазы или делись своими туторами через Telegraph."
    )

    # Telegram разрешает WebApp-кнопки только с HTTPS.
    if not WEBAPP_URL.lower().startswith("https://"):
        await message.answer(
            text + "\n\n⚠️ Кнопка карты отключена: WEBAPP_URL должен начинаться с https://"
        )
        return

    await message.answer(text, reply_markup=get_webapp_keyboard())


@dp.callback_query(F.data.startswith("approve_"))
async def callback_approve_spot(callback: CallbackQuery) -> None:
    """Админ нажал «Одобрить»: активируем точку и начисляем автору +40 руб."""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Доступ только у администратора.", show_alert=True)
        return

    spot_id = int(callback.data.replace("approve_", ""))
    db = SessionLocal()
    try:
        spot = db.get(Spot, spot_id)
        if not spot:
            await callback.answer("Точка не найдена.", show_alert=True)
            return
        spot.is_active = True
        # Начисляем автору +40 руб
        if spot.author_id:
            user = db.query(User).filter(User.tg_id == spot.author_id).first()
            if user:
                user.balance = (user.balance or 0) + 40
        db.commit()
        await callback.message.edit_text(
            callback.message.text + "\n\n✅ Одобрено. Автору начислено +40 руб."
        )
        await callback.answer("Точка одобрена.")
    finally:
        db.close()


@dp.callback_query(F.data.startswith("reject_"))
async def callback_reject_spot(callback: CallbackQuery) -> None:
    """Админ нажал «Отклонить»: точку можно удалить или оставить неактивной."""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Доступ только у администратора.", show_alert=True)
        return

    spot_id = int(callback.data.replace("reject_", ""))
    db = SessionLocal()
    try:
        spot = db.get(Spot, spot_id)
        if not spot:
            await callback.answer("Точка не найдена.", show_alert=True)
            return
        db.delete(spot)
        db.commit()
        await callback.message.edit_text(
            callback.message.text + "\n\n❌ Отклонено."
        )
        await callback.answer("Точка отклонена.")
    finally:
        db.close()


async def main() -> None:
    """Запуск бота: инициализация БД и polling."""
    init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
