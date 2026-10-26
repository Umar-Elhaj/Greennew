# GREEN — Agricultural Intelligence Platform

GREEN helps farms in Cameroon monitor crop health. Farmers photograph leaves (phone, webcam or the field rover). An EfficientNet-B0 model predicts the **probable** disease, which is an AI prediction and not a diagnosis. Each analysis gets a field sheet. Results are placed on the farm's parcels (GREEN Map), followed over time, discussed with an AI agronomic assistant (GreenBot), and aggregated anonymously for partners (GREEN Data).

The interface is fully bilingual **French / English**.

---

## Contents

1. [Features](#1-features)
2. [Architecture](#2-architecture)
3. [Project structure](#3-project-structure)
4. [Running locally](#4-running-locally)
5. [Configuration](#5-configuration)
6. [Tests and quality checks](#6-tests-and-quality-checks)
7. [Deployment](#7-deployment)
8. [API overview](#8-api-overview)
9. [Data, privacy and roles](#9-data-privacy-and-roles)
10. [Model](#10-model)
11. [Known limits and next steps](#11-known-limits-and-next-steps)

---

## 1. Features

| Page | What it does |
|---|---|
| **Sign in / register** (`/`, `/register`) | Phone (normalised to +237) or email. The dataset consent at registration is optional and unchecked by default. |
| **Dashboard** (`/dashboard`) | Key figures, results of the last 4 weeks, weather for the user's region, recent analyses. |
| **Camera analysis** (`/camera`) | Device camera, imported photos or rover stream on the local network. Every image is first kept in an **offline queue (IndexedDB)** with its context (parcel, mission cell, GPS, capture time), then sent when the network is available. |
| **GREEN Map** (`/map`) | Draw parcels, including offline: draggable points, "add my position" with accuracy, Turf checks for self-crossing, area and overlap. Changes are synced later. Square grid for the rover (1–50 m) with a serpentine path, frozen as a **mission** with JSON/GeoJSON exports. **Heatmap per cell**: share of probable diseases, highest alert level or dominant disease. |
| **History** (`/history`) | Filters and the field sheet of each analysis (symptoms, actions, other candidates, disclaimer), in the reader's language. |
| **GreenBot** (`/chatbot`) | Gemini-based assistant with retrieval (TF-IDF) and the context of one of the user's analyses. It answers in the interface language. |
| **Disease library** (`/diseases`) | 35 bilingual sheets (diseases and pests) with bilingual search. |
| **Crop calendar**, **Economic scenarios**, **My progress**, **Inputs catalogue** | Reference and planning pages. *My progress* compares the user only with their own history. The catalogue shows generic input types at indicative prices, with no online sale. |
| **GREEN Data** (`/green-data`, partner/admin only) | Consent-only aggregates: volume, plants, diseases, plant × disease matrix, regions (choropleth), seasonality, confidence, model quality, emerging alerts, dataset maturity, CSV/GeoJSON exports. Every figure based on fewer than 5 analyses is masked. |
| **Settings / Profile** | Theme, language, consents (dataset, photo GPS), rover address, account. |

---

## 2. Architecture

```
Browser (HTML + vanilla JS, Leaflet, Chart.js, Turf — vendored)
  │  i18n.js (fr/en, applied before first paint) · IndexedDB queues (images, parcels)
  │
  │  one origin on o2switch: Apache serves the pages and static files
  │  (linked into the domain's document root), /api/* goes to FastAPI
  ▼
FastAPI (backend/main.py) ── Passenger + a2wsgi on o2switch (backend/passenger_wsgi.py)
  ├─ auth (JWT HS256, bcrypt), roles farmer / agronomist / partner / admin
  ├─ camera → media.py (Pillow validation, re-encode, thumbnail, EXIF stripped)
  │          → inference.py (ONNX Runtime by default, PyTorch optional)
  │          → knowledge.py (bilingual field sheet from diseases.json)
  ├─ parcels / missions → geo.py (validation, area, region, grid + path)
  ├─ green-data (SQL aggregates, k-anonymity 5, 10-min cache)
  ├─ chatbot (TF-IDF retrieval over rag/ + Gemini), weather (OpenWeather proxy)
  └─ i18n.py (server messages per Accept-Language / ?lang)
  │
  ├─ MySQL/MariaDB of o2switch (localhost, PyMySQL) — schema managed by Alembic
  └─ MEDIA_DIR on disk (outside the web root) — images served only by
     GET /api/media/{path} with a Bearer token or a short-lived signed URL
```

The rover is a Raspberry Pi that creates its own Wi-Fi hotspot. A hosted server cannot reach it, so images travel through the browser queue (store-and-forward). The waypoint and upload contract is in [`docs/rover_mission_contract.md`](docs/rover_mission_contract.md).

---

## 3. Project structure

```
backend/
  main.py                FastAPI app, page routes, security headers, schema check
  passenger_wsgi.py      Passenger entry point (a2wsgi)
  config.py              environment (DATABASE_URL, SECRET_KEY, …)
  db_url.py, database.py DATABASE_URL normalisation, engine settings per database
  db_types.py            column types that behave the same on MySQL, SQLite and PostgreSQL
  models.py              SQLAlchemy models   ·  migrations/ (Alembic)
  sql/mysql_schema.sql   production schema (reference, importable in an empty database)
  sql/supabase_schema.sql  schema of the former Supabase database (history)
  auth.py, schemas.py    JWT, roles, validation (phone +237, password ≥ 8)
  media.py               image storage and signed URLs
  inference.py           EfficientNet-B0 (ONNX / PyTorch)
  knowledge.py           bilingual knowledge base, class → sheet mapping, field sheet
  geo.py                 parcel geometry, regions, grid, serpentine path
  i18n.py                server-side translations
  routers/               auth, dashboard, analysis, camera, media, parcels, missions,
                         green_data, chatbot, weather, diseases
  data/cameroon_regions.json   region boundaries (geoBoundaries, CC BY 3.0)
  tests/                 pytest (SQLite; whole suite also on MariaDB/MySQL and PostgreSQL)
frontend/
  *.html                 15 pages        ·  i18n/*.json → js/translations.js (generated)
  js/                    i18n, api, layout, utils, fiche, charts, upload-queue, parcel-store, theme-init
  vendor/                Leaflet 1.9.4, Chart.js 4.4.0, Turf 7.1.0 (+ licences, hashes)
qa/                      Playwright: e2e (pages), flows, consistency (a11y), journey
scripts/                 check_i18n, build_i18n, db_check, copy_database, media_report,
                         seed_demo, set_role, onnx_parity, smoke_prod.sh, configure_vercel
deploy/o2switch/         .htaccess snippet, publish_frontend.sh
docs/                    DEPLOY_O2SWITCH.md, rover_mission_contract.md, i18n_glossary.md
Models/                  best_efficientnet.onnx (production), .pth (development)
diseases.json            knowledge base (fr/en)   ·  rag/  GreenBot corpus
```

---

## 4. Running locally

Requirements: Python 3.12, Node 20+ (tests only), Git.

```bash
git clone <repo> && cd Greennew
python3.12 -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt     # includes PyTorch for the parity check
cp .env.example .env                                     # then set DEBUG=true for local work
cd backend && ../.venv/bin/uvicorn main:app --reload --port 8000
```

Open http://localhost:8000. Without `DATABASE_URL`, a SQLite file (`green.db`) is used and migrated automatically at startup. Useful extras:

```bash
DEBUG=true .venv/bin/python scripts/seed_demo.py          # demo data for GREEN Data (is_demo, removable)
.venv/bin/python scripts/set_role.py --phone +2376XXXXXXXX --role partner
```

**Translations.** Edit `frontend/i18n/<namespace>.json`, then run `python scripts/build_i18n.py`; the result `js/translations.js` is committed. Terms and tone are set in [`docs/i18n_glossary.md`](docs/i18n_glossary.md).

---

## 5. Configuration

Only `DATABASE_URL` and `SECRET_KEY` are required in production. Every other variable enables an optional feature, and the UI says clearly when a feature is disabled. The full commented list is in [`.env.example`](.env.example):

`DATABASE_URL`, `SECRET_KEY`, `DEBUG`, `CORS_ORIGINS`, `MEDIA_DIR`, `MAX_UPLOAD_MB`, `INFERENCE_BACKEND`, `MODEL_PATH`, `MODEL_VERSION`, `WARMUP`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `WEATHER_API_KEY`.

- **Database.** Production uses the MySQL/MariaDB database of the o2switch account: `mysql://<user>:<password>@localhost/<database>?unix_socket=<socket>` (or `@localhost:3306`). The PyMySQL driver and `charset=utf8mb4` are added automatically, each session runs in UTC with a strict SQL mode, and the password is masked in logs. On MySQL, floats are `DOUBLE`, dates `DATETIME(6)` and long texts `MEDIUMTEXT` (`backend/db_types.py`), so behaviour matches SQLite and PostgreSQL. PostgreSQL URLs are still accepted (former Supabase database, data copy with `scripts/copy_database.py`).
- **Schema.** It is managed by Alembic: `cd backend && alembic upgrade head` creates every table in an empty database; `backend/sql/mysql_schema.sql` is the same schema as a file (phpMyAdmin import), checked against the models by a test. On a PostgreSQL database created before Alembic, first run `alembic stamp 0001_baseline`. Every revision is additive.

---

## 6. Tests and quality checks

```bash
.venv/bin/pytest backend/tests                         # 149 tests (SQLite)
.venv/bin/pytest backend/tests -m slow                 # real model: ONNX ⇄ PyTorch parity
.venv/bin/ruff check --config backend/pyproject.toml backend scripts
.venv/bin/python scripts/check_i18n.py                 # keys, empty values, untranslated text
cd qa && npm ci && npx playwright install chromium && npx playwright test
```

- **MySQL/MariaDB (production database).** Start a disposable server (`docker run -d --rm -p 53306:3306 -e MARIADB_ROOT_PASSWORD=test -e MARIADB_DATABASE=green_suite mariadb:10.6`), then run `TEST_DATABASE_URL=mysql://root:test@127.0.0.1:53306/green_suite TEST_MYSQL_URL=mysql://root:test@127.0.0.1:53306/green_suite .venv/bin/pytest backend/tests -m "not slow and not postgres"` (whole suite on MariaDB, plus Alembic ⇄ models ⇄ `mysql_schema.sql` and the data copy). Checked on MariaDB 10.6 and 11.4.
- **PostgreSQL.** Start a disposable server (`docker run -d --rm -p 55432:5432 -e POSTGRES_PASSWORD=test -e POSTGRES_DB=green_test postgres:16-alpine`), then set `TEST_POSTGRES_URL` / `TEST_DATABASE_URL` to `postgresql://postgres:test@localhost:55432/<db>?sslmode=disable`.
- **Playwright** covers:
  - every page in French and English at 1366×768 and 390×844 (console errors, HTTP errors, text left in the wrong language, horizontal overflow);
  - functional flows: offline queue, offline parcel sync, map → mission → heatmap, GREEN Data roles, translated errors;
  - consistency in light and dark themes (shell, links, axe-core contrast);
  - the full reference journey in both languages.

---

## 7. Deployment

Everything runs on **o2switch**, on one domain, set up in this order:
1. **Database**: MySQL/MariaDB database and user created in cPanel, tables from `backend/sql/mysql_schema.sql` (or `alembic upgrade head`).
2. **Backend**: cPanel *Setup Python App* (Passenger, `backend/passenger_wsgi.py`), `backend/requirements-prod.txt` (ONNX Runtime and PyMySQL, no PyTorch, nothing to compile).
3. **Frontend**: `deploy/o2switch/publish_frontend.sh <document root>` links the pages and static files into the domain, where Apache serves them; `/api/*` goes to Passenger.

- The click-by-click walkthrough (in French) is [`GUIDE_INTEGRATION_O2SWITCH.md`](GUIDE_INTEGRATION_O2SWITCH.md): SSH, subdomain, Let's Encrypt, MySQL database, Setup Python App, optional copy of the former Supabase data (`scripts/copy_database.py`), `.htaccess`, Tiger Protect, frontend, smoke test, cron jobs and `mysqldump` backups, updates. The condensed reference is [`docs/DEPLOY_O2SWITCH.md`](docs/DEPLOY_O2SWITCH.md).
- **After each deployment.** Run `scripts/smoke_prod.sh <base_url>` (API, pages, private files refused, analysis, images, GREEN Data).
- Vercel is no longer used; `frontend/vercel.json` and `scripts/configure_vercel.py` are kept only for a possible return to it.

---

## 8. API overview

All routes are under `/api` and need `Authorization: Bearer <token>`, except authentication, health and the disease library. Errors are `{"detail": "<message in the request language>"}`.

| Area | Routes |
|---|---|
| Auth | `POST /auth/register`, `POST /auth/login`, `GET/PUT/DELETE /auth/me`, `POST /auth/change-password` |
| Analyses | `POST /camera/upload`, `POST /camera/analyze-frame` (+ `mission_id`, `cell_index`, `captured_at`, `source=rover`), `GET /analysis/history`, `GET/DELETE /analysis/{id}`, `GET /analysis/fiche/{id}`, `POST /analysis/{id}/verify` (agronomist) |
| Images | `GET /media/{yyyy}/{mm}/{uuid}[_thumb].jpg` (owner, agronomist or admin) |
| Parcels | `GET/POST /parcels`, `GET/PUT/DELETE /parcels/{id}`, `GET /parcels/{id}/analyses`, `GET /parcels/geo/analyses` |
| Missions | `POST /missions/preview`, `POST/GET /missions`, `GET/PATCH/DELETE /missions/{id}`, `GET /missions/{id}/waypoints`, `…/export.geojson`, `…/heatmap` |
| GREEN Data | `GET /green-data/{meta,overview,plants,diseases,regions,seasonality,confidence,model-quality,alerts,dataset}`, `…/export.csv`, `…/export.geojson` |
| Other | `GET /dashboard/{stats,disease-trends,recent-activity,progress}`, `GET /weather/{current,forecast}`, `/chat/sessions…`, `GET /diseases`, `GET /health` |

Interactive documentation is available at `/docs` when `DEBUG=true`.

---

## 9. Data, privacy and roles

- **Images.** They are stored outside the web root, without metadata. A GPS position read from a photo is kept only with the *location consent*.
- **Sharing with GREEN Data.** Only analyses whose author gave the *dataset consent*, and still gives it from an active account, are counted. Demo rows are excluded. A figure is published only if it covers at least 5 analyses from at least 5 farmers; the figures that would let a hidden one be recalculated (other cells of the same row or column, rates, alert baselines) are hidden too. The finest geography is one of the 10 regions (any other stored text is "unknown"), the period is given by month, and no names or coordinates are exported.
- **Roles.** `farmer` is the default. `agronomist` can view images and verify labels. `partner` has access to GREEN Data. `admin` can do everything. Roles are assigned with `scripts/set_role.py`.
- **Wording.** Every result is presented as a *probable disease*, with the mention "AI prediction, not a diagnosis".

---

## 10. Model

EfficientNet-B0 with 224×224 input and 11 classes: Cassava_Mosaic, Corn_Brown_Spots, Corn_Healthy, Corn_Leaf_Blight, Corn_Mildew, Corn_Streak, Corn_Stripe, Corn_Yellowing, Tomato_Brown_Spots, Tomato_Blight_Leaf, Tomato_Healthy.

- **Production.** `Models/best_efficientnet.onnx` through ONNX Runtime (about 20 ms per image and 180 MB peak on CPU).
- **Development.** `.pth` with PyTorch (`INFERENCE_BACKEND=torch`).
- **Parity.** `scripts/onnx_parity.py` checks that both give the same top-1 class on 24 images, with a maximum probability gap of 3e-6.

The "alert level" shown with a disease is derived from the model's confidence. It does not measure the extent of the damage.

---

## 11. Known limits and next steps

- **Class → reference sheet mapping.** It is in `backend/knowledge.py` and must be validated by an agronomist.
- **Pest detection (YOLO).** A trained model exists (`best.pt`) but is **not wired into the backend**. This is future work.
- **Rover.** It cannot upload by itself yet: the device-token endpoint is specified in the rover contract but not implemented. Physical rover navigation is out of scope.
- **Offline use.** There is no service worker: `/map` and `/camera` keep working offline only while the page stays open (no reload or navigation, no satellite tiles offline), and the camera page loads parcels and missions from the network. The queues are kept per account on the device.
- **Photo metadata.** Imported photos larger than 1600 px or 1.5 MB are re-encoded on the device before the upload, which drops their EXIF GPS and capture date: the *location consent* then has no effect, and the capture time is the import time. Reading EXIF in the browser before re-encoding is future work.
- **GreenBot.** It needs a Gemini key (`GEMINI_API_KEY`). Without one, the page explains that the assistant is not configured.
- **Change log.** It is kept in [`MODIFICATIONS.md`](MODIFICATIONS.md) (in French).
