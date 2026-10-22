# PROGRESS — GREEN : i18n, GREEN Map, GREEN Data, médias, Supabase, o2switch

Branche : `feat/green-map-data-o2switch` (créée depuis `main` @ `36d4768`).
Source d'état du chantier : relire ce fichier au début de chaque lot et après tout compactage de contexte.

Légende : `[ ]` à faire · `[~]` en cours · `[x]` fait (preuve en face) · `[!]` bloqué (voir « Blocages »)

---

## LOT 0 — État des lieux et socle

- [x] 0.1 Cloner le dépôt dans `~/Documents/github_reps/Greennew` et créer la branche
  - Preuve : `git ls-remote` → HEAD `36d47680…` ; `git checkout -b feat/green-map-data-o2switch`.
- [x] 0.2 venv Python 3.12 + dépendances, démarrage SQLite, ouverture de chaque page
  - Preuve : `AUDIT.md` §5 (health 200, 15 routes HTML 200, `/drone` → 307).
- [x] 0.3 `AUDIT.md` : tableau par page et par endpoint (fonctionnalité, état, preuve, correction prévue) + incohérences README ⇄ code
- [x] 0.4 Harnais : `backend/tests/` (pytest + TestClient, SQLite temporaire) — 21 passed, 6 xfailed (stricts)
- [x] 0.5 Harnais : `scripts/check_i18n.py` — échoue aujourd'hui (532 chaînes), attendu jusqu'au lot 3
- [x] 0.6 Harnais : `qa/e2e.spec.ts` (Playwright, fr/en × 1366×768/390×844, captures) — 21 passed / 35 failed (ligne de base, `AUDIT.md` §5)
- [x] 0.7 Harnais : `scripts/smoke_prod.sh <base_url>`
- [x] 0.8 Harnais : `ruff` configuré sur `backend/` — « All checks passed! »
- [x] 0.9 Nettoyage : suppression de `backend/=1.40.0`
- [x] 0.10 Nettoyage : `DEBUG=false` par défaut ; `SECRET_KEY` obligatoire si `DEBUG=false` ; `CORS_ORIGINS` configurable sans `*` + credentials
- [x] CP1 — résumé d'audit + prémisses P1–P5 + choix par défaut (réponses humaines du 22/10/2026 : D3–D8)

## LOT 1 — Supabase via `DATABASE_URL` uniquement

- [x] 1.1 Normalisation de l'URL (`postgres://`, `sslmode=require`), masquage du mot de passe dans les logs
- [x] 1.2 Pool selon le port du pooler (6543 → `NullPool` ; 5432 → `pool_size=2, max_overflow=2`) + documentation du pooler IPv4
- [x] 1.3 Alembic : baseline (stamp sur base existante) + révisions additives ; `create_all` limité à SQLite dev
- [~] 1.4 `backend/sql/supabase_schema.sql` aligné sur l'état final — garde-fou `test_reference_sql_matches_models` (Postgres) ; mis à jour à chaque nouvelle révision
- [x] 1.5 `scripts/db_check.py` (version PG, révision Alembic, comptage par table, URL jamais affichée)
- [x] 1.6 Tests verts sur SQLite puis Postgres jetable (Docker) — SQLite : 31 passed ; Postgres 16 (suite complète + `-m postgres`) : 33 passed + 3 passed
- [ ] CP2 — `alembic upgrade head --sql` présenté avant toute migration de production (reporté après les lots 2, 5 et 6, cf. D9)

## LOT 2 — Stockage des images d'inférence

- [x] 2.1 `MEDIA_DIR/<yyyy>/<mm>/<uuid>.jpg` + miniature `_thumb.jpg` (320 px) ; colonnes taille/dimensions ; déduplication sha256 par utilisateur
- [x] 2.2 `GET /api/media/{path}` authentifié (propriétaire / agronome / admin), anti-traversée, cache privé ; suppression du montage public
- [x] 2.3 Upload : taille max (`MAX_UPLOAD_MB`, 8 Mo), `verify()` Pillow, réencodage JPEG, EXIF retiré sauf GPS (stocké si consentement)
- [x] 2.4 `scripts/media_report.py` (disque, fichiers, orphelins ; `--apply` pour supprimer)
- [x] 2.5 Tests 401/403/200, traversée `../`, déduplication — `test_media.py` (14 tests), `test_media_report.py` ; SQLite 49 passed, Postgres 52 passed ; `smoke_prod.sh` local : 7/8 PASS (GREEN Data attendu au lot 6)

## LOT 3 — Internationalisation FR/EN intégrale

- [ ] 3.1 `i18n.js` étendu (attributs, interpolation, pluriels, `Intl` fr-CM/en-CM XAF), langue appliquée avant le premier rendu, sélecteur dans l'en-tête
- [ ] 3.2 Dictionnaire hiérarchisé + glossaire `docs/i18n_glossary.md`
- [ ] 3.3 Pages : balisage `data-i18n*` de toutes les pages
- [ ] 3.4 JS dynamique : chaînes JS, toasts, Chart.js, popups Leaflet, redessin sur `languageChanged`
- [ ] 3.5 Backend : `Accept-Language`/`lang`, `diseases.json` fr/en, erreurs API, GreenBot dans la langue de l'utilisateur
- [ ] 3.6 `check_i18n.py` vert + Playwright vert dans les deux langues

## LOT 4 — Audit et réparation fonctionnelle

- [ ] 4.1 Corriger chaque ligne « cassé »/« partiel » d'`AUDIT.md` (test ou étape Playwright à chaque fois)
- [x] 4.2 Legacy drone : `drone.html` hors navigation + redirection ; `drone_router` supprimé s'il n'a plus d'appelant — `drone.html`, `drone.css`, `drone_router.py` et `API.drone` supprimés (seul appelant : la page morte) ; `/drone` et `/drone.html` → 307 `/camera` (test)
- [ ] 4.3 Caméra : file d'attente IndexedDB (P1-a), indicateur « N en attente », envoi au retour du réseau, reprise, choix parcelle/mission

## LOT 5 — GREEN Map

- [ ] 5.1 Panneau des parcelles (nom, culture, surface, statut de synchro, dernière analyse, centrage)
- [ ] 5.2 Délimitation : points déplaçables, annuler, ≥ 3 points, « Ajouter ma position » (précision, alerte > 15 m), fond satellite Esri
- [ ] 5.3 Validation : `turf.kinks`, surface/périmètre/centroïde/emprise, chevauchement, région détectée
- [ ] 5.4 Formulaire + IndexedDB `pending_sync` → `POST /api/parcels` (GeoJSON Polygon WGS84 [lng, lat]) → `synced` ; file d'opérations hors ligne (le serveur gagne, brouillon local conservé)
- [ ] 5.5 Quadrillage (1–50 m, défaut 5 m), cellules numérotées, serpentin le long de l'axe long, départ choisi, distance/durée, garde-fou 5 000 cellules
- [ ] 5.6 Table `missions` + exports JSON/GeoJSON + `GET /api/missions/{id}/waypoints` + `docs/rover_mission_contract.md`
- [ ] 5.7 `disease_analyses.mission_id` + `cell_index` ; avancement de mission
- [ ] 5.8 Heatmap choroplèthe par cellule + `GET /api/missions/{id}/heatmap` + légende, filtres, détail de cellule
- [ ] 5.9 Tests géométrie + Playwright hors ligne + scénario complet (6 analyses → heatmap)

## LOT 6 — GREEN Data

- [ ] 6.1 `users.role` (`farmer|agronomist|partner|admin`) + garde d'accès `/api/green-data/*`
- [ ] 6.2 Endpoints d'agrégats SQL (volume, plantes, maladies, matrice, régions, saisonnalité, gravité/confiance, qualité modèle, alertes, maturité) + cache 10 min + index
- [ ] 6.3 Confidentialité : consentement seul, masquage `< 5`, exports sans données personnelles
- [ ] 6.4 Exports CSV + GeoJSON agrégé + encadré méthodologique
- [ ] 6.5 Page `green-data.html` (Chart.js 4.4.0, clair/sombre, états vides, traduite)
- [ ] 6.6 `scripts/seed_demo.py` (`is_demo`), interrupteur démo visible seulement en `DEBUG`
- [ ] 6.7 Tests agrégats/seuil/rôles + Playwright avec et sans données

## LOT 7 — Déploiement o2switch

- [ ] 7.1 Diagnostic serveur (lecture seule, ou liste de commandes pour l'humain)
- [ ] 7.2 `backend/passenger_wsgi.py` (a2wsgi) + vérification du lifespan / chargement paresseux verrouillé
- [ ] 7.3 `requirements-prod.txt` (onnxruntime, sans torch) + `INFERENCE_BACKEND=onnx|torch`
- [ ] 7.4 Test de parité ONNX ⇄ PyTorch (≥ 20 images, top-1 identique, |Δp| < 1e-3) + temps et RAM
- [ ] 7.5 `.env.example` complet, `.htaccess`, `docs/DEPLOY_O2SWITCH.md`, `scripts/smoke_prod.sh`
- [ ] CP3 — aucune modification serveur sans validation ; `smoke_prod.sh` après déploiement

## LOT 8 — Cohérence globale et revue

- [ ] 8.1 Parcours de référence Playwright FR + EN
- [ ] 8.2 Cohérence (navigation, en-tête, langue, thème, liens, états, 390 px, contraste AA)
- [ ] 8.3 Sous-agent relecteur indépendant → corrections → seconde passe
- [ ] 8.4 `README.md` + entrée datée dans `MODIFICATIONS.md`

---

## Décisions

| # | Décision | Justification |
|---|---|---|
| D3 | P1 : file d'attente IndexedDB côté navigateur (a) ; envoi direct par le Pi (c) **documenté seulement** (contrat d'API, pas de code serveur ni rover) | Choix humain au CP1. |
| D4 | P2 : `mission_id` + `cell_index` sur chaque analyse, GPS facultatif, rattachement serveur par point-dans-polygone | Défaut accepté (pas de GPS garanti sur le rover). |
| D5 | P3 : IndexedDB = copie hors ligne ; le serveur reste la source de vérité | Défaut accepté. |
| D6 | P4 : ONNX Runtime en production, PyTorch en dev seulement, après test de parité | Défaut accepté (limites LVE du mutualisé). |
| D7 | P5 : **frontend conservé sur Vercel** ; `vercel.json` réécrit `/api/*` vers le domaine o2switch (même origine vue du navigateur, donc pas de CORS nécessaire) ; `CORS_ORIGINS` limité au domaine Vercel en secours ; images compressées côté client avant envoi (limite de corps des proxys) ; images affichées via `fetch` + jeton → `blob:` (une balise `<img>` ne porte pas l'en-tête `Authorization`) | Choix humain au CP1. |
| D8 | Contenu inventé retiré (notes, badges « vérifié », marques réelles, moyennes régionales, chiffres marketing) ; catalogue marqué « aperçu, prix indicatifs » ; benchmark comparé à l'historique propre de l'utilisateur. YOLO retiré du README (travail futur, `best.pt` conservé) | Choix humain au CP1. |
| D9 | CP2 présenté une seule fois, quand les révisions additives des lots 2, 5 et 6 existent ; en production, la seule opération sera `alembic stamp 0001_baseline` puis `alembic upgrade head` | La production est déjà au niveau de la baseline (vérifié : `models.py` ⇄ SQL de `36d4768` sans écart sur Postgres 16) ; une seule fenêtre de migration validée. |
| D10 | `models.py` aligné sur le schéma Supabase réel (identity, jsonb, `ON DELETE CASCADE`, `NOT NULL`, noms d'index) | Sans ça, Alembic aurait généré des différences parasites ; `compare_metadata` = [] est maintenant testé. |
| D11 | Images servies par `GET /api/media/{path}` avec en-tête `Authorization` **ou** URL signée HMAC (utilisateur + expiration 1–2 h) renvoyée par l'API | Une balise `<img>` (historique, popups Leaflet, miniatures de heatmap) ne peut pas porter l'en-tête ; sans signature ni jeton : 401. |
| D12 | Toutes les métadonnées EXIF sont retirées du fichier ; la position GPS EXIF n'est stockée en base que si `users.location_consent` ; une position fournie explicitement l'emporte | Vie privée par défaut ; consentement explicite et distinct de `dataset_consent`. |
| D13 | Images stockées réduites à 2048 px de grand côté, JPEG q88 | Le modèle travaille en 224 px ; économise le quota disque du mutualisé. |
| D14 | `users.role` créé dès la révision 0002 (utilisé par l'accès aux médias), garde GREEN Data au lot 6 | Une seule migration pour les colonnes utilisateur. |
| D15 | Les anciens chemins publics `/assets/captures/...` ne sont plus servis | Ils étaient publics ; `media_report.py` les signale. |
| D2 | Dépendances de dev dans `backend/requirements-dev.txt` (pytest, ruff, onnx) | Ne pas alourdir le serveur de production. |
| D1 | Clone de `Umar-Elhaj/Greennew` dans `Greennew/` (et non `TCHOUANANG-dimitri/GREEN`) | Le prompt maître cible ce dépôt ; HEAD distant = `36d4768`, identique au contexte vérifié. |

## Blocages

_Aucun pour l'instant._

## Actions humaines en attente

1. Fournir le domaine public de l'API sur o2switch (pour la réécriture `/api/*` de `vercel.json`, lot 7).
2. T16 : faire valider par un agronome la correspondance classe du modèle → fiche maladie (lot 4).

## Écarts constatés par rapport au contexte fourni

- `translations.json` : 241 clés feuilles par langue (16 sections de premier niveau), et non 16 clés ; mais `i18n.js` n'est chargé que sur 3 pages sur 15.
- `Models/` pèse environ 78 Mo (et non 116 Mo).
- Aucun alias SSH `green-o2switch` (`~/.ssh/config` absent) : le diagnostic o2switch se fera sous forme de commandes à exécuter par l'humain.
- Navigateurs Playwright installés (`npx playwright install chromium`, Playwright 1.64.1).
- Aucun `.env` local : aucune connexion à Supabase de production n'est possible depuis cette machine sans action humaine (cohérent avec CP2).
- Docker disponible : Postgres jetable possible pour les tests du lot 1.

## Commandes de vérification

```bash
# depuis la racine du dépôt
.venv/bin/pytest backend/tests -q
.venv/bin/ruff check --config backend/pyproject.toml backend scripts
# Postgres jetable (Docker) :
#   docker run -d --rm --name green-pg-test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=green_test -p 55432:5432 postgres:16-alpine
#   TEST_POSTGRES_URL=postgresql://postgres:test@localhost:55432/green_test?sslmode=disable \
#   TEST_DATABASE_URL=postgresql://postgres:test@localhost:55432/green_suite?sslmode=disable \
#     .venv/bin/pytest backend/tests -m "not slow"
.venv/bin/python scripts/db_check.py
.venv/bin/python scripts/check_i18n.py
npx playwright test -c qa
```
