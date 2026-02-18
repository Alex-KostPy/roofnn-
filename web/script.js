/**
 * RoofNN Mini App — карта крыш Нижнего Новгорода.
 * Профиль (баланс, пополнение), список точек с автором, свои туторы — бесплатно.
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
  let profile = { balance: 0, free_attempts: 0, my_spot_ids: [] };
  const boughtSpots = {};

  const $mapEl = document.getElementById("map");
  const $listSection = document.getElementById("list-section");
  const $profileSection = document.getElementById("profile-section");
  const $addSection = document.getElementById("add-section");
  const $navMap = document.getElementById("nav-map");
  const $navList = document.getElementById("nav-list");
  const $navAdd = document.getElementById("nav-add");
  const $navProfile = document.getElementById("nav-profile");
  const $spotCard = document.getElementById("spot-card");
  const $spotTitle = document.getElementById("spot-title");
  const $spotAuthor = document.getElementById("spot-author");
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
  const $spotList = document.getElementById("spot-list");
  const $profileBalance = document.getElementById("profile-balance");
  const $profileAttempts = document.getElementById("profile-attempts");
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

  async function loadProfile() {
    const initData = getInitData();
    if (!initData) return;
    try {
      const res = await fetch(apiUrl("/api/me"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ init_data: initData }),
      });
      if (!res.ok) return;
      profile = await res.json();
      if ($profileBalance) $profileBalance.textContent = profile.balance;
      if ($profileAttempts) $profileAttempts.textContent = profile.free_attempts;
    } catch (e) {
      console.error("loadProfile", e);
    }
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

  function escapeHtml(s) {
    const div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
  }

  function isMySpot(spotId) {
    return profile.my_spot_ids && profile.my_spot_ids.indexOf(spotId) !== -1;
  }

  function selectSpot(spot) {
    const id = spot.id;
    const isMine = isMySpot(id);
    $spotCard.classList.remove("hidden");
    $spotError.classList.add("hidden");
    $spotError.textContent = "";
    $spotTitle.textContent = spot.title;
    $spotAuthor.textContent = spot.author_username ? "Туториал от " + spot.author_username : "";
    $spotAuthor.classList.toggle("hidden", !spot.author_username);
    $spotCoords.textContent = "Координаты: " + spot.lat.toFixed(5) + ", " + spot.lon.toFixed(5);
    $btnOpenTutor.dataset.spotId = String(id);
    if (boughtSpots[id]) {
      $btnOpenTutor.textContent = "Открыть туториал на Telegraph";
    } else if (isMine) {
      $btnOpenTutor.textContent = "Открыть свой тутор (бесплатно)";
    } else {
      $btnOpenTutor.textContent = "Открыть туториал (20 ₽ или 1 бесплатная попытка)";
    }
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

  function renderMarkers() {
    if (!map) return;
    if (window.markersLayer) map.removeLayer(window.markersLayer);
    const layer = L.layerGroup();
    spots.forEach((spot) => {
      const authorLine = spot.author_username ? " · " + spot.author_username : "";
      const marker = L.marker([spot.lat, spot.lon]).bindPopup(
        "<b>" + escapeHtml(spot.title) + "</b>" + escapeHtml(authorLine) + "<br>Нажми на карточку внизу."
      );
      marker.on("click", () => selectSpot(spot));
      layer.addLayer(marker);
    });
    layer.addTo(map);
    window.markersLayer = layer;
  }

  function renderList() {
    if (!$spotList) return;
    $spotList.innerHTML = "";
    spots.forEach((spot) => {
      const li = document.createElement("li");
      li.className = "spot-list__item";
      const isMine = isMySpot(spot.id);
      const author = spot.author_username ? " · " + spot.author_username : "";
      li.innerHTML =
        "<span class=\"spot-list__title\">" + escapeHtml(spot.title) + "</span>" +
        (author ? "<span class=\"spot-list__author\">" + escapeHtml(spot.author_username) + "</span>" : "") +
        (isMine ? "<span class=\"spot-list__badge\">Ваш</span>" : "");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn--small btn--primary";
      btn.textContent = isMine ? "Открыть" : "Открыть (20 ₽)";
      btn.addEventListener("click", () => selectSpot(spot));
      li.appendChild(btn);
      $spotList.appendChild(li);
    });
  }

  function showView(view) {
    const views = ["map", "list", "add", "profile"];
    views.forEach((v) => {
      const isActive = v === view;
      if (v === "map") {
        $mapEl.classList.toggle("hidden", !isActive);
        if (map && isActive) map.invalidateSize();
      }
      if (v === "list") $listSection.classList.toggle("hidden", !isActive);
      if (v === "add") $addSection.classList.toggle("hidden", !isActive);
      if (v === "profile") $profileSection.classList.toggle("hidden", !isActive);
      const nav = document.getElementById("nav-" + (v === "map" ? "map" : v === "list" ? "list" : v === "add" ? "add" : "profile"));
      if (nav) nav.classList.toggle("nav__btn--active", isActive);
    });
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
    $navList.addEventListener("click", () => showView("list"));
    $navAdd.addEventListener("click", () => showView("add"));
    $navProfile.addEventListener("click", () => {
      showView("profile");
      $profileBalance.textContent = profile.balance;
      $profileAttempts.textContent = profile.free_attempts;
    });

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
        $addSpotError.textContent = "Выберите место на карте: «Карта» → клик по карте → снова «Добавить».";
        $addSpotError.classList.remove("hidden");
        return;
      }

      const initData = getInitData();
      if (!initData) {
        showToast("Откройте приложение из бота в Telegram.");
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
        showToast("Точка отправлена на модерацию.");
        $addTitle.value = "";
        $addTelegraph.value = "";
        $addCoords.textContent = "— выберите место на карте";
        addSpotLatLng = null;
        showView("map");
        loadProfile();
      } catch (e) {
        $addSpotError.textContent = e.message || "Ошибка при отправке.";
        $addSpotError.classList.remove("hidden");
      }
      $btnAddSpot.disabled = false;
    });

    Promise.all([loadProfile(), loadSpots()]).then(() => {
      renderMarkers();
      renderList();
      $profileBalance.textContent = profile.balance;
      $profileAttempts.textContent = profile.free_attempts;
    });
  }

  initMap();
})();
