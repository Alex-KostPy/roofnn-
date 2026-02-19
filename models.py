"""
Pydantic-схемы для обмена данными между фронтендом Mini App и бэкендом (FastAPI).
"""
from typing import Optional

from pydantic import BaseModel, Field


# --- Ответы API ---

class SpotPublic(BaseModel):
    """Точка для карты: id, название, координаты, автор, опасность."""
    id: int
    title: str
    lat: float
    lon: float
    author_username: Optional[str] = None
    danger: Optional[str] = None


class MeResponse(BaseModel):
    """Профиль пользователя: баланс, попытки, ник, список ID своих точек."""
    balance: float
    free_attempts: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    my_spot_ids: list[int]


class BuySpotRequest(BaseModel):
    """Запрос на покупку доступа к точке."""
    spot_id: int
    init_data: str = Field(..., description="Telegram WebApp initData для проверки пользователя")


class BuySpotResponse(BaseModel):
    """Ответ после успешной покупки — ссылка на тутор."""
    success: bool = True
    telegraph_url: str


class AddSpotRequest(BaseModel):
    """Добавление новой точки пользователем."""
    title: str
    lat: float
    lon: float
    telegraph_url: str
    danger: Optional[str] = None  # камеры, охрана, бабки, замок на клетке, собаки, другое
    init_data: str = Field(..., description="Telegram WebApp initData")


class AddSpotResponse(BaseModel):
    """Ответ после добавления точки (ожидает модерации)."""
    success: bool = True
    message: str = "Точка отправлена на модерацию. После одобрения она появится на карте."


class MeRequest(BaseModel):
    """Запрос профиля: передаём initData из Telegram."""
    init_data: str = Field(..., description="Telegram WebApp initData")


class AddBalanceRequest(BaseModel):
    """Запрос админа: начислить баланс пользователю по tg_id."""
    tg_id: int
    amount: float = Field(..., gt=0, le=100000)
