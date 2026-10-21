# Journal des modifications — GREEN

Ce document liste chaque modification apportée au projet, ses raisons, et ce qu'il faut savoir pour la suite.
Les entrées sont classées de la plus récente à la plus ancienne.

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
