"use strict";

(function exposeQuerySessionTools(root, factory) {
  const tools = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = tools;
  } else {
    root.QuerySessionTools = tools;
  }
})(typeof globalThis === "object" ? globalThis : window, function createTools() {
  function buildLoadedResultView(pageCache) {
    if (!(pageCache instanceof Map)) {
      throw new TypeError("pageCache must be a Map");
    }

    const orderedPages = [...pageCache.entries()].sort(
      ([left], [right]) => left - right
    );
    const uniqueByUid = new Map();
    let rawCount = 0;

    orderedPages.forEach(([, page]) => {
      const results = Array.isArray(page?.results) ? page.results : [];
      results.forEach((place) => {
        const uid = typeof place?.uid === "string" ? place.uid : "";
        if (!uid) {
          return;
        }
        rawCount += 1;
        if (!uniqueByUid.has(uid)) {
          uniqueByUid.set(uid, place);
        }
      });
    });

    return {
      results: [...uniqueByUid.values()],
      loadedPageCount: orderedPages.length,
      rawCount,
      uniqueCount: uniqueByUid.size,
      duplicateCount: rawCount - uniqueByUid.size,
    };
  }

  return { buildLoadedResultView };
});
