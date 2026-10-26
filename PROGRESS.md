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

- [x] 3.1 `i18n.js` étendu (attributs, interpolation, pluriels, `Intl` fr-CM/en-CM XAF), langue appliquée avant le premier rendu, sélecteur dans l'en-tête
- [x] 3.2 Dictionnaire hiérarchisé + glossaire `docs/i18n_glossary.md` — sources `frontend/i18n/<ns>.json` → `js/translations.js` (`scripts/build_i18n.py`), 754 clés/langue
- [x] 3.3 Pages : balisage `data-i18n*` de toutes les pages (14/14 ; GREEN Data au lot 6)
- [x] 3.4 JS dynamique : chaînes JS, toasts, Chart.js, popups Leaflet, redessin sur `languageChanged`
- [x] 3.5 Backend : `Accept-Language`/`lang`, `diseases.json` fr/en, erreurs API, GreenBot dans la langue de l'utilisateur
- [x] 3.6 `check_i18n.py` vert + Playwright vert dans les deux langues — `check_i18n: 889 keys/lang, 0 problem(s)` ; Playwright 70 passed (56 balayages + 14 parcours)

## LOT 4 — Audit et réparation fonctionnelle

- [x] 4.1 Corriger chaque ligne « cassé »/« partiel » d'`AUDIT.md` (test ou étape Playwright à chaque fois)
- [x] 4.2 Legacy drone : `drone.html` hors navigation + redirection ; `drone_router` supprimé s'il n'a plus d'appelant — `drone.html`, `drone.css`, `drone_router.py` et `API.drone` supprimés (seul appelant : la page morte) ; `/drone` et `/drone.html` → 307 `/camera` (test)
- [x] 4.3 Caméra : file d'attente IndexedDB (P1-a), indicateur « N en attente », envoi au retour du réseau, reprise, choix parcelle/mission/cellule — preuves : `qa/flows.spec.ts` « camera: photos imported offline… », « captures are tagged with the mission and the cell »

## LOT 5 — GREEN Map

- [x] 5.1 Panneau des parcelles (nom, culture, surface, statut de synchro, dernière analyse, centrage)
- [x] 5.2 Délimitation : points déplaçables, annuler, ≥ 3 points, « Ajouter ma position » (précision, alerte > 15 m), fond satellite Esri
- [x] 5.3 Validation : `turf.kinks`, surface/périmètre/centroïde/emprise, chevauchement, région détectée
- [x] 5.4 Formulaire + IndexedDB `pending_sync` → `POST /api/parcels` (GeoJSON Polygon WGS84 [lng, lat]) → `synced` ; file d'opérations hors ligne (le serveur gagne, brouillon local conservé)
- [x] 5.5 Quadrillage (1–50 m, défaut 5 m), cellules numérotées, serpentin le long de l'axe long, départ choisi, distance/durée, garde-fou 5 000 cellules
- [x] 5.6 Table `missions` + exports JSON/GeoJSON + `GET /api/missions/{id}/waypoints` + `docs/rover_mission_contract.md`
- [x] 5.7 `disease_analyses.mission_id` + `cell_index` ; avancement de mission
- [x] 5.8 Heatmap choroplèthe par cellule + `GET /api/missions/{id}/heatmap` + légende, filtres, détail de cellule
- [x] 5.9 Tests géométrie + Playwright hors ligne + scénario complet (6 analyses → heatmap) — `test_geo.py` (21), `test_parcels.py` (11), `test_missions.py` (5) ; flows « GREEN Map: … » (3)

## LOT 6 — GREEN Data

- [x] 6.1 `users.role` (`farmer|agronomist|partner|admin`) + garde d'accès `/api/green-data/*`
- [x] 6.2 Endpoints d'agrégats SQL (volume, plantes, maladies, matrice, régions, saisonnalité, gravité/confiance, qualité modèle, alertes, maturité) + cache 10 min + index
- [x] 6.3 Confidentialité : consentement seul, masquage `< 5`, exports sans données personnelles
- [x] 6.4 Exports CSV + GeoJSON agrégé + encadré méthodologique
- [x] 6.5 Page `green-data.html` (Chart.js 4.4.0, clair/sombre, états vides, traduite)
- [x] 6.6 `scripts/seed_demo.py` (`is_demo`), interrupteur démo visible seulement en `DEBUG`
- [x] 6.7 Tests agrégats/seuil/rôles + Playwright avec et sans données — `test_green_data.py` (9, SQLite + Postgres) ; balayage `green-data` (sans données) ; flow « GREEN Data: farmers are refused, partners see aggregates »

## LOT 7 — Déploiement o2switch

- [x] 7.1 Diagnostic serveur (lecture seule, ou liste de commandes pour l'humain) — pas d'alias SSH : commandes et critères dans `docs/DEPLOY_O2SWITCH.md` §1, avec le modèle de demande au support
- [x] 7.2 `backend/passenger_wsgi.py` (a2wsgi) + vérification du lifespan / chargement paresseux verrouillé
- [x] 7.3 `requirements-prod.txt` (onnxruntime, sans torch) + `INFERENCE_BACKEND=onnx|torch`
- [x] 7.4 Test de parité ONNX ⇄ PyTorch (≥ 20 images, top-1 identique, |Δp| < 1e-3) + temps et RAM — 24/24 top-1, max |Δp| 3,19e-06 ; ONNX 19 ms/image, pic 177 Mo ; PyTorch 48 ms/image, pic 437 Mo
- [x] 7.5 `.env.example` complet, `.htaccess`, `docs/DEPLOY_O2SWITCH.md`, `scripts/smoke_prod.sh`
- [ ] CP3 — aucune modification serveur sans validation ; `smoke_prod.sh` après déploiement (répétition locale : environnement virtuel propre avec `requirements-prod.txt` seul, servi par `passenger_wsgi` via WSGI, `DEBUG=false` → smoke 8/8 PASS, `/docs` 404)

## LOT 8 — Cohérence globale et revue

- [x] 8.1 Parcours de référence Playwright FR + EN — `qa/journey.spec.ts` : 2 passed (deux exécutions) ; a révélé le bug de normalisation du téléphone (corrigé)
- [x] 8.2 Cohérence (navigation, en-tête, langue, thème, liens, états, 390 px, contraste AA) — `qa/consistency.spec.ts` (30 : 15 pages × clair/sombre, axe-core color-contrast), balayage à 390 px ; Playwright total 105 + 2 parcours
- [ ] 8.3 Sous-agent relecteur indépendant → corrections → seconde passe — 1re passe : 3 bloquants (confidentialité GREEN Data), 7 majeurs, 12 mineurs. Corrigés : B1–B3 (`b86de9e`, `d21bfc8`), M1 `d8b394a`, M2 `6297e1b`, M3–M5 `8803f1a`, M6 faux positif (attribut présent dans le HTML ; doc corrigée `e6cc218`), M7 `9ec2c0c`, mineurs m1/m2/m4–m7/m9/m11/m12 `6132af3` `a497601`, m3/m8/m10 documentés (README §11). Harnais : pytest 140 + 2 lents, PG 143, Playwright 111, ruff et i18n propres. Seconde passe : en cours
- [x] 8.4 `README.md` + entrée datée dans `MODIFICATIONS.md` — README réécrit (architecture réelle, variables, lancement, tests, déploiement, limites) ; « Modification 2 » datée du 22/10/2026

## LOT 9 — Tout sur o2switch : base MySQL/MariaDB, backend, frontend (26/10/2026, sur `main`)

- [x] 9.1 `git pull` de `origin/main` (déjà à `a0f4ca7`) ; modification locale du guide (valeurs du compte o2switch) conservée et intégrée
- [x] 9.2 Connexion MySQL : `mysql://`/`mariadb://` → `mysql+pymysql` + `utf8mb4`, session UTC + mode strict, pool 2 + 2 recyclé à 280 s, socket Unix accepté — `test_db_url.py` (13)
- [x] 9.3 Types portables (`db_types.py`) dans les modèles et les migrations ; tables InnoDB/utf8mb4 — `compare_metadata` = [] sur MariaDB 10.6 et 11.4
- [x] 9.4 `backend/sql/mysql_schema.sql` (import dans une base vide, `alembic_version` renseignée) — `test_mysql_reference_sql_matches_models` ; import double sans erreur avec le client `mariadb`
- [x] 9.5 `scripts/copy_database.py` (Supabase → MySQL, une transaction, essai à blanc) — `test_copy_database.py` (SQLite + MySQL) ; essai réel PostgreSQL 16 (schéma 36d4768) → MariaDB 10.6
- [x] 9.6 Frontend servi par Apache : `deploy/o2switch/publish_frontend.sh` (liens symboliques) + `htaccess-snippet.conf` (site complet) — vérifié dans un Apache 2.4 local ; `smoke_prod.sh` contrôle aussi pages, fichiers statiques et fichiers privés
- [x] 9.7 Guide d'intégration réécrit (préparation → base → backend → frontend → exploitation), `docs/DEPLOY_O2SWITCH.md`, `README.md`, `MODIFICATIONS.md` (Modification 3)
- [x] 9.8 Vérifications : SQLite 149 passed ; MariaDB 10.6 et 11.4 : 152 passed chacune (suite complète + tests `mysql`) ; PostgreSQL 16 : 152 passed (suite + tests `postgres`) ; ruff propre
- [ ] CP2/CP3 — création de la base et de l'application sur o2switch par l'humain, en suivant le guide

---

## Décisions

| # | Décision | Justification |
|---|---|---|
| D3 | P1 : file d'attente IndexedDB côté navigateur (a) ; envoi direct par le Pi (c) **documenté seulement** (contrat d'API, pas de code serveur ni rover) | Choix humain au CP1. |
| D4 | P2 : `mission_id` + `cell_index` sur chaque analyse, GPS facultatif, rattachement serveur par point-dans-polygone | Défaut accepté (pas de GPS garanti sur le rover). |
| D5 | P3 : IndexedDB = copie hors ligne ; le serveur reste la source de vérité | Défaut accepté. |
| D6 | P4 : ONNX Runtime en production, PyTorch en dev seulement, après test de parité | Défaut accepté (limites LVE du mutualisé). |
| D7 | *(remplacée par D38 le 26/10/2026)* P5 : **frontend conservé sur Vercel** ; `vercel.json` réécrit `/api/*` vers le domaine o2switch (même origine vue du navigateur, donc pas de CORS nécessaire) ; `CORS_ORIGINS` limité au domaine Vercel en secours ; images compressées côté client avant envoi (limite de corps des proxys) ; images affichées via `fetch` + jeton → `blob:` (une balise `<img>` ne porte pas l'en-tête `Authorization`) | Choix humain au CP1. |
| D8 | Contenu inventé retiré (notes, badges « vérifié », marques réelles, moyennes régionales, chiffres marketing) ; catalogue marqué « aperçu, prix indicatifs » ; benchmark comparé à l'historique propre de l'utilisateur. YOLO retiré du README (travail futur, `best.pt` conservé) | Choix humain au CP1. |
| D9 | CP2 présenté une seule fois, quand les révisions additives des lots 2, 5 et 6 existent ; en production, la seule opération sera `alembic stamp 0001_baseline` puis `alembic upgrade head` | La production est déjà au niveau de la baseline (vérifié : `models.py` ⇄ SQL de `36d4768` sans écart sur Postgres 16) ; une seule fenêtre de migration validée. |
| D10 | `models.py` aligné sur le schéma Supabase réel (identity, jsonb, `ON DELETE CASCADE`, `NOT NULL`, noms d'index) | Sans ça, Alembic aurait généré des différences parasites ; `compare_metadata` = [] est maintenant testé. |
| D11 | Images servies par `GET /api/media/{path}` avec en-tête `Authorization` **ou** URL signée HMAC (utilisateur + expiration 1–2 h) renvoyée par l'API | Une balise `<img>` (historique, popups Leaflet, miniatures de heatmap) ne peut pas porter l'en-tête ; sans signature ni jeton : 401. |
| D12 | Toutes les métadonnées EXIF sont retirées du fichier ; la position GPS EXIF n'est stockée en base que si `users.location_consent` ; une position fournie explicitement l'emporte | Vie privée par défaut ; consentement explicite et distinct de `dataset_consent`. |
| D13 | Images stockées réduites à 2048 px de grand côté, JPEG q88 | Le modèle travaille en 224 px ; économise le quota disque du mutualisé. |
| D14 | `users.role` créé dès la révision 0002 (utilisé par l'accès aux médias), garde GREEN Data au lot 6 | Une seule migration pour les colonnes utilisateur. |
| D15 | Les anciens chemins publics `/assets/captures/...` ne sont plus servis | Ils étaient publics ; `media_report.py` les signale. |
| D16 | Lots 3 et 4 menés ensemble, page par page (un commit par page) | Chaque page n'est ouverte qu'une fois ; le contenu inventé (D8) est supprimé au lieu d'être traduit. |
| D17 | Dictionnaire chargé en script synchrone dans `<head>` (`translations.js` généré depuis `frontend/i18n/*.json`) ; page masquée jusqu'à la traduction (filet de sécurité de 1,5 s) | Pas de flash de texte non traduit ; fonctionne hors ligne (GREEN Map). |
| D18 | Erreurs serveur écrites en anglais et traduites par un gestionnaire d'exceptions selon `Accept-Language`/`?lang` ; 422 aplati en une phrase | Un seul catalogue ; aucun routeur à modifier pour la langue ; test qui échoue si un message levé n'a pas de traduction. |
| D19 | Fiche terrain reconstruite à la lecture dans la langue du lecteur (`knowledge.py`) ; la colonne `fiche_terrain` reste un instantané | Une analyse faite en français se relit en anglais. |
| D20 | `severity` = « niveau d'alerte » fondé sur la confiance, `none` pour une plante saine (T4) | Le classifieur ne mesure pas l'étendue des dégâts ; l'interface le dit. |
| D21 | Correspondance classe → fiche corrigée (T16) et fiches ajoutées (rayure, helminthosporiose, mildiou du maïs, jaunissement) ; pourriture des cabosses à *Moniliophthora* (absente d'Afrique) remplacée par *P. megakarya* | Erreurs factuelles qui menaient au mauvais traitement ; validation agronome toujours demandée. |
| D22 | Marché = catalogue de types d'intrants génériques à prix indicatifs ; marques, photos de produits (licence inconnue), panier et formulaire factice supprimés | D8. |
| D23 | Benchmark → « Ma progression » (historique propre, `GET /api/dashboard/progress`) | D8 ; aucune moyenne inventée. |
| D24 | `GEMINI_MODEL` configurable, défaut `gemini-3.1-flash-lite` (vérifié stable sur ai.google.dev le 22/10/2026 ; `gemini-3.5-flash-lite` recommandé pour les nouveaux projets) | Pas de changement de comportement sans décision humaine. |
| D25 | Quadrillage et parcours calculés par le serveur (Python pur), grille orientée selon l'axe long, détours par des cellules de transit ; Turf côté client seulement pour valider le tracé hors ligne | Une seule implémentation testable (surface, nombre de cellules, absence de saut) ; l'aperçu de grille demande le réseau. |
| D26 | Région détectée côté serveur par point-dans-polygone (geoBoundaries ADM1 Cameroun, CC BY 3.0, `backend/data/cameroon_regions.json`) | Les boîtes englobantes d'origine se chevauchaient (Buea → « Littoral »). |
| D27 | Cellules numérotées à partir de 1 (affichage = stockage) ; cellule « non analysée » = aucune analyse dans la cellule pour les filtres choisis | Lisible pour l'exploitant et le rover. |
| D28 | Palette des graphiques validée (`dataviz/validate_palette.js`, clair et sombre) : couleur fixe par classe de maladie, bleu séquentiel pour les grandeurs, palette de statut réservée aux niveaux d'alerte ; la heatmap GREEN Map passe d'un arc-en-ciel à une rampe mono-teinte | Les couleurs suivent l'entité (un filtre ne repeint rien) ; lisible pour les daltoniens. |
| D29 | `scripts/set_role.py` pour attribuer les rôles (aucune interface d'administration) ; `POST /api/analysis/{id}/verify` pour les agronomes | Sans eux, aucun compte partenaire ni aucune mesure de qualité du modèle n'est possible. |
| D30 | Base SQLite de développement migrée par Alembic au démarrage (et non `create_all`) | Un `green.db` existant recevait sinon le nouveau code sans les nouvelles colonnes. |
| D31 | Pas de préchargement du modèle sous Passenger (lifespan non exécuté par a2wsgi) ; chargement paresseux protégé par un verrou ; `WARMUP=1` pour précharger | Chaque processus Passenger coûterait ~180 Mo ; limites LVE. |
| D32 | `vercel.json` généré par `scripts/configure_vercel.py <origine-api>` (réécriture `/api/*`, redirections `/drone`, en-têtes de sécurité) | Le domaine o2switch n'est pas encore connu ; pas de valeur fictive dans un fichier de production. |
| D33 | Contrôle de divulgation GREEN Data : publication si ≥ 5 analyses **et** ≥ 5 exploitants ; suppression secondaire (une cellule masquée seule dans une ligne ou colonne masque la plus petite visible) ; taux masqué si le total ou l'un des deux côtés l'est ; les zéros sont publics | Revue 8.3 (B1/B2) : un seuil sur les seules analyses laissait recalculer les cellules masquées par différence. |
| D34 | Régions : uniquement les 10 noms officiels (alias anglais et sans accents acceptés), toute autre valeur stockée est publiée « unknown » | Revue 8.3 (B3) : du texte libre (adresses, noms) était publié. |
| D35 | Retrait du consentement ou compte désactivé : les analyses passées sortent aussi des statistiques (filtre à la lecture, aucune donnée modifiée) | Cohérent avec « modifiable à tout moment » de l'inscription ; pas de requête destructive. |
| D36 | Files hors ligne : une base IndexedDB par compte (`green-parcels-u<id>`, `green-uploads-u<id>`) | Appareils partagés : rien n'est montré ni envoyé au nom d'un autre compte. |
| D37 | `/api/camera/connect` et `/capture` (le serveur récupère une IP quelconque) limités à DEBUG | SSRF sur l'hébergement mutualisé ; aucun appelant dans le frontend. |
| D38 | Tout sur o2switch, un seul domaine (`api-green.gitingeniering.com`) : base MySQL/MariaDB d'o2switch, API sous Passenger, pages servies par Apache ; Vercel abandonné (fichiers gardés) | Décision humaine du 26/10/2026 ; PostgreSQL exclu sur o2switch. |
| D39 | Pilote PyMySQL (et non mysqlclient) | 100 % Python : le compilateur est bloqué par défaut sur o2switch. |
| D40 | Sur MySQL : `DOUBLE`, `DATETIME(6)`, `MEDIUMTEXT`, InnoDB `utf8mb4_unicode_ci` via `with_variant` (`db_types.py`) ; SQL inchangé sur SQLite/PostgreSQL | `FLOAT` simple précision (GPS), perte des microsecondes (ordre du chat), `TEXT` limité à 64 Ko. |
| D41 | Session MySQL en UTC et en mode SQL strict explicite (`init_command`) | Même comportement quelle que soit la configuration du serveur (MariaDB ou MySQL 8). |
| D42 | Migrations existantes modifiées seulement pour MySQL (aucune base MySQL déployée) plutôt qu'une nouvelle révision | Le SQL PostgreSQL/SQLite est identique (tests) ; une base MySQL neuve passe 0001 → 0004. |
| D43 | Frontend publié par **liens symboliques** dans la racine du domaine, FastAPI en secours | Apache sert les fichiers statiques sans processus Passenger (limites LVE) ; un `git pull` suffit. |
| D44 | Reprise des données Supabase par script (`copy_database.py`), base cible vide et à jour, une transaction ; facultative | Pas de conversion de dump PostgreSQL → MySQL à la main ; identifiants et chemins d'images conservés. |
| D2 | Dépendances de dev dans `backend/requirements-dev.txt` (pytest, ruff, onnx) | Ne pas alourdir le serveur de production. |
| D1 | Clone de `Umar-Elhaj/Greennew` dans `Greennew/` (et non `TCHOUANANG-dimitri/GREEN`) | Le prompt maître cible ce dépôt ; HEAD distant = `36d4768`, identique au contexte vérifié. |

## Blocages

_Aucun pour l'instant._

## Actions humaines en attente

1. Suivre `GUIDE_INTEGRATION_O2SWITCH.md` : base MySQL (étapes 7 à 10), application Python (11 à 19), frontend (20), puis supprimer ou rediriger le projet Vercel (21).
2. Décider si les données de l'ancienne base Supabase sont reprises (étape 15) ; si oui, reprendre aussi l'ancienne `SECRET_KEY` et les images.
3. T16 : faire valider par un agronome la correspondance classe du modèle → fiche maladie (lot 4).

## Risques et notes de vérification

- Le balayage Playwright dépend de CDN externes (Google Fonts, Chart.js) : une coupure réseau donne un faux échec (`ERR_CONNECTION_RESET`), relancer.
- Le cache des navigateurs Playwright (`~/.cache/ms-playwright`) a disparu une fois pendant la session : `npx playwright install chromium` le rétablit.
- GreenBot avec une vraie clé n'est testé que côté backend (LLM simulé) ; aucune clé n'est disponible ici.
- Les tests Postgres exigent `?sslmode=disable` (le conteneur local n'a pas TLS ; `sslmode=require` est ajouté sinon).
- La suppression d'artefact `backend/test-results/.last-run.json` est entrée dans le commit `6132af3` (et non `a497601`).

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
# MariaDB jetable (Docker) — base de production :
#   docker run -d --rm --name green-maria-test -e MARIADB_ROOT_PASSWORD=test -e MARIADB_DATABASE=green_suite -p 53306:3306 mariadb:10.6
#   TEST_DATABASE_URL=mysql://root:test@127.0.0.1:53306/green_suite \
#   TEST_MYSQL_URL=mysql://root:test@127.0.0.1:53306/green_suite \
#     .venv/bin/pytest backend/tests -m "not slow and not postgres"
# Postgres jetable (Docker) :
#   docker run -d --rm --name green-pg-test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=green_test -p 55432:5432 postgres:16-alpine
#   TEST_POSTGRES_URL=postgresql://postgres:test@localhost:55432/green_test?sslmode=disable \
#   TEST_DATABASE_URL=postgresql://postgres:test@localhost:55432/green_suite?sslmode=disable \
#     .venv/bin/pytest backend/tests -m "not slow"
.venv/bin/python scripts/db_check.py
.venv/bin/python scripts/check_i18n.py
npx playwright test -c qa
```
