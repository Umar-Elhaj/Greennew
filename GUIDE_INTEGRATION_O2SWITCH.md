# Guide d'intégration de GREEN sur o2switch (offre Pro) : base de données, backend et frontend

Ce guide décrit, clic par clic, la mise en production complète de GREEN sur un hébergement **o2switch, offre Pro** (24 threads, 64 Go de RAM partagés, 16 « lunes », c'est-à-dire 16 comptes cPanel séparés). **Tout est hébergé chez o2switch**, sur un seul domaine :

| Brique | Technologie | Où |
|---|---|---|
| **1. Base de données** | MySQL / MariaDB d'o2switch (pas de PostgreSQL) | cPanel › *Bases de données MySQL*, sur la même machine que l'application |
| **2. Backend** | API FastAPI (inférence ONNX, GREEN Map, GREEN Data, GreenBot, météo, images) | cPanel › *Setup Python App* (Passenger) |
| **3. Frontend** | Pages HTML/JS (Leaflet, Chart.js, Turf inclus dans le dépôt) | Racine du domaine, servie par Apache |

Les trois intégrations se font **dans cet ordre**, qui est celui qui fonctionne le mieux :
1. **La base d'abord** : l'API refuse de démarrer sans `DATABASE_URL`, et ses tables doivent exister avant la première requête.
2. **Le backend ensuite** : il se vérifie seul (`/api/health`, `db_check.py`) avant que des utilisateurs n'arrivent.
3. **Le frontend en dernier** : les pages appellent `/api/…` sur le même domaine ; publiées avant l'API, elles n'afficheraient que des erreurs.

À la fin, toutes les fonctions implémentées sont en service et vérifiées : comptes et rôles ; analyse photo (ONNX) et stockage privé des images ; historique et fiches ; parcelles, grilles, missions et carte de chaleur ; GREEN Data ; GreenBot et météo.

> **Points de contrôle.** La création du schéma de production et l'éventuelle reprise des données (CP2, étapes 9 et 15), ainsi que toutes les étapes qui modifient le serveur (CP3), sont faites par vous. Lisez chaque commande avant de l'exécuter.
>
> **Secrets.** Ne collez jamais le mot de passe de la base, l'URL de connexion, la clé secrète ou une clé d'API dans un fichier du dépôt, un ticket, un e-mail ou une capture d'écran. Ils ne vont qu'à quatre endroits :
> - cPanel › *Setup Python App* ;
> - le fichier `~/.green/env` du serveur (étape 12) ;
> - le fichier `~/.my.cnf` du serveur (étape 8, outils `mysql` et sauvegardes) ;
> - le gestionnaire de mots de passe de l'équipe.

---

## Sommaire

**Partie 0 — Préparation**
0. [Avant de commencer](#0-avant-de-commencer)
1. [Ouvrir cPanel](#1-ouvrir-cpanel)
2. [Activer l'accès SSH](#2-activer-laccès-ssh)
3. [Diagnostic du serveur (lecture seule)](#3-diagnostic-du-serveur-lecture-seule)
4. [Créer le sous-domaine](#4-créer-le-sous-domaine)
5. [Installer le certificat HTTPS](#5-installer-le-certificat-https-lets-encrypt)
6. [Récupérer le code](#6-récupérer-le-code-git-version-control)

**Partie 1 — Base de données MySQL (MariaDB)**

7. [Créer la base et son utilisateur](#7-créer-la-base-et-son-utilisateur)
8. [Tester la connexion](#8-tester-la-connexion-et-relever-le-socket)
9. [Créer les tables (CP2)](#9-créer-les-tables-cp2)
10. [Composer `DATABASE_URL`](#10-composer-database_url)

**Partie 2 — Backend (API)**

11. [Créer l'application Python](#11-créer-lapplication-python-setup-python-app)
12. [Préparer l'environnement des scripts](#12-préparer-lenvironnement-des-scripts-ssh-et-tâches-cron)
13. [Installer les dépendances](#13-installer-les-dépendances)
14. [Vérifier la base depuis Python](#14-vérifier-la-base-depuis-python)
15. [Reprendre les données de Supabase (facultatif, CP2)](#15-reprendre-les-données-de-lancienne-base-supabase-facultatif-cp2)
16. [Sécuriser le domaine (.htaccess)](#16-sécuriser-le-domaine-htaccess)
17. [Démarrer et vérifier l'API](#17-démarrer-et-vérifier-lapi)
18. [Régler Tiger Protect](#18-régler-tiger-protect-pare-feu-applicatif)
19. [Activer GreenBot et la météo](#19-activer-greenbot-et-la-météo)

**Partie 3 — Frontend**

20. [Publier les pages](#20-publier-les-pages-dans-le-domaine)
21. [Retirer l'ancien frontend Vercel](#21-retirer-lancien-frontend-vercel)

**Partie 4 — Mise en service et exploitation**

22. [Créer les comptes à rôle](#22-créer-les-comptes-à-rôle)
23. [Tester de bout en bout](#23-tester-de-bout-en-bout)
24. [Exploitation : tâches planifiées, sauvegardes, surveillance](#24-exploitation--tâches-planifiées-sauvegardes-surveillance)
25. [Mettre à jour et revenir en arrière](#25-mettre-à-jour-et-revenir-en-arrière)
26. [Dépannage](#26-dépannage)

Annexes : [A. Variables d'environnement](#annexe-a--récapitulatif-des-variables-denvironnement) · [B. Liste de contrôle finale](#annexe-b--liste-de-contrôle-finale)

---

# Partie 0 — Préparation

## 0. Avant de commencer

### 0.1 Comptes nécessaires

| Compte | Usage | Obligatoire |
|---|---|---|
| o2switch, **offre Pro** | Base de données, API et pages | oui |
| Le domaine `gitingeniering.com` | Adresse publique de l'application : `api-green.gitingeniering.com` | oui |
| GitHub (accès au dépôt `Umar-Elhaj/Greennew`) | Récupération du code | oui |
| Supabase (ancien projet de GREEN) | Uniquement pour reprendre les données existantes (étape 15) | non |
| Google AI Studio | Clé Gemini pour GreenBot | non : sans elle, GreenBot affiche « non configuré » |
| OpenWeatherMap | Clé météo | non : sans elle, le widget affiche « non activé » |

Vercel n'est plus utilisé (étape 21).

### 0.2 Sur votre poste

- Un terminal avec `ssh`, `git`, `curl` et `python3` (Linux, macOS, ou Windows avec WSL ou Git Bash).
- Le dépôt cloné, sur la branche déployée : `main`.

### 0.3 Valeurs de ce déploiement

Les commandes de ce guide utilisent déjà ces valeurs.

| Élément | Valeur |
|---|---|
| Identifiant cPanel (nom d'utilisateur) | `sc1jsgw2086` |
| Serveur o2switch | `espadon.o2switch.net` (cPanel : `https://espadon.o2switch.net:2083`) |
| Adresse IP partagée | `109.234.161.148` |
| Répertoire de base | `/home/sc1jsgw2086` |
| Domaine | `gitingeniering.com` |
| Domaine de l'application (pages **et** API) | `api-green.gitingeniering.com` |
| Racine des documents du domaine | `/home/sc1jsgw2086/api-green.gitingeniering.com` |
| Code de l'application | `/home/sc1jsgw2086/green` |
| Base MySQL | `sc1jsgw2086_green` |
| Utilisateur MySQL | `sc1jsgw2086_greenapp` |
| Images analysées | `/home/sc1jsgw2086/green_media` |
| Branche Git déployée | `main` |
| Version de Python | `3.12` (étape 11) |

> **Nom du domaine.** Le domaine `api-green.gitingeniering.com` sert désormais l'application entière, pas seulement l'API. Si vous préférez une adresse plus parlante pour les utilisateurs (par exemple `green.gitingeniering.com`), créez ce sous-domaine à l'étape 4 et remplacez `api-green.gitingeniering.com` partout dans ce guide, **avant** de commencer.

### 0.4 Ce qui tournera en production

```
Navigateur ──HTTPS──► o2switch : api-green.gitingeniering.com
                      Apache + Tiger Protect
                        ├─ /, /css, /js, /vendor, *.html ─► fichiers du frontend (servis par Apache)
                        └─ /api/*, /dashboard, /map…     ─► Passenger ─► passenger_wsgi.py ─► a2wsgi ─► FastAPI
                                                              ├─ ONNX Runtime (Models/best_efficientnet.onnx)
                                                              ├─ images : ~/green_media (privé, hors web)
                                                              ├─ MariaDB (localhost, socket Unix) : base sc1jsgw2086_green
                                                              ├──HTTPS► Google Gemini (GreenBot, facultatif)
                                                              └──HTTPS► OpenWeatherMap (météo, facultatif)
```

Une seule origine : pas de CORS, pas de relais, et la base ne sort jamais de la machine.

Durée indicative : 1 h 30 à 2 h 30, plus la propagation DNS si vous créez des enregistrements chez un autre registraire.

---

## 1. Ouvrir cPanel

1. Connectez-vous à votre **espace client o2switch**.
2. Ouvrez le **cPanel** de l'hébergement (lien cPanel de votre service, ou `https://espadon.o2switch.net:2083`).
3. Dans la colonne de droite, panneau **Informations générales**, vérifiez que vous êtes sur le bon compte :
   - **nom d'utilisateur actuel** : `sc1jsgw2086` ;
   - **adresse IP partagée** : `109.234.161.148` (utile à l'étape 4 si le DNS du domaine est ailleurs) ;
   - **répertoire de base** : `/home/sc1jsgw2086`.

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
cat ~/.ssh/green_o2switch.pub | ssh sc1jsgw2086@espadon.o2switch.net \
  "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 644 ~/.ssh/authorized_keys"
```

### 2.3 Créer l'alias `green-o2switch`

Le bloc ci-dessous est à **ajouter** sur votre poste. Si `~/.ssh/config` n'existe pas encore, créez-le :

```bash
touch ~/.ssh/config && chmod 600 ~/.ssh/config
nano ~/.ssh/config    # collez le bloc, puis Ctrl+O, Entrée, Ctrl+X
```

```
Host green-o2switch
    HostName espadon.o2switch.net
    User sc1jsgw2086
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
# Client et serveur MySQL/MariaDB
mysql --version
# Limites du compte et espace disque
ulimit -a
df -h ~
```

Dans cPanel, ouvrez **Utilisation des ressources** et notez les plafonds affichés pour la mémoire physique, les processus et les *entry processes*.

**Connexions sortantes** (GreenBot, météo, GitHub) :

```bash
python3 - <<'PY'
import socket
for host, port in [("generativelanguage.googleapis.com", 443),
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
| MariaDB | **10.4 ou plus** (ou MySQL 8.0.16 ou plus) ; la version du serveur est confirmée à l'étape 8 |
| Mémoire physique | **1 Go ou plus** (chaque processus de l'API occupe environ 180 à 250 Mo une fois le modèle chargé) |
| Connexions sortantes | `OK` pour les services que vous activerez |

La base étant sur la même machine, aucun port sortant n'est nécessaire pour elle.

---

## 4. Créer le sous-domaine

1. cPanel › catégorie **Domaines** › outil **Sous-domaines** (ou **Domaines**, selon la version de cPanel).
2. Remplissez :

   | Champ | Valeur |
   |---|---|
   | **Sous-domaine** | `api-green` |
   | **Domaine** | `gitingeniering.com` (s'il n'apparaît pas, ajoutez-le d'abord avec l'outil **Domaines**) |
   | **Racine des documents** | laissez la valeur proposée : `/home/sc1jsgw2086/api-green.gitingeniering.com` |

3. Validez (bouton **Créer**).

> La racine des documents ne contiendra que le `.htaccess` et des **liens** vers les pages du dépôt (étape 20). Le code de l'application est ailleurs (`~/green`), comme le recommande o2switch : rien de privé n'est sous la racine web.

### 4.1 DNS

- **Domaine géré par o2switch** (serveurs `ns1.o2switch.net` et `ns2.o2switch.net`) : l'enregistrement est créé automatiquement.
- **Domaine géré ailleurs** : chez votre registraire, créez :

  | Type | Nom | Valeur | TTL |
  |---|---|---|---|
  | `A` | `api-green` | `109.234.161.148` | 3600 |

Vérifiez depuis votre poste (de quelques minutes à quelques heures) :

```bash
dig +short api-green.gitingeniering.com     # doit afficher 109.234.161.148
```

---

## 5. Installer le certificat HTTPS (Let's Encrypt)

L'outil **SSL/TLS** de cPanel ne délivre pas de certificat gratuit valide : utilisez l'outil **Let's Encrypt**.

1. cPanel › outil **Let's Encrypt**.
2. Cliquez sur le lien **Générer** en face de `api-green.gitingeniering.com`.
3. Laissez la méthode de validation **`http-01`** (par défaut, et recommandée). Ne cochez pas le wildcard.
4. Cliquez d'abord sur **Générer la simulation**. Si elle réussit, cliquez sur **Générer**.
5. Le renouvellement est automatique : pour recevoir les alertes, renseignez votre e-mail dans cPanel › **Coordonnées**.

Vérifiez :

```bash
curl -sI https://api-green.gitingeniering.com | head -1      # une réponse HTTP (même 403, 404 ou 503) sans erreur de certificat
```

> En cas d'erreur de limite Let's Encrypt (*rate limit*), attendez quelques jours avant de réessayer. Utilisez toujours la simulation d'abord.

---

## 6. Récupérer le code (Git Version Control)

### 6.1 Par cPanel

1. cPanel › outil **Git™ Version Control** › bouton **Créer**.
2. Activez **Clone a repository**, puis remplissez :

   | Champ | Valeur |
   |---|---|
   | **Clone URL** | `https://github.com/Umar-Elhaj/Greennew.git` |
   | **Repository Path** | `/home/sc1jsgw2086/green` |
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

### 6.2 Choisir la branche (sur le serveur)

```bash
cd ~/green
git fetch origin
git checkout main
git log --oneline -1                       # notez le commit déployé
ls -lh Models/best_efficientnet.onnx       # doit exister (environ 16 Mo)
ls backend/sql/mysql_schema.sql            # schéma de la base (étape 9)
```

> **Sans Git :** depuis votre poste, `rsync -av --exclude .git --exclude .venv --exclude node_modules --exclude 'Models/*.pth' --exclude 'Models/*tflite*' ./ green-o2switch:green/`

---

# Partie 1 — Base de données MySQL (MariaDB)

o2switch fournit MariaDB, compatible MySQL. GREEN s'y connecte avec le pilote **PyMySQL** (100 % Python : rien à compiler sur le serveur). La base est sur la même machine que l'application : elle n'est pas exposée sur Internet.

## 7. Créer la base et son utilisateur

cPanel préfixe automatiquement les noms par `sc1jsgw2086_`.

1. cPanel › catégorie **Bases de données** › outil **Assistant Base de données MySQL®**.
2. **Étape 1 : créer une base de données.** Nom : `green` (cPanel affiche `sc1jsgw2086_green`) › **Étape suivante**.
3. **Étape 2 : créer des utilisateurs de base de données.**
   - Nom d'utilisateur : `greenapp` (devient `sc1jsgw2086_greenapp`).
   - Mot de passe : cliquez sur **Générateur de mots de passe**, choisissez une longueur de 24 caractères ou plus, **sans** symboles si l'option existe (les caractères `@ : / ? # % &` devraient sinon être encodés dans l'URL de l'étape 10), puis copiez-le dans votre gestionnaire de mots de passe.
   - **Créer un utilisateur**.
4. **Étape 3 : ajouter l'utilisateur à la base de données.** Cochez **TOUS LES PRIVILÈGES** › **Effectuer les modifications**.
   Les migrations futures ont besoin de `CREATE`, `ALTER`, `INDEX`, `REFERENCES` et `DROP` (sur des index) : ne restreignez pas les privilèges.
5. Laissez l'outil **MySQL® distant** vide : seule l'application, sur la même machine, se connecte à la base.

## 8. Tester la connexion et relever le socket

### 8.1 Fichier d'identifiants pour les outils `mysql`

Sur le serveur, ce fichier évite de taper le mot de passe (et de le laisser dans l'historique) à chaque commande `mysql`/`mysqldump`, y compris dans les sauvegardes planifiées (étape 24) :

```bash
read -rsp 'Mot de passe MySQL de sc1jsgw2086_greenapp : ' P; echo
( umask 077; printf '[client]\nuser=sc1jsgw2086_greenapp\npassword="%s"\n' "$P" > ~/.my.cnf )
unset P
ls -l ~/.my.cnf        # doit afficher -rw------- (lisible par vous seul)
```

### 8.2 Tester

```bash
mysql sc1jsgw2086_green -e "select version(), @@socket, @@port, @@character_set_server, @@collation_server;"
```

Résultat attendu (les valeurs exactes peuvent varier) :

| Colonne | Attendu | À noter pour |
|---|---|---|
| `version()` | `10.4` ou plus, suivi de `-MariaDB` | étape 3 |
| `@@socket` | par exemple `/var/lib/mysql/mysql.sock` | **étape 10** |
| `@@port` | `3306` | étape 10 (variante) |
| `@@character_set_server` | indifférent : les tables de GREEN imposent `utf8mb4` | |

`ERROR 1045 (28000): Access denied` : mot de passe mal recopié, ou utilisateur non ajouté à la base (étape 7.4).

## 9. Créer les tables (CP2)

> **Point de contrôle humain.** Cette étape crée le schéma de production dans une base **vide**. Lisez le fichier avant de l'importer : il ne contient que des `CREATE TABLE IF NOT EXISTS` et l'enregistrement de la révision du schéma, aucun `DROP` ni `DELETE`.

```bash
less ~/green/backend/sql/mysql_schema.sql                                 # relecture
mysql sc1jsgw2086_green < ~/green/backend/sql/mysql_schema.sql            # création
mysql sc1jsgw2086_green -e "show tables; select version_num from alembic_version;"
```

Résultat attendu : 7 tables (`alembic_version`, `chat_messages`, `chat_sessions`, `disease_analyses`, `missions`, `parcels`, `users`) et la révision `0004_green_data`.

Ce fichier reproduit exactement ce que créent les migrations Alembic (`alembic upgrade head`) ; un test automatique vérifie qu'ils restent identiques. La table `alembic_version` étant renseignée, les **mises à jour futures** du schéma passeront par Alembic (étape 25), jamais par un nouvel import.

**Par phpMyAdmin (sans SSH) :** cPanel › **phpMyAdmin** › base `sc1jsgw2086_green` à gauche › onglet **Importer** › **Choisir un fichier** : `backend/sql/mysql_schema.sql` (depuis votre poste) › jeu de caractères `utf-8` › **Importer**.

**Ce que contient le schéma :** utilisateurs et rôles, parcelles (géométrie GeoJSON), missions (grille et parcours), analyses (chemins des images, prédictions, consentements, validation par un agronome), conversations GreenBot. Les images elles-mêmes restent sur le disque (`~/green_media`, étape 11.1), pas dans la base. Particularités MySQL (toutes voulues) : `DOUBLE` pour les coordonnées GPS, `DATETIME(6)` pour les dates (en UTC), `JSON` pour les géométries, `utf8mb4` pour les accents et les emojis, moteur `InnoDB` pour les clés étrangères.

## 10. Composer `DATABASE_URL`

C'est la seule variable dont l'application a besoin pour la base. Forme recommandée, par le **socket** relevé à l'étape 8.2 (même chemin que les sites PHP du serveur, sans passer par le réseau) :

```
mysql://sc1jsgw2086_greenapp:<mot-de-passe>@localhost/sc1jsgw2086_green?unix_socket=/var/lib/mysql/mysql.sock
```

Variante par TCP (si le socket est refusé, voir l'étape 26) :

```
mysql://sc1jsgw2086_greenapp:<mot-de-passe>@localhost:3306/sc1jsgw2086_green
```

- Remplacez `<mot-de-passe>` et, si besoin, le chemin du socket par celui affiché à l'étape 8.2.
- Mot de passe avec des caractères spéciaux : encodez-les (`@` → `%40`, `:` → `%3A`, `/` → `%2F`, `?` → `%3F`, `#` → `%23`, `%` → `%25`, `&` → `%26`). Pour l'encoder sans erreur : `python3 -c "import urllib.parse,getpass; print(urllib.parse.quote(getpass.getpass(), safe=''))"`.
- Inutile d'écrire le pilote ou le jeu de caractères : l'application transforme `mysql://` en `mysql+pymysql://` et ajoute `charset=utf8mb4`. Chaque connexion travaille en UTC et en mode SQL strict.
- Gardez l'URL complète dans votre gestionnaire de mots de passe : elle sert aux étapes 11 et 12.

La base est prête. Elle sera vérifiée depuis Python à l'étape 14.

---

# Partie 2 — Backend (API)

## 11. Créer l'application Python (Setup Python App)

### 11.1 Dossiers des images et des journaux

Sur le serveur :

```bash
mkdir -p ~/green_media && chmod 700 ~/green_media   # images analysées : privées, hors du web
mkdir -p ~/logs                                     # journal Passenger
mkdir -p ~/green/backend/tmp                        # pour le fichier de redémarrage
```

- **Ne placez jamais `green_media` sous `public_html`** ni sous la racine des documents d'un domaine. Les images ne sont servies que par l'API (`GET /api/media/…`), avec authentification ou lien signé.
- Chaque analyse occupe environ 0,2 à 0,6 Mo (image réduite à 2 048 px, plus une miniature).

### 11.2 Générer la clé secrète

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copiez le résultat dans votre gestionnaire de mots de passe : c'est `SECRET_KEY`.
- Ne la changez plus ensuite : un changement déconnecte tous les utilisateurs et invalide les liens d'images signés. Si vous reprenez les données de Supabase (étape 15), **reprenez aussi l'ancienne `SECRET_KEY`** : les comptes restent connectés.
- Elle doit être identique dans *Setup Python App* et dans `~/.green/env` (étape 12).

### 11.3 Créer l'application

1. cPanel › catégorie **Logiciels** › **Setup Python App** › bouton **Create Application**.
2. Remplissez :

   | Champ | Valeur |
   |---|---|
   | **Python Version** | `3.12` (sinon 3.11 ou 3.13) |
   | **Application Root** | `green/backend` |
   | **Application URL** | choisissez `api-green.gitingeniering.com` dans la liste, chemin vide |
   | **Application startup file** | `passenger_wsgi.py` |
   | **Application Entry Point** | `application` |
   | **Passenger log file** | `/home/sc1jsgw2086/logs/green-api.log` |

3. Section **Environment variables** : cliquez sur **Add Variable** pour chacune des variables ci-dessous (nom exact, valeur sans guillemets), en validant chaque ligne.

   | Name | Value | Obligatoire |
   |---|---|---|
   | `DATABASE_URL` | URL de l'étape 10 | **oui** : sans elle, l'API refuse de démarrer |
   | `SECRET_KEY` | clé de l'étape 11.2 | **oui** : sans elle, l'API refuse de démarrer |
   | `DEBUG` | `false` | oui (valeur de sécurité) |
   | `MEDIA_DIR` | `/home/sc1jsgw2086/green_media` | **oui en pratique** |
   | `INFERENCE_BACKEND` | `onnx` | recommandé |
   | `MODEL_VERSION` | `efficientnet-v1` | recommandé |
   | `MAX_UPLOAD_MB` | `8` | facultatif |
   | `CORS_ORIGINS` | *(ne pas créer)* : les pages et l'API sont sur le même domaine | non |
   | `WARMUP` | *(ne pas créer)* : le modèle se charge à la première analyse | non |
   | `MODEL_PATH` | *(ne pas créer)* : `Models/best_efficientnet.onnx` par défaut | non |
   | `GEMINI_API_KEY`, `GEMINI_MODEL`, `WEATHER_API_KEY` | voir l'étape 19 | non |

4. Cliquez sur **Create**. cPanel crée l'environnement virtuel et écrit un `.htaccess` dans `/home/sc1jsgw2086/api-green.gitingeniering.com/`.
5. En haut de la page de l'application, **copiez la commande « source … »**, qui active l'environnement. Elle ressemble à :
   `source /home/sc1jsgw2086/virtualenv/green/backend/3.12/bin/activate && cd /home/sc1jsgw2086/green/backend`

> **Ne modifiez jamais l'*Application Root* après la création** : o2switch le déconseille. Pour le changer, supprimez l'application (**Destroy**, qui ne touche pas au code) et recréez-la.
>
> **Pour modifier une variable plus tard :** page de l'application › *Environment variables* › modifier la valeur › **Save**, puis **Restart**.

L'application ne démarrera correctement qu'après l'étape 13 (dépendances).

---

## 12. Préparer l'environnement des scripts (SSH et tâches cron)

Les variables de *Setup Python App* sont transmises **uniquement à l'application**. Un terminal SSH ou une tâche cron ne les voit pas. Les scripts d'administration (`alembic`, `db_check.py`, `set_role.py`, `media_report.py`, `copy_database.py`) refusent de démarrer sans `DATABASE_URL`, pour ne pas travailler par erreur sur une base SQLite locale.

### 12.1 Fichier d'environnement privé

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

### 12.2 Lanceur de commandes

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

Si vous avez choisi une autre version de Python à l'étape 11, remplacez `3.12` dans le chemin.

Désormais, toute commande d'administration s'écrit :

```bash
~/.green/run.sh python scripts/db_check.py
```

> Pour changer le mot de passe MySQL ou une clé, mettez à jour **tous les endroits** : *Setup Python App* (puis **Restart**), `~/.green/env` (refaire l'étape 12.1) et, pour le mot de passe MySQL, `~/.my.cnf` (étape 8.1). Le mot de passe lui-même se change dans cPanel › **Bases de données MySQL®** › section *Utilisateurs actuels* › **Changer le mot de passe**.

---

## 13. Installer les dépendances

Sur le serveur, en SSH (pas dans le *Terminal* web) :

```bash
source /home/sc1jsgw2086/virtualenv/green/backend/3.12/bin/activate
cd ~/green
pip install --upgrade pip
pip install -r backend/requirements-prod.txt
```

`requirements-prod.txt` ne contient **ni PyTorch ni pilote PostgreSQL** : l'inférence passe par ONNX Runtime et la base par PyMySQL, pour un environnement d'environ 450 Mo. Toutes les dépendances ont des roues précompilées : aucun compilateur n'est nécessaire.

Vérifications :

```bash
python -c "import onnxruntime, fastapi, a2wsgi, pymysql, PIL, sklearn; print('ok', onnxruntime.__version__)"
# Chargement réel du modèle ONNX (environnement de production chargé)
~/.green/run.sh bash -c 'cd backend && python -c "import inference; inference.load(); print(\"modèle chargé :\", inference.is_loaded())"'
```

Résultat attendu : `ok 1.31.0` puis `modèle chargé : True`.

> **Méthode alternative dans cPanel :** dans *Setup Python App*, champ *Configuration files*, ajoutez `requirements-prod.txt` (**Add**), puis cliquez sur **Run pip install**. Sur une installation lourde, la méthode SSH est plus fiable.
>
> **Si `pip` réclame `gcc`** (« compiler access blocked ») : la version de Python choisie n'a pas de roue pour un paquet. Choisissez 3.12 ou 3.11 plutôt que de demander l'ouverture du compilateur.

---

## 14. Vérifier la base depuis Python

```bash
~/.green/run.sh python scripts/db_check.py
```

Le script affiche le type de base, sa version, la révision Alembic actuelle et la révision attendue, ainsi que le nombre de lignes par table. L'URL n'est jamais affichée. Résultat attendu :

```
backend : mysql — pool QueuePool
version : 10.x.x-MariaDB…
alembic : current=0004_green_data head=0004_green_data
rows    :
  chat_messages        0
  …
```

| Code de sortie | Signification |
|---|---|
| 0 | base joignable et à jour |
| 1 | schéma en retard : `~/.green/run.sh bash -c 'cd backend && alembic upgrade head'` |
| 2 | base injoignable : voir l'étape 26 (lignes « MySQL ») |

> Si vous avez sauté l'import de l'étape 9, `alembic upgrade head` crée exactement les mêmes tables dans une base vide. Pour lire le SQL d'abord : `~/.green/run.sh bash -c 'cd backend && alembic upgrade head --sql' | less`.

---

## 15. Reprendre les données de l'ancienne base Supabase (facultatif, CP2)

À faire **uniquement** si des comptes, parcelles ou analyses existent déjà dans l'ancienne base Supabase et doivent être conservés, et **avant** d'ouvrir l'application aux utilisateurs (étape 20). Sinon, passez à l'étape 16.

Le script `scripts/copy_database.py` :
- lit l'ancienne base (requêtes `SELECT` uniquement : Supabase n'est jamais modifiée) ;
- remplit la base MySQL, qui doit être **à jour et vide** (sinon il refuse) ;
- conserve les identifiants (les liens entre tables et les chemins d'images restent valables) ;
- donne leur valeur par défaut aux colonnes que l'ancienne base n'avait pas encore (rôle `farmer`, consentements à `false`…) ;
- fait tout dans **une seule transaction** : en cas d'erreur, la base MySQL reste vide.

### 15.1 Préparer (sur le serveur)

1. Supabase › votre projet › bouton **Connect** › **Session pooler** : copiez l'URI (`postgresql://postgres.<ref>:[YOUR-PASSWORD]@aws-0-eu-west-3.pooler.supabase.com:5432/postgres`) et remplacez `[YOUR-PASSWORD]`.
2. Vérifiez que le serveur peut joindre Supabase :
   ```bash
   python3 -c "import socket; socket.create_connection(('aws-0-eu-west-3.pooler.supabase.com', 5432), 5); print('OK')"
   ```
   (Gardez l'hôte exactement tel que Supabase l'affiche : il peut commencer par `aws-1-`.)
3. Installez le pilote PostgreSQL, pour cette copie seulement :
   ```bash
   source /home/sc1jsgw2086/virtualenv/green/backend/3.12/bin/activate && pip install psycopg2-binary==2.9.10
   ```

### 15.2 Copier

```bash
read -rsp 'URL Supabase : ' SOURCE_DATABASE_URL; echo; export SOURCE_DATABASE_URL
~/.green/run.sh python scripts/copy_database.py            # essai à blanc : ce qui serait copié
~/.green/run.sh python scripts/copy_database.py --apply    # copie réelle
unset SOURCE_DATABASE_URL
~/.green/run.sh python scripts/db_check.py                 # nombres de lignes identiques à l'ancienne base
```

L'essai à blanc affiche, table par table, le nombre de lignes et les colonnes qui prendront une valeur par défaut. La copie se termine par une ligne `copied : … ok` par table.

### 15.3 Après la copie

- **Images.** Si l'ancien serveur conservait des images, copiez-les en gardant leur arborescence (`AAAA/MM/…jpg`) dans `~/green_media`, par exemple depuis votre poste : `rsync -av <ancien dossier des images>/ green-o2switch:green_media/`. Le rapport `~/.green/run.sh python scripts/media_report.py` signale les images manquantes ou orphelines.
- **Clé secrète.** Si vous avez repris l'ancienne `SECRET_KEY` (étape 11.2), les utilisateurs restent connectés ; sinon, ils devront se reconnecter.
- **Pilote PostgreSQL.** Retirez-le : `pip uninstall -y psycopg2-binary`.
- **Ancienne base.** Gardez le projet Supabase en lecture seule quelques semaines, comme sauvegarde, puis supprimez-le.

> **Si le serveur ne peut pas joindre Supabase**, lancez la copie depuis votre poste, à la racine du dépôt, à travers un tunnel SSH vers le socket MySQL du serveur :
> ```bash
> ssh -N -L 3307:/var/lib/mysql/mysql.sock green-o2switch &            # chemin du socket : étape 8.2
> python3 -m venv .venv-copy && .venv-copy/bin/pip install -r backend/requirements-prod.txt psycopg2-binary==2.9.10
> read -rsp 'URL Supabase : ' SOURCE_DATABASE_URL; echo; export SOURCE_DATABASE_URL
> read -rsp 'DATABASE_URL (…@127.0.0.1:3307/sc1jsgw2086_green) : ' DATABASE_URL; echo; export DATABASE_URL
> .venv-copy/bin/python scripts/copy_database.py && .venv-copy/bin/python scripts/copy_database.py --apply
> unset SOURCE_DATABASE_URL DATABASE_URL; kill %1
> ```
> L'URL MySQL est alors `mysql://sc1jsgw2086_greenapp:<mot-de-passe>@127.0.0.1:3307/sc1jsgw2086_green` (sans `unix_socket`).

---

## 16. Sécuriser le domaine (.htaccess)

1. cPanel › **Gestionnaire de fichiers**.
2. **Paramètres** (en haut à droite) › cochez **Afficher les fichiers cachés (dotfiles)** › **Save**.
3. Ouvrez `/home/sc1jsgw2086/api-green.gitingeniering.com/`, sélectionnez `.htaccess` › **Modifier**.
4. Collez **en tout début de fichier**, au-dessus du bloc `# DO NOT REMOVE. CLOUDLINUX PASSENGER CONFIGURATION BEGIN` (bloc à laisser intact), le contenu de `deploy/o2switch/htaccess-snippet.conf` :

```apache
# ---- GREEN : site complet (pages + API) ----
# 1. Pas de liste des dossiers (js/, vendor/…)
Options -Indexes

# 2. HTTPS obligatoire (le certificat de l'étape 5 doit être actif)
RewriteEngine On
RewriteCond %{HTTPS} !=on
RewriteRule ^ https://%{HTTP_HOST}%{REQUEST_URI} [L,R=301]

<IfModule mod_headers.c>
  # 3. HSTS : HTTPS seulement pendant un an
  Header always set Strict-Transport-Security "max-age=31536000; includeSubDomains" env=HTTPS
  # 4. Mêmes en-têtes de sécurité que l'API, pour les fichiers servis par Apache
  Header always set X-Content-Type-Options "nosniff"
  Header always set Referrer-Policy "strict-origin-when-cross-origin"
  Header always set X-Frame-Options "DENY"
  Header always set Permissions-Policy "camera=(self), geolocation=(self), microphone=()"
  # 5. L'API n'est pas indexée, et son propre Cache-Control (images privées) n'est jamais remplacé
  <If "%{REQUEST_URI} =~ m#^/api/#">
    Header always set X-Robots-Tag "noindex, nofollow"
  </If>
  # 6. Images et polices : une semaine en cache
  <If "%{REQUEST_URI} !~ m#^/api/# && %{REQUEST_URI} =~ m#\.(png|jpe?g|webp|svg|ico|woff2?)$#">
    Header set Cache-Control "public, max-age=604800"
  </If>
  # 7. Pages, scripts, styles : revalidés à chaque visite (réponse 304 légère) ;
  #    une mise à jour est donc visible tout de suite
  <If "%{REQUEST_URI} !~ m#^/api/# && %{REQUEST_URI} !~ m#\.(png|jpe?g|webp|svg|ico|woff2?)$#">
    Header set Cache-Control "no-cache"
  </If>
</IfModule>

# 8. Compression
<IfModule mod_deflate.c>
  AddOutputFilterByType DEFLATE text/html text/css text/csv application/javascript text/javascript application/json application/geo+json image/svg+xml
</IfModule>

# 9. Jamais de fichiers privés, même en cas d'erreur de placement
<FilesMatch "^\.env|\.(py|db|sqlite3|ini|sql|sh|pth|onnx|tflite)$">
  Require all denied
</FilesMatch>
# ---- fin GREEN ----
```

5. Cliquez sur **Enregistrer les modifications**.

Les règles 6 et 7 concernent les pages publiées à l'étape 20 ; elles sont sans effet avant.

---

## 17. Démarrer et vérifier l'API

### 17.1 (Re)démarrer

Deux façons équivalentes :
- cPanel › **Setup Python App** › votre application › bouton **Restart** ;
- sur le serveur : `touch ~/green/backend/tmp/restart.txt`.

### 17.2 Vérifier

Depuis votre poste :

```bash
curl -s https://api-green.gitingeniering.com/api/health; echo
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
curl -sI https://api-green.gitingeniering.com/api/health | grep -i -E 'strict-transport|x-content-type|x-robots'
curl -s -o /dev/null -w '%{http_code}\n' http://api-green.gitingeniering.com/api/health    # 301 (vers HTTPS)
curl -s -o /dev/null -w '%{http_code}\n' https://api-green.gitingeniering.com/docs         # 404 (documentation désactivée en production)
curl -s -o /dev/null -w '%{http_code}\n' https://api-green.gitingeniering.com/api/parcels  # 401 (authentification requise : la base répond)
```

### 17.3 Journaux

```bash
tail -n 50 ~/logs/green-api.log
```

| Message dans le journal | Action |
|---|---|
| `SECRET_KEY is not set` | Ajouter la variable (étape 11.3), **Save**, **Restart** |
| `DATABASE_URL is not set` | Idem |
| `Database schema at revision …` | Étape 14 (`alembic upgrade head`) |
| `(1045, "Access denied…")`, `(2002…)`, `(2003…)` | Étape 26, lignes « MySQL » |

Pour un diagnostic ponctuel, o2switch permet d'afficher les erreurs détaillées dans le navigateur. Ajoutez temporairement en tête du `.htaccess` :

```apache
PassengerAppEnv development
PassengerFriendlyErrorPages on
```

**Retirez ces deux lignes dès le problème résolu** : elles exposent des détails internes.

---

## 18. Régler Tiger Protect (pare-feu applicatif)

Tiger Protect filtre les requêtes avant qu'elles n'atteignent l'application. Son mode par défaut convient, avec ces précautions :

1. cPanel › outil **Tiger Protect**.
2. **Laissez la règle par défaut active.**
3. **N'activez jamais le mode « Je suis attaqué »** sur `api-green.gitingeniering.com` : ses challenges ne peuvent pas être résolus par les appels `fetch` de l'application (JSON) ; toute l'API répondrait 403.
4. **N'activez pas les règles « Bloquer POST »** (connexion, analyses, parcelles sont des `POST`) et ne bloquez pas les requêtes sans *User-Agent* (le rover et les scripts de test en envoient peu).
5. Pas de blocage par pays : les utilisateurs sont au Cameroun.

**Symptôme d'un blocage :** l'étape 23 donne des `403` avec une page HTML de Tiger Protect au lieu d'un JSON. Désactivez la règle en cause, ou ouvrez un ticket avec l'URL bloquée, l'heure et votre IP.

---

## 19. Activer GreenBot et la météo

### 19.1 GreenBot (Google Gemini)

1. [Google AI Studio](https://aistudio.google.com) › **Get API key** › **Create API key**.
2. cPanel › *Setup Python App* › votre application › **Add Variable** :
   - `GEMINI_API_KEY` = la clé ;
   - `GEMINI_MODEL` : facultatif, `gemini-3.1-flash-lite` par défaut.
3. **Save**, puis **Restart**.

### 19.2 Météo (OpenWeatherMap)

1. Créez un compte sur [openweathermap.org](https://openweathermap.org) › menu du compte › **My API keys** › créez une clé. Son activation peut prendre jusqu'à quelques heures.
2. *Setup Python App* › **Add Variable** : `WEATHER_API_KEY` = la clé.
3. **Save**, puis **Restart**.

Vérifiez :

```bash
curl -s https://api-green.gitingeniering.com/api/health | python3 -m json.tool | grep -A3 services
# "greenbot": true, "weather": true
```

---

# Partie 3 — Frontend

L'API sait déjà servir les pages (`/`, `/dashboard`, `/map`…, et les fichiers de `frontend/`). On fait mieux : les fichiers du frontend sont **liés dans la racine du domaine**, et Apache les sert lui-même, avec les règles de cache de l'étape 16. Seuls `/api/*` et les adresses de pages sans `.html` passent par Python : chaque visite consomme beaucoup moins de processus Passenger, la ressource la plus limitée d'un hébergement mutualisé.

## 20. Publier les pages dans le domaine

Sur le serveur :

```bash
~/green/deploy/o2switch/publish_frontend.sh /home/sc1jsgw2086/api-green.gitingeniering.com
ls -l /home/sc1jsgw2086/api-green.gitingeniering.com
```

Le script crée un **lien symbolique** par élément de `frontend/` (pages `.html`, `css/`, `js/`, `vendor/`, `assets/`). Il ne touche ni au `.htaccess`, ni à `.well-known` (Let's Encrypt), ni à un fichier réel déjà présent. Comme ce sont des liens, un `git pull` met le site à jour immédiatement ; relancez simplement le script après une mise à jour (étape 25), au cas où une page aurait été ajoutée ou supprimée.

Vérifiez depuis votre poste :

```bash
for p in / /register /dashboard /map /js/api.js /css/main.css /vendor/leaflet-1.9.4/leaflet.js; do
  printf '%-36s %s\n' "$p" "$(curl -s -o /dev/null -w '%{http_code} %{content_type}' https://api-green.gitingeniering.com$p)"
done
curl -sI https://api-green.gitingeniering.com/js/api.js | grep -i -E 'cache-control|x-frame'
```

Attendu : `200` partout, `text/html` pour les pages, `application/javascript` (ou `text/javascript`) pour les scripts, et `Cache-Control: no-cache` sur `api.js`.

Ouvrez ensuite `https://api-green.gitingeniering.com` dans un navigateur : la page de connexion s'affiche, avec le bouton FR | EN.

> **Si Apache ne servait pas les fichiers liés** (règle du serveur sur les liens symboliques), rien ne casse : l'API sert exactement les mêmes fichiers. Vous pouvez alors retirer les liens (`find /home/sc1jsgw2086/api-green.gitingeniering.com -maxdepth 1 -type l -delete`) et laisser l'API tout servir.

## 21. Retirer l'ancien frontend Vercel

Le frontend n'est plus sur Vercel. Pour que personne ne continue sur l'ancienne adresse `greennew-app.vercel.app` :

1. Vercel › projet du frontend › **Settings › General** › tout en bas, **Delete Project** ; ou, pour garder l'adresse comme redirection, remplacez le contenu de `vercel.json` **dans le projet Vercel** (pas dans le dépôt) par :
   ```json
   { "redirects": [ { "source": "/(.*)", "destination": "https://api-green.gitingeniering.com/$1", "permanent": true } ] }
   ```
2. Prévenez les utilisateurs existants de la nouvelle adresse.

Le fichier `frontend/vercel.json` et le script `scripts/configure_vercel.py` restent dans le dépôt pour un éventuel retour à Vercel ; ils ne servent pas sur o2switch.

---

# Partie 4 — Mise en service et exploitation

## 22. Créer les comptes à rôle

Il n'y a pas d'écran d'administration. Les rôles se donnent sur le serveur, **après l'inscription normale** de la personne dans l'application (`https://api-green.gitingeniering.com/register`).

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

## 23. Tester de bout en bout

### 23.1 Test de fumée automatique

1. Dans l'application (`https://api-green.gitingeniering.com/register`), créez un **compte de test dédié**.
2. Donnez-lui le rôle `partner` (étape 22) pour inclure GREEN Data.
3. Depuis votre poste, à la racine du dépôt :

```bash
read -rs SMOKE_PASSWORD; export SMOKE_PASSWORD
SMOKE_IDENTIFIER=+2376XXXXXXXX scripts/smoke_prod.sh https://api-green.gitingeniering.com
```

Toutes les lignes doivent être `PASS` (code de sortie 0) :
- santé de l'API ;
- pages et fichiers du frontend (`/`, `/dashboard`, `/map`, scripts, styles, Leaflet), et fichiers privés **non** servis (`/.env`, `/passenger_wsgi.py`) ;
- connexion (donc lecture dans MySQL) ;
- liste des parcelles ;
- analyse d'une image (inférence ONNX réelle, écriture dans MySQL et sur le disque) ;
- lecture de l'image avec jeton, avec lien signé, et `401` sans les deux ;
- GREEN Data.

### 23.2 Recette fonctionnelle (navigateur, sur téléphone si possible)

| # | Fonction | Action | Résultat attendu |
|---|---|---|---|
| 1 | Inscription | `/register`, numéro `6XXXXXXXX`, région, consentement | Arrivée sur le tableau de bord |
| 2 | Connexion | Se déconnecter (*Paramètres*), se reconnecter avec `+237 6…` | Accepté, avec ou sans `+237` |
| 3 | Langue | Bouton FR/EN de l'en-tête | Tout le texte change sans rechargement |
| 4 | Accents et emojis | Nom de parcelle « Bafoussam – Maïs 🌽 », puis recharger | Affiché à l'identique (base en `utf8mb4`) |
| 5 | Analyse | `/camera` › onglet *Photos* › importer une photo de feuille | Fiche « maladie probable » avec la mention « pas un diagnostic » |
| 6 | Hors ligne | Couper le réseau, importer 2 photos, rétablir | File « 2 en attente » puis envoi automatique |
| 7 | Historique | `/history` › une ligne | Fiche avec image (servie par `/api/media`) |
| 8 | Parcelles | `/map` › nouvelle parcelle › 4 points › enregistrer | Surface, périmètre et région calculés |
| 9 | Mission | Parcelle › grille 10 m › aperçu › créer | Mission, exports JSON et GeoJSON téléchargeables |
| 10 | Carte de chaleur | Analyses avec mission et cellule, puis ouvrir la mission | Cellules colorées, légende |
| 11 | GreenBot | Depuis une fiche › « Demander à GreenBot » | Réponse dans la langue de l'interface, messages dans l'ordre |
| 12 | Météo | Tableau de bord | Météo de la région, conseil agronomique |
| 13 | Bibliothèque | `/diseases` › recherche | Fiches FR/EN |
| 14 | GREEN Data | Compte `partner` › `/green-data` › export CSV | Statistiques (cases masquées sous 5), CSV téléchargé |
| 15 | Rôles | Compte `farmer` › `/green-data` | Accès refusé |
| 16 | Thème | Basculer clair/sombre | Lisible dans les deux thèmes |

Pour suivre la recette, ouvrez `tail -f ~/logs/green-api.log` sur le serveur.

---

## 24. Exploitation : tâches planifiées, sauvegardes, surveillance

### 24.1 Tâches cron (cPanel › **Tâches Cron**)

1. Section **E-mail de la tâche cron** : saisissez l'adresse qui recevra les sorties › **Mettre à jour l'e-mail**. Une tâche n'envoie un e-mail que si elle produit une sortie.
2. Créez le dossier des sauvegardes de la base, sur le serveur : `mkdir -p ~/backups && chmod 700 ~/backups`.
3. Section **Ajouter une nouvelle tâche cron** : choisissez la fréquence dans **Paramètres communs**, collez la commande, puis cliquez sur **Ajouter une nouvelle tâche cron**.

| Fréquence | Commande | Rôle |
|---|---|---|
| Toutes les 15 min (`*/15 * * * *`) | `curl -fsS -o /dev/null https://api-green.gitingeniering.com/api/health \|\| echo "GREEN indisponible"` | Alerte si l'application ne répond plus |
| Une fois par jour (`0 6 * * *`) | `$HOME/.green/run.sh python scripts/db_check.py >/dev/null 2>&1 \|\| echo "GREEN : base injoignable ou schéma en retard"` | Alerte base |
| Une fois par jour (`30 2 * * *`) | `mysqldump --single-transaction --no-tablespaces sc1jsgw2086_green \| gzip > $HOME/backups/green-$(date +\%F).sql.gz && find $HOME/backups -name 'green-*.sql.gz' -mtime +14 -delete` | Sauvegarde de la base, 14 jours gardés |
| Une fois par semaine (`0 7 * * 1`) | `$HOME/.green/run.sh python scripts/media_report.py` | Rapport disque et images orphelines (sans rien supprimer) |

> Dans une tâche cron, le caractère `%` doit être écrit `\%` (d'où `date +\%F`). `mysqldump` lit ses identifiants dans `~/.my.cnf` (étape 8.1) : aucun mot de passe dans la commande.
>
> `media_report.py --apply` supprime les fichiers d'images orphelins. Lancez-le **à la main** après avoir lu le rapport, jamais en cron. Il refuse de s'exécuter si la base ne contient aucune image.

### 24.2 Sauvegardes

| Donnée | Où | Comment |
|---|---|---|
| Base de données | o2switch | Sauvegardes automatiques o2switch (cPanel › **JetBackup** › *Bases de données*), plus le `mysqldump` quotidien de l'étape 24.1 dans `~/backups` |
| Copie hors site de la base | Votre poste | `rsync -az green-o2switch:backups/ ./sauvegarde-green-db/` (hebdomadaire) |
| Images (`~/green_media`) | o2switch | Sauvegardes automatiques o2switch, consultables et restaurables dans **JetBackup** |
| Copie hors site des images | Votre poste ou un stockage externe | `rsync -az green-o2switch:green_media/ ./sauvegarde-green-media/` (hebdomadaire) |
| Code | GitHub | Le dépôt fait foi ; notez le commit déployé |
| Secrets | Gestionnaire de mots de passe | `SECRET_KEY`, mot de passe MySQL, clés Gemini et météo |

**Restaurer la base** depuis une sauvegarde (efface le contenu actuel des tables : à faire application arrêtée, après accord) :

```bash
gunzip -c ~/backups/green-AAAA-MM-JJ.sql.gz | mysql sc1jsgw2086_green
~/.green/run.sh python scripts/db_check.py
```

### 24.3 Surveillance

- **Externe (recommandé) :** un service gratuit de surveillance HTTP, comme UptimeRobot, sur `https://api-green.gitingeniering.com/api/health`, toutes les 5 minutes, avec alerte e-mail ou SMS.
- **Ressources :** cPanel › **Utilisation des ressources**. Atteindre ponctuellement un plafond est normal ; plus de 50 % en continu signale un problème. Des erreurs `503` indiquent trop de processus.
- **Base :** cPanel › **Bases de données MySQL®** affiche la taille de la base ; phpMyAdmin permet de la consulter en lecture.
- **Disque :** cPanel › *Utilisation du disque*, ou le rapport hebdomadaire.
- **Journaux Apache :** cPanel › **Erreurs** et **Accès brut**.

---

## 25. Mettre à jour et revenir en arrière

### 25.1 Mise à jour

1. Notez le commit actuel : `cd ~/green && git log --oneline -1`.
2. Sauvegardez la base : `mysqldump --single-transaction --no-tablespaces sc1jsgw2086_green | gzip > ~/backups/green-avant-maj-$(date +%F-%H%M).sql.gz`.
3. Récupérez le code : cPanel › *Git™ Version Control* › **Gérer** › onglet **Pull or Deploy** › **Update from Remote**. Équivalent en SSH :
   ```bash
   cd ~/green && git pull
   ```
4. Mettez à jour les dépendances :
   ```bash
   source /home/sc1jsgw2086/virtualenv/green/backend/3.12/bin/activate && pip install -r ~/green/backend/requirements-prod.txt
   ```
5. **Base (CP2)** : vérifiez, relisez puis appliquez une éventuelle nouvelle migration :
   ```bash
   ~/.green/run.sh python scripts/db_check.py                                  # code 1 = migration à appliquer
   ~/.green/run.sh bash -c 'cd backend && alembic upgrade head --sql' | less    # relecture du SQL
   ~/.green/run.sh bash -c 'cd backend && alembic upgrade head'
   ```
   Ne réimportez **jamais** `mysql_schema.sql` sur une base en service : il sert à créer une base vide.
6. Republiez les pages (prend en compte une page ajoutée ou supprimée) :
   ```bash
   ~/green/deploy/o2switch/publish_frontend.sh /home/sc1jsgw2086/api-green.gitingeniering.com
   ```
7. Redémarrez et vérifiez :
   ```bash
   touch ~/green/backend/tmp/restart.txt
   curl -s https://api-green.gitingeniering.com/api/health
   ```
8. Relancez le test de fumée (étape 23.1).

### 25.2 Retour arrière

```bash
cd ~/green && git checkout <commit-précédent>
source /home/sc1jsgw2086/virtualenv/green/backend/3.12/bin/activate && pip install -r backend/requirements-prod.txt
~/green/deploy/o2switch/publish_frontend.sh /home/sc1jsgw2086/api-green.gitingeniering.com
touch backend/tmp/restart.txt
```

- Les migrations étant additives, l'ancien code fonctionne avec le nouveau schéma. **Pas de `alembic downgrade`** en production : les retours en arrière suppriment des colonnes.
- En dernier recours seulement, restaurez la sauvegarde de l'étape 25.1 (procédure de l'étape 24.2).
- Les images de `~/green_media` ne sont jamais touchées par un déploiement.

---

## 26. Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| `503` ou page Passenger « Web application could not be started » | Erreur au démarrage | `tail ~/logs/green-api.log` ; étape 17.3 |
| `ModuleNotFoundError` dans le journal (par exemple `pymysql`) | Dépendances non installées dans **le** virtualenv de l'application | Étape 13 avec la commande `source` exacte de *Setup Python App* |
| `No matching distribution found for onnxruntime==…` | Pas de roue pour cette version de Python | Recréer l'application en Python 3.12 ou 3.11 |
| Erreur citant `gcc`, `make` ou `ld` | Un paquet tente une compilation ; le compilateur est bloqué par défaut | Même solution ; sinon, demander au support l'accès au compilateur |
| `pip` : `out of memory` ou `fork failed` | Terminal web de cPanel trop limité | Utiliser un vrai client SSH (étape 2) |
| MySQL `(1045, "Access denied for user …")` | Mot de passe faux ou mal encodé dans l'URL ; utilisateur non ajouté à la base | Étape 10 (encodage) ; étape 7.4 (privilèges). Si `mysql` (étape 8) fonctionne mais pas l'application en TCP, passez à la forme `unix_socket` de l'étape 10 |
| MySQL `(2002…)` ou `(2003, "Can't connect…")` | Chemin du socket faux, ou port TCP fermé | Recopier `@@socket` de l'étape 8.2 ; sinon essayer la variante TCP `@localhost:3306` (ou `@127.0.0.1:3306`) |
| MySQL `(1049, "Unknown database …")` | Nom de base sans le préfixe | `sc1jsgw2086_green`, pas `green` |
| MySQL `(1142 … command denied)` pendant `alembic upgrade` | Privilèges incomplets | Étape 7.4 : **TOUS LES PRIVILÈGES** |
| MySQL `(1040/1203, "Too many connections")` | Trop de processus Passenger × connexions | Chaque processus garde au plus 4 connexions ; réduire le nombre de processus ou demander au support la limite `max_user_connections` |
| `Lost connection to MySQL server` après une période calme | Connexion fermée par le serveur | Sans effet visible : l'application recycle ses connexions toutes les 280 s et les teste avant usage |
| Caractères `?` à la place des emojis | Table créée hors des scripts du dépôt | Recréer les tables avec `mysql_schema.sql` ou Alembic (`utf8mb4` imposé) |
| `Database schema at revision …` | Migration non appliquée | Étapes 14 et 25.1 |
| `copy_database.py` : `REFUSED : target not empty` | La base MySQL contient déjà des lignes | La copie ne remplit qu'une base neuve ; vider les tables (après sauvegarde) ou repartir de l'étape 9 sur une base vide |
| `403` avec une page HTML Tiger Protect | Règle du pare-feu applicatif | Étape 18 |
| `413` à l'envoi d'une photo | Image de plus de 8 Mo ou de plus de 50 mégapixels | Normal ; ajuster `MAX_UPLOAD_MB` si besoin (l'application réduit déjà les photos à 1 600 px avant envoi) |
| Page blanche ou ancien affichage après une mise à jour | Fichiers liés absents, ou cache du navigateur | Relancer `publish_frontend.sh` (étape 20) ; recharger avec Ctrl+F5 |
| `403 Forbidden` sur toutes les pages | Liens symboliques refusés par Apache | Étape 20, encadré : retirer les liens, l'API sert les pages |
| Images de l'historique absentes (`401`) | Session expirée, ou `SECRET_KEY` modifiée | Se reconnecter ; ne pas changer `SECRET_KEY` |
| Images absentes (`404`) après une reprise de Supabase | Fichiers d'images non copiés | Étape 15.3 ; `media_report.py` |
| Première analyse lente (quelques secondes) | Chargement paresseux du modèle par processus | Normal ; `WARMUP=1` le précharge, au prix d'environ 180 Mo par processus |
| GreenBot « non configuré » | `GEMINI_API_KEY` absente | Étape 19.1 |
| Météo « non activée » ou `401` du fournisseur | Clé absente ou pas encore active | Étape 19.2 ; attendre l'activation de la clé |
| GREEN Data affiche « masqué » partout | Moins de 5 analyses ou de 5 exploitants consentants par case | Comportement voulu (protection des exploitants) |
| `DATABASE_URL is not set` en lançant un script | Environnement non chargé | Passer par `~/.green/run.sh` (étape 12) |
| `Permission denied (publickey)` en SSH | IP non autorisée, ou clé absente | Étape 2.1 (IP), puis 2.2 (clé) |

---

## Annexe A : récapitulatif des variables d'environnement

Référence commentée : `.env.example` à la racine du dépôt.

| Variable | Où | Valeur | Obligatoire |
|---|---|---|---|
| `DATABASE_URL` | *Setup Python App* et `~/.green/env` | `mysql://sc1jsgw2086_greenapp:<mot-de-passe>@localhost/sc1jsgw2086_green?unix_socket=<socket>` (étape 10) | oui |
| `SECRET_KEY` | *Setup Python App* et `~/.green/env` | 48 octets aléatoires (étape 11.2) | oui |
| `MEDIA_DIR` | *Setup Python App* et `~/.green/env` | `/home/sc1jsgw2086/green_media` | oui en pratique |
| `DEBUG` | *Setup Python App* | `false` | valeur de sécurité |
| `INFERENCE_BACKEND` | *Setup Python App* | `onnx` | non (par défaut) |
| `MODEL_VERSION` | *Setup Python App* | `efficientnet-v1` | non |
| `MODEL_PATH` | *Setup Python App* | vide : `Models/best_efficientnet.onnx` | non |
| `MAX_UPLOAD_MB` | *Setup Python App* | `8` | non |
| `WARMUP` | *Setup Python App* | vide (ou `1` pour précharger le modèle) | non |
| `CORS_ORIGINS` | *Setup Python App* | vide : une seule origine | non |
| `GEMINI_API_KEY` | *Setup Python App* | clé Google AI Studio | non (GreenBot) |
| `GEMINI_MODEL` | *Setup Python App* | vide : `gemini-3.1-flash-lite` | non |
| `WEATHER_API_KEY` | *Setup Python App* | clé OpenWeatherMap | non (météo) |
| `SOURCE_DATABASE_URL` | terminal, le temps de l'étape 15 | URI du *Session pooler* Supabase | non (reprise des données seulement) |

---

## Annexe B : liste de contrôle finale

**Préparation**
- [ ] SSH par clé avec l'alias `green-o2switch` (étape 2)
- [ ] Diagnostic conforme : Python 3.11 à 3.13, glibc ≥ 2.28, AVX (étape 3)
- [ ] `api-green.gitingeniering.com` résout vers o2switch (étape 4) et répond en HTTPS valide (étape 5)
- [ ] Code cloné dans `~/green`, branche et commit notés (étape 6)

**Base de données**
- [ ] Base `sc1jsgw2086_green` et utilisateur `sc1jsgw2086_greenapp` avec tous les privilèges (étape 7)
- [ ] `~/.my.cnf` en `600` ; MariaDB ≥ 10.4 ; socket relevé (étape 8)
- [ ] 7 tables créées, `alembic_version` = `0004_green_data` (étape 9)
- [ ] `DATABASE_URL` composée et rangée dans le gestionnaire de mots de passe (étape 10)

**Backend**
- [ ] `~/green_media` en `700`, hors du web ; application Python créée avec ses variables (étape 11)
- [ ] `~/.green/env` en `600` et `~/.green/run.sh` en place (étape 12)
- [ ] Dépendances installées, `modèle chargé : True` (étape 13)
- [ ] `db_check.py` : `backend : mysql`, `current = head`, code 0 (étape 14)
- [ ] Données Supabase reprises et images copiées, si besoin (étape 15)
- [ ] `.htaccess` complet : HTTPS, HSTS, en-têtes, cache, `noindex` sur `/api/` (étape 16)
- [ ] `/api/health` : `status: ok`, `inference_backend: onnx` (étape 17)
- [ ] Tiger Protect sans mode « Je suis attaqué » (étape 18)
- [ ] GreenBot et météo : `services` à `true` si souhaité (étape 19)

**Frontend**
- [ ] Pages liées dans la racine du domaine ; `/`, `/dashboard`, scripts et styles en `200` (étape 20)
- [ ] Ancien projet Vercel supprimé ou redirigé (étape 21)

**Mise en service**
- [ ] Comptes `admin` et `partner` attribués (étape 22)
- [ ] `smoke_prod.sh` : toutes les lignes `PASS` (étape 23.1)
- [ ] Recette fonctionnelle des 16 points (étape 23.2)
- [ ] Tâches cron (santé, base, sauvegarde `mysqldump`, images), sauvegardes hors site et surveillance externe en place (étape 24)
