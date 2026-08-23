import test from "node:test";
import assert from "node:assert/strict";
import { resolveLiveryCode } from "../src/airlines.js";
import { applyModifiers } from "../src/game.js";

test("painted_as wins over operating_as", () => {
  assert.equal(resolveLiveryCode({
    painted_as: "AFR",
    operating_as: "CCA",
    callsign: "CCA123"
  }), "AFR");
});

test("A350 type does not determine airline", () => {
  assert.equal(resolveLiveryCode({
    type: "A359",
    callsign: null,
    painted_as: null,
    operating_as: null
  }), "UNKNOWN");
});

test("cost modifier", () => {
  const r = applyModifiers(1000, [
    { category:"fuel", mode:"percentage", value:-7 }
  ], "fuel");
  assert.equal(r.result, 930);
});
