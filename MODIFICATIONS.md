# Journal des modifications — GREEN

Ce document liste chaque modification apportée au projet, ses raisons, et ce qu'il faut savoir pour la suite.
Les entrées sont classées de la plus récente à la plus ancienne.

---

## Modification 3 — Tout sur o2switch : base MySQL/MariaDB, backend et frontend

**Date :** 26/10/2026 · **Branche :** `main` · Suivi : `PROGRESS.md` (lot 9, décisions D38 à D44).

### Contexte et raison

L'hébergement change de décision : **tout est désormais hébergé chez o2switch** (offre Pro), sur un seul domaine (`api-green.gitingeniering.com`) :
- **base de données** : la base MySQL/MariaDB fournie par o2switch. PostgreSQL n'est pas utilisé sur o2switch, et Supabase n'est plus la base de production ;
- **backend** : l'API FastAPI sous Passenger (inchangé dans son principe) ;
- **frontend** : les pages ne sont plus sur Vercel ; Apache les sert depuis la racine du domaine.

Une seule origine, une seule facture, et la base ne quitte plus la machine de l'application (plus de dépendance au port sortant du *pooler* Supabase, qui risquait d'être fermé).

### Ce qui change pour les utilisateurs

- **Adresse.** L'application s'ouvre sur `https://api-green.gitingeniering.com` ; l'ancienne adresse Vercel doit être supprimée ou redirigée (guide, étape 21).
- **Données.** Les comptes, parcelles, analyses et conversations existants peuvent être repris tels quels (mêmes identifiants, mêmes liens d'images) avec `scripts/copy_database.py`. Aucune fonction ne change.

### Base de données

- **Connexion.** `DATABASE_URL` accepte `mysql://` (et `mariadb://`) : l'application utilise le pilote **PyMySQL** (100 % Python, rien à compiler sur le mutualisé), ajoute `charset=utf8mb4`, ouvre chaque session en **UTC** et en **mode SQL strict**, garde un petit pool (2 + 2 par processus Passenger) recyclé toutes les 280 s. Connexion recommandée par le **socket Unix** du serveur (`?unix_socket=…`).
- **Types.** Pour que MySQL se comporte comme SQLite et PostgreSQL : `DOUBLE` au lieu de `FLOAT` (simple précision : les positions GPS perdaient des décimètres), `DATETIME(6)` (sinon les microsecondes disparaissent et deux messages du chat enregistrés dans la même seconde ne se trient plus), `MEDIUMTEXT` (`TEXT` s'arrête à 64 Ko), tables InnoDB en `utf8mb4_unicode_ci` (accents et emojis). Ces types sont regroupés dans `backend/db_types.py` et utilisés par les modèles et les migrations. Sur SQLite et PostgreSQL, le SQL produit est inchangé.
- **Schéma.** Les migrations Alembic créent la base MySQL complète (`alembic upgrade head`). Le même schéma est livré en SQL commenté, importable dans une base vide (`mysql` ou phpMyAdmin) : `backend/sql/mysql_schema.sql`. Il renseigne `alembic_version`, si bien que les mises à jour suivantes passent par Alembic.
- **Reprise des données.** `scripts/copy_database.py` copie l'ancienne base (Supabase, lue seulement) vers la base MySQL : base cible à jour et vide obligatoire, une seule transaction, identifiants conservés, colonnes absentes de la source à leur valeur par défaut, essai à blanc par défaut. Les URL viennent de l'environnement et ne sont jamais affichées.
- **Outils.** `scripts/db_check.py` reconnaît MySQL (version, comptage des tables avec la bonne syntaxe de noms).

### Frontend

- `deploy/o2switch/publish_frontend.sh` lie les fichiers de `frontend/` dans la racine du domaine : Apache les sert lui-même, seuls `/api/*` et les adresses de pages passent par Python (moins de processus Passenger consommés). Ce sont des liens : un `git pull` met le site à jour. L'API continue de servir les mêmes fichiers en secours.
- `deploy/o2switch/htaccess-snippet.conf` couvre maintenant le site entier : pas de liste des dossiers, en-têtes de sécurité aussi sur les fichiers statiques, pages et scripts revalidés à chaque visite (`no-cache`, une mise à jour est visible tout de suite), images en cache une semaine, `noindex` réservé à `/api/`, compression, fichiers privés refusés. Vérifié dans un Apache 2.4 local.
- `frontend/vercel.json` et `scripts/configure_vercel.py` sont conservés pour un éventuel retour à Vercel, mais ne servent plus.

### Fichiers ajoutés

| Fichier | Rôle |
|---|---|
| `backend/db_types.py` | Types de colonnes communs (JSON, DOUBLE, DATETIME(6), MEDIUMTEXT) et options des tables MySQL |
| `backend/sql/mysql_schema.sql` | Schéma de production MySQL/MariaDB, importable dans une base vide |
| `scripts/copy_database.py` | Reprise unique des données de Supabase vers MySQL |
| `deploy/o2switch/publish_frontend.sh` | Publication du frontend dans la racine du domaine |
| `backend/tests/test_copy_database.py` | Tests de la reprise des données (SQLite, et MySQL avec `TEST_MYSQL_URL`) |

### Fichiers modifiés

| Fichier | Modification |
|---|---|
| `backend/db_url.py` | URL MySQL (`mysql+pymysql`, `utf8mb4`), session UTC et stricte, pool, avertissement si l'hôte MySQL est distant |
| `backend/models.py`, `backend/migrations/versions/0001_baseline.py`, `0003_map_missions.py` | Types de `db_types.py`, options InnoDB/utf8mb4, `CURRENT_TIMESTAMP(6)` sur MySQL |
| `backend/config.py`, `backend/database.py`, `backend/main.py`, `.env.example` | Commentaires et exemple de `DATABASE_URL` pour o2switch ; `CORS_ORIGINS` vide (une seule origine) |
| `backend/requirements-prod.txt` | `PyMySQL` remplace `psycopg2-binary` |
| `backend/requirements.txt` | `PyMySQL` ajouté (`psycopg2-binary` conservé pour la reprise et les tests PostgreSQL) |
| `backend/tests/*`, `backend/pyproject.toml` | Tests MySQL (URL, migrations ⇄ modèles, fichier SQL de référence, SQL hors ligne), marqueur `mysql` |
| `backend/sql/supabase_schema.sql` | En-tête : ancienne base |
| `scripts/db_check.py` | Prise en charge de MySQL |
| `scripts/smoke_prod.sh` | Vérifie aussi les pages, les fichiers statiques et le refus des fichiers privés |
| `deploy/o2switch/htaccess-snippet.conf` | Règles pour le site complet |
| `GUIDE_INTEGRATION_O2SWITCH.md` | Réécrit : préparation, puis **base de données → backend → frontend**, puis mise en service et exploitation (sauvegardes `mysqldump`, mises à jour, dépannage MySQL) |
| `docs/DEPLOY_O2SWITCH.md`, `README.md`, `PROGRESS.md` | Nouvelle architecture |

### À savoir pour la suite

1. **Ordre d'installation.** Base de données, puis backend, puis frontend : l'API refuse de démarrer sans base, et les pages appellent l'API du même domaine.
2. **Évolutions du schéma.** Une nouvelle révision Alembic doit mettre à jour `backend/sql/mysql_schema.sql` (y compris la ligne `alembic_version`) ; le test `test_mysql_reference_sql_matches_models` le vérifie quand `TEST_MYSQL_URL` est défini. En production, les mises à jour passent toujours par `alembic upgrade head`, jamais par un nouvel import.
3. **Tests sur MariaDB.** `docker run -d --rm -p 53306:3306 -e MARIADB_ROOT_PASSWORD=test -e MARIADB_DATABASE=green_suite mariadb:10.6`, puis `TEST_DATABASE_URL` et `TEST_MYSQL_URL` = `mysql://root:test@127.0.0.1:53306/green_suite`.
4. **Vérifications.** SQLite : 149 tests ; MariaDB 10.6 et 11.4 : suite complète + tests `mysql` (152) ; PostgreSQL : suite complète + tests `postgres` (non-régression) ; ruff sans erreur. Copie Supabase → MariaDB essayée sur une base PostgreSQL au schéma de 36d4768 (accents, emojis, JSON, microsecondes, `AUTO_INCREMENT` repris).
5. **À faire par un humain.** Créer la base et l'application sur o2switch en suivant le guide ; décider si les données de Supabase sont reprises (étape 15) ; supprimer ou rediriger le projet Vercel.

---

## Modification 2 — Traduction intégrale, GREEN Map, GREEN Data, images privées, Supabase, déploiement o2switch

**Date :** 22/10/2026 · **Branche :** `feat/green-map-data-o2switch` · Suivi détaillé : `PROGRESS.md` (décisions D1 à D32), état des lieux : `AUDIT.md`.

### Contexte et raison

Le chantier suit un plan en 9 lots (0 à 8). Il couvre :
- la traduction complète français/anglais ;
- la réparation des fonctionnalités cassées ou trompeuses relevées par l'audit ;
- la cartographie des parcelles avec quadrillage pour le rover et carte des résultats ;
- les statistiques pour les partenaires ;
- la protection des images ;
- la base Supabase pilotée par la seule variable `DATABASE_URL` ;
- le déploiement de l'API (inférence comprise) sur un hébergement mutualisé o2switch.

Décisions humaines prises au point de contrôle CP1 :
- **Rover.** Les images passent par une file d'attente dans le navigateur. L'envoi direct par le Raspberry Pi est seulement documenté.
- **Hébergement.** Le frontend reste sur Vercel et relaie `/api/*` vers o2switch.
- **Contenu.** Le contenu inventé est retiré (marché, benchmark), ainsi que la détection YOLO du README.

### Ce qui change pour les utilisateurs

- **Langue.** Toute l'interface est en français ou en anglais (bouton FR | EN dans l'en-tête, sans rechargement) : les messages du serveur, la fiche terrain, la bibliothèque des maladies et les réponses de GreenBot suivent la langue choisie.
- **Résultats.** Un résultat est présenté comme une **maladie probable**, jamais comme un diagnostic. Une plante saine n'affiche plus un niveau « élevé » en rouge.
- **Caméra.** Les images sont gardées sur l'appareil puis envoyées dès que la connexion le permet (indicateur « N images en attente »). Elles peuvent être rattachées à une parcelle, à une cellule de mission et à la position GPS.
- **GREEN Map.**
  - Tracé des parcelles, y compris hors ligne, avec synchronisation au retour du réseau.
  - Région détectée correctement.
  - Quadrillage du rover en serpentin, figé sous forme de mission et exportable.
  - Carte des résultats par cellule.
- **GREEN Data** (comptes partenaire et administrateur) : statistiques anonymes, fondées uniquement sur les analyses partagées avec consentement, avec masquage « < 5 ».
- **Pages corrigées.**
  - Tableau de bord : analyses récentes, chiffres et météo de la région de l'utilisateur.
  - Profil : messages et enregistrement.
  - Scénarios économiques : rentabilité nette, la formule était fausse.
  - Historique : suppression et filtres.
  - GreenBot : erreurs affichées, conversation fantôme.
  - Calendrier : ligne « criquets » renommée.
- **Contenu retiré.** Le benchmark devient « Ma progression », calculée sur l'historique de l'utilisateur. Le marché devient un catalogue de types d'intrants à prix indicatifs, sans marques, sans notes et sans faux panier.
- **Inscription et connexion.** Les numéros camerounais sont acceptés avec ou sans +237. Le mot de passe compte au moins 8 caractères. Le consentement au partage des données est facultatif et décoché par défaut.

### Sécurité

- **Images.** Elles ne sont plus publiques : `GET /api/media/…` exige un jeton ou une URL signée temporaire. Leurs métadonnées EXIF sont supprimées.
- **Analyses d'autrui.** GreenBot ne peut plus lire l'analyse d'un autre utilisateur (faille corrigée), et une analyse ne peut plus être rattachée à la parcelle d'un autre utilisateur.
- **XSS.** Toutes les données affichées sont échappées.
- **Configuration.** `SECRET_KEY` est obligatoire hors mode développement, `DEBUG` est désactivé par défaut, et CORS n'est plus ouvert à tous.
- **Interface.** Ajout d'en-têtes de sécurité, d'un contraste AA et de bibliothèques servies par l'application elle-même (Leaflet, Chart.js, Turf).

### Fichiers ajoutés (principaux)

| Fichier | Rôle |
|---|---|
| `backend/media.py`, `backend/routers/media_router.py` | Stockage des images, miniatures, accès authentifié |
| `backend/knowledge.py` | Base de connaissances bilingue, correspondance classe → fiche, fiche terrain |
| `backend/geo.py`, `backend/data/cameroon_regions.json` | Géométrie des parcelles, régions, quadrillage et parcours |
| `backend/routers/mission_router.py`, `backend/routers/green_data_router.py` | Missions et heatmap ; statistiques GREEN Data |
| `backend/i18n.py`, `frontend/i18n/*.json`, `frontend/js/i18n.js` | Traductions serveur et interface |
| `backend/migrations/` (0001 à 0004), `backend/schema_check.py`, `backend/db_url.py` | Alembic, contrôle du schéma, URL Supabase |
| `backend/passenger_wsgi.py`, `backend/requirements-prod.txt` | Déploiement o2switch (ONNX Runtime, sans PyTorch) |
| `frontend/green-data.html`, `frontend/js/{upload-queue,parcel-store,fiche,charts,theme-init}.js`, `frontend/vendor/` | Nouvelle page, files hors ligne, fiche partagée, palette des graphiques |
| `scripts/*` | `check_i18n`, `build_i18n`, `db_check`, `media_report`, `seed_demo`, `set_role`, `onnx_parity`, `smoke_prod.sh`, `configure_vercel` |
| `qa/*` | Tests Playwright : pages, parcours, cohérence, parcours de référence |
| `docs/*` | Déploiement o2switch, contrat rover, glossaire FR/EN |

### Fichiers supprimés

| Fichier | Raison |
|---|---|
| `frontend/drone.html`, `frontend/css/drone.css`, `backend/routers/drone_router.py` | Page morte (`/drone` redirigeait déjà vers `/camera`) |
| `frontend/js/translations.json` | Remplacé par `frontend/i18n/*.json` → `js/translations.js` |
| `frontend/assets/marketplace_img/` | Photos de produits de marque, de provenance inconnue |
| `backend/=1.40.0` | Fichier parasite issu d'un `pip install` sans guillemets |

### À savoir pour la suite

1. **Base de production (CP2).** Exécuter `alembic stamp 0001_baseline`, relire le SQL de `alembic upgrade head --sql`, puis lancer `alembic upgrade head`. Les migrations sont toutes additives. Le détail est dans `docs/DEPLOY_O2SWITCH.md` §2.
2. **Développement local.** Une base SQLite existante (`green.db`) est mise à niveau automatiquement au démarrage.
3. **Traductions.** Toute nouvelle chaîne visible passe par `frontend/i18n/*.json`, puis `python scripts/build_i18n.py`. `scripts/check_i18n.py` doit rester à 0 problème.
4. **Rôles.** Ils s'attribuent avec `scripts/set_role.py`, faute d'interface d'administration.
5. **À faire valider par un agronome.** La correspondance classes du modèle → fiches, dans `backend/knowledge.py`.
6. **Vérifications.** 124 tests backend (plus 2 tests lents d'inférence réelle), ruff sans erreur, `check_i18n` à 0 problème, 107 tests Playwright (60 pages × langues × tailles, 30 cohérence, 15 parcours, 2 parcours de référence).

---

## Modification 1 — Abandon de l'ESP32-CAM au profit du Rover

**Date :** 21/10/2026

### Contexte et raison

On n'utilise plus d'ESP32-CAM. Le matériel de terrain est désormais un **Rover** construit autour d'une **Raspberry Pi**.

Le rôle du rover se limite à :

1. créer son propre **hotspot Wi-Fi** ;
2. envoyer le **flux vidéo** (ou des images) du champ à la machine connectée à ce hotspot.

La machine de l'utilisateur se connecte au hotspot du rover. **L'inférence IA et tout le reste du traitement se font dans l'application web**, pas sur le rover.

L'intégration ESP32-CAM (découverte mDNS, proxy MJPEG, surveillance en arrière-plan, firmware Arduino) n'a donc plus de raison d'exister. Elle a été retirée entièrement, et seul le mode Rover reste.

### Fichiers supprimés

| Fichier | Rôle d'origine |
|---|---|
| `backend/camera/__init__.py` | Package d'abstraction caméra (utilisé uniquement par l'ESP32) |
| `backend/camera/provider.py` | Interface `CameraProvider` + `CameraInfo` |
| `backend/camera/esp32.py` | Implémentation `ESP32CameraProvider` (`/status`, `/capture`, `/stream`, `/info`) |
| `backend/camera/discovery.py` | Découverte automatique de l'ESP32 (mDNS `green-cam.local` puis IP fixe) |
| `backend/camera/healthcheck.py` | Boucle de surveillance en arrière-plan (toutes les 15 s) |
| `backend/camera/state.py` | Singleton `camera_state` (caméra active) |
| `backend/routers/esp32_router.py` | Endpoints `/api/esp32/*` (status, info, health, discover, connect, disconnect, stream, capture) |
| `firmware/GREEN_CAM/GREEN_CAM.ino` | Firmware Arduino de l'ESP32-CAM |

### Fichiers modifiés

**`backend/main.py`**
- Retrait de l'import et de l'enregistrement de `esp32_router`.
- Retrait, dans le `lifespan`, de la découverte ESP32 au démarrage et de la tâche `camera_healthcheck_loop`.
  → Le serveur démarre plus vite : il n'attend plus une tentative mDNS ou une IP fixe (jusqu'à environ 8 s quand aucune caméra n'est présente).
- Retrait de l'import `asyncio`, devenu inutile.

**`backend/config.py`**
- Retrait des variables `ESP32_DEFAULT_IP`, `ESP32_MDNS_HOST` et `ESP32_DISCOVERY_ENABLED`.

**`.env`** (fichier local, non versionné)
- Retrait du bloc `ESP32-CAM` (`ESP32_DEFAULT_IP=…`). Les autres variables sont inchangées.
  → Chaque membre de l'équipe doit retirer ce bloc de son propre `.env`. Si on le laisse, il est simplement ignoré.

**`frontend/camera.html`**
- Retrait de l'onglet **ESP32-CAM**, de son panneau (découverte automatique, connexion manuelle par IP, puce d'infos firmware/RSSI) et de tout le JavaScript associé (`_esp32*`, `discoverEsp32`, `connectEsp32Manual`, `disconnectEsp32`, `_silentEsp32Adopt`).
- La page ne tente plus de se rattacher automatiquement à une ESP32 au chargement.
- Les libellés « Drone » deviennent « Rover » : titre de la page, bannière, champ « Rover IP address », messages d'état, alt de l'image, logs console.
- La note du mode IP Stream explique désormais le nouveau fonctionnement : se connecter au hotspot du rover, le flux arrive en MJPEG, et l'inférence se fait dans l'application web.

**`frontend/js/api.js`**
- Retrait du client `API.esp32` (status, info, health, discover, connect, disconnect, capture, streamSrc).

**`frontend/css/camera.css`**
- Retrait des règles `.esp32-manual-row` et `#sectionEsp32`. Les règles partagées `.device-row` sont conservées.

### Ce qui n'a pas changé

- **Chemin Rover, inchangé et opérationnel :** `backend/routers/camera_router.py` et `backend/rover_common.py`, avec les endpoints `/api/camera/connect`, `/capture`, `/analyze-frame` et `/upload`.
- **Pipeline IA** (`inference.py`, `analyze_image_bytes`) et format de la fiche terrain : aucun changement.
- **Modes « Camera » (webcam/USB) et « Upload »** de la page `/camera` : conservés, car ils ne dépendent pas de l'ESP32.
- **Base de données :** aucune migration nécessaire. La base locale ne contenait aucune analyse avec `source = "esp32"`.

### À savoir

**Fonctionnement actuel du mode Rover (« IP Stream »)**

1. L'utilisateur connecte sa machine au hotspot du rover.
2. Dans `/camera`, il saisit l'IP et le port du rover (par défaut `192.168.10.1:8080`, modifiables dans Paramètres), puis clique sur **Connect**.
3. Le backend vérifie que le flux répond (`POST /api/camera/connect`).
4. Le navigateur affiche le flux **directement depuis le rover** (`<img src="http://IP:PORT/">`).
5. Toutes les 8 s, le backend récupère la première image JPEG du flux (`POST /api/camera/capture`), lance l'inférence, enregistre l'analyse et renvoie la fiche terrain.

**Ce que le rover doit exposer pour que ça fonctionne sans modification de code**

- Un flux **MJPEG** (`multipart/x-mixed-replace`) servi en HTTP à la **racine** : `http://<IP>:<PORT>/`.
- Le backend extrait une image en cherchant les marqueurs JPEG (`FFD8` … `FFD9`) dans le flux. Un autre format (RTSP, WebRTC, H.264) **ne fonctionnera pas** sans adaptation.

**Le backend doit tourner sur la machine connectée au hotspot**

Le serveur FastAPI va lui-même chercher les images sur l'IP du rover. S'il est déployé ailleurs (cloud, Vercel…), il ne pourra pas joindre `192.168.x.x` sur le hotspot.

**Nommage « drone » encore présent dans le code (volontairement non touché)**

Il reste `DEFAULT_DRONE_IP` / `DEFAULT_DRONE_STREAM_PORT` dans `config.py`, `drone_router.py` (legacy), la route `/drone` (redirige vers `/camera`) et des messages d'erreur côté backend.

Ce n'est pas lié à l'ESP32. Un renommage complet « drone → rover » peut faire l'objet d'une modification séparée.

**Cache navigateur**

`api.js` est chargé avec `?v=2`. Un ancien `api.js` en cache contient encore `API.esp32`, mais plus rien ne l'appelle, donc ce n'est pas bloquant.

### Points ouverts (informations à fournir sur le rover)

Ces informations permettront d'ajuster les valeurs par défaut et, si besoin, le code :

1. **IP du rover sur son hotspot.** Une Raspberry Pi en hotspot via NetworkManager utilise souvent `10.42.0.1`. La valeur par défaut actuelle est `192.168.10.1`.
2. **Port et chemin du flux.** Le code attend `http://IP:PORT/`. Si le flux est sur `/stream` ou `/video_feed`, il faudra l'adapter.
3. **Format du flux.** MJPEG ou autre (RTSP, WebRTC, H.264).
4. **Endpoint d'image unique** (ex. `/capture` ou `/snapshot`). S'il existe, il serait plus fiable que d'extraire une image du flux.
5. **Rover « images seulement »** (sans flux vidéo continu) : faut-il un mode dédié ?
