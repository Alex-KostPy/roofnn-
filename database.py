"""
База данных: SQLAlchemy + SQLite.
Таблицы: Users (пользователи), Spots (точки/крыши).
"""
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.orm import Session, sessionmaker

# Папка проекта — рядом с ней будет лежать roofnn.db
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "roofnn.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"


class Base(DeclarativeBase):
    """Базовый класс для всех моделей."""
    pass


class User(Base):
    """
    Пользователь Telegram.
    balance — баланс в рублях для покупки доступа к туторам.
    free_attempts — бесплатные попытки открыть точку (по умолчанию 2).
    """
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(unique=True, index=True)
    balance: Mapped[float] = mapped_column(default=0.0)
    free_attempts: Mapped[int] = mapped_column(default=2)



class Spot(Base):
    """
    Точка (крыша/пролаз).
    is_active=False пока админ не одобрит — в списке на карте не показывается.
    """
    __tablename__ = "spots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column()
    lat: Mapped[float] = mapped_column()
    lon: Mapped[float] = mapped_column()
    telegraph_url: Mapped[str] = mapped_column()
    price: Mapped[int] = mapped_column(default=20)  # руб за просмотр тутора
    author_id: Mapped[Optional[int]] = mapped_column(nullable=True)  # tg_id автора (не FK)
    is_active: Mapped[bool] = mapped_column(default=False)


# Движок и сессия
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(engine, autocommit=False, autoflush=False)


def init_db() -> None:
    """Создаёт таблицы в БД, если их ещё нет."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    """Генератор сессии БД (для FastAPI dependency)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
