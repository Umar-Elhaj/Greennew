# Guide d'intégration du backend GREEN sur o2switch (offre Pro)

Ce guide décrit, clic par clic, la mise en production de l'API GREEN (FastAPI, inférence ONNX, GREEN Map, GREEN Data, GreenBot, météo, images) sur un hébergement **o2switch, offre Pro**, la plus haute des offres mutualisées : 24 threads, 64 Go de RAM partagés et 16 « lunes », c'est-à-dire 16 comptes cPanel séparés.

- **Base de données :** Supabase (PostgreSQL), joint par son *pooler*.
- **Frontend :** reste sur Vercel, qui relaie `/api/*` vers o2switch. Pour tout héberger sur o2switch, voir l'[annexe A](#annexe-a--tout-héberger-sur-o2switch-sans-vercel).

À la fin, toutes les fonctions implémentées sont en service et vérifiées :
- comptes et rôles ;
- analyse photo (ONNX) et stockage privé des images ;
- historique et fiches ;
- parcelles, grilles, missions et carte de chaleur ;
- GREEN Data ;
- GreenBot et météo.

> **Points de contrôle.** L'étape 12 (migration de la base de production, CP2) et toutes les étapes qui modifient le serveur (CP3) sont faites par vous. Lisez chaque commande avant de l'exécuter.
>
> **Secrets.** Ne collez jamais l'URL de la base, la clé secrète ou une clé d'API dans un fichier du dépôt, un ticket, un e-mail ou une capture d'écran. Ils ne vont qu'à trois endroits :
> - cPanel › *Setup Python App* ;
> - le fichier `~/.green/env` du serveur (étape 10) ;
> - le gestionnaire de mots de passe de l'équipe.

---

## Sommaire

0. [Avant de commencer](#0-avant-de-commencer)
1. [Ouvrir cPanel](#1-ouvrir-cpanel)
2. [Activer l'accès SSH](#2-activer-laccès-ssh)
3. [Diagnostic du serveur (lecture seule)](#3-diagnostic-du-serveur-lecture-seule)
4. [Créer le sous-domaine de l'API](#4-créer-le-sous-domaine-de-lapi)
5. [Installer le certificat HTTPS](#5-installer-le-certificat-https-lets-encrypt)
6. [Préparer Supabase](#6-préparer-supabase)
7. [Récupérer le code](#7-récupérer-le-code-git-version-control)
8. [Créer les dossiers des images et des journaux](#8-créer-les-dossiers-des-images-et-des-journaux)
9. [Créer l'application Python](#9-créer-lapplication-python-setup-python-app)
10. [Préparer l'environnement des scripts](#10-préparer-lenvironnement-des-scripts-ssh-et-tâches-cron)
11. [Installer les dépendances](#11-installer-les-dépendances)
12. [Migrer la base de données (CP2)](#12-migrer-la-base-de-données-cp2)
13. [Sécuriser le domaine (.htaccess)](#13-sécuriser-le-domaine-htaccess)
14. [Démarrer et vérifier l'API](#14-démarrer-et-vérifier-lapi)
15. [Régler Tiger Protect (pare-feu applicatif)](#15-régler-tiger-protect-pare-feu-applicatif)
16. [Créer les comptes à rôle](#16-créer-les-comptes-à-rôle)
17. [Activer GreenBot et la météo](#17-activer-greenbot-et-la-météo)
18. [Brancher le frontend Vercel](#18-brancher-le-frontend-vercel)
19. [Tester de bout en bout](#19-tester-de-bout-en-bout)
20. [Exploitation : tâches planifiées, sauvegardes, surveillance](#20-exploitation--tâches-planifiées-sauvegardes-surveillance)
21. [Mettre à jour et revenir en arrière](#21-mettre-à-jour-et-revenir-en-arrière)
22. [Dépannage](#22-dépannage)

Annexes : [A. Tout sur o2switch](#annexe-a--tout-héberger-sur-o2switch-sans-vercel) · [B. PostgreSQL d'o2switch](#annexe-b--base-postgresql-do2switch-si-supabase-est-injoignable) · [C. Variables](#annexe-c--récapitulatif-des-variables-denvironnement) · [D. Liste de contrôle finale](#annexe-d--liste-de-contrôle-finale)

---

## 0. Avant de commencer

### 0.1 Comptes nécessaires

| Compte | Usage | Obligatoire |
|---|---|---|
| o2switch, **offre Pro** | Hébergement de l'API | oui |
| Un nom de domaine (inclus ou non chez o2switch) | Adresse publique de l'API, par exemple `api.mondomaine.cm` | oui |
| Supabase (projet existant de GREEN) | Base PostgreSQL | oui |
| GitHub (accès au dépôt `Umar-Elhaj/Greennew`) | Récupération du code | oui |
| Vercel (projet du frontend) | Pages web de l'application | oui (sauf [annexe A](#annexe-a--tout-héberger-sur-o2switch-sans-vercel)) |
| Google AI Studio | Clé Gemini pour GreenBot | non : sans elle, GreenBot affiche « non configuré » |
| OpenWeatherMap | Clé météo | non : sans elle, le widget affiche « non activé » |

### 0.2 Sur votre poste

- Un terminal avec `ssh`, `git`, `curl` et `python3` (Linux, macOS, ou Windows avec WSL ou Git Bash).
- Le dépôt cloné, sur la branche à déployer : `main` après fusion de `feat/green-map-data-o2switch`, ou cette branche directement.

### 0.3 Valeurs à remplacer partout dans ce guide

| Repère | Signification | Exemple |
|---|---|---|
| `<compte>` | Identifiant cPanel (en haut à droite dans cPanel) | `greenagri` |
| `<serveur>` | Nom du serveur o2switch (cPanel › *Informations générales*, ou e-mail de bienvenue) | `xxxx.o2switch.net` |
| `mondomaine.cm` | Votre domaine | |
| `api.mondomaine.cm` | Sous-domaine de l'API (o2switch) | |
| `app.mondomaine.cm` | Domaine du frontend (Vercel) | |
| `<ref>`, `<region>` | Référence et région du projet Supabase | `abcdefghijkl`, `eu-west-3` |
| `<branche>` | Branche Git déployée | `main` |
| `3.12` | Version de Python choisie à l'étape 9 (remplacez-la partout si vous en prenez une autre) | |

### 0.4 Ce qui tournera en production

```
Navigateur ──HTTPS──► Vercel (app.mondomaine.cm : pages HTML/JS)
                        │  réécriture /api/*  (même origine : pas de CORS)
                        ▼
                o2switch (api.mondomaine.cm)
                Apache + Tiger Protect ─► Passenger ─► passenger_wsgi.py ─► a2wsgi ─► FastAPI
                        │                                   ├─ ONNX Runtime (Models/best_efficientnet.onnx)
                        │                                   └─ images : ~/green_media (privé, hors web)
                        ├──TLS──► Supabase PostgreSQL (pooler, port 6543)
                        ├──HTTPS► Google Gemini (GreenBot, facultatif)
                        └──HTTPS► OpenWeatherMap (météo, facultatif)
```

Durée indicative : 1 h 30 à 2 h 30, plus la propagation DNS si vous créez des enregistrements chez un autre registraire.

---

## 1. Ouvrir cPanel

1. Connectez-vous à votre **espace client o2switch**.
2. Ouvrez le **cPanel** de l'hébergement (lien cPanel de votre service, ou `https://<serveur>:2083`).
3. Dans la colonne de droite, panneau **Informations générales**, notez :
   - le **nom d'utilisateur actuel** : c'est `<compte>` ;
   - l'**adresse IP partagée** : c'est l'IP du serveur, utile à l'étape 4 si votre DNS est ailleurs ;
   - le **répertoire de base** : `/home/<compte>`.

Avec l'offre Pro, vous pouvez réserver une « lune » (un compte cPanel) à GREEN seul. C'est recommandé : ses limites de ressources ne sont alors pas partagées avec d'autres sites.

---

## 2. Activer l'accès SSH

Le terminal intégré de cPanel (*Terminal*) a des limites de mémoire et de nombre de processus plus basses : `pip install` peut y échouer (`out of memory`, `fork failed`). **Utilisez un vrai client SSH.**

### 2.1 Autoriser votre adresse IP

1. cPanel › outil **Autorisation SSH**.
2. Ajoutez votre **adresse IP publique actuelle** (affichée par l'outil, ou par `curl -4 ifconfig.me` sur votre poste).
   - Avec une IP qui change souvent, indiquez un nom d'hôte de DNS dynamique (par exemple No-IP).
   - Un compte cPanel accepte **5 autorisations** au plus.
3. Validez, puis attendez **3 à 5 minutes** que la règle soit appliquée.

### 2.2 Créer et installer une clé SSH

Sur votre poste :

```bash
ssh-keygen -t ed25519 -C "green-o2switch" -f ~/.ssh/green_o2switch
# (l'outil o2switch documente aussi : ssh-keygen -t rsa -b 4096)
```

Installez la clé publique sur le serveur. Cette fois, la connexion demande le **mot de passe cPanel** :

```bash
cat ~/.ssh/green_o2switch.pub | ssh <compte>@<serveur> \
  "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 644 ~/.ssh/authorized_keys"
```

### 2.3 Créer l'alias `green-o2switch`

Ajoutez ce bloc à `~/.ssh/config` sur votre poste :

```
Host green-o2switch
    HostName <serveur>
    User <compte>
    Port 22
    IdentityFile ~/.ssh/green_o2switch
    IdentitiesOnly yes
    ServerAliveInterval 30
```

Testez :

```bash
ssh green-o2switch 'echo connecté : $(whoami) sur $(hostname)'
```

Toutes les commandes « sur le serveur » de la suite se tapent après `ssh green-o2switch`.

---

## 3. Diagnostic du serveur (lecture seule)

Ces commandes ne modifient rien. Exécutez-les sur le serveur et gardez leur sortie.

```bash
# Versions de Python disponibles pour « Setup Python App »
ls /opt/alt/ | grep -i python
# glibc : les roues onnxruntime demandent glibc >= 2.28
ldd --version | head -1
# Jeu d'instructions AVX (requis par onnxruntime x86_64)
grep -o -m1 -w avx2 /proc/cpuinfo || grep -o -m1 -w avx /proc/cpuinfo
# Limites du compte
ulimit -a
# Espace disque
df -h ~
```

Dans cPanel, ouvrez **Utilisation des ressources** et notez les plafonds affichés pour la mémoire physique, les processus et les *entry processes*.

**Connexions sortantes.** Remplacez l'hôte du pooler par celui de votre projet (étape 6.1) :

```bash
python3 - <<'PY'
import socket
for host, port in [("aws-0-<region>.pooler.supabase.com", 6543),
                   ("aws-0-<region>.pooler.supabase.com", 5432),
                   ("generativelanguage.googleapis.com", 443),
                   ("api.openweathermap.org", 443),
                   ("github.com", 443)]:
    try:
        socket.create_connection((host, port), 5).close(); print("OK     ", host, port)
    except OSError as e:
        print("BLOQUÉ ", host, port, e)
PY
```

**Résultats attendus avant de continuer :**

| Contrôle | Attendu |
|---|---|
| Python | une version **3.11, 3.12 ou 3.13** (3.12 recommandée : c'est celle des tests) |
| glibc | **2.28 ou plus** |
| AVX | `avx2` ou `avx` affiché |
| Mémoire physique | **1 Go ou plus** (chaque processus de l'API occupe environ 180 à 250 Mo une fois le modèle chargé) |
| Pooler Supabase | **au moins un des deux ports en `OK`** |

**Si les deux ports du pooler sont `BLOQUÉ`**, ouvrez un ticket depuis l'espace client o2switch :

> Bonjour, sur le compte `<compte>` (offre Pro), une application Python (Setup Python App) doit se connecter à une base PostgreSQL hébergée chez Supabase. Pourriez-vous autoriser les connexions sortantes TCP vers `aws-0-<region>.pooler.supabase.com` sur le port 6543 (et 5432 si possible) ? Le test `socket.create_connection` renvoie actuellement : `<message d'erreur>`. Merci.

En attendant la réponse, vous pouvez poursuivre jusqu'à l'étape 11 incluse. Si le port reste fermé, voir l'[annexe B](#annexe-b--base-postgresql-do2switch-si-supabase-est-injoignable).

---

## 4. Créer le sous-domaine de l'API

1. cPanel › catégorie **Domaines** › outil **Sous-domaines**.
2. Remplissez :

   | Champ | Valeur |
   |---|---|
   | **Sous-domaine** | `api` |
   | **Domaine** | `mondomaine.cm` (s'il n'apparaît pas, ajoutez-le d'abord avec l'outil **Domaines configurés**) |
   | **Racine des documents** | laissez la valeur proposée, par exemple `/home/<compte>/api.mondomaine.cm` |

3. Validez (bouton **Créer**).

> La racine des documents ne contiendra que le `.htaccess` écrit par cPanel. Le code de l'application est ailleurs (`~/green`), comme le recommande o2switch : si l'application est arrêtée, rien de privé n'est exposé.

### 4.1 DNS

- **Domaine géré par o2switch** (serveurs `ns1.o2switch.net` et `ns2.o2switch.net`) : l'enregistrement est créé automatiquement.
- **Domaine géré ailleurs** : chez votre registraire, créez :

  | Type | Nom | Valeur | TTL |
  |---|---|---|---|
  | `A` | `api` | adresse IP partagée notée à l'étape 1 | 3600 |

Vérifiez depuis votre poste (cela peut prendre de quelques minutes à quelques heures) :

```bash
dig +short api.mondomaine.cm     # doit afficher l'IP partagée o2switch
```

---

## 5. Installer le certificat HTTPS (Let's Encrypt)

L'outil **SSL/TLS** de cPanel ne délivre pas de certificat gratuit valide : utilisez l'outil **Let's Encrypt**.

1. cPanel › outil **Let's Encrypt**.
2. Cliquez sur le lien **Générer** en face de `api.mondomaine.cm`.
3. Laissez la méthode de validation **`http-01`** (par défaut, et recommandée). Ne cochez pas le wildcard.
4. Cliquez d'abord sur **Générer la simulation**. Si elle réussit, cliquez sur **Générer**.
5. Le message de succès indique que le certificat est installé. Le renouvellement est automatique : pour recevoir les alertes, renseignez votre e-mail dans cPanel › **Coordonnées**.

Vérifiez :

```bash
curl -sI https://api.mondomaine.cm | head -1      # une réponse HTTP (même 404 ou 503) sans erreur de certificat
```

> En cas d'erreur de limite Let's Encrypt (*rate limit*), attendez quelques jours avant de réessayer. Utilisez toujours la simulation d'abord.

---

## 6. Préparer Supabase

### 6.1 Récupérer l'URL du pooler

1. Supabase › votre projet › bouton **Connect** (en haut de la page du projet).
2. Onglet des chaînes de connexion › **Transaction pooler** : copiez l'URI. Elle a la forme :
   `postgresql://postgres.<ref>:[YOUR-PASSWORD]@aws-0-<region>.pooler.supabase.com:6543/postgres`
3. Remplacez `[YOUR-PASSWORD]` par le mot de passe de la base.
   - Mot de passe oublié : *Project Settings › Database* › **Reset database password**.
   - Si le mot de passe contient `@ : / ? # [ ] %`, encodez-le pour une URL (par exemple `@` devient `%40`), ou générez-en un sans ces caractères.

Pourquoi ce choix :
- **Port 6543** (mode transaction) : l'application n'ouvre pas de pool. C'est le meilleur choix avec Passenger, qui lance plusieurs processus.
- **Port 5432** (*Session pooler*) : solution de repli ; l'application garde alors un petit pool (2 + 2 connexions par processus).
- N'utilisez pas l'hôte direct `db.<ref>.supabase.co`, joignable en IPv6 seulement.
- `sslmode=require` est ajouté automatiquement par l'application ; inutile de l'écrire.

### 6.2 Réglages réseau et sécurité (Supabase › *Project Settings › Database*)

- **SSL :** vous pouvez activer **Enforce SSL on incoming connections** ; l'application se connecte toujours en TLS.
- **Network Restrictions :** si elles sont activées, ajoutez l'IPv4 sortante du serveur o2switch. Pour l'obtenir, tapez sur le serveur `curl -4 -s https://ifconfig.me`. Sinon l'API ne pourra pas se connecter.
- **Pause des projets gratuits :** sur l'offre gratuite, un projet inactif peut être mis en pause. Pour un service en production, l'offre payante de Supabase évite ce risque et donne des sauvegardes quotidiennes.

---

## 7. Récupérer le code (Git Version Control)

### 7.1 Par cPanel

1. cPanel › outil **Git™ Version Control** › bouton **Créer**.
2. Activez **Clone a repository**, puis remplissez :

   | Champ | Valeur |
   |---|---|
   | **Clone URL** | `https://github.com/Umar-Elhaj/Greennew.git` |
   | **Repository Path** | `/home/<compte>/green` |
   | **Repository Name** | `green` |

3. Cliquez sur **Créer**. Le clonage prend quelques minutes : le dépôt contient le modèle ONNX (16 Mo) et d'autres fichiers de modèle.

**Dépôt privé :** l'outil n'accepte pas d'identifiants dans l'URL. Utilisez une URL `ssh://git@github.com/Umar-Elhaj/Greennew.git` avec une **clé de déploiement** :
1. Sur le serveur : `ssh-keygen -t ed25519 -f ~/.ssh/github_green -N ""`.
2. Ajoutez le contenu de `~/.ssh/github_green.pub` dans GitHub › dépôt › *Settings › Deploy keys* › **Add deploy key**, en **lecture seule**.
3. Ajoutez ce bloc dans `~/.ssh/config` du serveur :
   ```
   Host github.com
       IdentityFile ~/.ssh/github_green
       IdentitiesOnly yes
   ```
4. Acceptez une fois l'empreinte du serveur : `ssh -T git@github.com`.

### 7.2 Choisir la branche (sur le serveur)

```bash
cd ~/green
git fetch origin
git checkout <branche>
git log --oneline -1                       # notez le commit déployé
ls -lh Models/best_efficientnet.onnx       # doit exister (environ 16 Mo)
```

> **Sans Git :** depuis votre poste, `rsync -av --exclude .git --exclude .venv --exclude node_modules --exclude 'Models/*.pth' --exclude 'Models/*tflite*' ./ green-o2switch:green/`

---

## 8. Créer les dossiers des images et des journaux

Sur le serveur :

```bash
mkdir -p ~/green_media && chmod 700 ~/green_media   # images analysées : privées, hors du web
mkdir -p ~/logs                                     # journal Passenger
mkdir -p ~/green/backend/tmp                        # pour le fichier de redémarrage
```

- **Ne placez jamais `green_media` sous `public_html`** ni sous la racine des documents d'un domaine. Les images ne sont servies que par l'API (`GET /api/media/…`), avec authentification ou lien signé.
- Chaque analyse occupe environ 0,2 à 0,6 Mo (image réduite à 2 048 px, plus une miniature).

---

## 9. Créer l'application Python (Setup Python App)

### 9.1 Générer la clé secrète

Sur le serveur (ou votre poste) :

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copiez le résultat dans votre gestionnaire de mots de passe : c'est `SECRET_KEY`.
- Ne la changez plus ensuite : un changement déconnecte tous les utilisateurs et invalide les liens d'images signés.
- Elle doit être identique dans *Setup Python App* et dans `~/.green/env` (étape 10).

### 9.2 Créer l'application

1. cPanel › catégorie **Logiciels** › **Setup Python App** › bouton **Create Application**.
2. Remplissez :

   | Champ | Valeur |
   |---|---|
   | **Python Version** | `3.12` (sinon 3.11 ou 3.13) |
   | **Application Root** | `green/backend` |
   | **Application URL** | choisissez `api.mondomaine.cm` dans la liste, chemin vide |
   | **Application startup file** | `passenger_wsgi.py` |
   | **Application Entry Point** | `application` |
   | **Passenger log file** | `/home/<compte>/logs/green-api.log` |

3. Section **Environment variables** : cliquez sur **Add Variable** pour chacune des variables ci-dessous (nom exact, valeur sans guillemets), en validant chaque ligne.

   | Name | Value | Obligatoire |
   |---|---|---|
   | `DATABASE_URL` | URI du pooler de l'étape 6.1 | **oui** : sans elle, l'API refuse de démarrer |
   | `SECRET_KEY` | clé de l'étape 9.1 | **oui** : sans elle, l'API refuse de démarrer |
   | `DEBUG` | `false` | oui (valeur de sécurité) |
   | `MEDIA_DIR` | `/home/<compte>/green_media` | **oui en pratique** |
   | `INFERENCE_BACKEND` | `onnx` | recommandé |
   | `MODEL_VERSION` | `efficientnet-v1` | recommandé |
   | `MAX_UPLOAD_MB` | `8` | facultatif |
   | `CORS_ORIGINS` | *(ne pas créer, ou vide)* : inutile avec la réécriture Vercel | non |
   | `WARMUP` | *(ne pas créer)* : le modèle se charge à la première analyse | non |
   | `MODEL_PATH` | *(ne pas créer)* : `Models/best_efficientnet.onnx` par défaut | non |
   | `GEMINI_API_KEY`, `GEMINI_MODEL`, `WEATHER_API_KEY` | voir l'étape 17 | non |

4. Cliquez sur **Create**. cPanel crée l'environnement virtuel et écrit un `.htaccess` dans `/home/<compte>/api.mondomaine.cm/`.
5. En haut de la page de l'application, **copiez la commande « source … »**, qui active l'environnement. Elle ressemble à :
   `source /home/<compte>/virtualenv/green/backend/3.12/bin/activate && cd /home/<compte>/green/backend`

> **Ne modifiez jamais l'*Application Root* après la création** : o2switch le déconseille. Pour le changer, supprimez l'application (**Destroy**, qui ne touche pas au code) et recréez-la.
>
> **Pour modifier une variable plus tard :** page de l'application › *Environment variables* › modifier la valeur › **Save**, puis **Restart**.

L'application ne démarrera correctement qu'après l'étape 11 (dépendances).

---

## 10. Préparer l'environnement des scripts (SSH et tâches cron)

Les variables de *Setup Python App* sont transmises **uniquement à l'application**. Un terminal SSH ou une tâche cron ne les voit pas. Les scripts d'administration (`alembic`, `db_check.py`, `set_role.py`, `media_report.py`) refusent de démarrer sans `DATABASE_URL`, pour ne pas travailler par erreur sur une base SQLite locale.

### 10.1 Fichier d'environnement privé

Sur le serveur, créez le fichier sans que les valeurs apparaissent à l'écran ni dans l'historique :

```bash
mkdir -p ~/.green && chmod 700 ~/.green
read -rsp 'DATABASE_URL : ' V1; echo
read -rsp 'SECRET_KEY : ' V2; echo
( umask 077; printf 'export DATABASE_URL=%q\nexport SECRET_KEY=%q\nexport MEDIA_DIR=%q\n' \
    "$V1" "$V2" "$HOME/green_media" > ~/.green/env )
unset V1 V2
ls -l ~/.green/env        # doit afficher -rw------- (lisible par vous seul)
```

### 10.2 Lanceur de commandes

```bash
cat > ~/.green/run.sh <<'SH'
#!/bin/bash
# Lance une commande GREEN avec l'environnement de production.
set -a; . "$HOME/.green/env"; set +a
source "$HOME/virtualenv/green/backend/3.12/bin/activate"
cd "$HOME/green" || exit 1
exec "$@"
SH
chmod 700 ~/.green/run.sh
```

Si vous avez choisi une autre version de Python à l'étape 9, remplacez `3.12` dans le chemin.

Désormais, toute commande d'administration s'écrit :

```bash
~/.green/run.sh python scripts/db_check.py
```

> Pour changer de mot de passe Supabase ou de clé, mettez à jour **les deux endroits** : *Setup Python App* (puis **Restart**) et `~/.green/env` (refaire l'étape 10.1).

---

## 11. Installer les dépendances

Sur le serveur, en SSH (pas dans le *Terminal* web) :

```bash
source /home/<compte>/virtualenv/green/backend/3.12/bin/activate
cd ~/green
pip install --upgrade pip
pip install -r backend/requirements-prod.txt
```

`requirements-prod.txt` ne contient **pas** PyTorch : l'inférence passe par ONNX Runtime, avec un environnement d'environ 450 Mo. Toutes les dépendances ont des roues précompilées : aucun compilateur n'est nécessaire.

Vérifications :

```bash
python -c "import onnxruntime, fastapi, a2wsgi, psycopg2, PIL, sklearn; print('ok', onnxruntime.__version__)"
# Chargement réel du modèle ONNX (environnement de production chargé)
~/.green/run.sh bash -c 'cd backend && python -c "import inference; inference.load(); print(\"modèle chargé :\", inference.is_loaded())"'
```

Résultat attendu : `ok 1.31.0` puis `modèle chargé : True`.

> **Méthode alternative dans cPanel :** dans *Setup Python App*, champ *Configuration files*, ajoutez `requirements-prod.txt` (**Add**), puis cliquez sur **Run pip install**. Sur une installation lourde, la méthode SSH est plus fiable.
>
> **Si `pip` réclame `gcc`** (« compiler access blocked ») : la version de Python choisie n'a pas de roue pour un paquet. Choisissez 3.12 ou 3.11 plutôt que de demander l'ouverture du compilateur.

---

## 12. Migrer la base de données (CP2)

> **Point de contrôle humain.** Les migrations sont **additives** : elles ajoutent des colonnes, une table, des index et des contraintes, sans suppression. Lisez le SQL avant de l'appliquer.

### 12.1 État des lieux (lecture seule)

```bash
~/.green/run.sh python scripts/db_check.py
```

Le script affiche la version de PostgreSQL, le mode du pooler, la révision Alembic actuelle et la révision attendue, ainsi que le nombre de lignes par table. L'URL n'est jamais affichée.

| Code de sortie | Signification |
|---|---|
| 0 | base à jour |
| 1 | schéma en retard |
| 2 | base injoignable |

### 12.2 Base existante créée avant Alembic (`current=None`)

C'est le cas de la base Supabase actuelle de GREEN.

1. **Affichez le SQL qui sera exécuté**, sans rien appliquer :
   ```bash
   ~/.green/run.sh bash -c 'cd backend && alembic upgrade 0001_baseline:head --sql' > ~/green-migration.sql
   less ~/green-migration.sql
   ```
   Vérifiez qu'il ne contient que des `ALTER TABLE … ADD`, `CREATE TABLE`, `CREATE INDEX` et des contraintes, sans `DROP` ni `DELETE`.
2. **Après validation** :
   ```bash
   ~/.green/run.sh bash -c 'cd backend && alembic stamp 0001_baseline && alembic upgrade head'
   ~/.green/run.sh python scripts/db_check.py      # doit indiquer current = head, code 0
   ```

### 12.3 Base Supabase neuve et vide

```bash
~/.green/run.sh bash -c 'cd backend && alembic upgrade head'
~/.green/run.sh python scripts/db_check.py
```

La révision de base active la *Row Level Security* sur toutes les tables, sans politique. L'API REST publique de Supabase (clé `anon`) ne peut donc rien lire. L'API GREEN, qui se connecte comme propriétaire des tables, n'est pas concernée.

> **Ne lancez jamais `alembic downgrade` en production** : les retours en arrière suppriment des colonnes.

---

## 13. Sécuriser le domaine (.htaccess)

1. cPanel › **Gestionnaire de fichiers**.
2. **Paramètres** (en haut à droite) › cochez **Afficher les fichiers cachés (dotfiles)** › **Save**.
3. Ouvrez `/home/<compte>/api.mondomaine.cm/`, sélectionnez `.htaccess` › **Modifier**.
4. Collez **en tout début de fichier**, au-dessus du bloc `# DO NOT REMOVE. CLOUDLINUX PASSENGER CONFIGURATION BEGIN` (bloc à laisser intact) :

```apache
# ---- GREEN : sécurité du domaine de l'API ----
# 1. HTTPS obligatoire (le certificat de l'étape 5 doit être actif)
RewriteEngine On
RewriteCond %{HTTPS} !=on
RewriteRule ^ https://%{HTTP_HOST}%{REQUEST_URI} [L,R=301]

<IfModule mod_headers.c>
  # 2. HSTS : HTTPS seulement pendant un an
  Header always set Strict-Transport-Security "max-age=31536000; includeSubDomains" env=HTTPS
  # 3. L'API ne doit pas être indexée par les moteurs de recherche
  Header always set X-Robots-Tag "noindex, nofollow"
</IfModule>

# 4. Jamais de fichiers privés, même en cas d'erreur de placement
<FilesMatch "^\.env|\.(py|db|sqlite3|ini|pth|onnx|tflite)$">
  Require all denied
</FilesMatch>

# 5. Compression des réponses JSON et texte (facultatif)
<IfModule mod_deflate.c>
  AddOutputFilterByType DEFLATE application/json application/geo+json text/csv text/html text/css application/javascript
</IfModule>
# ---- fin GREEN ----
```

5. Cliquez sur **Enregistrer les modifications**.

Les autres en-têtes de sécurité (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`) sont ajoutés par l'application elle-même. La même configuration, sans les points 3 et 5, est versionnée dans `deploy/o2switch/htaccess-snippet.conf`.

---

## 14. Démarrer et vérifier l'API

### 14.1 (Re)démarrer

Deux façons équivalentes :
- cPanel › **Setup Python App** › votre application › bouton **Restart** ;
- sur le serveur : `touch ~/green/backend/tmp/restart.txt`.

### 14.2 Vérifier

Depuis votre poste :

```bash
curl -s https://api.mondomaine.cm/api/health; echo
```

Réponse attendue (ordre des clés indifférent) :

```json
{"status":"ok","app":"…","version":"…","model_version":"efficientnet-v1",
 "models":{"efficientnet":"lazy","inference_backend":"onnx","rag_index":"lazy"},
 "services":{"greenbot":false,"weather":false}}
```

`"lazy"` est normal : le modèle se charge à la première analyse.

Contrôles complémentaires :

```bash
curl -sI https://api.mondomaine.cm/api/health | grep -i -E 'strict-transport|x-content-type|x-robots'
curl -s -o /dev/null -w '%{http_code}\n' http://api.mondomaine.cm/api/health    # 301 (vers HTTPS)
curl -s -o /dev/null -w '%{http_code}\n' https://api.mondomaine.cm/docs         # 404 (documentation désactivée en production)
curl -s -o /dev/null -w '%{http_code}\n' https://api.mondomaine.cm/api/parcels  # 401 (authentification requise)
```

### 14.3 Journaux

```bash
tail -n 50 ~/logs/green-api.log
```

| Message dans le journal | Action |
|---|---|
| `SECRET_KEY is not set` | Ajouter la variable (étape 9), **Save**, **Restart** |
| `DATABASE_URL is not set` | Idem |
| `Database schema at revision …` | Faire l'étape 12 |
| `could not connect to server` / délai dépassé | Port du pooler bloqué (étape 3) ou restrictions réseau Supabase (étape 6.2) |

Pour un diagnostic ponctuel, o2switch permet d'afficher les erreurs détaillées dans le navigateur. Ajoutez temporairement en tête du `.htaccess` :

```apache
PassengerAppEnv development
PassengerFriendlyErrorPages on
```

**Retirez ces deux lignes dès le problème résolu** : elles exposent des détails internes.

---

## 15. Régler Tiger Protect (pare-feu applicatif)

Tiger Protect filtre les requêtes avant qu'elles n'atteignent l'API. Son mode par défaut convient, avec quatre précautions :

1. cPanel › outil **Tiger Protect**.
2. **Laissez la règle par défaut active.**
3. **N'activez jamais le mode « Je suis attaqué »** sur `api.mondomaine.cm`. Ses challenges ne peuvent pas être résolus par l'application (appels `fetch` en JSON) ni par le relais Vercel : toute l'API répondrait 403.
4. **N'activez pas les règles « Bloquer POST »** et ne bloquez ni les requêtes sans *User-Agent*, ni les réseaux d'hébergeurs (*ASN*). Les appels relayés par Vercel viennent de centres de données.
5. Pas de blocage par pays : les utilisateurs sont au Cameroun.

**Symptôme d'un blocage :** l'étape 19 donne des `403` avec une page HTML de Tiger Protect au lieu d'un JSON. Désactivez la règle en cause, ou ouvrez un ticket avec l'URL bloquée, l'heure et votre IP.

---

## 16. Créer les comptes à rôle

Il n'y a pas d'écran d'administration. Les rôles se donnent sur le serveur, **après l'inscription normale** de la personne dans l'application (étape 18 terminée).

| Rôle | Droits |
|---|---|
| `farmer` | par défaut : ses parcelles, analyses, missions |
| `agronomist` | voit les images des analyses et valide les étiquettes |
| `partner` | accès à GREEN Data (statistiques agrégées) |
| `admin` | tout |

```bash
~/.green/run.sh python scripts/set_role.py --phone +2376XXXXXXXX --role admin
~/.green/run.sh python scripts/set_role.py --email partenaire@exemple.org --role partner
~/.green/run.sh python scripts/set_role.py --list          # comptes qui ne sont pas « farmer »
```

La personne doit **se reconnecter** pour que le nouveau rôle apparaisse dans le menu.

> **GREEN Data** masque tout chiffre portant sur moins de 5 analyses **ou** moins de 5 exploitants consentants. Au démarrage, la plupart des cases sont donc « masquées » : c'est voulu.
>
> N'exécutez **pas** `scripts/seed_demo.py` en production : ce script de démonstration est réservé au développement.

---

## 17. Activer GreenBot et la météo

### 17.1 GreenBot (Google Gemini)

1. [Google AI Studio](https://aistudio.google.com) › **Get API key** › **Create API key**.
2. cPanel › *Setup Python App* › votre application › **Add Variable** :
   - `GEMINI_API_KEY` = la clé ;
   - `GEMINI_MODEL` : facultatif, `gemini-3.1-flash-lite` par défaut.
3. **Save**, puis **Restart**.

### 17.2 Météo (OpenWeatherMap)

1. Créez un compte sur [openweathermap.org](https://openweathermap.org) › menu du compte › **My API keys** › créez une clé. Son activation peut prendre jusqu'à quelques heures.
2. *Setup Python App* › **Add Variable** : `WEATHER_API_KEY` = la clé.
3. **Save**, puis **Restart**.

Vérifiez :

```bash
curl -s https://api.mondomaine.cm/api/health | python3 -m json.tool | grep -A3 services
# "greenbot": true, "weather": true
```

---

## 18. Brancher le frontend Vercel

### 18.1 Écrire la réécriture `/api/*` (sur votre poste)

```bash
cd Greennew
python3 scripts/configure_vercel.py https://api.mondomaine.cm
python3 scripts/configure_vercel.py --check      # affiche l'origine de l'API configurée
git add frontend/vercel.json
git commit -m "chore(vercel): proxy /api to o2switch"
git push
```

Fusionnez ensuite dans la branche suivie par Vercel (en général `main`, par une pull request).

### 18.2 Réglages du projet Vercel

1. Vercel › votre projet › **Settings**.
   - **Root Directory** : `frontend`.
   - **Framework Preset** : `Other`.
   - Build Command et Output Directory : vides (site statique).
2. Les pages sont statiques. L'application n'a besoin d'**aucune variable d'environnement côté Vercel** : elle appelle `/api/…` sur sa propre origine, et Vercel relaie vers o2switch.
3. **Settings › Domains** › **Add** › `app.mondomaine.cm`. Créez chez votre gestionnaire DNS l'enregistrement que Vercel affiche, en général `CNAME app → cname.vercel-dns.com`. Si le DNS est chez o2switch : cPanel › **Éditeur de zone** › ajoutez ce `CNAME`.
4. **Redéployez** (onglet *Deployments* › dernier déploiement › **Redeploy**), ou poussez un commit.

Vérifiez que le relais fonctionne :

```bash
curl -s https://app.mondomaine.cm/api/health; echo     # même JSON qu'à l'étape 14
```

Le navigateur ne voit qu'une seule origine (`app.mondomaine.cm`) : pas de CORS. Le jeton d'authentification et les liens d'images signés passent par la même réécriture.

> **Piège connu :** tant que `configure_vercel.py` n'a pas été exécuté et le résultat déployé, **tous les appels `/api/*` renvoient 404 sur Vercel**.

---

## 19. Tester de bout en bout

### 19.1 Test de fumée automatique

1. Dans l'application (`https://app.mondomaine.cm/register`), créez un **compte de test dédié**.
2. Donnez-lui le rôle `partner` (étape 16) pour inclure GREEN Data.
3. Depuis votre poste, à la racine du dépôt :

```bash
SMOKE_IDENTIFIER=+2376XXXXXXXX SMOKE_PASSWORD='…' scripts/smoke_prod.sh https://app.mondomaine.cm
SMOKE_IDENTIFIER=+2376XXXXXXXX SMOKE_PASSWORD='…' scripts/smoke_prod.sh https://api.mondomaine.cm
```

Toutes les lignes doivent être `PASS` (code de sortie 0) :
- santé ;
- connexion ;
- liste des parcelles ;
- analyse d'une image (inférence ONNX réelle) ;
- lecture de l'image avec jeton, avec lien signé, et `401` sans les deux ;
- GREEN Data.

> Préfixez la commande d'une espace pour qu'elle n'entre pas dans l'historique du shell (selon la configuration de `HISTCONTROL`), ou saisissez le mot de passe avec `read -rs SMOKE_PASSWORD; export SMOKE_PASSWORD`.

### 19.2 Recette fonctionnelle (navigateur, sur téléphone si possible)

| # | Fonction | Action | Résultat attendu |
|---|---|---|---|
| 1 | Inscription | `/register`, numéro `6XXXXXXXX`, région, consentement | Arrivée sur le tableau de bord |
| 2 | Connexion | Se déconnecter (*Paramètres*), se reconnecter avec `+237 6…` | Accepté, avec ou sans `+237` |
| 3 | Langue | Bouton FR/EN de l'en-tête | Tout le texte change sans rechargement |
| 4 | Analyse | `/camera` › onglet *Photos* › importer une photo de feuille | Fiche « maladie probable » avec la mention « pas un diagnostic » |
| 5 | Hors ligne | Couper le réseau, importer 2 photos, rétablir | File « 2 en attente » puis envoi automatique |
| 6 | Historique | `/history` › une ligne | Fiche avec image (servie par `/api/media`) |
| 7 | Parcelles | `/map` › nouvelle parcelle › 4 points › enregistrer | Surface, périmètre et région calculés |
| 8 | Mission | Parcelle › grille 10 m › aperçu › créer | Mission, exports JSON et GeoJSON téléchargeables |
| 9 | Carte de chaleur | Analyses avec mission et cellule, puis ouvrir la mission | Cellules colorées, légende |
| 10 | GreenBot | Depuis une fiche › « Demander à GreenBot » | Réponse dans la langue de l'interface |
| 11 | Météo | Tableau de bord | Météo de la région, conseil agronomique |
| 12 | Bibliothèque | `/diseases` › recherche | Fiches FR/EN |
| 13 | GREEN Data | Compte `partner` › `/green-data` › export CSV | Statistiques (cases masquées sous 5), CSV téléchargé |
| 14 | Rôles | Compte `farmer` › `/green-data` | Accès refusé |
| 15 | Thème | Basculer clair/sombre | Lisible dans les deux thèmes |

Pour suivre la recette, ouvrez `tail -f ~/logs/green-api.log` sur le serveur.

---

## 20. Exploitation : tâches planifiées, sauvegardes, surveillance

### 20.1 Tâches cron (cPanel › **Tâches Cron**)

1. Section **E-mail de la tâche cron** : saisissez l'adresse qui recevra les sorties › **Mettre à jour l'e-mail**. Une tâche n'envoie un e-mail que si elle produit une sortie.
2. Section **Ajouter une nouvelle tâche cron** : choisissez la fréquence dans **Paramètres communs**, collez la commande, puis cliquez sur **Ajouter une nouvelle tâche cron**.

| Fréquence | Commande | Rôle |
|---|---|---|
| Toutes les 15 min (`*/15 * * * *`) | `curl -fsS -o /dev/null https://api.mondomaine.cm/api/health \|\| echo "API GREEN indisponible"` | Alerte si l'API ne répond plus |
| Une fois par jour (`0 6 * * *`) | `$HOME/.green/run.sh python scripts/db_check.py >/dev/null 2>&1 \|\| echo "GREEN : base injoignable ou schéma en retard"` | Alerte base |
| Une fois par semaine (`0 7 * * 1`) | `$HOME/.green/run.sh python scripts/media_report.py` | Rapport disque et images orphelines (sans rien supprimer) |

> `media_report.py --apply` supprime les fichiers d'images orphelins. Lancez-le **à la main** après avoir lu le rapport, jamais en cron. Il refuse de s'exécuter si la base ne contient aucune image.

### 20.2 Sauvegardes

| Donnée | Où | Comment |
|---|---|---|
| Images (`~/green_media`) | o2switch | Sauvegardes automatiques o2switch, consultables et restaurables dans cPanel › **JetBackup** |
| Copie hors site des images | Votre poste ou un stockage externe | `rsync -az green-o2switch:green_media/ ./sauvegarde-green-media/` (hebdomadaire) |
| Base de données | Supabase | *Database › Backups* (offre payante : sauvegardes quotidiennes). Sur l'offre gratuite, faites un export régulier depuis votre poste, avec un `pg_dump` de même version majeure que le serveur, via le *Session pooler* (port 5432) : `pg_dump "<URL session pooler>" -Fc -f green-$(date +%F).dump` |
| Code | GitHub | Le dépôt fait foi ; notez le commit déployé |
| Secrets | Gestionnaire de mots de passe | `SECRET_KEY`, URL de la base, clés Gemini et météo |

### 20.3 Surveillance

- **Externe (recommandé) :** un service gratuit de surveillance HTTP, comme UptimeRobot, sur `https://app.mondomaine.cm/api/health`, toutes les 5 minutes, avec alerte e-mail ou SMS.
- **Ressources :** cPanel › **Utilisation des ressources**. Atteindre ponctuellement un plafond est normal ; plus de 50 % en continu signale un problème. Des erreurs `503` indiquent trop de processus.
- **Disque :** cPanel › *Utilisation du disque*, ou le rapport hebdomadaire.
- **Journaux Apache :** cPanel › **Erreurs** et **Accès brut**.

---

## 21. Mettre à jour et revenir en arrière

### 21.1 Mise à jour

1. Notez le commit actuel : `cd ~/green && git log --oneline -1`.
2. Récupérez le code : cPanel › *Git™ Version Control* › **Gérer** › onglet **Pull or Deploy** › **Update from Remote**. Équivalent en SSH :
   ```bash
   cd ~/green && git pull
   ```
3. Mettez à jour les dépendances :
   ```bash
   source /home/<compte>/virtualenv/green/backend/3.12/bin/activate && pip install -r ~/green/backend/requirements-prod.txt
   ```
4. Vérifiez la base, puis relisez et appliquez une éventuelle nouvelle migration (CP2) :
   ```bash
   ~/.green/run.sh python scripts/db_check.py
   ~/.green/run.sh bash -c 'cd backend && alembic upgrade head --sql' | less
   ~/.green/run.sh bash -c 'cd backend && alembic upgrade head'
   ```
5. Redémarrez et vérifiez :
   ```bash
   touch ~/green/backend/tmp/restart.txt
   curl -s https://api.mondomaine.cm/api/health
   ```
6. Relancez le test de fumée (étape 19.1).

### 21.2 Retour arrière

```bash
cd ~/green && git checkout <commit-précédent>
source /home/<compte>/virtualenv/green/backend/3.12/bin/activate && pip install -r backend/requirements-prod.txt
touch backend/tmp/restart.txt
```

- Les migrations étant additives, l'ancien code fonctionne avec le nouveau schéma. **Pas de `alembic downgrade`.**
- Les images de `~/green_media` ne sont jamais touchées par un déploiement.

---

## 22. Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| `503` ou page Passenger « Web application could not be started » | Erreur au démarrage | `tail ~/logs/green-api.log` ; étape 14.3 |
| `ModuleNotFoundError` dans le journal | Dépendances non installées dans **le** virtualenv de l'application | Étape 11 avec la commande `source` exacte de *Setup Python App* |
| `No matching distribution found for onnxruntime==…` | Pas de roue pour cette version de Python | Recréer l'application en Python 3.12 ou 3.11 |
| Erreur citant `gcc`, `make` ou `ld` | Un paquet tente une compilation ; le compilateur est bloqué par défaut | Même solution ; sinon, demander au support l'accès au compilateur |
| `pip` : `out of memory` ou `fork failed` | Terminal web de cPanel trop limité | Utiliser un vrai client SSH (étape 2) |
| `server does not support SSL` | Base locale sans TLS (annexe B) | Ajouter `?sslmode=disable` à l'URL **uniquement** pour une base sur `localhost` |
| `connection timed out` vers `pooler.supabase.com` | Port sortant bloqué ou restriction réseau Supabase | Étapes 3 et 6.2 ; ticket o2switch |
| `password authentication failed` | Mot de passe faux ou mal encodé dans l'URL | Étape 6.1 (encodage des caractères spéciaux) |
| `Database schema at revision …` | Migration non appliquée | Étape 12 |
| `403` avec une page HTML Tiger Protect | Règle du pare-feu applicatif | Étape 15 |
| `413` à l'envoi d'une photo | Image de plus de 8 Mo ou de plus de 50 mégapixels | Normal ; ajuster `MAX_UPLOAD_MB` si besoin (l'application réduit déjà les photos à 1 600 px avant envoi) |
| `404` sur toutes les routes `/api/*` via Vercel | Réécriture absente de `vercel.json` | Étape 18.1 |
| Images de l'historique absentes (`401`) | Session expirée, ou `SECRET_KEY` modifiée | Se reconnecter ; ne pas changer `SECRET_KEY` |
| Première analyse lente (quelques secondes) | Chargement paresseux du modèle par processus | Normal ; `WARMUP=1` le précharge, au prix d'environ 180 Mo par processus |
| GreenBot « non configuré » | `GEMINI_API_KEY` absente | Étape 17.1 |
| Météo « non activée » ou `401` du fournisseur | Clé absente ou pas encore active | Étape 17.2 ; attendre l'activation de la clé |
| GREEN Data affiche « masqué » partout | Moins de 5 analyses ou de 5 exploitants consentants par case | Comportement voulu (protection des exploitants) |
| `DATABASE_URL is not set` en lançant un script | Environnement non chargé | Passer par `~/.green/run.sh` (étape 10) |
| `Permission denied (publickey)` en SSH | IP non autorisée, ou clé absente | Étape 2.1 (IP), puis 2.2 (clé) |

---

## Annexe A : tout héberger sur o2switch (sans Vercel)

L'API sert aussi les pages du frontend : `main.py` expose `/`, `/dashboard`, `/map`, etc., ainsi que les fichiers statiques de `frontend/`. On peut donc tout héberger sur o2switch, sur **une seule origine** : pas de réécriture, pas de CORS. La décision du projet (CP1) reste Vercel pour le frontend ; cette variante est une solution de repli simple.

1. Étape 4 : créez `app.mondomaine.cm` au lieu de (ou en plus de) `api.mondomaine.cm`, puis faites l'étape 5 pour ce domaine.
2. Étape 9 : **Application URL** = `app.mondomaine.cm`. Laissez `CORS_ORIGINS` vide.
3. Étape 13 : même `.htaccess`, mais **sans** la ligne `X-Robots-Tag` si les pages doivent être indexées.
4. Ignorez l'étape 18. Testez avec `scripts/smoke_prod.sh https://app.mondomaine.cm`.

Inconvénient : les fichiers statiques sont servis par Python et non par un CDN. La différence est sensible seulement avec beaucoup de trafic.

---

## Annexe B : base PostgreSQL d'o2switch (si Supabase est injoignable)

À n'envisager que si o2switch ne peut pas ouvrir les ports sortants du pooler (étape 3). Cette variante **change l'architecture décidée** (Supabase) : elle demande votre accord, et un transfert des données existantes avec `pg_dump`/`pg_restore`, à préparer séparément.

1. cPanel › **Bases de données PostgreSQL** :
   - créez la base `green` (cPanel la préfixe : `<compte>_green`) ;
   - créez un utilisateur avec un mot de passe fort ;
   - ajoutez l'utilisateur à la base avec **tous les privilèges**.
2. Vérifiez la version (10 ou plus requise) : `psql -h localhost -U <compte>_<utilisateur> <compte>_green -c 'select version()'`.
3. `DATABASE_URL` (étapes 9 et 10) :
   `postgresql://<compte>_<utilisateur>:<mot-de-passe>@localhost:5432/<compte>_green?sslmode=disable`
   `sslmode=disable` n'est acceptable **que** parce que la connexion reste sur la machine (`localhost`).
4. Base neuve : `~/.green/run.sh bash -c 'cd backend && alembic upgrade head'`.
5. Sauvegardes : JetBackup inclut les bases de l'hébergement ; vérifiez-le dans l'outil.

---

## Annexe C : récapitulatif des variables d'environnement

Référence commentée : `.env.example` à la racine du dépôt.

| Variable | Où | Valeur | Obligatoire |
|---|---|---|---|
| `DATABASE_URL` | *Setup Python App* et `~/.green/env` | URI du *Transaction pooler* Supabase | oui |
| `SECRET_KEY` | *Setup Python App* et `~/.green/env` | 48 octets aléatoires (étape 9.1) | oui |
| `MEDIA_DIR` | *Setup Python App* et `~/.green/env` | `/home/<compte>/green_media` | oui en pratique |
| `DEBUG` | *Setup Python App* | `false` | valeur de sécurité |
| `INFERENCE_BACKEND` | *Setup Python App* | `onnx` | non (par défaut) |
| `MODEL_VERSION` | *Setup Python App* | `efficientnet-v1` | non |
| `MODEL_PATH` | *Setup Python App* | vide : `Models/best_efficientnet.onnx` | non |
| `MAX_UPLOAD_MB` | *Setup Python App* | `8` | non |
| `WARMUP` | *Setup Python App* | vide (ou `1` pour précharger le modèle) | non |
| `CORS_ORIGINS` | *Setup Python App* | vide avec la réécriture Vercel | non |
| `GEMINI_API_KEY` | *Setup Python App* | clé Google AI Studio | non (GreenBot) |
| `GEMINI_MODEL` | *Setup Python App* | vide : `gemini-3.1-flash-lite` | non |
| `WEATHER_API_KEY` | *Setup Python App* | clé OpenWeatherMap | non (météo) |

---

## Annexe D : liste de contrôle finale

- [ ] SSH par clé avec l'alias `green-o2switch` (étape 2)
- [ ] Diagnostic conforme : Python 3.11 à 3.13, glibc ≥ 2.28, AVX, pooler joignable (étape 3)
- [ ] `api.mondomaine.cm` résout vers o2switch (étape 4) et répond en HTTPS valide (étape 5)
- [ ] Code cloné dans `~/green`, branche et commit notés (étape 7)
- [ ] `~/green_media` en `700`, hors du web (étape 8)
- [ ] Application Python créée avec ses variables (étape 9)
- [ ] `~/.green/env` en `600` et `~/.green/run.sh` en place (étape 10)
- [ ] Dépendances installées, `modèle chargé : True` (étape 11)
- [ ] `db_check.py` : `current = head`, code 0 (étape 12)
- [ ] `.htaccess` sécurisé : redirection HTTPS, HSTS, `noindex` (étape 13)
- [ ] `/api/health` : `status: ok`, `inference_backend: onnx` (étape 14)
- [ ] Tiger Protect sans mode « Je suis attaqué » (étape 15)
- [ ] Comptes `admin` et `partner` attribués (étape 16)
- [ ] GreenBot et météo : `services` à `true` si souhaité (étape 17)
- [ ] `https://app.mondomaine.cm/api/health` répond (étape 18)
- [ ] `smoke_prod.sh` : toutes les lignes `PASS` sur les deux domaines (étape 19.1)
- [ ] Recette fonctionnelle des 15 points (étape 19.2)
- [ ] Tâches cron, sauvegardes et surveillance externe en place (étape 20)
