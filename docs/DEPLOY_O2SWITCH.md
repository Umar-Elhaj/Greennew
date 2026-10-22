# Déploiement de l'API GREEN sur o2switch

Procédure reproductible pour héberger le backend FastAPI (inférence comprise) sur un hébergement mutualisé o2switch (cPanel, CloudLinux, Phusion Passenger).
Le frontend reste sur Vercel et relaie `/api/*` vers ce domaine (décision D7). La base est Supabase PostgreSQL.

> **Rien n'est installé ni modifié sur le serveur sans validation humaine (point de contrôle CP3).**
> Les étapes 1 et 2 sont en lecture seule ; à partir de l'étape 3, chaque action est faite par vous, ou validée par vous.

Valeurs à remplacer dans ce document :
- `<compte>` : votre identifiant cPanel ;
- `api.example.cm` : le (sous-)domaine choisi pour l'API ;
- `<ref>` / `<region>` : la référence et la région du projet Supabase.

---

## 0. Ce qui tourne en production

| Élément | Choix | Pourquoi |
|---|---|---|
| Serveur d'application | Passenger (WSGI) → `backend/passenger_wsgi.py` → `a2wsgi` → FastAPI | Passenger ne parle pas ASGI. |
| Inférence | ONNX Runtime, `Models/best_efficientnet.onnx` (16 Mo) | Pas de PyTorch : environ 180 Mo de RAM au pic au lieu d'environ 440 Mo, 20 ms par image. Parité vérifiée : 24/24 top-1 identiques, écart max 3e-6 (`scripts/onnx_parity.py`). |
| Dépendances | `backend/requirements-prod.txt` (environnement virtuel d'environ 450 Mo) | Sans torch, torchvision ni timm. |
| Base | Supabase via **l'URL du pooler** | La connexion directe `db.<ref>.supabase.co` est en IPv6 seulement. |
| Images analysées | `MEDIA_DIR` **hors** de `public_html` | Jamais publiques : servies par `GET /api/media/…` avec authentification. |
| Flux MJPEG du rover | non utilisé en production | Passenger met les réponses en tampon et un serveur hébergé ne peut pas joindre l'IP privée du rover ; voir `docs/rover_mission_contract.md`. |

---

## 1. Diagnostic (lecture seule)

Connectez-vous en SSH (cPanel › *Terminal*, ou `ssh <compte>@<serveur>`), puis exécutez ces commandes et conservez leur sortie. Aucune ne modifie le serveur.

```bash
# Versions de Python proposées par « Setup Python App » (CloudLinux)
ls /opt/alt/ | grep -i python
# Bibliothèque C (les roues onnxruntime manylinux_2_28 demandent glibc >= 2.28)
ldd --version | head -1
# Processeur (onnxruntime x86_64 a besoin d'AVX)
grep -o -m1 -w avx2 /proc/cpuinfo || grep -o -m1 -w avx /proc/cpuinfo
# Limites du compte (processus, mémoire)
ulimit -a
# Espace disque et quota
df -h ~ ; quota -s 2>/dev/null || echo "voir cPanel > Utilisation du disque"
```

Dans cPanel, ouvrez *Utilisation des ressources* (CloudLinux LVE) et notez la limite de mémoire physique (PMEM) et le nombre maximal de processus (NPROC).

**Connectivité sortante.** Remplacez l'hôte et le port du pooler par ceux de votre projet (Supabase › *Project Settings › Database › Connection string*) :

```bash
python3 - <<'PY'
import socket
for host, port in [("aws-0-<region>.pooler.supabase.com", 6543),
                   ("aws-0-<region>.pooler.supabase.com", 5432),
                   ("generativelanguage.googleapis.com", 443),
                   ("api.openweathermap.org", 443)]:
    try:
        socket.create_connection((host, port), 5).close(); print("OK     ", host, port)
    except OSError as e:
        print("BLOQUÉ ", host, port, e)
PY
```

Ce qu'il faut obtenir avant de continuer :
- une version de Python de **3.11 à 3.13** (3.12 recommandée : c'est celle des tests) ;
- **glibc ≥ 2.28** et **AVX** présents ;
- **PMEM ≥ 1 Go**, l'installation de `pip` demandant aussi de la mémoire ;
- **au moins un des deux ports du pooler en `OK`**.

**Si les deux ports du pooler sont bloqués, arrêtez-vous** et envoyez ce message au support o2switch (ticket depuis l'espace client) :

> Bonjour, sur le compte `<compte>`, j'héberge une application Python (Setup Python App) qui doit se connecter à une base PostgreSQL hébergée chez Supabase. Pourriez-vous autoriser les connexions sortantes TCP vers `aws-0-<region>.pooler.supabase.com` sur le port 6543 (et 5432 si possible) ? Le test `socket.create_connection` échoue actuellement : `<message d'erreur>`. Merci.

---

## 2. Préparer Supabase (CP2 : migration de la base de production)

1. Dans Supabase › *Project Settings › Database*, copiez la chaîne **Transaction pooler**, de la forme `postgresql://postgres.<ref>:<mot-de-passe>@aws-0-<region>.pooler.supabase.com:6543/postgres`.
   - Port **6543** (mode transaction) : l'application n'ouvre pas de pool (NullPool), ce qui convient le mieux à Passenger, qui lance plusieurs processus.
   - Port 5432 (mode session) : petit pool de 2 connexions + 2 en débordement par processus.
   - `sslmode=require` est ajouté automatiquement. Ne collez jamais cette URL dans un fichier versionné, un ticket ou un message.
2. Sur votre poste, dans `backend/`, avec `DATABASE_URL` défini dans votre terminal uniquement, faites d'abord un **état des lieux en lecture seule** :
   ```bash
   ../.venv/bin/python ../scripts/db_check.py
   ```
   Il affiche la version de Postgres, la révision Alembic et le nombre de lignes par table, sans jamais afficher l'URL.
3. Sur la base existante, créée avec `sql/supabase_schema.sql` avant Alembic (`current=None`), **affichez le SQL qui sera exécuté** et relisez-le. Il ne contient que des `ADD COLUMN`, `CREATE TABLE`, `CREATE INDEX` et contraintes, aucune suppression :
   ```bash
   ../.venv/bin/alembic upgrade 0001_baseline:head --sql > /tmp/green-migration.sql
   ```
4. **Après validation de ce SQL** :
   ```bash
   ../.venv/bin/alembic stamp 0001_baseline   # marque l'état actuel comme baseline (crée alembic_version)
   ../.venv/bin/alembic upgrade head           # applique 0002 → 0004 (additives)
   ../.venv/bin/python ../scripts/db_check.py  # doit afficher current=head
   ```
   Sur une base **vide**, `alembic upgrade head` suffit (la baseline crée tout, RLS comprise).

---

## 3. Créer l'application Python (cPanel)

1. cPanel › *Domaines* : créez le sous-domaine `api.example.cm`, puis activez AutoSSL (cPanel › *SSL/TLS Status*).
2. cPanel › *Git™ Version Control* › *Create* :
   - URL du dépôt : celle du dépôt GitHub (HTTPS ; dépôt privé : clé de déploiement en lecture seule) ;
   - chemin : `/home/<compte>/green` ;
   - branche : celle à déployer.

   Le modèle ONNX (16 Mo) est versionné et arrive avec le dépôt. Alternative sans Git :
   `rsync -av --exclude .git --exclude .venv --exclude 'Models/*.pth' --exclude 'Models/*tflite*' ./ <compte>@<serveur>:green/`
3. cPanel › *Setup Python App* › *Create Application* :

   | Champ | Valeur |
   |---|---|
   | Python version | 3.12 (ou la plus proche de 3.11 à 3.13 disponible) |
   | Application root | `green/backend` |
   | Application URL | `api.example.cm` |
   | Application startup file | `passenger_wsgi.py` |
   | Application Entry point | `application` |
   | Passenger log file | `/home/<compte>/logs/green-api.log` |

4. Dans la même page, section *Environment variables*, ajoutez les variables de l'étape 5. Notez la commande `source …/activate` affichée en haut de la page.

---

## 4. Installer les dépendances

```bash
source /home/<compte>/virtualenv/green/backend/3.12/bin/activate   # commande affichée par cPanel
cd ~/green
pip install --upgrade pip
pip install -r backend/requirements-prod.txt
python -c "import onnxruntime, fastapi, a2wsgi; print('ok', onnxruntime.__version__)"
```

Si `onnxruntime==1.31.0` n'a pas de roue pour la version de Python du serveur, `pip` l'indique. Choisissez alors la version de Python la plus proche, et ne compilez rien sur le serveur.

---

## 5. Variables d'environnement (cPanel › Setup Python App)

Mettez uniquement des valeurs, jamais dans un fichier du dépôt. La référence commentée est `.env.example`.

| Variable | Obligatoire | Valeur en production |
|---|---|---|
| `DATABASE_URL` | oui | URL du pooler Supabase (étape 2) |
| `SECRET_KEY` | oui | `python -c "import secrets; print(secrets.token_urlsafe(48))"` ; sans elle, l'application refuse de démarrer |
| `DEBUG` | non | `false` (valeur par défaut) |
| `MEDIA_DIR` | oui en pratique | `/home/<compte>/green_media` |
| `INFERENCE_BACKEND` | non | `onnx` (valeur par défaut) |
| `MODEL_PATH` | non | vide : `Models/best_efficientnet.onnx` |
| `MODEL_VERSION` | non | `efficientnet-v1` |
| `MAX_UPLOAD_MB` | non | `8` |
| `WARMUP` | non | vide (chargement du modèle à la première analyse) |
| `CORS_ORIGINS` | non | vide avec la réécriture Vercel |
| `GEMINI_API_KEY` | non | sans elle, GreenBot affiche « non configuré » |
| `GEMINI_MODEL` | non | vide = `gemini-3.1-flash-lite` |
| `WEATHER_API_KEY` | non | sans elle, la météo affiche « non activée » |

Créez le dossier des images, hors de `public_html` et non lisible par les autres comptes :

```bash
mkdir -p ~/green_media && chmod 700 ~/green_media
```

---

## 6. Sécurité HTTP

Ajoutez **en tête** du `.htaccess` du domaine de l'API les lignes de `deploy/o2switch/htaccess-snippet.conf` (redirection HTTPS, HSTS, fichiers privés interdits). Laissez intact le bloc `CLOUDLINUX PASSENGER CONFIGURATION` écrit par cPanel. Les autres en-têtes de sécurité sont ajoutés par l'application elle-même.

---

## 7. Démarrer, vérifier, journaux

```bash
cd ~/green/backend && mkdir -p tmp && touch tmp/restart.txt   # (re)démarrage Passenger
curl -s https://api.example.cm/api/health
tail -n 50 ~/logs/green-api.log                                # erreurs de démarrage
```

La réponse attendue de `/api/health` est `"status":"ok"`, avec `"inference_backend":"onnx"`.
- Si l'application refuse de démarrer, le journal indique la cause (par exemple `SECRET_KEY is not set`).
- Si le schéma est en retard, le journal contient `Database schema at revision …` : reprendre l'étape 2.

---

## 8. Comptes à rôle

Il n'y a pas d'interface d'administration : les rôles se donnent sur le serveur, après l'inscription normale de la personne dans l'application.

```bash
source /home/<compte>/virtualenv/green/backend/3.12/bin/activate && cd ~/green
python scripts/set_role.py --phone +2376XXXXXXXX --role admin        # ou partner, agronomist
python scripts/set_role.py --list
```

---

## 9. Brancher le frontend Vercel

Sur votre poste :

```bash
python scripts/configure_vercel.py https://api.example.cm
git add frontend/vercel.json && git commit -m "chore(vercel): proxy /api to o2switch"
```

Poussez, puis redéployez le projet Vercel (dossier racine du projet : `frontend/`). Le navigateur ne voit qu'une seule origine : pas de CORS, et les liens signés des images passent par la même réécriture.

---

## 10. Test de fumée

Créez dans l'application un compte de test dédié, puis lancez :

```bash
SMOKE_IDENTIFIER=+2376XXXXXXXX SMOKE_PASSWORD='…' scripts/smoke_prod.sh https://<domaine-vercel>
SMOKE_IDENTIFIER=+2376XXXXXXXX SMOKE_PASSWORD='…' scripts/smoke_prod.sh https://api.example.cm
```

Le script vérifie les points suivants :
- santé de l'API, connexion, liste des parcelles ;
- analyse d'une image (inférence ONNX réelle) ;
- lecture de l'image stockée, avec jeton et avec URL signée, et 401 sans les deux ;
- un endpoint GREEN Data.

Il renvoie le nombre de vérifications en échec.

---

## 11. Mettre à jour

```bash
cd ~/green && git pull                     # ou « Update from Remote » dans cPanel › Git
source /home/<compte>/virtualenv/green/backend/3.12/bin/activate
pip install -r backend/requirements-prod.txt
cd backend && alembic upgrade head --sql | less   # relire s'il y a une nouvelle révision
alembic upgrade head
touch tmp/restart.txt
```

## 12. Retour arrière

1. Revenez au commit précédent : `cd ~/green && git checkout <commit-précédent>`, puis `pip install -r backend/requirements-prod.txt` et `touch backend/tmp/restart.txt`.
2. Les migrations sont **additives** : l'ancien code fonctionne avec le nouveau schéma. **Ne lancez pas** `alembic downgrade` sur la base de production, car les downgrades suppriment des colonnes (outils de développement seulement).
3. Les images de `MEDIA_DIR` ne sont jamais touchées par un déploiement.

## 13. Exploitation courante

| Besoin | Commande |
|---|---|
| État de la base | `python scripts/db_check.py` |
| Disque et images orphelines | `python scripts/media_report.py` (ajoutez `--apply` pour supprimer les fichiers orphelins) |
| Sauvegarde des images | `rsync -a ~/green_media/ <destination>/` (la base est sauvegardée par Supabase) |
| Quota | cPanel › *Utilisation du disque* : chaque analyse occupe environ 0,2 à 0,6 Mo (image réduite à 2 048 px + miniature) |
