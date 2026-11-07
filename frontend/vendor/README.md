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
| `andika-5.3.0/andika-latin-400-normal.woff2` | https://www.npmjs.com/package/@fontsource/andika/v/5.3.0 | `dd6bb7266c94cd2fc5d797886050e4bb17bf2375c26b3f28c8474018d8c81b73` |
| `andika-5.3.0/andika-latin-700-normal.woff2` | https://www.npmjs.com/package/@fontsource/andika/v/5.3.0 | `61c90acb5f966627a0970d5742df8d9a212c2528f88caeed3cb7832234c7ee99` |
| `andika-5.3.0/andika-latin-400-italic.woff2` | https://www.npmjs.com/package/@fontsource/andika/v/5.3.0 | `4a57d92a37d664cdd3ea93a117e18b12153534feae9e73cd3083b285eeaf73ef` |
| `andika-5.3.0/andika-latin-ext-400-normal.woff2` | https://www.npmjs.com/package/@fontsource/andika/v/5.3.0 | `3b5fd6ac2e3881c8a033440c2220b72c48a2af820413a7c38cd0e37d217cddaa` |
| `andika-5.3.0/andika-latin-ext-700-normal.woff2` | https://www.npmjs.com/package/@fontsource/andika/v/5.3.0 | `60bde176a34bcfe68f00ae1c7bf9b3677ed4e1e8054fd396968411d9e86c5e69` |
| `andika-5.3.0/andika-latin-ext-400-italic.woff2` | https://www.npmjs.com/package/@fontsource/andika/v/5.3.0 | `5288a0b32127b3a50230ad87c98a916242d9839264cadc87912ff175a932d52f` |
| `andika-5.3.0/andika-vietnamese-400-normal.woff2` | https://www.npmjs.com/package/@fontsource/andika/v/5.3.0 | `656c0fe2f642c68462c54dd15e3923ab3c5d6a56f73055e9b55eb3ffe740a3c1` |
| `andika-5.3.0/andika-vietnamese-700-normal.woff2` | https://www.npmjs.com/package/@fontsource/andika/v/5.3.0 | `afbc6f5d03009e5267c8cccd0acfab8018cb633a9afc46bd80be97b97a3df972` |
| `andika-5.3.0/andika-vietnamese-400-italic.woff2` | https://www.npmjs.com/package/@fontsource/andika/v/5.3.0 | `5f51ef7a831e12b9a3e0fbaae3a1b421679341a4ba5209afa20c09cc074de44b` |
| `bricolage-grotesque-5.3.0/bricolage-grotesque-latin-opsz-normal.woff2` | https://www.npmjs.com/package/@fontsource-variable/bricolage-grotesque/v/5.3.0 | `a79fdb52d4a5c76552452f69202add96e287401fff03d3e8c0e38b4dcb5a99cd` |
| `bricolage-grotesque-5.3.0/bricolage-grotesque-latin-ext-opsz-normal.woff2` | https://www.npmjs.com/package/@fontsource-variable/bricolage-grotesque/v/5.3.0 | `776f6dcaf03636cd69a5802c94808cc8896c0a66c8e9ce0fe147231b6ee01957` |
| `bricolage-grotesque-5.3.0/bricolage-grotesque-vietnamese-opsz-normal.woff2` | https://www.npmjs.com/package/@fontsource-variable/bricolage-grotesque/v/5.3.0 | `b50a9d90a5264f20d1e45be0b948fe947ddb3644557f1e85ef5d3bd06427c944` |

Licences: Leaflet BSD-2-Clause, Chart.js MIT, Turf MIT, Andika and Bricolage Grotesque SIL OFL 1.1 (a copy sits next to each library).

Fonts were added on 2026-11-06. The `.woff2` files are the published ones, unmodified: Andika's name is reserved by its licence, so do not subset or edit them under that name.
