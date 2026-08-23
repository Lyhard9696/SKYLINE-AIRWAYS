# SKYLINE AIRWAYS v1.3.5

- Hub satellite/OSM removed from runtime: local lightweight model from runway coordinates.
- No synthetic trucks, buses or ground vehicles on Hub; only FR24 aircraft are shown.
- Direct **Gestion du hub** button opens zones/upgrades without loading a map.
- World FR24 traffic is progressive from world zoom using small bounded tiles; density increases while zooming.
- FR24 ground-vehicle category excluded; aircraft on the ground remain included.
- Aircraft detail/photo loaded only on click; exact registration photo or neutral silhouette.
- Missing bank/hotel provider badge assets added and hotel UI upgraded.
- Shop cards use known local aircraft/livery visuals instead of unrelated images.
- Special Ops country map is now a lightweight local schematic (no satellite tile dependency).
- Render worker/concurrency/memory settings tightened for 512 MB instances.
