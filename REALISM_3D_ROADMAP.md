# SKYLINE AIRWAYS — photorealistic 3D architecture

SKYLINE's management game remains a web application. Flight-Simulator-class visual scenes should be built as a separate 3D client/service that consumes the same game state rather than forcing the FastAPI/Render server to render 3D.

## 1. Photorealistic observation cockpit
Recommended production target: **Unreal Engine 5**.

- One optimized cockpit model per aircraft family (A320 family, A350, 737, 787, etc.), authored/licensed for the project.
- Unreal `SkyAtmosphere`, dynamic sun/moon, physically based lighting, Lumen where the target hardware supports it.
- Instrument screens are visual/observation displays driven from SKYLINE flight-state data; the player does not need full flight-simulator avionics or pilot controls.
- Position, altitude, heading, speed and flight phase come from the SKYLINE backend; the 3D client interpolates between updates for smooth motion.
- Exterior airport/city/weather scene changes continuously with the simulated aircraft position.

For web/iPhone before a native Unreal app exists, expose the Unreal cockpit through **Pixel Streaming** from a GPU server. The management UI stays in the browser and opens the streamed cockpit view when requested.

## 2. Volumetric clouds and severe weather
Production target: Unreal Engine volumetric weather.

- Volumetric Cloud + SkyAtmosphere for layered clouds.
- Niagara/GPU particles for rain, snow and localized effects.
- Lightning events generated only when the weather provider reports convective conditions.
- Weather data can continue to come from a weather API; the renderer converts cloud cover, precipitation, wind and weather codes into a visual preset.
- Do not attempt Flight-Simulator-class ray-marched clouds in the main mobile web UI: battery/GPU cost and browser variability are too high.

## 3. Fully 3D airports
Use a georeferenced world plus bespoke airport assets.

- Real runway, taxiway, apron, stand and gate topology from open/licensed geodata.
- Custom terminal/hangar/control-tower models for priority hubs (CDG, NCE, JFK, DXB, etc.).
- Generic but geographically correct modular terminals for the long tail of airports.
- Satellite/terrain/3D-tile provider chosen under a license compatible with the intended release.
- Player aircraft, service vehicles and real traffic are separate entities placed over the airport geometry.
- Live FR24 aircraft positions stay at their real coordinates. Optional map-matching to taxiways may be used only when positional confidence is high; the game must not invent a gate or taxi route and present it as live truth.

## 4. Hybrid SKYLINE architecture

```text
Browser / iPhone management UI
        |
        | HTTPS / WebSocket game state
        v
FastAPI + PostgreSQL (Render today)
        |
        +---- FR24 / weather / licensed geodata
        |
        +---- 3D state feed --------------------+
                                                 |
                                                 v
                                   Unreal Engine 5 renderer
                                   (GPU server / Pixel Streaming)
                                                 |
                                                 v
                                      Cockpit / airport 3D view
```

Render's small web instance should host the management/API layer only. Unreal Pixel Streaming requires a GPU-capable host and should be deployed separately.

## 5. Practical rollout

**Phase A — now:** premium 2D/2.5D management UI, satellite hubs, real FR24 traffic, real airport topology.

**Phase B:** one showcase 3D airport (CDG) + one showcase observation cockpit (A350), connected to the existing simulation.

**Phase C:** weather/volumetric-cloud pipeline + NCE/JFK/DXB and additional cockpit families.

**Phase D:** native Unreal client or broader Pixel Streaming deployment, depending on cost and audience.
