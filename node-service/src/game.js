import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SHARED = path.resolve(__dirname, "../../shared/game");

export const eras = JSON.parse(fs.readFileSync(path.join(SHARED, "eras.json"), "utf8"));
export const allianceLevels = JSON.parse(fs.readFileSync(path.join(SHARED, "alliance-levels.json"), "utf8"));
export const allianceGoals = JSON.parse(fs.readFileSync(path.join(SHARED, "alliance-goals.json"), "utf8"));

const VALID_CATEGORIES = new Set([
  "fuel","training","maintenance","aircraft_purchase","aircraft_lease",
  "route_creation","reputation","demand"
]);

export function applyModifiers(base, modifiers = [], category = null) {
  const initial = Number(base);
  if (!Number.isFinite(initial) || initial < 0) throw new Error("base invalide");

  const usable = (Array.isArray(modifiers) ? modifiers : []).filter(m =>
    m && VALID_CATEGORIES.has(m.category) && (!category || m.category === category)
  );

  let percent = 0;
  let flat = 0;

  for (const m of usable) {
    const value = Number(m.value);
    if (!Number.isFinite(value)) continue;
    if (m.mode === "percentage") percent += value;
    if (m.mode === "flat") flat += value;
  }

  // Safety caps: prevent accidental economy destruction.
  percent = Math.max(-50, Math.min(100, percent));
  const result = Math.max(0, (initial + flat) * (1 + percent / 100));

  return {
    base: initial,
    category,
    percentageApplied: percent,
    flatApplied: flat,
    result: Math.round(result * 100) / 100
  };
}
