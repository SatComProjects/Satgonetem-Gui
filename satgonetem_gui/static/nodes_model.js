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

export const FAVORITES_KEY = "sgnt_node_favorites";
export const MAX_FAVORITES = 200;

function nameCompare(left, right) {
  return String(left?.name || "").localeCompare(
    String(right?.name || ""),
    undefined,
    { numeric: true, sensitivity: "base" },
  );
}

/** Normalize stored favorite names to unique, trimmed strings. */
export function normalizeFavorites(raw) {
  if (!Array.isArray(raw)) return [];
  const favorites = [];
  const seen = new Set();
  for (const entry of raw) {
    if (entry === null || entry === undefined) continue;
    const name = String(entry).trim();
    if (!name || seen.has(name)) continue;
    seen.add(name);
    favorites.push(name);
    if (favorites.length >= MAX_FAVORITES) break;
  }
  return favorites;
}

export function toggleFavorite(favorites, name) {
  const current = normalizeFavorites(favorites);
  const clean = String(name ?? "").trim();
  if (!clean) return current;
  const next = current.includes(clean)
    ? current.filter((entry) => entry !== clean)
    : [...current, clean];
  return next.slice(0, MAX_FAVORITES);
}

function nodeText(node) {
  return `${node?.name || ""} ${node?.city || ""} ${node?.type || ""}`.toLowerCase();
}

/** Filter nodes by query, type, and the favorites-only toggle. */
export function filterNodes(nodes, options = {}) {
  if (!Array.isArray(nodes)) return [];
  const query = String(options.query ?? "").trim().toLowerCase();
  const type = options.type || "all";
  const favorites = new Set(
    options.favoritesOnly ? normalizeFavorites(options.favorites) : [],
  );
  return nodes.filter((node) => {
    if (!node || typeof node !== "object") return false;
    if (type !== "all" && node.type !== type) return false;
    if (options.favoritesOnly && !favorites.has(node.name)) return false;
    return !query || nodeText(node).includes(query);
  });
}

function typeRank(node) {
  if (node?.type === "satellite") return 0;
  if (node?.type === "ground_station") return 1;
  return 2;
}

/** Return a sorted copy; name sorting is numeric-aware. */
export function sortNodes(nodes, key = "name") {
  if (!Array.isArray(nodes)) return [];
  const sorted = [...nodes];
  if (key === "city") {
    sorted.sort((left, right) => {
      const leftCity = String(left?.city || "").trim();
      const rightCity = String(right?.city || "").trim();
      if (leftCity && !rightCity) return -1;
      if (!leftCity && rightCity) return 1;
      return (
        leftCity.localeCompare(rightCity, undefined, {
          sensitivity: "base",
        }) || nameCompare(left, right)
      );
    });
  } else if (key === "type") {
    sorted.sort(
      (left, right) => typeRank(left) - typeRank(right) || nameCompare(left, right),
    );
  } else {
    sorted.sort(nameCompare);
  }
  return sorted;
}

export function nodeCountText(shown, total) {
  if (
    shown === null ||
    shown === undefined ||
    shown === "" ||
    total === null ||
    total === undefined ||
    total === ""
  ) {
    return "\u2014";
  }
  const visible = Number(shown);
  const all = Number(total);
  if (!Number.isFinite(visible) || !Number.isFinite(all)) return "\u2014";
  if (visible === all) {
    return `${all} node${all === 1 ? "" : "s"}`;
  }
  return `Showing ${visible} of ${all} nodes`;
}
