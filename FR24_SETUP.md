# SKYLINE AIRWAYS — Flightradar24 API setup (v0.7.1)

## Security first
The API token must exist **only** as a server-side environment variable. Never paste a production token into `game.js`, HTML, CSS, GitHub, screenshots, or `render.yaml` values.

If a token has been posted in a chat or other shared location, revoke it in the Flightradar24 API portal and create a fresh one before deployment.

## Render
1. Open the Render service `skyline-airways`.
2. Environment → Add Environment Variable.
3. Key: `FR24_API_TOKEN`.
4. Value: paste the newly rotated production API token.
5. Save and redeploy.

`render.yaml` declares `FR24_API_TOKEN` with `sync: false`, so the secret is never committed.

## What changed
- Hub traffic now uses the official FR24 API when configured; previously the hub endpoint was still OpenSky-only while the globe endpoint supported FR24.
- Requests send `Authorization: Bearer ...`, `Accept: application/json`, and `Accept-Version: v1`.
- Bounds use the FR24 `N,S,W,E` format.
- Ground traffic at airports such as CDG and Limoges is inferred relative to the airport elevation, distance, and groundspeed instead of the broken `alt < 200 ft` rule.
- The hub shows both surface aircraft and low terminal-area traffic.
- Fake/decorative aircraft are disabled in the hub ultra-realism layer. If live data is unavailable, the game says so instead of inventing traffic.
- The frontend never receives the API token.

## Diagnostic endpoint
After logging into SKYLINE, open:

`/api/integrations/fr24/status`

Expected with a token configured:

```json
{"configured":true,"provider":"Flightradar24 API","api_version":"v1","secret_location":"server environment","token_exposed":false}
```

Then test a hub:

`/api/live-traffic?ident=CDG`

Look for:
- `source: "Flightradar24 API"`
- `configured: true`
- `ground_count`
- `nearby_count`

If FR24 rejects the request, the endpoint falls back to OpenSky and includes only a sanitized status such as `fr24_error: "HTTP 401"`; the token itself is never returned.

## Credit control
The hub endpoint is cached for about 22 seconds and the globe endpoint for about 24 seconds. The result limit is capped server-side to reduce unnecessary API credit usage.
