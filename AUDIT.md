# AUDIT — GREEN (`main` @ `36d4768`, 21/10/2026)

Méthode : lecture intégrale du backend et de `frontend/js/*` ; audit statique des 15 pages réparti en 3 groupes, avec vérification ponctuelle des défauts les plus graves dans le code ; puis exécution (`uvicorn` en SQLite, pytest, Playwright), dont les preuves d'exécution sont marquées **[exec]**.
États : **OK** · **cassé** (ne marche pas) · **partiel** (marche en partie ou mal) · **mort** (code ou interface sans effet) · **trompeur** (affiche une information fausse ou inventée).
Les numéros de ligne renvoient à `36d4768`.

## 1. Défauts transverses (priorité haute)

| # | Défaut | État | Preuve | Correction prévue (lot) |
|---|---|---|---|---|
| T1 | Images d'analyse lisibles sans authentification | cassé (sécurité) | `main.py:226` `app.mount(MEDIA_URL_PREFIX, StaticFiles(...))` | `GET /api/media/{path}` authentifié (L2) |
| T2 | IDOR GreenBot : `analysis_id` d'un autre utilisateur injecté dans le contexte LLM | cassé (sécurité) | `chatbot_router.py:284` `filter(DiseaseAnalysis.id == analysis_id)` sans `user_id` | Filtrer par propriétaire (L4) |
| T3 | XSS : `innerHTML` alimenté par des données serveur ou utilisateur sans échappement ; aucun helper d'échappement | cassé (sécurité) | `map.html:792,799,834` (nom de parcelle saisi par l'utilisateur) ; `app.js:137` `toast` en innerHTML ; `dashboard.html:784`, `camera.html:943,1016`, `history.html:428,500` | `escapeHtml()` dans `utils.js`, toast en `textContent` (L4) |
| T4 | « Severity » = seuil de *confiance* du modèle, pas une gravité ; une plante **saine** prédite avec assurance s'affiche « high » en rouge | trompeur | `inference.py:233-238,310` ; `dashboard.html:783`, `camera.html:916`, `history.html:423` | Gravité `none` si saine ; afficher « confiance » séparément (L4) |
| T5 | Prédiction présentée comme un diagnostic | trompeur | `camera.html:424,835` « Disease detected » / « Maladie détectée » ; `camera.html:396` « diagnostic approfondi » ; `history.html:294` | « Maladie probable » + mention « prédiction IA, à confirmer » partout (L3/L4) |
| T6 | i18n : `i18n.js` chargé sur 3 pages sur 15 ; 532 chaînes HTML statiques non balisées **[exec]** (`check_i18n.py`), auxquelles s'ajoutent les chaînes JS ; FR et EN mélangés (camera, economics, chatbot, diseases.json) | cassé | `scripts/check_i18n.py --summary` | Lot 3 |
| T7 | Deux clés de langue concurrentes : `green_language` (i18n.js:25) et `green_lang` (utils.js:66) | cassé | — | Une seule clé (L3) |
| T8 | Erreur 422 affichée « [object Object] » (`detail` est un tableau) | cassé | `api.js:87` | Aplatir `detail[].msg` (L4) |
| T9 | `App.boot()` exécuté deux fois (app.js:14 + chaque page), donc 2 à 3 appels `/api/auth/me` | partiel | `profile.html:303`, `settings.html:328` | Boot idempotent (L4) |
| T10 | Mode flux rover impossible en production : le serveur o2switch ne joint pas l'IP privée du rover ; `<img src="http://…">` bloqué dans une page HTTPS ; échecs seulement en `console.warn` | cassé en prod | `rover_common.py:60-104` ; `camera.html:548,568,765,785` | Prémisse P1 → file d'attente IndexedDB + contrat d'upload par le rover (L4) |
| T11 | Aucune analyse n'est géolocalisée ni rattachée à une parcelle (camera n'envoie ni `latitude`, ni `longitude`, ni `parcel_id`), donc la carte n'a aucun point | partiel | `camera.html:765,771,776` | Sélecteur parcelle/mission + géolocalisation (L4/L5) |
| T12 | Upload : type de fichier vérifié par `content_type` déclaré uniquement ; octets bruts stockés, **EXIF (dont GPS) conservé** ; limite de 10 Mo codée en dur | partiel (sécurité/vie privée) | `rover_common.py:116-125,290-296` | Pillow `verify()`, réencodage, EXIF retiré (L2) |
| T13 | Schéma : `create_all` à l'import, aucune migration (une table existante n'est jamais altérée) | partiel | `main.py:37` | Alembic (L1) |
| T14 | Config : `SECRET_KEY` par défaut codé en dur, `DEBUG=true` par défaut, CORS `*` + credentials, `.env` prioritaire sur l'environnement (`override=True`) | cassé (sécurité) | `config.py:11,14,77` ; `main.py:101-107` | **Corrigé en 0.10** |
| T15 | Fichier parasite `backend/=1.40.0` | mort | — | **Supprimé en 0.9** |
| T16 | Correspondances classe → fiche agronomiquement fausses (Corn_Leaf_Blight → brûlure *bactérienne* Xanthomonas ; Corn_Mildew → oïdium de la courgette ; Tomato_Blight_Leaf → alternariose alors que l'entrée `mildiou` existe) ; l'exploitant reçoit le mauvais traitement | trompeur | `rover_common.py:33-45` ; `diseases.json` | Revoir la table et la valider avec un agronome (L4, à confirmer par l'humain) |

## 2. Endpoints backend

| Endpoint | Fonctionnalité | État | Preuve | Correction prévue |
|---|---|---|---|---|
| `POST /api/auth/register` | Inscription | OK | tests `test_auth.py` **[exec]** | — ; email non validé côté serveur (`EmailStr` importé, non utilisé) → L4 |
| `POST /api/auth/login` | Connexion téléphone/email | OK | tests **[exec]** | — |
| `GET/PUT/DELETE /api/auth/me` | Profil | partiel | `auth_router.py:140` `exclude_none=True` : impossible de vider un champ ; prénom `""` accepté | Validation + effacement explicite (L4) |
| `POST /api/auth/change-password` | Mot de passe | OK | tests **[exec]** | — |
| `GET /api/dashboard/stats` | KPIs | OK | tests **[exec]** | — |
| `GET /api/dashboard/disease-trends` | Tendance hebdo | partiel | libellés « Week n » en anglais générés côté serveur ; agrégation en Python | Libellés côté client (L3) |
| `GET /api/dashboard/recent-activity` | 5 dernières | mort (aucun appelant) | absent d'`api.js` | L'utiliser dans le dashboard (L4) |
| `GET /api/analysis/history` | Historique paginé + filtres | OK | tests **[exec]** | — |
| `GET/DELETE /api/analysis/{id}`, `GET /fiche/{id}` | Détail, suppression | OK | tests **[exec]** | — |
| `POST /api/camera/connect`, `/capture` | Flux MJPEG via serveur | cassé en prod | T10 | Conservés pour le dev local ; voie de production = image unique (L4/L7) |
| `POST /api/camera/analyze-frame`, `/upload` | Analyse d'une image | OK (avec le modèle mocké) | tests **[exec]** | Durcissement (L2) |
| `/api/drone/*` | Doublon legacy de `/api/camera/*` | mort | seul appelant : `drone.html` (page inaccessible, `/drone` redirige) | Suppression (L4.2) |
| `GET/POST /api/parcels`, `GET/PUT/DELETE /{id}` | CRUD parcelles | partiel | tests **[exec]** ; aucune validation de géométrie ; centroïde = moyenne des sommets (fermeture comprise) | Validation GeoJSON + centroïde surfacique (L5) |
| `GET /api/parcels/{id}/analyses` | Analyses d'une parcelle | OK | — | — |
| `GET /api/parcels/geo/analyses` | Analyses géolocalisées | **cassé** | route déclarée **après** `/{parcel_id}/analyses` : « geo » est capturé comme `parcel_id` → **422 `int_parsing`** **[exec]** | Réordonner les routes (L4) |
| `/api/chat/*` | Sessions GreenBot | partiel | T2 ; 503 sans `GEMINI_API_KEY` (attendu) ; messages d'erreur en français codés en dur | L3/L4 |
| `GET /api/weather/*` | Proxy OpenWeather | partiel | `lang: "fr"` et messages FR codés en dur ; `strftime("%A")` en anglais | Langue de la requête (L3) |
| `GET /api/diseases` | Référentiel | partiel | 37 entrées, 6 paires de doublons, FR/EN mélangés par champ, coquille « Cotonnnier » | Champs `fr`/`en`, fusion des doublons (L3) |
| `GET /api/health` | Santé | OK | — | — |

## 3. Pages

### Authentification : `index.html`, `register.html` (+ `auth.js`)
| Fonctionnalité | État | Preuve | Correction prévue |
|---|---|---|---|
| Connexion / inscription | OK | `auth.js:79,255` | — |
| Redirection si déjà connecté | mort | `auth.js:16` commentée | Réactiver (L4) |
| Validation du téléphone client ≠ serveur | partiel | `auth.js:177` compte les séparateurs | Aligner sur 8–15 chiffres (L4) |
| Soumission depuis l'étape 1 avec étape 2 invalide | partiel | `auth.js:243-251` pas de `goToStep(2)` | Corriger (L4) |
| « Mot de passe oublié », CGU, Confidentialité | mort | `index.html:270,293`, `register.html:544` `href="#"` | Masquer (aucun flux de reset) (L4) |
| Chiffres marketing (« 39+ maladies », « 3 s », « ∞ ») | trompeur | `index.html:163,167`, `register.html:196-205` | Retirer ou rendre exacts (L4) |
| `<p>` non fermé, `inputmode="tel"` sur un champ téléphone/email | cassé (mineur) | `index.html:108,220` | Corriger (L4) |
| i18n | partiel/absent | 5 `data-i18n` dans un panneau `aria-hidden` ; register : 0 | L3 |

### `dashboard.html`
| Fonctionnalité | État | Preuve | Correction prévue |
|---|---|---|---|
| Tableau « Analyses récentes » | **cassé** | `:755` `data.length`/`data.map` alors que l'API renvoie `{items}` → TypeError, carte vide | Lire `data.items` (L4) |
| KPIs en cas d'erreur API | trompeur | `:622-624` zéros affichés comme réels | État d'erreur « — » (L4) |
| Bandeau « vos champs sont sains » | trompeur | `:316` statique ; `:643` affiché même si l'API échoue | Message calculé à partir des données, sinon neutre (L4) |
| « This season » | trompeur | `:381,642` alors qu'il s'agit du total depuis toujours | « Au total » (L4) |
| Tendance « 30 jours » | partiel | `:668` `diseaseTrends(28)` ; badge « Live » statique ; repli silencieux sur des zéros | Corriger (L4) |
| Météo | partiel | `:739` `'yaounde'` codé en dur ; message technique en 503 | Région de l'utilisateur ; message clair (L4) |
| Lien « View » | partiel | `:790` `/history` générique | `/history?id=` (L4) |

### `profile.html`
| Fonctionnalité | État | Preuve | Correction prévue |
|---|---|---|---|
| Messages après sauvegarde / changement de mot de passe | **cassé** | `:350-366` `showAlert(element)` alors que la fonction attend un id → aucun message | Passer l'id (L4) |
| Bouton en chargement | cassé | `:341,349` `setButtonLoading(element)` | Idem (L4) |
| Vider un champ | partiel | voir `PUT /api/auth/me` | L4 |
| Minimum du mot de passe : 8 (UI) contre 6 (serveur) | incohérent | `:266,363` | Aligner (L4) |
| Rôle de repli « Agribusiness Manager » | trompeur (mineur) | `:318` | Afficher le vrai rôle (L6) |

### `settings.html`
| Fonctionnalité | État | Preuve | Correction prévue |
|---|---|---|---|
| Thème | OK | `:337` | — |
| Langue | partiel | n'agit que sur 3 pages ; clés décalées (`:178,197,215`) | L3 |
| Alertes « haute sévérité » et son | mort | `:238,248` `savePref` jamais relu ailleurs | Retirer (L4) |
| Statut des modèles IA | trompeur | `:301-304` « API online » d'après un simple 200 ; `data.models` ignoré ; version `v1.0.0-mvp` codée en dur | Lire `/api/health` (L4) |
| IP/port du rover | OK | lus par `camera.html:489` | — |

### `camera.html`
| Fonctionnalité | État | Preuve | Correction prévue |
|---|---|---|---|
| Webcam (getUserMedia) + `analyze-frame` | OK | `:670-723,771` | — |
| Flux IP du rover (connect, affichage, capture) | cassé en prod | T10 | P1 (L4.3) |
| Texte d'aide sur l'architecture | trompeur | `:162` | Réécrire (L4) |
| `switchMode` n'arrête pas la boucle : un canvas vide est analysé et **enregistré** ; en mode upload, `file=null` part toutes les 8 s | **cassé** | `:517,719,776` | Arrêter la boucle et les flux (L4) |
| Boucle automatique toutes les 8 s : ~450 lignes en base et ~450 images par heure | partiel | `:477` | Capture manuelle par défaut + déduplication (L2/L4) |
| Erreurs d'upload invisibles | partiel | `:783-786` | Toast (L4) |
| Résultat « uncertain » | mort | `:869-878` jamais renvoyé par le backend | Brancher sur `low_confidence` (L4) |
| Top 3 non affiché | partiel | `disease.top3` ignoré | Afficher (L4) |

### `drone.html`
| Fonctionnalité | État | Preuve | Correction prévue |
|---|---|---|---|
| Page entière | mort | `/drone` redirige vers `/camera` ; ids du layout erronés (`app-shell`) ; port 8080 codé en dur | Supprimer la page, `drone.css` et `/api/drone/*` (L4.2) |

### `history.html`
| Fonctionnalité | État | Preuve | Correction prévue |
|---|---|---|---|
| Liste paginée, filtres source/type, fiche | OK | `:398,463` | — |
| Filtre par plante | absent | supporté par l'API, pas par l'interface | Ajouter (L4) |
| `low_confidence` et top 3 non montrés | partiel | `:470-511` | Afficher (L4) |
| Supprimer la dernière ligne de la dernière page | cassé | `:516-523` page vide alors que total > 0 | Reculer d'une page (L4) |
| Lien vers GreenBot depuis la fiche | absent | — | Ajouter (L4) |

### `map.html`
| Fonctionnalité | État | Preuve | Correction prévue |
|---|---|---|---|
| Liste et création de parcelles (Polygon GeoJSON [lng, lat]) | OK | `:695,766,1025` | — |
| Surface | absent (saisie manuelle) | `:486` | Calcul géodésique (L5) |
| Région détectée | trompeur | `:622-642` boîtes englobantes qui se chevauchent : Buea → « Littoral » | Point dans polygone (L5) |
| Clic sur la carte pour remplir lat/lon | mort | la modale `inset:0` couvre la carte | L5 |
| Points des analyses | partiel | `:880` 100 dernières seulement ; `/geo/analyses` inutilisé | L5 |
| Suppression de la dernière parcelle | cassé | `:785-788` liste non vidée | L5 |
| Édition | absent | `parcels.update` jamais appelé | L5 |
| XSS (nom, culture) | cassé | T3 | L4 |

### `chatbot.html`
| Fonctionnalité | État | Preuve | Correction prévue |
|---|---|---|---|
| Sessions, envoi, rendu markdown échappé | OK | `:534-651,869` | — |
| Suppression de la dernière session | cassé | `:538-544` session fantôme, puis 404 | L4 |
| 503 (pas de clé Gemini) | partiel | `:663` toast seulement ; message sans réponse | Bulle d'erreur explicite (L4) |
| `analysis_id` conservé pour toutes les sessions | partiel | `:523` | Lier à une seule session (L4) |
| Liens markdown | partiel | `:666` | L4 (mineur) |

### `marketplace.html`
| Fonctionnalité | État | Preuve | Correction prévue |
|---|---|---|---|
| Catalogue (28 produits, images cohérentes) | partiel (statique, prix sans source) | `:716-750` | Bandeau « aperçu, prix indicatifs » (L4) |
| Notes et avis, « GREEN recommended » | trompeur (inventés) | `:718-749,908` | Retirer (L4) |
| Fabricants réels marqués « vérifiés » (Syngenta, Bayer, IRAD, CARBAP) | trompeur, risque juridique | `:718-749` | Retirer le badge et les marques non partenaires (L4, **décision humaine**) |
| Statistiques du bandeau (18 fournisseurs, lancement « Q3 2026 ») | trompeur | `:543-551` | Retirer (L4) |
| « Order request recorded », « You're on the list! » alors que rien n'est envoyé | trompeur | `:1019,1029` | Messages honnêtes (L4) |

### `calendar.html`
| Fonctionnalité | État | Preuve | Correction prévue |
|---|---|---|---|
| Calendrier cultural statique | OK (référence) mais non sourcé ; valable pour la zone bimodale seulement | `:193,260-326` | Source + mention de zone (L4) |
| « Disease Risk — Maize » = criquets | trompeur | `:302` | Renommer (L4) |

### `diseases.html`
| Fonctionnalité | État | Preuve | Correction prévue |
|---|---|---|---|
| Liste, recherche, détail | OK | `api.js:388` | — |
| Recherche « tomato », « maize » sans résultat | partiel | `affectedPlants` en français | Champs bilingues (L3) |
| 6 paires de doublons | cassé (contenu) | `diseases.json` | Fusion (L3) |

### `economics.html`
| Fonctionnalité | État | Preuve | Correction prévue |
|---|---|---|---|
| Simulation côté client, Chart.js | OK techniquement | `:622-636` | — |
| « Revenu net » sans coûts de production | trompeur | `:561` | Renommer (L4) |
| ROI = gain / coût (410 % au lieu de 310 %) | cassé (calcul) | `:563,585` | `(gain − coût) / coût` (L4) |
| Hypothèses cachées du scénario épidémie | trompeur | `:565-571` | Les afficher (L4) |
| Sources de prix vagues et dupliquées | partiel | `:436-505` | Une seule table datée (L4) |

### `benchmark.html`
| Fonctionnalité | État | Preuve | Correction prévue |
|---|---|---|---|
| « Moyennes régionales » inventées, présentées comme mesurées ; « 2× faster » | **trompeur** | `:310-318,266,418,452,582` | Retirer ; remplacer par l'historique propre de l'utilisateur (ou GREEN Data agrégé, L6) |
| Taux de maladie (numérateur limité à 100 éléments, dénominateur total) | cassé (calcul) | `:345` | `stats.diseases / stats.analyses` (L4) |
| Scans par mois = total / 3 | inventé | `:348` | Calcul à partir des dates (L4) |
| Score sur 100 et badges | trompeur | `:355,427` | Retirer le score (L4) |

## 4. Incohérences README ⇄ code

| README | Réalité du code | Action |
|---|---|---|
| Détection de ravageurs YOLOv8 (criquets, papillons), inférence double via `asyncio.gather`, `ThreadPoolExecutor(max_workers=2)` | Aucune dépendance `ultralytics` ; `best.pt` jamais chargé ; un seul modèle, `max_workers=1` | Retirer du README ou en faire un lot à part (décision humaine) |
| GreenBot : `gemini-2.5-flash-lite`, contexte « analyses récentes, parcelles, météo » | `GEMINI_MODEL = "gemini-3.1-flash-lite"` codé en dur ; contexte = une seule analyse, optionnelle | Vérifier le nom du modèle ; le rendre configurable (`GEMINI_MODEL`) (L3/L7) |
| « Chat sessions persisted in SQLite », schéma SQLite | Supabase PostgreSQL via `DATABASE_URL` en production, SQLite en repli | L8 |
| Rover sur « Arduino Uno Q » | Raspberry Pi (`MODIFICATIONS.md`) | L8 |
| `GET /api/camera/stream`, « Gemini enrichment (treatment advice) » dans la chaîne caméra | Inexistants | L8 |
| « 12 pages », « 38-entry knowledge base » | 15 pages, 37 entrées (dont 6 paires de doublons) | L8 |

## 5. Vérifications d'exécution

Serveur : `DEBUG=true DATABASE_URL=sqlite:///… uvicorn main:app` (venv Python 3.12, torch 2.13.0+cpu).

| Vérification | Résultat |
|---|---|
| `GET /api/health` | 200 `{"status":"ok", "models":{"efficientnet":"lazy","rag_index":"lazy"}}` |
| 15 routes HTML (`/`, `/register`, `/dashboard`, …, `/benchmark`) | 200 ; `/drone` → 307 vers `/camera` ; `/drone.html` reste servi (200) par le montage statique |
| `POST /api/camera/upload` avec le **vrai** modèle (image unie 300×300) | 200 en 0,25 s ; `Corn_Mildew`, confiance 0,21, `severity` « low » ; image écrite dans `MEDIA_DIR/2026/10/<uuid>.jpg` |
| Lecture de l'image **sans jeton** | **200** → T1 confirmé |
| `GET /api/parcels/geo/analyses` | **422** `int_parsing` sur `parcel_id="geo"` |
| `POST /api/auth/register` invalide | 422, `detail` = **tableau** d'objets → T8 confirmé |
| GreenBot sans `GEMINI_API_KEY` | 503 avec message français codé en dur (le contexte de l'analyse d'un autre utilisateur est construit **avant** l'appel LLM : T2 non démontrable sans clé, test avec LLM mocké prévu en L4) |
| `/docs` | 200 en `DEBUG=true` uniquement |

### Ligne de base du harnais (22/10/2026)

| Commande | Résultat |
|---|---|
| `.venv/bin/pytest -q` (dans `backend/`) | 21 passed, 6 xfailed (xfail stricts = défauts connus : médias publics, pas de déduplication, pas de validation géométrique) |
| `.venv/bin/ruff check backend` | 11 erreurs (imports inutilisés, variable morte) → corrigées, « All checks passed! » |
| `python scripts/check_i18n.py --summary` | 532 chaînes HTML statiques non balisées |
| `npx playwright test` (dans `qa/`) | 21 passed, 35 failed : 28 × FR (texte anglais visible), `dashboard` (`pageerror: data.map is not a function`, 4 combinaisons), débordement horizontal à 390 px sur `camera` (86 px), `calendar`, `economics`, `benchmark`, `marketplace` (164 à 366 px) |

### Défauts découverts pendant les lots 1–2

| # | Défaut | État | Correction |
|---|---|---|---|
| T17 | `dataset_consent` absent de `UserResponse`/`UserUpdate` : aucun utilisateur ne pouvait consentir, GREEN Data serait toujours vide | cassé | Exposé et modifiable via `PUT /api/auth/me` (lot 2) |
| T18 | `parcel_id` d'upload non vérifié : une analyse pouvait être rattachée à la parcelle d'un autre utilisateur | cassé (sécurité) | 404 si la parcelle n'appartient pas à l'utilisateur (lot 2) |
| T19 | En-tête `Authorization` absent → 403 au lieu de 401 | partiel | `HTTPBearer(auto_error=False)` + 401 (lot 2) |

## Suivi des corrections (lots 3–4, au 22/10/2026)

| Réf. | Statut | Commit |
|---|---|---|
| T1 médias publics | corrigé (lot 2) | `c7414c4` |
| T2 IDOR GreenBot | corrigé, test `test_other_users_analysis_is_never_used` | `751ee61` |
| T3 XSS | corrigé sur toutes les pages réécrites (`escapeHtml`, toasts en texte) ; `map.html` au lot 5 | plusieurs |
| T4 « sévérité » | corrigé : `none` si sain, « niveau d'alerte » expliqué | `28def9d` |
| T5 diagnostic | corrigé : « maladie probable » + mention sur chaque fiche | `e246b41`, `c891734` |
| T6 / T7 i18n | corrigé hors `map.html` ; clé de langue unique `green_lang` | `4f88877` et suivants |
| T8 « [object Object] » | corrigé (serveur et client) | `4f88877` |
| T9 double boot | corrigé (boot idempotent) | `4f88877` |
| T10 flux rover | voie de production = file IndexedDB (P1-a) ; avertissement HTTPS | `12fe55e` |
| T11 analyses sans contexte | parcelle + GPS joints aux captures ; mission au lot 5 | `12fe55e` |
| T12 upload | corrigé (lot 2) | `c7414c4` |
| T16 correspondances | corrigé, à valider par un agronome | `c891734` |
| Pages dashboard, profile, settings, history, camera, chatbot, diseases, calendar, economics, benchmark, marketplace, index, register | toutes les lignes « cassé / partiel / trompeur / mort » traitées dans le commit de la page | voir `git log` |
| `map.html` | lot 5 | — |
