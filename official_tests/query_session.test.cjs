"use strict";

const assert = require("node:assert/strict");
const {
  buildLoadedResultView,
} = require("../official_viewer/static/query_session.js");

const a = { uid: "a", name: "A" };
const b = { uid: "b", name: "B" };
const changedB = { uid: "b", name: "B newer fields" };
const c = { uid: "c", name: "C" };
const pages = new Map([
  [1, { results: [changedB, c, c, {}] }],
  [0, { results: [a, b] }],
  [2, { results: null }],
]);

const view = buildLoadedResultView(pages);
assert.deepEqual(view.results, [a, b, c]);
assert.equal(view.loadedPageCount, 3);
assert.equal(view.rawCount, 5);
assert.equal(view.uniqueCount, 3);
assert.equal(view.duplicateCount, 2);
assert.equal(pages.get(1).results.length, 4);
assert.throws(() => buildLoadedResultView({}), /pageCache must be a Map/);
