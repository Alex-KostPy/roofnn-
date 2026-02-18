"""
Pydantic-схемы для обмена данными между фронтендом Mini App и бэкендом (FastAPI).
"""
from pydantic import BaseModel, Field


# --- Ответы API ---

class SpotPublic(BaseModel):
    """Точка для карты: только координаты и ID (без Telegraph-ссылки)."""
    id: int
    title: str
    lat: float
    lon: float


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
    init_data: str = Field(..., description="Telegram WebApp initData")


class AddSpotResponse(BaseModel):
    """Ответ после добавления точки (ожидает модерации)."""
    success: bool = True
    message: str = "Точка отправлена на модерацию. После одобрения она появится на карте."
