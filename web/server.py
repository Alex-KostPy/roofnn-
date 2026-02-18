"""
FastAPI-сервер для Mini App RoofNN.
Эндпоинты: список точек, покупка доступа к тутору, добавление новой точки.
Уведомление админа при добавлении точки отправляется через Telegram Bot API.
"""
import hashlib
import hmac
import json
import os
from urllib.parse import parse_qs, unquote

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

# Загружаем переменные из корня проекта
load_dotenv()

from database import get_db, init_db, Spot, User, SessionLocal
from models import SpotPublic, BuySpotRequest, BuySpotResponse, AddSpotRequest, AddSpotResponse

BOT_TOKEN = (os.environ.get("BOT_TOKEN", "") or "").strip()
ADMIN_ID = (os.environ.get("ADMIN_ID", "") or "").strip()
SPOT_PRICE = 20

app = FastAPI(title="RoofNN API", description="API для Mini App «Путеводитель по крышам НН»")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def validate_init_data(init_data: str, bot_token: str) -> bool:
    """
    Проверка подлинности initData от Telegram WebApp.
    Секретный ключ = HMAC-SHA256("WebAppData", bot_token).
    """
    if not init_data or not bot_token:
        return False
    try:
        parsed = parse_qs(init_data, keep_blank_values=True)
        # parse_qs возвращает списки; берём первые значения
        vals = {k: unquote(v[0]) for k, v in parsed.items()}
        received_hash = vals.pop("hash", None)
        if not received_hash:
            return False
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(vals.items()))
        secret_key = hmac.new(
            b"WebAppData",
            bot_token.encode(),
            hashlib.sha256,
        ).digest()
        computed_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(computed_hash, received_hash)
    except Exception:
        return False


def get_tg_user_from_init_data(init_data: str) -> dict | None:
    """Из initData извлекаем объект user (с полем id — tg_id)."""
    try:
        parsed = parse_qs(init_data, keep_blank_values=True)
        user_str = parsed.get("user", [None])[0]
        if not user_str:
            return None
        return json.loads(unquote(user_str))
    except Exception:
        return None


@app.on_event("startup")
def startup():
    init_db()


# --- Эндпоинты ---

@app.get("/api/health")
def health():
    """Проверка доступности API (для холодного старта Render и т.п.)."""
    return {"status": "ok"}


@app.get("/api/spots", response_model=list[SpotPublic])
def list_spots(db: Session = Depends(get_db)):
    """
    Список активных точек для карты.
    Без telegraph_url — только id, title, lat, lon.
    """
    spots = db.query(Spot).filter(Spot.is_active == True).all()
    return [SpotPublic(id=s.id, title=s.title, lat=s.lat, lon=s.lon) for s in spots]


@app.post("/api/buy_spot", response_model=BuySpotResponse)
def buy_spot(body: BuySpotRequest, db: Session = Depends(get_db)):
    """
    Покупка доступа к тутору: 20 руб с баланса или 1 бесплатная попытка.
    Возвращает telegraph_url для открытия.
    """
    if not validate_init_data(body.init_data, BOT_TOKEN):
        raise HTTPException(status_code=401, detail="Неверные данные авторизации")

    user_data = get_tg_user_from_init_data(body.init_data)
    if not user_data:
        raise HTTPException(status_code=401, detail="Пользователь не найден в initData")

    tg_id = user_data["id"]
    spot = db.query(Spot).filter(Spot.id == body.spot_id, Spot.is_active == True).first()
    if not spot:
        raise HTTPException(status_code=404, detail="Точка не найдена")

    user = db.query(User).filter(User.tg_id == tg_id).first()
    if not user:
        user = User(tg_id=tg_id)
        db.add(user)
        db.flush()

    # Сначала бесплатные попытки, потом баланс
    if user.free_attempts and user.free_attempts > 0:
        user.free_attempts -= 1
        db.commit()
        return BuySpotResponse(telegraph_url=spot.telegraph_url)
    if (user.balance or 0) >= SPOT_PRICE:
        user.balance -= SPOT_PRICE
        db.commit()
        return BuySpotResponse(telegraph_url=spot.telegraph_url)

    raise HTTPException(
        status_code=402,
        detail="Недостаточно средств. Пополните баланс или используйте бесплатные попытки.",
    )


def _normalize_telegraph_url(url: str) -> str:
    """Приводит ссылку на Telegraph к виду https://telegra.ph/..."""
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


@app.post("/api/add_spot", response_model=AddSpotResponse)
def add_spot(body: AddSpotRequest, db: Session = Depends(get_db)):
    """
    Добавить новую точку. Сохраняется с is_active=False.
    Админу в Telegram уходит уведомление с кнопками «Одобрить» / «Отклонить».
    """
    init_data = (body.init_data or "").strip()
    if not init_data:
        raise HTTPException(
            status_code=401,
            detail="Откройте приложение из бота в Telegram — без этого нельзя добавить точку.",
        )
    if not validate_init_data(init_data, BOT_TOKEN):
        raise HTTPException(
            status_code=401,
            detail="Неверная авторизация. Откройте карту из бота в Telegram и попробуйте снова.",
        )

    user_data = get_tg_user_from_init_data(init_data)
    tg_id = user_data["id"] if user_data else None

    title = (body.title or "").strip()
    if not title or len(title) > 200:
        raise HTTPException(status_code=400, detail="Название точки: от 1 до 200 символов.")

    telegraph_url = _normalize_telegraph_url(body.telegraph_url)
    if not telegraph_url or "telegra.ph" not in telegraph_url:
        raise HTTPException(
            status_code=400,
            detail="Укажите ссылку на статью в Telegraph (например https://telegra.ph/...)",
        )

    spot = Spot(
        title=title,
        lat=body.lat,
        lon=body.lon,
        telegraph_url=telegraph_url,
        price=SPOT_PRICE,
        author_id=tg_id,
        is_active=False,
    )
    db.add(spot)
    db.commit()
    db.refresh(spot)

    # Уведомление админу в боте с кнопками
    if BOT_TOKEN and ADMIN_ID:
        text = (
            f"Новая точка на модерацию:\n"
            f"ID: {spot.id}\n"
            f"Название: {spot.title}\n"
            f"Координаты: {spot.lat}, {spot.lon}\n"
            f"Telegraph: {spot.telegraph_url}"
        )
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "Одобрить (+40 руб)", "callback_data": f"approve_{spot.id}"},
                    {"text": "Отклонить", "callback_data": f"reject_{spot.id}"},
                ]
            ]
        }
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        with httpx.Client() as client:
            client.post(
                url,
                json={
                    "chat_id": int(ADMIN_ID),
                    "text": text,
                    "reply_markup": keyboard,
                },
                timeout=10.0,
            )

    return AddSpotResponse()


# --- Админ: одобрить/отклонить точку (вызывает бот, БД на Render) ---

def verify_bot_token(authorization: str = Header(None)) -> None:
    """Проверка, что запрос от бота: Authorization: Bearer <BOT_TOKEN>."""
    if not BOT_TOKEN:
        raise HTTPException(status_code=503, detail="Сервер не настроен")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Требуется авторизация бота")
    token = authorization[7:].strip()
    if token != BOT_TOKEN:
        raise HTTPException(status_code=403, detail="Неверный токен")


@app.post("/api/admin/approve_spot")
def admin_approve_spot(
    spot_id: int = Query(..., description="ID точки"),
    _: None = Depends(verify_bot_token),
    db: Session = Depends(get_db),
):
    """Одобрить точку: is_active=True, автору +40 руб. Вызывается ботом при нажатии «Одобрить»."""
    spot = db.query(Spot).filter(Spot.id == spot_id).first()
    if not spot:
        raise HTTPException(status_code=404, detail="Точка не найдена")
    spot.is_active = True
    if spot.author_id:
        user = db.query(User).filter(User.tg_id == spot.author_id).first()
        if user:
            user.balance = (user.balance or 0) + 40
    db.commit()
    return {"ok": True, "message": "Одобрено"}


@app.post("/api/admin/reject_spot")
def admin_reject_spot(
    spot_id: int = Query(..., description="ID точки"),
    _: None = Depends(verify_bot_token),
    db: Session = Depends(get_db),
):
    """Отклонить точку: удалить из БД. Вызывается ботом при нажатии «Отклонить»."""
    spot = db.query(Spot).filter(Spot.id == spot_id).first()
    if not spot:
        raise HTTPException(status_code=404, detail="Точка не найдена")
    db.delete(spot)
    db.commit()
    return {"ok": True, "message": "Отклонено"}


# --- Раздача статики Mini App (HTML, CSS, JS) ---

from fastapi.responses import FileResponse

WEB_DIR = os.path.dirname(__file__)


def _send_file(name: str):
    path = os.path.join(WEB_DIR, name)
    if os.path.isfile(path):
        return FileResponse(path)
    raise HTTPException(status_code=404, detail=f"{name} not found")


@app.get("/")
def index():
    """Главная страница — карта Mini App."""
    return _send_file("index.html")


@app.get("/style.css")
def style_css():
    return _send_file("style.css")


@app.get("/script.js")
def script_js():
    return _send_file("script.js")
