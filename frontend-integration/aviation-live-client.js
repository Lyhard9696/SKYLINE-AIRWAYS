export class AviationLiveClient {
  constructor({ apiBase = "" } = {}) {
    this.apiBase = apiBase.replace(/\/$/, "");
    this.controller = null;
  }

  async _get(path) {
    const r = await fetch(`${this.apiBase}${path}`, {
      headers: { Accept: "application/json" }
    });
    const body = await r.json().catch(() => null);
    if (!r.ok || !body?.ok) {
      throw new Error(body?.message || `HTTP ${r.status}`);
    }
    return body;
  }

  getWorldFlights({ includeGround = true } = {}) {
    return this._get(`/api/fr24/live?scope=world&includeGround=${includeGround ? "true" : "false"}`);
  }

  getBoundsFlights(bounds, { includeGround = true } = {}) {
    const value = typeof bounds === "string"
      ? bounds
      : `${bounds.north},${bounds.south},${bounds.west},${bounds.east}`;

    return this._get(
      `/api/fr24/live?bounds=${encodeURIComponent(value)}&includeGround=${includeGround ? "true" : "false"}`
    );
  }

  getMetar(icao) {
    return this._get(`/api/aviation/metar?icao=${encodeURIComponent(icao)}`);
  }

  getTaf(icao) {
    return this._get(`/api/aviation/taf?icao=${encodeURIComponent(icao)}`);
  }

  getAircraftPhoto({ registration, hex }) {
    const qs = new URLSearchParams();
    if (registration) qs.set("reg", registration);
    if (hex) qs.set("hex", hex);
    return this._get(`/api/aircraft/photo?${qs.toString()}`);
  }

  getAirline(icao) {
    return this._get(`/api/fr24/airline/${encodeURIComponent(icao)}`);
  }
}

export function fr24StatusText(result) {
  if (!result?.ok) return "Flightradar24 indisponible";
  const s = result.stats || {};
  return `Flightradar24 OK · full · ${result.count} positions · ${s.airborne ?? 0} en vol · ${s.groundEstimated ?? 0} sol estimé`;
}

export function aircraftVisualIdentity(aircraft) {
  // Never derive airline from aircraftType.
  return {
    airlineCode: aircraft?.liveryCode || aircraft?.paintedAs || aircraft?.operatingAs || "UNKNOWN",
    paintedAs: aircraft?.paintedAs || null,
    operatingAs: aircraft?.operatingAs || null,
    fallbackNeutral: !aircraft?.liveryCode || aircraft.liveryCode === "UNKNOWN"
  };
}
