import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { cache } from "./cache.js";
import { fetchJson } from "./http.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const seedPath = path.resolve(__dirname, "../../shared/data/airlines.seed.json");
const SEED = JSON.parse(fs.readFileSync(seedPath, "utf8"));

const API_BASE = (process.env.FR24_API_BASE || "https://fr24api.flightradar24.com/api").replace(/\/$/, "");

function token() {
  const t = process.env.FR24_API_TOKEN;
  if (!t) throw new Error("FR24_API_TOKEN manquant");
  return t;
}

export function callsignAirlineCode(callsign) {
  if (!callsign || typeof callsign !== "string") return null;
  const m = callsign.trim().toUpperCase().match(/^([A-Z]{3})/);
  if (!m) return null;
  return SEED[m[1]] ? m[1] : null;
}

export function resolveLiveryCode(flight) {
  const painted = String(flight?.painted_as || "").trim().toUpperCase();
  const operating = String(flight?.operating_as || "").trim().toUpperCase();
  return painted || operating || callsignAirlineCode(flight?.callsign) || "UNKNOWN";
}

export async function getAirline(icao) {
  const code = String(icao || "").trim().toUpperCase();
  if (!/^[A-Z0-9]{2,4}$/.test(code)) return null;
  if (SEED[code]) return { icao: code, ...SEED[code], source: "seed" };

  const { value } = await cache.getOrCreate(`airline:${code}`, 86400, async () => {
    const url = `${API_BASE}/static/airlines/${encodeURIComponent(code)}/light`;
    const body = await fetchJson(url, {
      headers: {
        "Accept": "application/json",
        "Accept-Version": "v1",
        "Authorization": `Bearer ${token()}`
      }
    }, 8000);
    return body ? { ...body, source: "fr24" } : null;
  });
  return value;
}
