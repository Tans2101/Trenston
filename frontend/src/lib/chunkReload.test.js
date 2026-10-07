import { isChunkLoadError, reloadForNewVersion } from "@/lib/chunkReload";

function memoryStorage() {
  const data = {};
  return {
    getItem: (k) => (k in data ? data[k] : null),
    setItem: (k, v) => {
      data[k] = String(v);
    },
  };
}

test("recognizes webpack and native dynamic import chunk failures", () => {
  expect(isChunkLoadError({ name: "ChunkLoadError", message: "Loading chunk 412 failed." })).toBe(true);
  expect(isChunkLoadError(new Error("Loading CSS chunk 88 failed. (/static/css/88.css)"))).toBe(true);
  expect(isChunkLoadError(new TypeError("Failed to fetch dynamically imported module: /assets/x.js"))).toBe(true);
  expect(isChunkLoadError(new TypeError("Cannot read properties of undefined"))).toBe(false);
  expect(isChunkLoadError(null)).toBe(false);
});

test("reloads once, then refuses a second reload inside the window", () => {
  const storage = memoryStorage();
  const reload = jest.fn();
  expect(reloadForNewVersion({ storage, reload, now: 1_000_000 })).toBe(true);
  expect(reloadForNewVersion({ storage, reload, now: 1_010_000 })).toBe(false);
  expect(reload).toHaveBeenCalledTimes(1);
  expect(reloadForNewVersion({ storage, reload, now: 1_100_000 })).toBe(true);
  expect(reload).toHaveBeenCalledTimes(2);
});

test("does not reload when session storage is unavailable", () => {
  const reload = jest.fn();
  expect(reloadForNewVersion({ storage: null, reload })).toBe(false);
  const throwing = {
    getItem: () => {
      throw new Error("blocked");
    },
    setItem: () => {},
  };
  expect(reloadForNewVersion({ storage: throwing, reload })).toBe(false);
  expect(reload).not.toHaveBeenCalled();
});

test("does not reload while offline", () => {
  const reload = jest.fn();
  expect(reloadForNewVersion({ storage: memoryStorage(), reload, offline: true })).toBe(false);
  expect(reload).not.toHaveBeenCalled();
});
