"""
RoofNN — Telegram-бот. Приветствие, кнопка «Открыть карту», админ-модерация точек.
Одобрение/отклонение точек идёт через API на Render (там же БД), а не через локальную БД.
"""
import os
import logging
from pathlib import Path
import httpx
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton

from database import init_db

# Важно: load_dotenv по умолчанию НЕ перезаписывает уже заданные переменные окружения.
# Если вы меняете `.env`, а в системе уже есть WEBAPP_URL/BOT_TOKEN/ADMIN_ID,
# бот может продолжать брать старые значения. Поэтому override=True.
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env", override=True)

# ID администратора — только он получает уведомления о новых точках и может одобрять/отклонять
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
BOT_TOKEN = (os.environ.get("BOT_TOKEN", "") or "").strip()
WEBAPP_URL = (os.environ.get("WEBAPP_URL", "https://your-domain.com") or "").strip()
# URL API на Render — бот дергает сюда одобрение/отклонение (БД там)
API_BASE = (os.environ.get("ROOFNN_API_URL", "https://roofnn.onrender.com") or "").strip().rstrip("/")

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
    """Админ нажал «Одобрить»: дергаем API на Render (там БД с точками)."""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Доступ только у администратора.", show_alert=True)
        return

    spot_id = int(callback.data.replace("approve_", ""))
    url = f"{API_BASE}/api/admin/approve_spot"
    headers = {"Authorization": f"Bearer {BOT_TOKEN}"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(url, params={"spot_id": spot_id}, headers=headers)
        if r.status_code == 404:
            await callback.answer("Точка не найдена.", show_alert=True)
            return
        if r.status_code >= 400:
            await callback.answer("Ошибка API. Попробуйте позже.", show_alert=True)
            return
        await callback.message.edit_text(
            callback.message.text + "\n\n✅ Одобрено. Автору начислено +40 руб."
        )
        await callback.answer("Точка одобрена.")
    except Exception as e:
        logger.exception("approve_spot API call failed")
        await callback.answer("Сервер недоступен. Подождите и попробуйте снова.", show_alert=True)


@dp.callback_query(F.data.startswith("reject_"))
async def callback_reject_spot(callback: CallbackQuery) -> None:
    """Админ нажал «Отклонить»: дергаем API на Render."""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Доступ только у администратора.", show_alert=True)
        return

    spot_id = int(callback.data.replace("reject_", ""))
    url = f"{API_BASE}/api/admin/reject_spot"
    headers = {"Authorization": f"Bearer {BOT_TOKEN}"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(url, params={"spot_id": spot_id}, headers=headers)
        if r.status_code == 404:
            await callback.answer("Точка не найдена.", show_alert=True)
            return
        if r.status_code >= 400:
            await callback.answer("Ошибка API. Попробуйте позже.", show_alert=True)
            return
        await callback.message.edit_text(
            callback.message.text + "\n\n❌ Отклонено."
        )
        await callback.answer("Точка отклонена.")
    except Exception as e:
        logger.exception("reject_spot API call failed")
        await callback.answer("Сервер недоступен. Подождите и попробуйте снова.", show_alert=True)


async def main() -> None:
    """Запуск бота: инициализация БД и polling."""
    init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
