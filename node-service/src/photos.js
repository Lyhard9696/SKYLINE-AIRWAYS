import { cache } from "./cache.js";
import { fetchJson } from "./http.js";

const BASE = "https://api.planespotters.net/pub/photos";

function clean(v) {
  return String(v || "").trim().toUpperCase().replace(/[^A-Z0-9-]/g, "");
}

function normalizePhoto(body) {
  const photos = Array.isArray(body?.photos) ? body.photos : [];
  const p = photos[0];
  if (!p) return { found: false, photo: null };

  return {
    found: true,
    photo: {
      thumbnail: p?.thumbnail?.src ?? null,
      thumbnailSize: p?.thumbnail?.size ?? null,
      large: p?.large?.src ?? null,
      largeSize: p?.large?.size ?? null,
      photographer: p?.photographer ?? null,
      sourceUrl: p?.link ?? null
    }
  };
}

async function lookup(kind, value) {
  const key = clean(value);
  if (!key) return { found: false, photo: null };

  try {
    const body = await fetchJson(`${BASE}/${kind}/${encodeURIComponent(key)}`, {
      headers: {
        "Accept": "application/json",
        "User-Agent": "AviationGame/2.0"
      }
    }, 6000);
    return normalizePhoto(body);
  } catch {
    return { found: false, photo: null };
  }
}

export async function getAircraftPhoto({ reg, hex }) {
  const cacheKey = `photo:${clean(reg)}:${clean(hex)}`;
  const hit = cache.get(cacheKey);
  if (hit) return { ok: true, cached: true, ...hit };

  let result = await lookup("reg", reg);
  if (!result.found) result = await lookup("hex", hex);

  cache.set(cacheKey, result, result.found ? 86400 : 21600);
  return { ok: true, cached: false, ...result };
}
