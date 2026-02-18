# RoofNN — Путеводитель по крышам Нижнего Новгорода

Telegram-бот с Mini App: карта точек (крыш/пролазов), покупка доступа к туторам через Telegraph, модерация новых точек админом.

## Структура проекта

- **main.py** — бот на aiogram 3.x: команда `/start`, кнопка «Открыть карту», админ-кнопки «Одобрить (+40 руб)» / «Отклонить».
- **database.py** — SQLAlchemy + SQLite: таблицы `Users` (tg_id, balance, free_attempts), `Spots` (title, lat, lon, telegraph_url, price, author_id, is_active).
- **models.py** — Pydantic-схемы для API.
- **web/** — Mini App:
  - **server.py** — FastAPI: `GET /api/spots`, `POST /api/buy_spot`, `POST /api/add_spot`; раздача `index.html`, `style.css`, `script.js`.
  - **index.html** — карта Leaflet (тёмная тема CartoDB).
  - **style.css** — неоновый стиль (фон #0a0a0b, акцент #00ffcc).
  - **script.js** — логика карты, маркеры, покупка/добавление точки; аутентификация через Telegram InitData (@twa-dev/sdk).

## Установка и запуск

1. Клонируйте репозиторий и перейдите в каталог проекта.

2. Создайте виртуальное окружение и установите зависимости:

   ```bash
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Скопируйте `.env.example` в `.env` и заполните:

   - `BOT_TOKEN` — токен от [@BotFather](https://t.me/BotFather).
   - `ADMIN_ID` — ваш Telegram user ID (например, от [@userinfobot](https://t.me/userinfobot)).
   - `WEBAPP_URL` — URL, на котором открывается Mini App (после деплоя или через ngrok).

4. Запуск бота (из корня проекта):

   ```bash
   python main.py
   ```

5. Запуск веб-сервера Mini App (из корня проекта):

   ```bash
   uvicorn web.server:app --reload --host 0.0.0.0 --port 8000
   ```

   Карта будет доступна по адресу `http://localhost:8000/`. Для теста в Telegram Mini App укажите в BotFather URL вашего сервера (например, через ngrok: `https://xxxx.ngrok.io`).

## Как это работает

- Пользователь нажимает «Открыть карту» в боте — открывается Mini App с картой Нижнего Новгорода.
- На карте отображаются одобренные точки (без ссылок на Telegraph).
- При клике на маркер появляется карточка с кнопкой «Открыть тутор». При нажатии списывается 20 ₽ или 1 бесплатная попытка (у новых пользователей 2 попытки), затем открывается ссылка на Telegraph.
- Кнопка «+» открывает форму добавления точки: название, ссылка на Telegraph, клик по карте для координат. Точка сохраняется с `is_active=False`; админу в боте приходит уведомление с кнопками «Одобрить (+40 руб)» и «Отклонить».
- Аутентификация в API: фронт передаёт `init_data` из Telegram Web App (через @twa-dev/sdk); бэкенд проверяет подпись HMAC-SHA256.

## Язык

Все тексты интерфейса и комментарии в коде — на русском языке.
