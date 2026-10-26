# Déploiement de GREEN sur o2switch (référence condensée)

Tout est hébergé chez o2switch (cPanel, CloudLinux, Phusion Passenger), sur un seul domaine : **base de données MySQL/MariaDB**, **backend FastAPI** (inférence comprise) et **frontend**. PostgreSQL n'est pas utilisé sur o2switch.

> Version détaillée, clic par clic (boutons cPanel, champs, SSH, Let's Encrypt, phpMyAdmin, Tiger Protect, tâches cron, sauvegardes, dépannage) : [`GUIDE_INTEGRATION_O2SWITCH.md`](../GUIDE_INTEGRATION_O2SWITCH.md). Ce document-ci en est le résumé de référence ; les numéros d'étapes renvoient au guide.

> **Rien n'est installé ni modifié sur le serveur sans validation humaine (point de contrôle CP3).** La création du schéma de production et la reprise des données (CP2) sont relues avant d'être appliquées.

Valeurs utilisées : compte `sc1jsgw2086`, domaine `api-green.gitingeniering.com`, code dans `~/green`, base `sc1jsgw2086_green`, utilisateur MySQL `sc1jsgw2086_greenapp`.

---

## 0. Ce qui tourne en production

| Élément | Choix | Pourquoi |
|---|---|---|
| Base | MariaDB d'o2switch, sur la même machine (socket Unix ou `localhost:3306`), pilote **PyMySQL** | Pas de PostgreSQL chez o2switch pour ce projet ; PyMySQL est 100 % Python (le compilateur est bloqué par défaut). |
| Schéma | Alembic (`backend/migrations`) ; `backend/sql/mysql_schema.sql` = même schéma, importable dans une base vide | Un test vérifie modèles ⇄ migrations ⇄ fichier SQL sur MariaDB. |
| Types MySQL | `DOUBLE`, `DATETIME(6)`, `MEDIUMTEXT`, `JSON`, InnoDB + `utf8mb4_unicode_ci` (`backend/db_types.py`) | `FLOAT` perdrait de la précision GPS, `DATETIME` les microsecondes (ordre des messages), `TEXT` s'arrête à 64 Ko. |
| Session MySQL | UTC, mode SQL strict, pool de 2 + 2 connexions par processus, recyclage à 280 s (`backend/db_url.py`) | Même comportement sur MariaDB et MySQL 8 ; connexions fermées par `wait_timeout` sans effet visible. |
| Serveur d'application | Passenger (WSGI) → `backend/passenger_wsgi.py` → `a2wsgi` → FastAPI | Passenger ne parle pas ASGI. |
| Inférence | ONNX Runtime, `Models/best_efficientnet.onnx` (16 Mo) | Environ 180 Mo de RAM au pic, 20 ms par image ; parité avec PyTorch vérifiée (`scripts/onnx_parity.py`). |
| Dépendances | `backend/requirements-prod.txt` (environ 450 Mo) | Sans torch, torchvision, timm ni pilote PostgreSQL. |
| Frontend | Fichiers de `frontend/` liés dans la racine du domaine (`deploy/o2switch/publish_frontend.sh`), servis par Apache ; FastAPI les sert aussi en secours | Une seule origine (pas de CORS) ; les fichiers statiques ne consomment pas de processus Passenger. |
| Images analysées | `MEDIA_DIR` = `~/green_media`, **hors** de la racine web | Jamais publiques : servies par `GET /api/media/…` avec authentification ou lien signé. |
| Flux MJPEG du rover | non utilisé en production | Un serveur hébergé ne peut pas joindre l'IP privée du rover ; voir `docs/rover_mission_contract.md`. |

---

## 1. Préparation (guide, étapes 1 à 6)

Diagnostic en lecture seule, sur le serveur :

```bash
ls /opt/alt/ | grep -i python                         # Python 3.11 à 3.13 (3.12 recommandée)
ldd --version | head -1                               # glibc >= 2.28 (roues onnxruntime)
grep -o -m1 -w avx2 /proc/cpuinfo || grep -o -m1 -w avx /proc/cpuinfo
mysql --version
ulimit -a ; df -h ~
```

Puis : sous-domaine `api-green.gitingeniering.com` (racine `~/api-green.gitingeniering.com`), certificat **Let's Encrypt**, dépôt cloné par *Git™ Version Control* dans `~/green`, branche `main`.

---

## 2. Base de données MySQL (guide, étapes 7 à 10)

1. cPanel › *Assistant Base de données MySQL®* : base `green`, utilisateur `greenapp`, **tous les privilèges** (noms préfixés `sc1jsgw2086_`).
2. `~/.my.cnf` en `600` avec l'utilisateur et le mot de passe (sert à `mysql` et `mysqldump`), puis :
   ```bash
   mysql sc1jsgw2086_green -e "select version(), @@socket, @@port;"   # MariaDB >= 10.4, noter @@socket
   ```
3. **CP2** — création des tables dans la base vide, après relecture du fichier :
   ```bash
   mysql sc1jsgw2086_green < ~/green/backend/sql/mysql_schema.sql
   mysql sc1jsgw2086_green -e "show tables; select version_num from alembic_version;"   # 7 tables, 0004_green_data
   ```
   Équivalent par Alembic (après l'étape 3 ci-dessous) : `alembic upgrade head`.
4. `DATABASE_URL` :
   ```
   mysql://sc1jsgw2086_greenapp:<mot-de-passe-encodé>@localhost/sc1jsgw2086_green?unix_socket=<@@socket>
   ```
   Variante TCP : `…@localhost:3306/sc1jsgw2086_green`. `mysql+pymysql://` et `charset=utf8mb4` sont ajoutés par l'application.

---

## 3. Backend (guide, étapes 11 à 19)

1. `mkdir -p ~/green_media ~/logs ~/green/backend/tmp && chmod 700 ~/green_media`.
2. cPanel › *Setup Python App* › *Create Application* :

   | Champ | Valeur |
   |---|---|
   | Python version | 3.12 |
   | Application root | `green/backend` |
   | Application URL | `api-green.gitingeniering.com` |
   | Application startup file | `passenger_wsgi.py` |
   | Application Entry point | `application` |
   | Passenger log file | `/home/sc1jsgw2086/logs/green-api.log` |

   Variables : `DATABASE_URL`, `SECRET_KEY`, `DEBUG=false`, `MEDIA_DIR=/home/sc1jsgw2086/green_media`, `INFERENCE_BACKEND=onnx`, `MODEL_VERSION=efficientnet-v1` ; facultatives : `GEMINI_API_KEY`, `GEMINI_MODEL`, `WEATHER_API_KEY`, `MAX_UPLOAD_MB`, `WARMUP`. `CORS_ORIGINS` reste vide (une seule origine).
3. `~/.green/env` (`DATABASE_URL`, `SECRET_KEY`, `MEDIA_DIR`, en `600`) et `~/.green/run.sh` (charge l'environnement et le virtualenv) pour les scripts SSH et cron : les variables de *Setup Python App* ne leur sont pas transmises.
4. Dépendances, en SSH :
   ```bash
   source /home/sc1jsgw2086/virtualenv/green/backend/3.12/bin/activate
   pip install -r ~/green/backend/requirements-prod.txt
   python -c "import onnxruntime, fastapi, a2wsgi, pymysql, PIL, sklearn; print('ok')"
   ~/.green/run.sh python scripts/db_check.py      # backend : mysql, current = head, code 0
   ```
5. **Facultatif, CP2** — reprise des données de l'ancienne base Supabase, avant l'ouverture aux utilisateurs : `pip install psycopg2-binary==2.9.10`, puis `SOURCE_DATABASE_URL` (Session pooler Supabase) exportée dans le terminal et :
   ```bash
   ~/.green/run.sh python scripts/copy_database.py            # essai à blanc
   ~/.green/run.sh python scripts/copy_database.py --apply    # une transaction ; base cible à jour et vide
   ```
   Identifiants conservés, colonnes absentes de la source à leur valeur par défaut, Supabase seulement lue. Copier aussi les anciennes images dans `~/green_media` et reprendre l'ancienne `SECRET_KEY`.
6. `.htaccess` du domaine : coller `deploy/o2switch/htaccess-snippet.conf` **au-dessus** du bloc Passenger de cPanel (HTTPS, HSTS, en-têtes de sécurité, cache des fichiers statiques, `noindex` sur `/api/`, fichiers privés refusés).
7. Démarrage : *Restart* ou `touch ~/green/backend/tmp/restart.txt` ; `curl -s https://api-green.gitingeniering.com/api/health` → `"status":"ok"`. Journal : `~/logs/green-api.log`.
8. Tiger Protect : jamais le mode « Je suis attaqué » ni « Bloquer POST » sur ce domaine.

---

## 4. Frontend (guide, étapes 20 et 21)

```bash
~/green/deploy/o2switch/publish_frontend.sh /home/sc1jsgw2086/api-green.gitingeniering.com
```

Le script lie chaque élément de `frontend/` (pages, `css/`, `js/`, `vendor/`, `assets/`) dans la racine du domaine, sans toucher au `.htaccess` ni à `.well-known`. Vérifier `/`, `/dashboard`, `/js/api.js` en `200`. L'ancien projet Vercel est supprimé ou redirigé vers le nouveau domaine.

---

## 5. Mise en service et exploitation (guide, étapes 22 à 26)

- Rôles : `~/.green/run.sh python scripts/set_role.py --phone +2376XXXXXXXX --role admin` (après inscription normale).
- Test de fumée : `SMOKE_IDENTIFIER=… SMOKE_PASSWORD=… scripts/smoke_prod.sh https://api-green.gitingeniering.com` (API, pages, fichiers privés refusés, connexion, analyse, images, GREEN Data).
- Cron : santé toutes les 15 min ; `db_check.py` quotidien ; `mysqldump --single-transaction --no-tablespaces sc1jsgw2086_green | gzip > ~/backups/green-$(date +\%F).sql.gz` quotidien (14 jours gardés) ; `media_report.py` hebdomadaire.
- Sauvegardes : JetBackup (base et images) + copies hors site par `rsync`.

### Mettre à jour

```bash
mysqldump --single-transaction --no-tablespaces sc1jsgw2086_green | gzip > ~/backups/green-avant-maj-$(date +%F-%H%M).sql.gz
cd ~/green && git pull
source /home/sc1jsgw2086/virtualenv/green/backend/3.12/bin/activate && pip install -r backend/requirements-prod.txt
~/.green/run.sh bash -c 'cd backend && alembic upgrade head --sql' | less     # CP2 : relire
~/.green/run.sh bash -c 'cd backend && alembic upgrade head'
~/green/deploy/o2switch/publish_frontend.sh /home/sc1jsgw2086/api-green.gitingeniering.com
touch ~/green/backend/tmp/restart.txt
```

### Revenir en arrière

`git checkout <commit-précédent>`, `pip install -r backend/requirements-prod.txt`, `publish_frontend.sh`, redémarrage. Les migrations sont additives : **jamais de `alembic downgrade`** en production ; la sauvegarde d'avant mise à jour reste le dernier recours.
