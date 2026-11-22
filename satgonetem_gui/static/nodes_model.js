/** Pure cache helpers for the Node Explorer page. */

export const DETAIL_TTL_MS = 30_000;

export function cacheEntry(data, now = Date.now()) {
  return { data, at: now };
}

export function isFresh(entry, now = Date.now(), ttl = DETAIL_TTL_MS) {
  return Boolean(entry) && now - entry.at < ttl;
}

export function staleCacheKeys(cachedNames, activeNames) {
  const active = new Set(activeNames);
  return [...cachedNames].filter((name) => !active.has(name));
}
