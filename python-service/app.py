import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
SHARED = BASE_DIR.parent / "shared"
AIRLINES = json.loads((SHARED / "data" / "airlines.seed.json").read_text(encoding="utf-8"))
ERAS = json.loads((SHARED / "game" / "eras.json").read_text(encoding="utf-8"))
ALLIANCE_LEVELS = json.loads((SHARED / "game" / "alliance-levels.json").read_text(encoding="utf-8"))
ALLIANCE_GOALS = json.loads((SHARED / "game" / "alliance-goals.json").read_text(encoding="utf-8"))

FR24_BASE = os.getenv("FR24_API_BASE", "https://fr24api.flightradar24.com/api").rstrip("/")
WORLD_STRATEGY = os.getenv("FR24_WORLD_STRATEGY", "tiles").lower()
CACHE_SECONDS = max(5, int(os.getenv("FR24_CACHE_SECONDS", "15")))
CORS_ORIGIN = os.getenv("CORS_ORIGIN", "*")
MAX_LIMIT = 20000

WORLD_TILES = [
    f"{n},{s},{w},{e}"
    for n, s in [(89.999,30),(30,-30),(-30,-89.999)]
    for w, e in [(-179.999,-120),(-120,-60),(-60,0),(0,60),(60,120),(120,179.999)]
]

_cache = {}
_inflight = {}
_lock = threading.Lock()

def cache_get(key):
    with _lock:
        item = _cache.get(key)
        if not item:
            return None
        if time.time() >= item["expires"]:
            _cache.pop(key, None)
            return None
        return item["value"]

def cache_set(key, value, ttl):
    with _lock:
        _cache[key] = {"value": value, "expires": time.time() + ttl}

def token():
    value = os.getenv("FR24_API_TOKEN")
    if not value:
        raise RuntimeError("FR24_API_TOKEN manquant")
    return value

def fr24_headers():
    return {
        "Accept": "application/json",
        "Accept-Version": "v1",
        "Authorization": f"Bearer {token()}",
    }

def fetch_json(url, *, headers=None, params=None, timeout=8):
    r = requests.get(url, headers=headers or {}, params=params or {}, timeout=timeout)
    r.raise_for_status()
    return r.json()

def callsign_airline(callsign):
    if not callsign:
        return None
    m = re.match(r"^([A-Z]{3})", str(callsign).strip().upper())
    if not m:
        return None
    return m.group(1) if m.group(1) in AIRLINES else None

def livery_code(f):
    return (
        str(f.get("painted_as") or "").strip().upper()
        or str(f.get("operating_as") or "").strip().upper()
        or callsign_airline(f.get("callsign"))
        or "UNKNOWN"
    )

def motion(f):
    try:
        alt = float(f.get("alt"))
    except (TypeError, ValueError):
        alt = None
    try:
        speed = float(f.get("gspeed"))
    except (TypeError, ValueError):
        speed = None

    if alt is not None and alt > 100:
        return "airborne"
    if speed is not None and speed > 80:
        return "airborne"
    if alt is not None and alt <= 100 and (speed is None or speed <= 80):
        return "groundEstimated"
    return "unknown"

def normalize(f):
    return {
        "id": f.get("fr24_id"),
        "fr24Id": f.get("fr24_id"),
        "flight": f.get("flight"),
        "callsign": f.get("callsign"),
        "lat": f.get("lat"),
        "lon": f.get("lon"),
        "heading": f.get("track"),
        "altitudeFt": f.get("alt"),
        "groundSpeedKt": f.get("gspeed"),
        "verticalSpeedFpm": f.get("vspeed"),
        "squawk": f.get("squawk"),
        "timestamp": f.get("timestamp"),
        "source": f.get("source"),
        "hex": f.get("hex"),
        "aircraftType": f.get("type"),
        "registration": f.get("reg"),
        "paintedAs": f.get("painted_as"),
        "operatingAs": f.get("operating_as"),
        "liveryCode": livery_code(f),
        "originIata": f.get("orig_iata"),
        "originIcao": f.get("orig_icao"),
        "destinationIata": f.get("dest_iata"),
        "destinationIcao": f.get("dest_icao"),
        "eta": f.get("eta"),
        "motion": motion(f),
    }

def fr24_fetch(bounds=None):
    params = {"limit": MAX_LIMIT}
    if bounds:
        params["bounds"] = bounds
    body = fetch_json(
        f"{FR24_BASE}/live/flight-positions/full",
        headers=fr24_headers(),
        params=params,
        timeout=12,
    )
    return body.get("data", []) if isinstance(body, dict) else []

def dedupe(rows):
    out = {}
    for row in rows:
        key = row.get("fr24_id") or f'{row.get("hex")}:{row.get("callsign")}:{row.get("lat")}:{row.get("lon")}'
        prev = out.get(key)
        if prev is None or str(row.get("timestamp") or "") >= str(prev.get("timestamp") or ""):
            out[key] = row
    return list(out.values())

def world_raw():
    if WORLD_STRATEGY == "single":
        return fr24_fetch()

    rows = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(fr24_fetch, tile): tile for tile in WORLD_TILES}
        for future in as_completed(futures):
            tile = futures[future]
            try:
                rows.extend(future.result())
            except Exception as exc:
                app.logger.warning("FR24 tile failed %s: %s", tile, exc)
    return dedupe(rows)

def get_cached(key, ttl, factory):
    hit = cache_get(key)
    if hit is not None:
        return hit, True
    value = factory()
    cache_set(key, value, ttl)
    return value, False

def stats(data):
    result = {"airborne":0,"groundEstimated":0,"unknown":0}
    for f in data:
        value = f["motion"]
        if value in result:
            result[value] += 1
    return result

@app.after_request
def cors(response):
    response.headers["Access-Control-Allow-Origin"] = CORS_ORIGIN
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response

@app.route("/health")
def health():
    return jsonify({
        "ok": True,
        "service": "aviation-live-service",
        "fr24": {
            "apiBase": FR24_BASE,
            "sandboxLikely": "sandbox" in FR24_BASE.lower(),
            "worldStrategy": WORLD_STRATEGY,
            "cacheSeconds": CACHE_SECONDS,
            "tokenConfigured": bool(os.getenv("FR24_API_TOKEN")),
        },
    })

@app.route("/api/fr24/live")
def live():
    try:
        bounds = request.args.get("bounds")
        scope = (request.args.get("scope") or ("bounds" if bounds else "world")).lower()
        include_ground = request.args.get("includeGround", "true").lower() not in ("0","false","no","off")

        if scope == "world" and not bounds:
            raw, cached = get_cached(f"fr24:world:{WORLD_STRATEGY}", CACHE_SECONDS, world_raw)
        else:
            if not bounds or not re.match(r"^-?\d+(\.\d+)?,-?\d+(\.\d+)?,-?\d+(\.\d+)?,-?\d+(\.\d+)?$", bounds):
                return jsonify({"ok":False,"message":"bounds invalide"}), 400
            raw, cached = get_cached(f"fr24:bounds:{bounds}", CACHE_SECONDS, lambda: fr24_fetch(bounds))

        data = [normalize(x) for x in raw]
        if not include_ground:
            data = [x for x in data if x["motion"] != "groundEstimated"]

        return jsonify({
            "ok": True,
            "provider": "flightradar24",
            "mode": "full",
            "scope": "world" if scope == "world" and not bounds else "bounds",
            "strategy": WORLD_STRATEGY if scope == "world" and not bounds else None,
            "cached": cached,
            "count": len(data),
            "stats": stats(data),
            "data": data,
        })
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 503
        app.logger.error("FR24 HTTP %s", status)
        return jsonify({"ok":False,"provider":"flightradar24","status":"temporarily_unavailable"}), status
    except Exception as exc:
        app.logger.exception("FR24 error")
        return jsonify({"ok":False,"provider":"flightradar24","status":"temporarily_unavailable"}), 503

def aviation_weather(product, icao, ttl):
    code = (icao or "").strip().upper()
    if not re.match(r"^[A-Z0-9]{4}$", code):
        return jsonify({"ok":False,"message":"ICAO invalide"}), 400

    try:
        key = f"aw:{product}:{code}"
        body, cached = get_cached(
            key,
            ttl,
            lambda: fetch_json(
                f"https://aviationweather.gov/api/data/{product}",
                headers={"Accept":"application/json","User-Agent":"AviationGame/2.0"},
                params={"ids":code,"format":"json"},
                timeout=8,
            ),
        )
        return jsonify({
            "ok":True,
            "provider":"aviationweather.gov",
            "product":product.upper(),
            "station":code,
            "cached":cached,
            "data":body,
        })
    except Exception:
        app.logger.exception("AviationWeather error")
        return jsonify({"ok":False,"provider":"aviationweather.gov","status":"temporarily_unavailable"}), 503

@app.route("/api/aviation/metar")
def metar():
    return aviation_weather("metar", request.args.get("icao"), 90)

@app.route("/api/aviation/taf")
def taf():
    return aviation_weather("taf", request.args.get("icao"), 600)

@app.route("/api/fr24/airline/<icao>")
def airline(icao):
    code = (icao or "").strip().upper()
    if code in AIRLINES:
        return jsonify({"ok":True,"found":True,"airline":{"icao":code,**AIRLINES[code],"source":"seed"}})
    try:
        body, cached = get_cached(
            f"airline:{code}",
            86400,
            lambda: fetch_json(
                f"{FR24_BASE}/static/airlines/{code}/light",
                headers=fr24_headers(),
                timeout=8,
            ),
        )
        if not body:
            return jsonify({"ok":False,"found":False}), 404
        body["source"] = "fr24"
        return jsonify({"ok":True,"found":True,"cached":cached,"airline":body})
    except Exception:
        return jsonify({"ok":False,"found":False}), 404

@app.route("/api/aircraft/photo")
def photo():
    reg = re.sub(r"[^A-Z0-9-]", "", (request.args.get("reg") or "").upper())
    hexcode = re.sub(r"[^A-Z0-9-]", "", (request.args.get("hex") or "").upper())
    key = f"photo:{reg}:{hexcode}"
    hit = cache_get(key)
    if hit is not None:
        return jsonify({"ok":True,"cached":True,**hit})

    result = {"found":False,"photo":None}
    for kind, value in [("reg", reg), ("hex", hexcode)]:
        if not value:
            continue
        try:
            body = fetch_json(
                f"https://api.planespotters.net/pub/photos/{kind}/{value}",
                headers={"Accept":"application/json","User-Agent":"AviationGame/2.0"},
                timeout=6,
            )
            photos = body.get("photos", []) if isinstance(body, dict) else []
            if photos:
                p = photos[0]
                result = {
                    "found":True,
                    "photo":{
                        "thumbnail":(p.get("thumbnail") or {}).get("src"),
                        "large":(p.get("large") or {}).get("src"),
                        "photographer":p.get("photographer"),
                        "sourceUrl":p.get("link"),
                    }
                }
                break
        except Exception:
            pass

    cache_set(key, result, 86400 if result["found"] else 21600)
    return jsonify({"ok":True,"cached":False,**result})

@app.route("/api/game/eras")
def game_eras():
    return jsonify({"ok":True,"data":ERAS})

@app.route("/api/game/alliance-levels")
def game_alliance_levels():
    return jsonify({"ok":True,"data":ALLIANCE_LEVELS})

@app.route("/api/game/alliance-goals")
def game_alliance_goals():
    return jsonify({"ok":True,"data":ALLIANCE_GOALS})

@app.route("/api/game/effective-cost", methods=["POST"])
def effective_cost():
    body = request.get_json(silent=True) or {}
    try:
        base = float(body.get("base"))
        category = body.get("category")
        modifiers = body.get("modifiers") or []
        percent = 0.0
        flat = 0.0
        for m in modifiers:
            if category and m.get("category") != category:
                continue
            value = float(m.get("value", 0))
            if m.get("mode") == "percentage":
                percent += value
            elif m.get("mode") == "flat":
                flat += value
        percent = max(-50, min(100, percent))
        result = max(0, (base + flat) * (1 + percent / 100))
        return jsonify({
            "ok":True,
            "base":base,
            "category":category,
            "percentageApplied":percent,
            "flatApplied":flat,
            "result":round(result, 2),
        })
    except Exception:
        return jsonify({"ok":False,"message":"payload invalide"}), 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "3000")))
