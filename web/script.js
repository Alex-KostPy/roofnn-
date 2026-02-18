/**
 * RoofNN Mini App — карта крыш Нижнего Новгорода.
 * Туториалы хранятся в Telegraph; открытие — по кнопке после списания 20 ₽ или 1 бесплатной попытки.
 */
(() => {
  "use strict";

  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  if (tg) {
    tg.ready();
    tg.expand();
  }

  const API_BASE = (window.ROOFNN_API_BASE || "").replace(/\/+$/, "");
  const apiUrl = (path) => (API_BASE ? `${API_BASE}${path}` : path);

  const NIZHNY_CENTER = [56.3287, 44.002];
  const DEFAULT_ZOOM = 12;

  let map = null;
  let addSpotLatLng = null;
  let spots = [];
  const boughtSpots = {};

  const $header = document.querySelector(".header");
  const $main = document.querySelector(".main");
  const $mapEl = document.getElementById("map");
  const $addSection = document.getElementById("add-section");
  const $navMap = document.getElementById("nav-map");
  const $navAdd = document.getElementById("nav-add");
  const $spotCard = document.getElementById("spot-card");
  const $spotTitle = document.getElementById("spot-title");
  const $spotCoords = document.getElementById("spot-coords");
  const $btnOpenTutor = document.getElementById("btn-open-tutor");
  const $spotError = document.getElementById("spot-error");
  const $btnGeolocate = document.getElementById("btn-geolocate");
  const $addTitle = document.getElementById("add-title");
  const $addTelegraph = document.getElementById("add-telegraph");
  const $addCoords = document.getElementById("add-coords");
  const $btnAddSpot = document.getElementById("btn-add-spot");
  const $btnCloseAdd = document.getElementById("btn-close-add");
  const $addSpotError = document.getElementById("add-spot-error");
  const $toast = document.getElementById("toast");

  function showToast(message) {
    if (!$toast) return;
    $toast.textContent = message;
    $toast.classList.remove("hidden");
    setTimeout(() => $toast.classList.add("hidden"), 4000);
  }

  function getInitData() {
    return (tg && tg.initData) || "";
  }

  async function loadSpots(retriesLeft = 1) {
    try {
      const res = await fetch(apiUrl("/api/spots"));
      if (!res.ok) throw new Error("Сервер вернул ошибку");
      spots = await res.json();
      return spots;
    } catch (e) {
      console.error("loadSpots", e);
      if (retriesLeft > 0) {
        showToast("Сервер просыпается, подождите…");
        await new Promise((r) => setTimeout(r, 3000));
        return loadSpots(retriesLeft - 1);
      }
      showToast("Не удалось загрузить точки. Откройте приложение через минуту.");
      return [];
    }
  }

  async function buySpot(spotId) {
    const initData = getInitData();
    const res = await fetch(apiUrl("/api/buy_spot"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ spot_id: spotId, init_data: initData }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Ошибка покупки");
    return data.telegraph_url;
  }

  function renderMarkers() {
    if (!map) return;
    if (window.markersLayer) map.removeLayer(window.markersLayer);
    const layer = L.layerGroup();
    spots.forEach((spot) => {
      const marker = L.marker([spot.lat, spot.lon]).bindPopup(
        "<b>" + escapeHtml(spot.title) + "</b><br>Нажми на карточку внизу, чтобы открыть туториал на Telegraph."
      );
      marker.on("click", () => selectSpot(spot.id, spot.title, spot.lat, spot.lon));
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

  function selectSpot(id, title, lat, lon) {
    $spotCard.classList.remove("hidden");
    $spotError.classList.add("hidden");
    $spotError.textContent = "";
    $spotTitle.textContent = title;
    $spotCoords.textContent = "Координаты: " + lat.toFixed(5) + ", " + lon.toFixed(5);
    $btnOpenTutor.dataset.spotId = String(id);
    $btnOpenTutor.textContent = boughtSpots[id]
      ? "Открыть туториал на Telegraph"
      : "Открыть туториал (20 ₽ или 1 бесплатная попытка)";
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
      $btnOpenTutor.textContent = "Открыть туториал на Telegraph";
      window.open(url, "_blank");
    } catch (e) {
      $spotError.textContent = e.message || "Ошибка";
      $spotError.classList.remove("hidden");
    }
    $btnOpenTutor.disabled = false;
  }

  function showView(view) {
    const isMap = view === "map";
    $addSection.classList.toggle("hidden", isMap);
    $mapEl.classList.toggle("hidden", !isMap);
    $navMap.classList.toggle("nav__btn--active", isMap);
    $navAdd.classList.toggle("nav__btn--active", !isMap);
    if (map && isMap) map.invalidateSize();
  }

  function initMap() {
    if (!window.L) {
      showToast("Ошибка загрузки карты. Проверьте интернет.");
      return;
    }

    map = L.map("map", { center: NIZHNY_CENTER, zoom: DEFAULT_ZOOM });
    L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
      attribution: "&copy; OpenStreetMap &copy; CARTO",
      subdomains: "abcd",
      maxZoom: 20,
    }).addTo(map);

    map.on("click", (e) => {
      addSpotLatLng = e.latlng;
      $addCoords.textContent = addSpotLatLng.lat.toFixed(5) + ", " + addSpotLatLng.lng.toFixed(5);
    });

    $btnGeolocate.addEventListener("click", () => {
      if (!navigator.geolocation) {
        showToast("Геолокация недоступна.");
        return;
      }
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          const latlng = [pos.coords.latitude, pos.coords.longitude];
          map.setView(latlng, 15);
          if (window.userMarker) map.removeLayer(window.userMarker);
          window.userMarker = L.marker(latlng).addTo(map).bindPopup("Вы здесь");
        },
        () => showToast("Не удалось определить местоположение.")
      );
    });

    $btnOpenTutor.addEventListener("click", onOpenTutorClick);

    $navMap.addEventListener("click", () => showView("map"));
    $navAdd.addEventListener("click", () => showView("add"));

    $btnCloseAdd.addEventListener("click", () => showView("map"));

    $btnAddSpot.addEventListener("click", async () => {
      const title = $addTitle.value.trim();
      let telegraph = $addTelegraph.value.trim();
      $addSpotError.classList.add("hidden");
      $addSpotError.textContent = "";

      if (!title) {
        $addSpotError.textContent = "Введите название точки.";
        $addSpotError.classList.remove("hidden");
        return;
      }
      if (!telegraph) {
        $addSpotError.textContent = "Вставьте ссылку на туториал в Telegraph.";
        $addSpotError.classList.remove("hidden");
        return;
      }
      if (!telegraph.startsWith("http")) telegraph = "https://" + telegraph;
      if (!telegraph.includes("telegra.ph")) {
        $addSpotError.textContent = "Ссылка должна вести на telegra.ph (Telegraph).";
        $addSpotError.classList.remove("hidden");
        return;
      }
      if (!addSpotLatLng) {
        $addSpotError.textContent = "Выберите место на карте: переключитесь на «Карта», нажмите на карту, затем снова «Добавить точку».";
        $addSpotError.classList.remove("hidden");
        return;
      }

      const initData = getInitData();
      if (!initData) {
        showToast("Откройте приложение из бота в Telegram — так можно добавлять точки.");
        return;
      }

      $btnAddSpot.disabled = true;
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
        showToast("Точка отправлена на модерацию. После одобрения появится на карте.");
        $addTitle.value = "";
        $addTelegraph.value = "";
        $addCoords.textContent = "— выберите место на карте";
        addSpotLatLng = null;
        showView("map");
      } catch (e) {
        $addSpotError.textContent = e.message || "Ошибка при отправке.";
        $addSpotError.classList.remove("hidden");
      }
      $btnAddSpot.disabled = false;
    });

    loadSpots().then(renderMarkers);
  }

  initMap();
})();
