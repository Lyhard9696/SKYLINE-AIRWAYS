import { cache } from "./cache.js";
import { fetchJson } from "./http.js";
import { resolveLiveryCode } from "./airlines.js";

const API_BASE = (process.env.FR24_API_BASE || "https://fr24api.flightradar24.com/api").replace(/\/$/, "");
const CACHE_SECONDS = Math.max(5, Number(process.env.FR24_CACHE_SECONDS || 15));
const WORLD_STRATEGY = String(process.env.FR24_WORLD_STRATEGY || "tiles").toLowerCase();
const MAX_LIMIT = 20000;

// 3 latitude bands x 6 longitude bands.
// Boundaries overlap only at their edges; fr24_id deduplication removes duplicates.
const WORLD_TILES = [];
for (const [north, south] of [[89.999, 30], [30, -30], [-30, -89.999]]) {
  for (const [west, east] of [[-179.999,-120],[-120,-60],[-60,0],[0,60],[60,120],[120,179.999]]) {
    WORLD_TILES.push(`${north},${south},${west},${east}`);
  }
}

function token() {
  const t = process.env.FR24_API_TOKEN;
  if (!t) throw new Error("FR24_API_TOKEN manquant");
  return t;
}

function headers() {
  return {
    "Accept": "application/json",
    "Accept-Version": "v1",
    "Authorization": `Bearer ${token()}`
  };
}

function buildUrl(params = {}) {
  const url = new URL(`${API_BASE}/live/flight-positions/full`);
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, String(value));
    }
  }
  return url;
}

async function fetchFull(params = {}) {
  // IMPORTANT: no categories / altitude_ranges / airport filter here.
  // This endpoint is intentionally allowed to return both airborne and ground-tracked aircraft.
  const url = buildUrl(params);
  const body = await fetchJson(url, { headers: headers() }, 12000);
  const data = Array.isArray(body?.data) ? body.data : [];
  return data;
}

function classifyMotion(f) {
  const alt = Number(f.alt);
  const speed = Number(f.gspeed);
  const hasAlt = Number.isFinite(alt);
  const hasSpeed = Number.isFinite(speed);

  // This is only an estimation for UI statistics.
  // It NEVER determines whether a record is kept.
  if (hasAlt && alt > 100) return "airborne";
  if (hasSpeed && speed > 80) return "airborne";
  if ((hasAlt && alt <= 100) && (!hasSpeed || speed <= 80)) return "groundEstimated";
  return "unknown";
}

function normalize(f) {
  return {
    id: f.fr24_id ?? null,
    fr24Id: f.fr24_id ?? null,
    flight: f.flight ?? null,
    callsign: f.callsign ?? null,
    lat: f.lat ?? null,
    lon: f.lon ?? null,
    heading: f.track ?? null,
    altitudeFt: f.alt ?? null,
    groundSpeedKt: f.gspeed ?? null,
    verticalSpeedFpm: f.vspeed ?? null,
    squawk: f.squawk ?? null,
    timestamp: f.timestamp ?? null,
    source: f.source ?? null,
    hex: f.hex ?? null,
    aircraftType: f.type ?? null,
    registration: f.reg ?? null,
    paintedAs: f.painted_as ?? null,
    operatingAs: f.operating_as ?? null,
    liveryCode: resolveLiveryCode(f),
    originIata: f.orig_iata ?? null,
    originIcao: f.orig_icao ?? null,
    destinationIata: f.dest_iata ?? null,
    destinationIcao: f.dest_icao ?? null,
    eta: f.eta ?? null,
    motion: classifyMotion(f)
  };
}

function dedupe(rows) {
  const map = new Map();
  for (const row of rows) {
    const key = row.fr24_id || `${row.hex || ""}:${row.callsign || ""}:${row.lat || ""}:${row.lon || ""}`;
    const previous = map.get(key);
    if (!previous) {
      map.set(key, row);
      continue;
    }
    // Keep the freshest record when timestamps are available.
    const pt = Date.parse(previous.timestamp || 0) || 0;
    const nt = Date.parse(row.timestamp || 0) || 0;
    if (nt >= pt) map.set(key, row);
  }
  return [...map.values()];
}

async function mapLimit(items, concurrency, fn) {
  const out = new Array(items.length);
  let cursor = 0;
  async function worker() {
    while (true) {
      const i = cursor++;
      if (i >= items.length) return;
      out[i] = await fn(items[i], i);
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, worker));
  return out;
}

async function getWorldRaw() {
  if (WORLD_STRATEGY === "single") {
    return fetchFull({ limit: MAX_LIMIT });
  }

  const chunks = await mapLimit(WORLD_TILES, 3, async (bounds) => {
    try {
      return await fetchFull({ bounds, limit: MAX_LIMIT });
    } catch (error) {
      console.error(JSON.stringify({
        provider: "fr24",
        event: "tile_error",
        bounds,
        status: error?.status || null,
        message: error?.message || "unknown"
      }));
      return [];
    }
  });

  return dedupe(chunks.flat());
}

function stats(data) {
  const result = { airborne: 0, groundEstimated: 0, unknown: 0 };
  for (const f of data) {
    if (f.motion === "airborne") result.airborne++;
    else if (f.motion === "groundEstimated") result.groundEstimated++;
    else result.unknown++;
  }
  return result;
}

export async function getWorldFlights({ includeGround = true } = {}) {
  const { value: raw, cached } = await cache.getOrCreate(
    `fr24:world:${WORLD_STRATEGY}`,
    CACHE_SECONDS,
    getWorldRaw
  );
  let data = raw.map(normalize);
  if (!includeGround) data = data.filter(f => f.motion !== "groundEstimated");

  return {
    ok: true,
    provider: "flightradar24",
    mode: "full",
    scope: "world",
    strategy: WORLD_STRATEGY,
    cached,
    count: data.length,
    stats: stats(data),
    data
  };
}

export async function getBoundsFlights(bounds, { includeGround = true } = {}) {
  const clean = String(bounds || "").trim();
  if (!/^-?\d+(\.\d+)?,-?\d+(\.\d+)?,-?\d+(\.\d+)?,-?\d+(\.\d+)?$/.test(clean)) {
    const e = new Error("bounds invalide. Format: north,south,west,east");
    e.status = 400;
    throw e;
  }

  const { value: raw, cached } = await cache.getOrCreate(
    `fr24:bounds:${clean}`,
    CACHE_SECONDS,
    () => fetchFull({ bounds: clean, limit: MAX_LIMIT })
  );

  let data = raw.map(normalize);
  if (!includeGround) data = data.filter(f => f.motion !== "groundEstimated");

  return {
    ok: true,
    provider: "flightradar24",
    mode: "full",
    scope: "bounds",
    bounds: clean,
    cached,
    count: data.length,
    stats: stats(data),
    data
  };
}

export function fr24RuntimeInfo() {
  return {
    apiBase: API_BASE,
    sandboxLikely: /sandbox/i.test(API_BASE),
    worldStrategy: WORLD_STRATEGY,
    cacheSeconds: CACHE_SECONDS,
    tokenConfigured: Boolean(process.env.FR24_API_TOKEN)
  };
}
