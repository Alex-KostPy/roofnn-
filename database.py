"""
База данных: SQLAlchemy + SQLite.
Таблицы: Users (пользователи), Spots (точки/крыши).
"""
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import UniqueConstraint, create_engine, text
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
    username / first_name — для отображения в списке (кто добавил тутор).
    """
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(unique=True, index=True)
    balance: Mapped[float] = mapped_column(default=0.0)
    free_attempts: Mapped[int] = mapped_column(default=2)
    last_free_refill: Mapped[Optional[datetime]] = mapped_column(nullable=True)  # когда последний раз начисляли +2 попытки
    username: Mapped[Optional[str]] = mapped_column(nullable=True)  # @nick в Telegram
    first_name: Mapped[Optional[str]] = mapped_column(nullable=True)


class Spot(Base):
    """
    Точка (крыша/пролаз).
    is_active=False пока админ не одобрит — в списке на карте не показывается.
    author_username — ник автора для отображения (кто сделал тутор).
    """
    __tablename__ = "spots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column()
    lat: Mapped[float] = mapped_column()
    lon: Mapped[float] = mapped_column()
    telegraph_url: Mapped[str] = mapped_column()
    price: Mapped[int] = mapped_column(default=20)  # руб за просмотр тутора
    author_id: Mapped[Optional[int]] = mapped_column(nullable=True)  # tg_id автора (не FK)
    author_username: Mapped[Optional[str]] = mapped_column(nullable=True)  # ник для отображения
    is_active: Mapped[bool] = mapped_column(default=False)


class SpotAccess(Base):
    """Кто уже купил доступ к точке (один раз купил — смотрит бесплатно всегда)."""
    __tablename__ = "spot_access"
    __table_args__ = (UniqueConstraint("tg_id", "spot_id", name="uq_spot_access_tg_spot"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(index=True)
    spot_id: Mapped[int] = mapped_column(index=True)


# Движок и сессия
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(engine, autocommit=False, autoflush=False)


def init_db() -> None:
    """Создаёт таблицы в БД, если их ещё нет. Добавляет новые колонки в существующие таблицы (SQLite)."""
    Base.metadata.create_all(bind=engine)
    # Добавить колонки в существующую БД, если их ещё нет (миграция «на месте» для SQLite)
    for table, column, col_type in [
        ("users", "username", "TEXT"),
        ("users", "first_name", "TEXT"),
        ("users", "last_free_refill", "TIMESTAMP"),
        ("spots", "author_username", "TEXT"),
    ]:
        try:
            with engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                conn.commit()
        except Exception:
            pass  # колонка уже есть
    # Таблица покупок доступа к точкам
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    """Генератор сессии БД (для FastAPI dependency)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
