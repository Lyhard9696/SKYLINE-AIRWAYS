import { AviationLiveClient, fr24StatusText } from "./aviation-live-client.js";

const api = new AviationLiveClient({ apiBase: "" });

let timer = null;
let lastGood = null;

export async function loadWorldGlobe() {
  try {
    const result = await api.getWorldFlights({ includeGround: true });
    lastGood = result;
    return {
      status: fr24StatusText(result),
      flights: result.data,
      stats: result.stats,
      stale: false
    };
  } catch (error) {
    return {
      status: lastGood
        ? `${fr24StatusText(lastGood)} · données en cache`
        : "Flightradar24 temporairement indisponible",
      flights: lastGood?.data || [],
      stats: lastGood?.stats || { airborne:0, groundEstimated:0, unknown:0 },
      stale: true
    };
  }
}

export function startWorldRefresh(onUpdate, intervalMs = 15000) {
  clearInterval(timer);

  const run = async () => onUpdate(await loadWorldGlobe());
  run();
  timer = setInterval(run, intervalMs);

  return () => {
    clearInterval(timer);
    timer = null;
  };
}
