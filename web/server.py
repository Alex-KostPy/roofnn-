"""
FastAPI-сервер для Mini App RoofNN.
Эндпоинты: список точек, покупка доступа к тутору, добавление новой точки.
Уведомление админа при добавлении точки отправляется через Telegram Bot API.
"""
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from urllib.parse import parse_qs, unquote

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

# Загружаем переменные из корня проекта
load_dotenv()

from database import get_db, init_db, Spot, SpotAccess, User, SessionLocal
from models import (
    SpotPublic,
    BuySpotRequest,
    BuySpotResponse,
    AddSpotRequest,
    AddSpotResponse,
    MeRequest,
    MeResponse,
    AddBalanceRequest,
)

BOT_TOKEN = (os.environ.get("BOT_TOKEN", "") or "").strip()
ADMIN_ID = (os.environ.get("ADMIN_ID", "") or "").strip()
SPOT_PRICE = 20

# Варианты опасности на точке (выбор при добавлении)
DANGER_CHOICES = ["камеры", "охрана", "бабки", "замок на клетке", "собаки", "другое"]

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
    Список активных точек для карты и списка.
    С полем author_username (ник того, кто добавил тутор).
    """
    spots = db.query(Spot).filter(Spot.is_active == True).all()
    return [
        SpotPublic(
            id=s.id,
            title=s.title,
            lat=s.lat,
            lon=s.lon,
            author_username=getattr(s, "author_username", None) or None,
            danger=getattr(s, "danger", None) or None,
        )
        for s in spots
    ]


def _ensure_user_from_init_data(db: Session, user_data: dict) -> User:
    """Создать или обновить пользователя из initData, вернуть User."""
    tg_id = user_data["id"]
    user = db.query(User).filter(User.tg_id == tg_id).first()
    if not user:
        user = User(tg_id=tg_id)
        db.add(user)
        db.flush()
    username = user_data.get("username")
    first_name = user_data.get("first_name")
    if username is not None and getattr(user, "username", None) != username:
        user.username = username
    if first_name is not None and getattr(user, "first_name", None) != first_name:
        user.first_name = first_name
    _apply_weekly_refill(user)
    return user


def _apply_weekly_refill(user: User) -> None:
    """Раз в 7 дней начислять +2 бесплатных попытки."""
    now = datetime.now(timezone.utc)
    last = getattr(user, "last_free_refill", None)
    if last is None:
        user.free_attempts = (user.free_attempts or 0) + 2
        user.last_free_refill = now
        return
    try:
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        delta = (now - last).total_seconds()
        if delta >= 7 * 24 * 3600:  # 7 дней
            user.free_attempts = (user.free_attempts or 0) + 2
            user.last_free_refill = now
    except Exception:
        pass


@app.post("/api/me", response_model=MeResponse)
def api_me(body: MeRequest, db: Session = Depends(get_db)):
    """Профиль текущего пользователя: баланс, бесплатные попытки, свои точки."""
    init_data = (body.init_data or "").strip()
    if not validate_init_data(init_data, BOT_TOKEN):
        raise HTTPException(status_code=401, detail="Неверная авторизация")
    user_data = get_tg_user_from_init_data(init_data)
    if not user_data:
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    tg_id = user_data["id"]
    user = _ensure_user_from_init_data(db, user_data)
    db.commit()
    my_spots = db.query(Spot.id).filter(Spot.author_id == tg_id, Spot.is_active == True).all()
    return MeResponse(
        balance=user.balance or 0,
        free_attempts=user.free_attempts or 0,
        username=getattr(user, "username", None),
        first_name=getattr(user, "first_name", None),
        my_spot_ids=[s.id for s in my_spots],
    )


def _grant_spot_access(db: Session, tg_id: int, spot_id: int) -> None:
    """Записать, что пользователь получил доступ к точке (чтобы потом не списывать снова)."""
    exists = db.query(SpotAccess).filter(SpotAccess.tg_id == tg_id, SpotAccess.spot_id == spot_id).first()
    if not exists:
        db.add(SpotAccess(tg_id=tg_id, spot_id=spot_id))


@app.post("/api/buy_spot", response_model=BuySpotResponse)
def buy_spot(body: BuySpotRequest, db: Session = Depends(get_db)):
    """
    Покупка доступа к тутору: 20 руб с баланса или 1 бесплатная попытка.
    Автор смотрит бесплатно. Один раз купил — доступ навсегда, повторно не списывается.
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

    # Только автор или тот, кто уже купил, получают ссылку без списания
    if spot.author_id is not None and int(spot.author_id) == int(tg_id):
        _grant_spot_access(db, tg_id, spot.id)
        db.commit()
        return BuySpotResponse(telegraph_url=spot.telegraph_url)
    access = db.query(SpotAccess).filter(SpotAccess.tg_id == tg_id, SpotAccess.spot_id == spot.id).first()
    if access:
        return BuySpotResponse(telegraph_url=spot.telegraph_url)

    user = _ensure_user_from_init_data(db, user_data)
    free_attempts = user.free_attempts or 0
    balance = user.balance or 0

    if free_attempts > 0:
        user.free_attempts = free_attempts - 1
        _grant_spot_access(db, tg_id, spot.id)
        db.commit()
        return BuySpotResponse(telegraph_url=spot.telegraph_url)
    if balance >= SPOT_PRICE:
        user.balance = balance - SPOT_PRICE
        _grant_spot_access(db, tg_id, spot.id)
        db.commit()
        return BuySpotResponse(telegraph_url=spot.telegraph_url)

    raise HTTPException(
        status_code=402,
        detail="Недостаточно средств. Пополните баланс или используйте бесплатные попытки.",
    )


def _normalize_content_url(url: str) -> str:
    """Нормализует ссылку на туториал (Telegraph, Imgur или любая https)."""
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
    author_display = "Аноним"
    if user_data:
        un = user_data.get("username")
        fn = user_data.get("first_name") or ""
        author_display = f"@{un}" if un else (fn.strip() or "Аноним")

    title = (body.title or "").strip()
    if not title or len(title) > 200:
        raise HTTPException(status_code=400, detail="Название точки: от 1 до 200 символов.")

    telegraph_url = _normalize_content_url(body.telegraph_url)
    if not telegraph_url or not telegraph_url.startswith("https://"):
        raise HTTPException(
            status_code=400,
            detail="Укажите ссылку на туториал (https), например Telegraph, Imgur или другой сервис.",
        )

    danger = (body.danger or "").strip() or None
    if danger and danger not in DANGER_CHOICES:
        danger = "другое"

    spot = Spot(
        title=title,
        lat=body.lat,
        lon=body.lon,
        telegraph_url=telegraph_url,
        price=SPOT_PRICE,
        author_id=tg_id,
        author_username=author_display,
        danger=danger,
        is_active=False,
    )
    db.add(spot)
    db.commit()
    db.refresh(spot)

    # Уведомление админу в боте с кнопками
    if BOT_TOKEN and ADMIN_ID:
        danger_line = f"\nОпасность: {spot.danger}" if getattr(spot, "danger", None) else ""
        text = (
            f"Новая точка на модерацию:\n"
            f"ID: {spot.id}\n"
            f"Название: {spot.title}\n"
            f"Координаты: {spot.lat}, {spot.lon}\n"
            f"Туториал: {spot.telegraph_url}"
            f"{danger_line}"
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
    author_tg_id = spot.author_id
    if author_tg_id is not None:
        author_tg_id = int(author_tg_id)
        user = db.query(User).filter(User.tg_id == author_tg_id).first()
        if not user:
            user = User(tg_id=author_tg_id)
            db.add(user)
            db.flush()
        user.balance = (user.balance or 0) + 40
        db.flush()
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


@app.post("/api/admin/add_balance")
def admin_add_balance(
    body: AddBalanceRequest,
    _: None = Depends(verify_bot_token),
    db: Session = Depends(get_db),
):
    """Начислить баланс пользователю по tg_id (для пополнения). Вызывается ботом или админом."""
    user = db.query(User).filter(User.tg_id == body.tg_id).first()
    if not user:
        user = User(tg_id=body.tg_id)
        db.add(user)
        db.flush()
    user.balance = (user.balance or 0) + body.amount
    db.commit()
    return {"ok": True, "balance": user.balance}


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
