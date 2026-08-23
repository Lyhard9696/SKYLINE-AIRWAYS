# SKYLINE AIRWAYS v0.7.1 — FR24 READY

- Fixed the hub traffic provider: airport views now prefer the official Flightradar24 API just like the world globe.
- Added required FR24 Bearer authentication and `Accept-Version: v1` headers.
- Fixed ground-aircraft classification for airports above 200 ft elevation.
- Added terminal-area live aircraft around the selected hub.
- Removed decorative fake aircraft from the hub live-traffic layer.
- Added secure Render secret placeholder (`FR24_API_TOKEN: sync: false`).
- Added `.env.example`, `.gitignore`, FR24 diagnostics and deployment documentation.
- Added a photorealistic 3D/Unreal architecture roadmap for cockpit, volumetric clouds and complete 3D airports.
- Bumped PWA cache so iPhone/browser clients load the corrected JavaScript.
