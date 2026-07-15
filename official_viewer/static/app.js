"use strict";

const state = {
  browserAk: null,
  page: 0,
  pageSize: 20,
  maxPagesPerQuery: 20,
  maxResultsPerQuery: 400,
  pageCount: 1,
  hasSearched: false,
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
  pageCache: new Map(),
};

const elements = {
  form: document.getElementById("query-form"),
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

function readSearchInputs() {
  return {
    city: elements.city.value.trim(),
    query: elements.query.value.trim(),
  };
}

function inputsMatchActiveSearch() {
  if (!state.hasSearched) {
    return false;
  }
  const inputs = readSearchInputs();
  return inputs.city === state.city && inputs.query === state.query;
}

function updateControls() {
  const activeInputs = inputsMatchActiveSearch();
  elements.search.disabled = state.busy;
  elements.city.disabled = state.busy;
  elements.query.disabled = state.busy;
  elements.previous.disabled = state.busy || !activeInputs || state.page <= 0;
  elements.next.disabled = state.busy || !activeInputs || !state.hasNext;
  elements.list.setAttribute("aria-busy", String(state.busy));
  elements.pageStatus.textContent = state.hasSearched
    ? `第 ${state.page + 1} / ${state.pageCount} 页`
    : "尚未查询";
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
  select.dataset.uid = place.uid;
  select.setAttribute("aria-label", `查看 ${place.name} 的全景`);
  select.setAttribute("aria-pressed", "false");
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
  const hasTotal = Number.isInteger(data.total);
  const total = hasTotal ? `官方返回 ${data.total} 条` : "官方结果";
  const resultPageCount = hasTotal
    ? Math.ceil(data.total / state.pageSize)
    : state.maxPagesPerQuery;
  state.pageCount = Math.max(
    1,
    Math.min(state.maxPagesPerQuery, resultPageCount)
  );
  elements.summary.textContent =
    `${total}；按官方边界最多显示 ${state.maxResultsPerQuery} 条。`;
  state.hasNext = Boolean(data.has_next);
  updateControls();
}

async function search(page, options = {}) {
  const inputs = readSearchInputs();
  const city = (options.city ?? inputs.city).trim();
  const query = (options.query ?? inputs.query).trim();
  const useCache = Boolean(options.useCache);
  if (!city || !query) {
    setNotice("请填写城市和关键词。", "error");
    return;
  }
  if (useCache && !inputsMatchActiveSearch()) {
    setNotice("检索条件已修改，请先重新搜索。", "error");
    return;
  }
  if (useCache && state.pageCache.has(page)) {
    state.page = page;
    renderResults(state.pageCache.get(page));
    setNotice("已从本次会话缓存恢复，未发送新的官方请求。", "success");
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
    if (!useCache || city !== state.city || query !== state.query) {
      state.pageCache.clear();
    }
    state.city = city;
    state.query = query;
    state.page = data.page;
    state.hasSearched = true;
    state.pageCache.set(data.page, data);
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

function markSelectedPlace(uid) {
  elements.list.querySelectorAll(".result-item").forEach((item) => {
    const button = item.querySelector("button");
    const selected = button?.dataset.uid === uid;
    item.toggleAttribute("data-selected", selected);
    button?.setAttribute("aria-pressed", String(selected));
  });
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
  markSelectedPlace(place.uid);
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
    if (Number.isInteger(config.page_size) && config.page_size > 0) {
      state.pageSize = config.page_size;
    }
    if (
      Number.isInteger(config.max_pages_per_query) &&
      config.max_pages_per_query > 0
    ) {
      state.maxPagesPerQuery = config.max_pages_per_query;
    }
    if (
      Number.isInteger(config.max_results_per_query) &&
      config.max_results_per_query > 0
    ) {
      state.maxResultsPerQuery = config.max_results_per_query;
    }
    updateControls();
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

elements.form.addEventListener("submit", (event) => {
  event.preventDefault();
  const inputs = readSearchInputs();
  search(0, { city: inputs.city, query: inputs.query });
});
elements.previous.addEventListener("click", () =>
  search(state.page - 1, {
    city: state.city,
    query: state.query,
    useCache: true,
  })
);
elements.next.addEventListener("click", () =>
  search(state.page + 1, {
    city: state.city,
    query: state.query,
    useCache: true,
  })
);
elements.city.addEventListener("input", updateControls);
elements.query.addEventListener("input", updateControls);

updateControls();
initialize();
