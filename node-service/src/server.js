import express from "express";
import { getWorldFlights, getBoundsFlights, fr24RuntimeInfo } from "./fr24.js";
import { getMetar, getTaf } from "./aviationWeather.js";
import { getAircraftPhoto } from "./photos.js";
import { getAirline } from "./airlines.js";
import { eras, allianceLevels, allianceGoals, applyModifiers } from "./game.js";

const app = express();
app.use(express.json({ limit: "1mb" }));

const allowedOrigin = process.env.CORS_ORIGIN || "*";
app.use((req, res, next) => {
  res.setHeader("Access-Control-Allow-Origin", allowedOrigin);
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  res.setHeader("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  if (req.method === "OPTIONS") return res.sendStatus(204);
  next();
});

function boolParam(value, fallback = true) {
  if (value === undefined) return fallback;
  return !["0","false","no","off"].includes(String(value).toLowerCase());
}

function sendError(res, error, provider = null) {
  const status = Number(error?.status) || 503;
  console.error(JSON.stringify({
    provider,
    status,
    message: error?.message || "unknown"
  }));
  res.status(status >= 400 && status < 600 ? status : 503).json({
    ok: false,
    provider,
    status: "temporarily_unavailable",
    message: status === 400 ? error.message : "Service temporairement indisponible"
  });
}

app.get("/health", (req, res) => {
  res.json({ ok: true, service: "aviation-live-service", fr24: fr24RuntimeInfo() });
});

app.get("/api/fr24/live", async (req, res) => {
  try {
    const includeGround = boolParam(req.query.includeGround, true);
    const bounds = req.query.bounds ? String(req.query.bounds) : null;
    const scope = String(req.query.scope || (bounds ? "bounds" : "world")).toLowerCase();

    const result = (scope === "world" && !bounds)
      ? await getWorldFlights({ includeGround })
      : await getBoundsFlights(bounds, { includeGround });

    res.json(result);
  } catch (error) {
    sendError(res, error, "flightradar24");
  }
});

app.get("/api/fr24/airline/:icao", async (req, res) => {
  try {
    const airline = await getAirline(req.params.icao);
    if (!airline) return res.status(404).json({ ok:false, found:false });
    res.json({ ok:true, found:true, airline });
  } catch (error) {
    sendError(res, error, "flightradar24");
  }
});

app.get("/api/aviation/metar", async (req, res) => {
  try { res.json(await getMetar(req.query.icao)); }
  catch (error) { sendError(res, error, "aviationweather.gov"); }
});

app.get("/api/aviation/taf", async (req, res) => {
  try { res.json(await getTaf(req.query.icao)); }
  catch (error) { sendError(res, error, "aviationweather.gov"); }
});

app.get("/api/aircraft/photo", async (req, res) => {
  try { res.json(await getAircraftPhoto({ reg:req.query.reg, hex:req.query.hex })); }
  catch (error) { sendError(res, error, "planespotters"); }
});

app.get("/api/game/eras", (req, res) => res.json({ ok:true, data:eras }));
app.get("/api/game/alliance-levels", (req, res) => res.json({ ok:true, data:allianceLevels }));
app.get("/api/game/alliance-goals", (req, res) => res.json({ ok:true, data:allianceGoals }));

app.post("/api/game/effective-cost", (req, res) => {
  try {
    res.json({ ok:true, ...applyModifiers(req.body?.base, req.body?.modifiers, req.body?.category || null) });
  } catch (error) {
    res.status(400).json({ ok:false, message:error.message });
  }
});

app.use((req, res) => res.status(404).json({ ok:false, message:"Route introuvable" }));

const port = Number(process.env.PORT || 3000);
app.listen(port, "0.0.0.0", () => {
  console.log(`aviation-live-service listening on 0.0.0.0:${port}`);
});
