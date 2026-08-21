# v0.5.1 Stability Hotfix

- Bounded LRU caches for weather, traffic and airport surface geometry.
- Surface OSM geometry capped to operational features to prevent memory spikes.
- World airport layer reduced to 900 airports at once.
- Real-world aircraft display capped to 140 per viewport.
- Slower background polling (state 6 s, traffic 30–45 s, cockpit weather 90 s).
- Reduced decorative ground traffic.
- Render low-memory allocator settings.
- Keeps accounts, PostgreSQL data, careers and all v0.5 gameplay features.
