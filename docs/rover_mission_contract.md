# Contrat rover ⇄ GREEN

Ce document décrit ce que le rover (Raspberry Pi) reçoit de GREEN et ce qu'il doit lui renvoyer.
La navigation physique du rover est hors du périmètre de GREEN.

Toutes les coordonnées sont en **WGS84 (EPSG:4326)**. Les dates sont en ISO 8601 ; sans fuseau horaire, elles sont lues comme UTC.

## 1. Récupérer une mission

Une mission est créée dans GREEN Map (parcelle → quadrillage → « Créer la mission »).
Elle fige la grille et le parcours. Une modification ultérieure de la parcelle ne change pas une mission existante.

```
GET /api/missions/{mission_id}/waypoints
Authorization: Bearer <jeton de l'utilisateur>
```

Réponse :

```json
{
  "mission_id": 12,
  "parcel_id": 4,
  "cell_size_m": 5,
  "speed_mps": 0.5,
  "cells_total": 40,
  "distance_m": 195.3,
  "crs": "EPSG:4326",
  "waypoints": [
    {"index": 0, "cell_index": 1, "lat": 3.8500225, "lng": 11.5000225, "capture": true},
    {"index": 1, "cell_index": 2, "lat": 3.8500225, "lng": 11.5000676, "capture": true}
  ]
}
```

| Champ | Sens |
|---|---|
| `index` | Ordre de passage (0, 1, 2…). Suivre la liste dans cet ordre. |
| `cell_index` | Numéro de la cellule (1 à `cells_total`), le même que dans l'interface. |
| `lat`, `lng` | Point à atteindre : à l'intérieur de la cellule et de la parcelle. |
| `capture` | `true` : prendre une image ici. `false` : point de transit (contournement d'une partie concave), pas de prise de vue. |

Garanties :
- **Grille.** Elle est alignée sur l'axe le plus long de la parcelle. Les cellules sont carrées (`cell_size_m`), découpées au contour, et celles de moins de 10 % d'une cellule entière sont supprimées.
- **Parcours.** Il suit un serpentin (boustrophédon). Deux points consécutifs sont toujours dans des cellules voisines (8-connexité), sans saut.
- **Captures.** Chaque cellule apparaît exactement une fois avec `capture: true`, dans l'ordre croissant de `cell_index`.

Autres exports, depuis GREEN Map :
- « Points de passage (JSON) » : la même réponse que ci-dessus.
- « Quadrillage et parcours (GeoJSON) » via `GET /api/missions/{id}/export.geojson` : la parcelle, les cellules (`kind: "cell"`, `cell_index`) et le parcours (`kind: "path"`).

## 2. Envoyer les images (voie actuelle : par le navigateur)

Le navigateur de l'opérateur est connecté au Wi-Fi du rover et n'a donc pas Internet. Il capture les images et les garde en file d'attente (IndexedDB). Il les envoie dès que la connexion revient. Pour chaque image :

```
POST /api/camera/analyze-frame        (multipart/form-data)
Authorization: Bearer <jeton de l'utilisateur>

file         image JPEG/PNG/WebP (8 Mo max, configurable : MAX_UPLOAD_MB)
source       "rover"
mission_id   12
cell_index   7                 (facultatif si latitude/longitude sont fournies)
latitude     3.85012           (facultatif)
longitude    11.50031          (facultatif)
captured_at  2026-10-22T08:31:05+01:00   (heure de prise de vue sur l'appareil)
```

Règles côté serveur :
- **Contrôles de cohérence.**
  - Une mission d'un autre utilisateur → 404.
  - `cell_index` hors de 1…`cells_total` → 422.
  - `parcel_id` différent de celui de la mission → 422.
- **Position GPS sans cellule.** La cellule est trouvée par un test point-dans-polygone. Sans mission, c'est la parcelle de l'utilisateur qui contient le point qui est retenue.
- **Doublons.** Une image identique (même `sha256`) déjà envoyée par le même utilisateur n'est pas réanalysée : la réponse renvoie l'analyse existante, avec `"duplicate": true`.
- **Réponse.** Elle contient `analysis_id`, la maladie probable, `fiche_terrain`, ainsi que `image_path` et `thumb_path`, des URL signées valables une à deux heures.

### Pour que la capture depuis le flux MJPEG fonctionne dans le navigateur

- **Partage inter-origines.** Le rover doit répondre avec `Access-Control-Allow-Origin: *` sur le flux MJPEG. Sans cet en-tête, le navigateur affiche le flux mais refuse d'en extraire une image : la zone de dessin est marquée « tainted ».
- **Contenu mixte.** Une page servie en HTTPS (production) ne peut pas afficher un flux `http://192.168.x.x`. En production, utilisez l'une des options suivantes :
  - le mode « Caméra » sur un téléphone fixé au rover ;
  - l'import des photos prises par le rover ;
  - la voie 3 ci-dessous.

## 3. Voie future : envoi direct par le Raspberry Pi (non implémentée)

Cette voie est **documentée seulement** (décision D3, prémisse P1-c). Elle supposerait que le Pi ait sa propre connexion Internet, par exemple une clé 4G.

```
POST /api/devices/{device_id}/frames      (multipart/form-data)
Authorization: Device <jeton d'appareil>

file, mission_id, cell_index, latitude, longitude, captured_at   (comme ci-dessus ; source = "rover")
```

Éléments à construire le jour où cette voie sera retenue :
1. **Table `devices`.** Colonnes : `id`, `user_id`, `name`, `token_hash` (le jeton n'est jamais stocké en clair), `created_at`, `last_seen_at` et `revoked_at`. Ajout par une révision Alembic additive.
2. **Gestion des jetons.** L'utilisateur crée un appareil depuis les Paramètres et le jeton ne lui est montré qu'une fois. Il peut révoquer l'appareil à tout moment.
3. **Endpoint.**
   - L'authentification `Device` est vérifiée par comparaison à temps constant du hachage.
   - L'image est ensuite rattachée au compte du propriétaire de l'appareil, avec les mêmes contrôles et le même traitement que `analyze-frame` (`rover_common.analyze_image_bytes`).
   - Le nombre de requêtes est limité par appareil.
4. **Hors ligne côté Pi.** Le Pi garde les images sur sa carte SD et les renvoie dans l'ordre ; le serveur ignore déjà les doublons.

## 4. Suivi

- **Avancement.** L'avancement d'une mission correspond au nombre de cellules distinctes ayant au moins une analyse, sur `cells_total`. Il est visible dans GREEN Map et dans `GET /api/missions/{id}`.
- **Statut.** Il est modifiable dans GREEN Map ou par `PATCH /api/missions/{id}` (`draft`, `ready`, `running`, `done`).
