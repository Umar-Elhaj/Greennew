# Vendored libraries

Served by the app itself, with no CDN at run time. Pages keep working when a CDN is slow or blocked, and GREEN Map keeps working offline once loaded.
Exact versions, downloaded on 2026-10-22 from the official npm packages.
To update one, download the new exact version into a new `<name>-<version>/` folder, update the `<script>`/`<link>` tags and this table.

| File | Source | sha256 |
|---|---|---|
| `leaflet-1.9.4/leaflet.js` | https://unpkg.com/leaflet@1.9.4/dist/leaflet.js | `db49d009c841f5ca34a888c96511ae936fd9f5533e90d8b2c4d57596f4e5641a` |
| `leaflet-1.9.4/leaflet.css` | https://unpkg.com/leaflet@1.9.4/dist/leaflet.css | `a7837102824184820dfa198d1ebcd109ff6d0ff9a2672a074b9a1b4d147d04c6` |
| `leaflet-1.9.4/images/*.png` | https://unpkg.com/leaflet@1.9.4/dist/images/ | `—` |
| `chart.js-4.4.0/chart.umd.min.js` | https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js | `0e2326c6868072bec1592760c6729043caeea2960a2b46cee6a2192aac6abff0` |
| `turf-7.1.0/turf.min.js` | https://unpkg.com/@turf/turf@7.1.0/turf.min.js | `c45af4551952fa41f0493cf48c3539b1800774f2abfc031ec6af72accf18be9f` |

Licences: Leaflet BSD-2-Clause, Chart.js MIT, Turf MIT (a copy sits next to each library).
