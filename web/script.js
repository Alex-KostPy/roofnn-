/**
 * RoofNN Mini App — карта крыш Нижнего Новгорода.
 * Аутентификация через Telegram InitData (window.Telegram.WebApp.initData).
 *
 * Важно: из-за ограничений WebView/хостинга (Netlify и т.п.) ESM-importы из CDN
 * могут «ронять» весь скрипт и оставлять чёрный экран. Поэтому здесь без import,
 * максимально совместимый вариант.
 * При клике на маркер — кнопка «Открыть тутор»; после покупки открывается Telegraph.
 */

(() => {
  "use strict";

  // Telegram WebApp API (внутри Telegram). В обычном браузере может быть undefined.
  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  if (tg) {
    tg.ready();
    tg.expand();
  }

  // Если API на другом домене (например, фронт на Netlify, API на Render) — задайте window.ROOFNN_API_BASE в index.html
  const API_BASE = (window.ROOFNN_API_BASE || "").replace(/\/+$/, ""); // без trailing slash
  const apiUrl = (path) => (API_BASE ? `${API_BASE}${path}` : path);

  // Центр Нижнего Новгорода
  const NIZHNY_CENTER = [56.3287, 44.002];
  const DEFAULT_ZOOM = 12;

  let map = null;
  let userLocation = null;
  let addSpotLatLng = null;
  let spots = [];
  const boughtSpots = {}; // spotId -> telegraph_url (после покупки)

  const $spotCard = document.getElementById("spot-card");
  const $spotTitle = document.getElementById("spot-title");
  const $spotCoords = document.getElementById("spot-coords");
  const $btnOpenTutor = document.getElementById("btn-open-tutor");
  const $spotError = document.getElementById("spot-error");
  const $btnGeolocate = document.getElementById("btn-geolocate");
  const $addPanel = document.getElementById("add-spot-panel");
  const $addTitle = document.getElementById("add-title");
  const $addTelegraph = document.getElementById("add-telegraph");
  const $addCoords = document.getElementById("add-coords");
  const $btnAddSpot = document.getElementById("btn-add-spot");
  const $btnCloseAdd = document.getElementById("btn-close-add");
  const $btnShowAdd = document.getElementById("btn-show-add");

  function toast(message) {
    const el = document.createElement("div");
    el.textContent = message;
    el.style.position = "fixed";
    el.style.left = "1rem";
    el.style.top = "1rem";
    el.style.right = "1rem";
    el.style.maxWidth = "28rem";
    el.style.margin = "0 auto";
    el.style.zIndex = "2000";
    el.style.padding = "0.75rem 1rem";
    el.style.background = "rgba(18,18,20,0.92)";
    el.style.border = "1px solid #00ffcc";
    el.style.borderRadius = "10px";
    el.style.boxShadow = "0 0 18px rgba(0,255,204,0.45)";
    el.style.color = "#e4e4e7";
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 4500);
  }

  /**
   * Получить initData для запросов к API (аутентификация от Telegram).
   * На бэкенде проверяется через HMAC-SHA256.
   */
  function getInitData() {
    return (tg && tg.initData) || "";
  }

  /**
   * Загрузка списка активных точек с сервера.
   */
  async function loadSpots() {
    try {
      const res = await fetch(apiUrl("/api/spots"));
      if (!res.ok) throw new Error("Не удалось загрузить точки");
      spots = await res.json();
      return spots;
    } catch (e) {
      console.error("loadSpots", e);
      toast(
        API_BASE
          ? "Не удалось загрузить точки: проверь API (ROOFNN_API_BASE) и CORS."
          : "Не удалось загрузить точки: нет API на этом домене."
      );
      return [];
    }
  }

  /**
   * Покупка доступа к точке: списание 20 руб или 1 бесплатной попытки.
   * Возвращает telegraph_url или бросает ошибку.
   */
  async function buySpot(spotId) {
    const initData = getInitData();
    const res = await fetch(apiUrl("/api/buy_spot"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ spot_id: spotId, init_data: initData }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || "Ошибка покупки");
    }
    return data.telegraph_url;
  }

  /**
   * Отображение маркеров на карте.
   */
  function renderMarkers() {
    if (!map) return;
    // Очищаем старые слои маркеров (кроме тайлов и т.п. — только наши маркеры храним в группе)
    if (window.markersLayer) {
      map.removeLayer(window.markersLayer);
    }
    const layer = L.layerGroup();
    spots.forEach(function (spot) {
      const marker = L.marker([spot.lat, spot.lon])
        .bindPopup("<b>" + escapeHtml(spot.title) + "</b><br>Нажми на карточку внизу, чтобы открыть тутор.");
      marker.spotId = spot.id;
      marker.spotTitle = spot.title;
      marker.on("click", function () {
        selectSpot(spot.id, spot.title, spot.lat, spot.lon);
      });
      layer.addLayer(marker);
    });
    layer.addTo(map);
    window.markersLayer = layer;
  }

  function escapeHtml(s) {
    const div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
  }

  /**
   * Выбор точки: показать карточку и кнопку «Открыть тутор».
   * Если уже куплено — открываем Telegraph; иначе при нажатии — покупка и открытие.
   */
  function selectSpot(id, title, lat, lon) {
    $spotCard.classList.remove("hidden");
    $spotError.classList.add("hidden");
    $spotTitle.textContent = title;
    $spotCoords.textContent = "Координаты: " + lat.toFixed(5) + ", " + lon.toFixed(5);
    $btnOpenTutor.dataset.spotId = String(id);
    $btnOpenTutor.textContent = boughtSpots[id] ? "Открыть тутор" : "Открыть тутор (20 ₽ или 1 бесплатная попытка)";
  }

  async function onOpenTutorClick() {
    const spotId = parseInt($btnOpenTutor.dataset.spotId, 10);
    if (!spotId) return;

    if (boughtSpots[spotId]) {
      window.open(boughtSpots[spotId], "_blank");
      return;
    }

    $spotError.classList.add("hidden");
    $btnOpenTutor.disabled = true;
    try {
      const url = await buySpot(spotId);
      boughtSpots[spotId] = url;
      $btnOpenTutor.textContent = "Открыть тутор";
      window.open(url, "_blank");
    } catch (e) {
      $spotError.textContent = e.message || "Ошибка";
      $spotError.classList.remove("hidden");
    }
    $btnOpenTutor.disabled = false;
  }

  /**
   * Добавление новой точки: сохраняем координаты клика и показываем форму.
   */
  function initMap() {
    if (!window.L) {
      toast("Ошибка: Leaflet не загрузился. Проверь подключение к CDN (unpkg).");
      return;
    }

    map = L.map("map", { center: NIZHNY_CENTER, zoom: DEFAULT_ZOOM });
    L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
      attribution: "&copy; <a href=\"https://www.openstreetmap.org/copyright\">OpenStreetMap</a> &copy; <a href=\"https://carto.com/attributions\">CARTO</a>",
      subdomains: "abcd",
      maxZoom: 20,
    }).addTo(map);

    map.on("click", function (e) {
      if ($addPanel.classList.contains("hidden")) return;
      addSpotLatLng = e.latlng;
      $addCoords.textContent = addSpotLatLng.lat.toFixed(5) + ", " + addSpotLatLng.lng.toFixed(5);
    });

    $btnGeolocate.addEventListener("click", function () {
      if (!navigator.geolocation) {
        alert("Геолокация недоступна в этом браузере.");
        return;
      }
      navigator.geolocation.getCurrentPosition(
        function (pos) {
          userLocation = [pos.coords.latitude, pos.coords.longitude];
          map.setView(userLocation, 15);
          if (window.userMarker) map.removeLayer(window.userMarker);
          window.userMarker = L.marker(userLocation).addTo(map).bindPopup("Вы здесь");
        },
        function () {
          alert("Не удалось определить местоположение.");
        }
      );
    });

    $btnOpenTutor.addEventListener("click", onOpenTutorClick);

    $btnShowAdd.addEventListener("click", function () {
      $addPanel.classList.remove("hidden");
      addSpotLatLng = null;
      $addCoords.textContent = "—";
      $addTitle.value = "";
      $addTelegraph.value = "";
    });

    $btnCloseAdd.addEventListener("click", function () {
      $addPanel.classList.add("hidden");
    });

    $btnAddSpot.addEventListener("click", async function () {
      const title = $addTitle.value.trim();
      const telegraph = $addTelegraph.value.trim();
      if (!title || !telegraph) {
        alert("Заполните название и ссылку на Telegraph.");
        return;
      }
      if (!addSpotLatLng) {
        alert("Кликните на карте, чтобы указать координаты точки.");
        return;
      }
      const initData = getInitData();
      try {
        const res = await fetch(apiUrl("/api/add_spot"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: title,
            lat: addSpotLatLng.lat,
            lon: addSpotLatLng.lng,
            telegraph_url: telegraph,
            init_data: initData,
          }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || "Ошибка отправки");
        alert("Точка отправлена на модерацию. После одобрения она появится на карте.");
        $addPanel.classList.add("hidden");
      } catch (e) {
        alert(e.message || "Ошибка при добавлении точки.");
      }
    });

    loadSpots().then(renderMarkers);
  }

  initMap();
})();
