"use strict";

const state = {
  browserAk: null,
  page: 0,
  hasNext: false,
  city: "",
  query: "",
  map: null,
  panorama: null,
  panoramaService: null,
  permittedUids: new Set(),
  mapReady: false,
  busy: false,
  panoramaBusy: false,
};

const elements = {
  city: document.getElementById("city-input"),
  query: document.getElementById("query-input"),
  search: document.getElementById("search-button"),
  previous: document.getElementById("previous-page"),
  next: document.getElementById("next-page"),
  pageStatus: document.getElementById("page-status"),
  summary: document.getElementById("result-summary"),
  list: document.getElementById("results-list"),
  notice: document.getElementById("notice"),
  configuration: document.getElementById("configuration-status"),
  mapStatus: document.getElementById("map-status"),
  panoramaStatus: document.getElementById("panorama-status"),
  selectedPlace: document.getElementById("selected-place"),
};

function setNotice(message, tone = "") {
  elements.notice.textContent = message;
  if (tone) {
    elements.notice.dataset.tone = tone;
  } else {
    delete elements.notice.dataset.tone;
  }
}

function updateControls() {
  elements.search.disabled = state.busy;
  elements.previous.disabled = state.busy || state.page <= 0;
  elements.next.disabled = state.busy || !state.hasNext;
  elements.pageStatus.textContent = `第 ${state.page + 1} 页`;
}

async function requestJson(path, options = {}) {
  const response = await fetch(path, {
    cache: "no-store",
    credentials: "same-origin",
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || "本地服务未能完成请求。");
  }
  return payload;
}

function hasBaiduMapSdk() {
  return Boolean(
    window.BMap &&
      typeof window.BMap.Map === "function" &&
      typeof window.BMap.Point === "function" &&
      typeof window.BMap.Marker === "function"
  );
}

function hasBaiduPanoramaSdk() {
  return Boolean(
    window.BMap &&
      typeof window.BMap.Panorama === "function" &&
      typeof window.BMap.PanoramaService === "function"
  );
}

function loadBaiduMaps(browserAk) {
  if (hasBaiduMapSdk()) {
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    const callbackName = `__baiduMapReady_${Date.now()}_${Math.random()
      .toString(36)
      .slice(2)}`;
    const script = document.createElement("script");
    const url = new URL("https://api.map.baidu.com/api");
    let settled = false;
    let timeoutId = 0;

    const finish = (error) => {
      if (settled) {
        return;
      }
      settled = true;
      window.clearTimeout(timeoutId);
      delete window[callbackName];
      if (error) {
        reject(error);
      } else if (hasBaiduMapSdk()) {
        resolve();
      } else {
        reject(
          new Error(
            "官方 JavaScript API 未完成初始化。请检查 Browser AK 的 JavaScript API 服务和 Referer 白名单。"
          )
        );
      }
    };

    const waitForSdk = () => {
      if (settled) {
        return;
      }
      if (hasBaiduMapSdk()) {
        finish();
        return;
      }
      window.setTimeout(waitForSdk, 50);
    };

    url.searchParams.set("v", "3.0");
    url.searchParams.set("ak", browserAk);
    url.searchParams.set("s", "1");
    url.searchParams.set("callback", callbackName);
    script.src = url.toString();
    script.async = true;
    script.onload = () => {
      if (hasBaiduMapSdk()) {
        finish();
      }
    };
    script.onerror = () => finish(new Error("无法加载官方 JavaScript API。"));
    window[callbackName] = waitForSdk;
    timeoutId = window.setTimeout(
      () =>
        finish(
          new Error(
            "官方 JavaScript API 未完成初始化。请检查 Browser AK 的 JavaScript API 服务和 Referer 白名单。"
          )
        ),
      15000
    );
    document.head.appendChild(script);
    waitForSdk();
  });
}

async function initializeMaps() {
  if (!state.browserAk) {
    elements.mapStatus.textContent = "Browser AK 未配置。";
    elements.panoramaStatus.textContent = "Browser AK 未配置。";
    return;
  }
  try {
    await loadBaiduMaps(state.browserAk);
    const initialPoint = new window.BMap.Point(116.404, 39.915);
    state.map = new window.BMap.Map("map");
    state.map.centerAndZoom(initialPoint, 5);
    state.map.enableScrollWheelZoom(true);
    state.mapReady = true;
    elements.mapStatus.textContent = "官方地图已就绪。";
    elements.panoramaStatus.textContent = "选择一个地点后请求官方全景（需要高级权限）。";
  } catch (error) {
    const message = error instanceof Error ? error.message : "官方地图初始化失败。";
    elements.mapStatus.textContent = message;
    elements.panoramaStatus.textContent = "官方全景不可用。请检查 Browser AK、Referer 白名单和全景高级权限。";
  }
}

function createResultItem(place) {
  const item = document.createElement("li");
  item.className = "result-item";
  const text = document.createElement("div");
  const name = document.createElement("p");
  name.className = "result-name";
  name.textContent = place.name;
  const address = document.createElement("p");
  address.className = "result-address";
  address.textContent = place.address || "官方地点结果未提供地址";
  text.append(name, address);

  const select = document.createElement("button");
  select.type = "button";
  select.textContent = "查看全景";
  select.addEventListener("click", () => selectPlace(place));
  item.append(text, select);
  return item;
}

function renderResults(data) {
  elements.list.replaceChildren();
  if (!data.results.length) {
    const empty = document.createElement("li");
    empty.className = "empty-row";
    empty.textContent = "本页没有可展示的官方地点结果。";
    elements.list.appendChild(empty);
  } else {
    data.results.forEach((place) => elements.list.appendChild(createResultItem(place)));
  }
  const total = Number.isInteger(data.total) ? `官方返回 ${data.total} 条` : "官方结果";
  elements.summary.textContent = `${total}；本工具每次查询最多显示 100 条。`;
  state.hasNext = Boolean(data.has_next);
  updateControls();
}

async function search(page) {
  const city = elements.city.value.trim();
  const query = elements.query.value.trim();
  if (!city || !query) {
    setNotice("请填写城市和关键词。", "error");
    return;
  }
  state.busy = true;
  updateControls();
  setNotice("正在请求一页官方地点结果。", "");
  try {
    const data = await requestJson("/api/search", {
      method: "POST",
      body: JSON.stringify({ city, query, page }),
    });
    state.city = city;
    state.query = query;
    state.page = data.page;
    renderResults(data);
    const remaining = data.usage?.place_remaining;
    const suffix = Number.isInteger(remaining) ? ` 本地地点预算剩余 ${remaining} 次。` : "";
    setNotice("已加载官方地点结果。" + suffix, "success");
  } catch (error) {
    const message = error instanceof Error ? error.message : "地点检索失败。";
    setNotice(message, "error");
  } finally {
    state.busy = false;
    updateControls();
  }
}

function showPlaceOnMap(place) {
  if (!state.mapReady || !state.map) {
    return;
  }
  const point = new window.BMap.Point(place.location.lng, place.location.lat);
  state.map.clearOverlays();
  state.map.addOverlay(new window.BMap.Marker(point));
  state.map.centerAndZoom(point, 17);
}

function setPanoramaButtonsDisabled(disabled) {
  elements.list.querySelectorAll("button").forEach((button) => {
    button.disabled = disabled;
  });
}

function initializePanorama() {
  if (state.panorama && state.panoramaService) {
    return true;
  }
  if (!hasBaiduPanoramaSdk()) {
    elements.panoramaStatus.textContent =
      "当前 Browser AK 未提供可用的官方全景能力。请确认高级权限。";
    return false;
  }
  try {
    const panorama = new window.BMap.Panorama("panorama", {
      navigationControl: true,
      linksControl: true,
      albumsControl: false,
    });
    const panoramaService = new window.BMap.PanoramaService();
    state.panorama = panorama;
    state.panoramaService = panoramaService;
    return true;
  } catch (error) {
    const message = error instanceof Error ? error.message : "官方全景初始化失败。";
    elements.panoramaStatus.textContent = message;
    return false;
  }
}

function getPanoramaByPoiId(uid) {
  return new Promise((resolve, reject) => {
    let finished = false;
    const timeoutId = window.setTimeout(() => {
      if (!finished) {
        finished = true;
        resolve(null);
      }
    }, 15000);
    try {
      state.panoramaService.getPanoramaByPOIId(uid, (data) => {
        if (finished) {
          return;
        }
        finished = true;
        window.clearTimeout(timeoutId);
        resolve(data || null);
      });
    } catch (error) {
      window.clearTimeout(timeoutId);
      reject(error);
    }
  });
}

async function selectPlace(place) {
  if (state.panoramaBusy) {
    return;
  }
  elements.selectedPlace.textContent = place.name;
  showPlaceOnMap(place);
  if (!state.mapReady) {
    elements.panoramaStatus.textContent = "官方地图尚不可用。请检查 Browser AK 和 Referer 白名单。";
    return;
  }
  if (!initializePanorama()) {
    return;
  }
  state.panoramaBusy = true;
  setPanoramaButtonsDisabled(true);
  try {
    if (!state.permittedUids.has(place.uid)) {
      const permit = await requestJson("/api/panorama-permit", {
        method: "POST",
        body: JSON.stringify({ uid: place.uid }),
      });
      state.permittedUids.add(place.uid);
      const remaining = permit.usage?.panorama_remaining;
      elements.panoramaStatus.textContent = Number.isInteger(remaining)
        ? `正在请求官方全景。本地全景预算剩余 ${remaining} 次。`
        : "正在请求官方全景。";
    } else {
      elements.panoramaStatus.textContent = "正在展示已选择地点的官方全景。";
    }
    // The panorama ID remains inside the official SDK only. It is not rendered,
    // copied, stored, or sent back to the local server.
    const data = await getPanoramaByPoiId(place.uid);
    if (!data || !data.id) {
      elements.panoramaStatus.textContent = "该官方地点当前没有可展示的全景，或请求已超时。";
      return;
    }
    state.panorama.setId(data.id);
    elements.panoramaStatus.textContent = "正在展示官方全景。";
  } catch (error) {
    const message = error instanceof Error ? error.message : "全景展示失败。";
    elements.panoramaStatus.textContent = message;
  } finally {
    state.panoramaBusy = false;
    setPanoramaButtonsDisabled(false);
  }
}

async function initialize() {
  try {
    const [health, config] = await Promise.all([
      requestJson("/api/health", { method: "GET", headers: {} }),
      requestJson("/api/config", { method: "GET", headers: {} }),
    ]);
    state.browserAk = config.browser_ak || null;
    const placeStatus = health.place_search_configured ? "Server AK 已配置" : "Server AK 未配置";
    const panoramaStatus = health.panorama_configured ? "Browser AK 已配置" : "Browser AK 未配置";
    elements.configuration.textContent = `${placeStatus} · ${panoramaStatus}`;
    await initializeMaps();
  } catch (error) {
    const message = error instanceof Error ? error.message : "无法连接本地服务。";
    elements.configuration.textContent = message;
    setNotice(message, "error");
  }
}

elements.search.addEventListener("click", () => search(0));
elements.previous.addEventListener("click", () => search(state.page - 1));
elements.next.addEventListener("click", () => search(state.page + 1));
elements.query.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    search(0);
  }
});

updateControls();
initialize();
