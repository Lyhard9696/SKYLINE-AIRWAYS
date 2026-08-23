import { cache } from "./cache.js";
import { fetchJson } from "./http.js";

const BASE = "https://aviationweather.gov/api/data";

function station(value) {
  const icao = String(value || "").trim().toUpperCase();
  if (!/^[A-Z0-9]{4}$/.test(icao)) {
    const error = new Error("ICAO invalide");
    error.status = 400;
    throw error;
  }
  return icao;
}

async function getProduct(product, icao, ttl) {
  const code = station(icao);
  const { value, cached } = await cache.getOrCreate(
    `aw:${product}:${code}`,
    ttl,
    async () => {
      const url = new URL(`${BASE}/${product}`);
      url.searchParams.set("ids", code);
      url.searchParams.set("format", "json");
      return fetchJson(url, {
        headers: {
          "Accept": "application/json",
          "User-Agent": "AviationGame/2.0"
        }
      }, 8000);
    }
  );

  return {
    ok: true,
    provider: "aviationweather.gov",
    product: product.toUpperCase(),
    station: code,
    cached,
    data: value
  };
}

export const getMetar = (icao) => getProduct("metar", icao, 90);
export const getTaf = (icao) => getProduct("taf", icao, 600);
