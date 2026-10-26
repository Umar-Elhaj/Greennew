-- ============================================================
-- GREEN App — Schéma MySQL / MariaDB (o2switch)
-- RÉFÉRENCE de l'état final du schéma de production. La voie normale est
-- Alembic, depuis le serveur :
--   cd backend && alembic upgrade head
-- Ce fichier peut aussi être importé tel quel dans une base VIDE
-- (cPanel › phpMyAdmin › base sc1jsgw2086_green › Importer) : il crée les
-- tables et la table alembic_version déjà à jour (révision 0004_green_data),
-- si bien qu'aucun « alembic stamp » n'est nécessaire ensuite.
--
-- Reflète exactement backend/models.py (SQLAlchemy) ; vérifié par
-- tests/test_migrations.py::test_mysql_reference_sql_matches_models.
-- Compatible MariaDB 10.4+ et MySQL 8.0.16+ (contraintes CHECK appliquées).
--
-- Choix propres à MySQL (backend/db_types.py) :
--   - DOUBLE et non FLOAT (simple précision : les positions GPS perdraient
--     des décimètres) ;
--   - DATETIME(6) : microsecondes conservées (ordre des messages du chat) ;
--   - MEDIUMTEXT pour les textes longs (TEXT s'arrête à 64 Ko) ;
--   - JSON (LONGTEXT vérifié par json_valid sous MariaDB) ;
--   - InnoDB + utf8mb4 / utf8mb4_unicode_ci pour toutes les tables.
-- Les dates sont en UTC : l'application ouvre chaque session avec
-- time_zone = '+00:00' (backend/db_url.py).
-- Les images ne sont PAS stockées ici : seul leur chemin relatif
-- (ex. "2026/10/3f2a….jpg") est conservé dans disease_analyses.image_path.
-- ============================================================

SET NAMES utf8mb4;
SET time_zone = '+00:00';

-- ------------------------------------------------------------
-- USERS — Comptes de la plateforme
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id               INT NOT NULL AUTO_INCREMENT,
    first_name       VARCHAR(100) NOT NULL,
    last_name        VARCHAR(100) NOT NULL,
    phone            VARCHAR(20)  NOT NULL,
    email            VARCHAR(255) NULL,
    password_hash    VARCHAR(255) NOT NULL,
    company_name     VARCHAR(255) NULL,
    region           VARCHAR(100) NULL,
    avatar_url       VARCHAR(500) NULL,
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    -- Green Data : accord pour réutiliser les images dans le dataset
    dataset_consent  BOOLEAN NOT NULL DEFAULT FALSE,
    -- Conserver la position GPS trouvée dans les métadonnées des photos
    location_consent BOOLEAN NOT NULL DEFAULT FALSE,
    -- farmer | agronomist (vérifie les analyses) | partner (GREEN Data) | admin
    role             VARCHAR(20) NOT NULL DEFAULT 'farmer',
    created_at       DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at       DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY phone (phone),
    UNIQUE KEY email (email),
    CONSTRAINT users_role_check CHECK (role IN ('farmer', 'agronomist', 'partner', 'admin'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- PARCELS — Parcelles agricoles
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS parcels (
    id          INT NOT NULL AUTO_INCREMENT,
    user_id     INT NOT NULL,
    name        VARCHAR(255) NOT NULL,
    crop_type   VARCHAR(100) NULL,
    area_ha     DOUBLE NULL,                  -- calculée depuis la géométrie
    perimeter_m DOUBLE NULL,                  -- calculé depuis la géométrie
    sowing_date DATE NULL,                    -- date de semis
    region      VARCHAR(100) NULL,
    description MEDIUMTEXT NULL,
    geometry    JSON NULL,                    -- Polygone GeoJSON, WGS84, [lng, lat]
    client_id   VARCHAR(36) NULL,             -- id créé hors ligne par le navigateur (idempotence)
    latitude    DOUBLE NULL,
    longitude   DOUBLE NULL,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY ix_parcels_user_id (user_id),
    UNIQUE KEY uq_parcels_user_client_id (user_id, client_id),
    CONSTRAINT parcels_user_id_fkey FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- MISSIONS — Quadrillage figé + parcours en serpentin (GREEN Map)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS missions (
    id          INT NOT NULL AUTO_INCREMENT,
    user_id     INT NOT NULL,
    parcel_id   INT NOT NULL,
    name        VARCHAR(255) NULL,
    status      VARCHAR(20) NOT NULL DEFAULT 'draft',
    cell_size_m DOUBLE NOT NULL,
    speed_mps   DOUBLE NOT NULL DEFAULT 0.5,
    start_lat   DOUBLE NULL,
    start_lng   DOUBLE NULL,
    angle_deg   DOUBLE NULL,                  -- orientation du quadrillage (axe long)
    cells_total INT NOT NULL,
    distance_m  DOUBLE NOT NULL,
    duration_s  INT NOT NULL,
    grid        JSON NOT NULL,                -- cellules [{index,row,col,polygon,center,area_m2}]
    waypoints   JSON NOT NULL,                -- [{index,cell_index,lat,lng,capture}]
    created_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY ix_missions_user_id (user_id),
    KEY ix_missions_parcel_id (parcel_id),
    CONSTRAINT missions_user_id_fkey   FOREIGN KEY (user_id)   REFERENCES users (id)   ON DELETE CASCADE,
    CONSTRAINT missions_parcel_id_fkey FOREIGN KEY (parcel_id) REFERENCES parcels (id) ON DELETE CASCADE,
    CONSTRAINT missions_status_check CHECK (status IN ('draft', 'ready', 'running', 'done'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- DISEASE_ANALYSES — Chaque analyse d'image (= une entrée Green Data)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS disease_analyses (
    id               INT NOT NULL AUTO_INCREMENT,
    user_id          INT NOT NULL,
    parcel_id        INT NULL,

    -- Entrée
    source           VARCHAR(50) NULL DEFAULT 'camera',  -- camera | upload | drone
    image_path       VARCHAR(500) NULL,                  -- chemin relatif dans MEDIA_DIR
    image_sha256     CHAR(64) NULL,                      -- détection des doublons
    image_bytes      INT NULL,                           -- taille du JPEG stocké
    image_width      INT NULL,
    image_height     INT NULL,

    -- Sortie du modèle
    detected_disease VARCHAR(255) NULL,
    disease_name     VARCHAR(255) NULL,
    confidence       DOUBLE NULL,
    severity         VARCHAR(50) NULL,
    plant_type       VARCHAR(100) NULL,
    predictions      JSON NULL,                          -- top-3 [{class, confidence}]
    model_version    VARCHAR(100) NULL,

    -- GPS
    latitude         DOUBLE NULL,
    longitude        DOUBLE NULL,

    -- GREEN Map : cellule de mission, date de prise de vue sur l'appareil
    mission_id       INT NULL,
    cell_index       INT NULL,
    captured_at      DATETIME(6) NULL,

    fiche_terrain    JSON NULL,
    notes            MEDIUMTEXT NULL,

    -- Green Data : validation humaine + consentement
    consent_dataset  BOOLEAN NOT NULL DEFAULT FALSE,
    verified_label   VARCHAR(255) NULL,                  -- classe corrigée par un agronome
    verified_by      INT NULL,
    verified_at      DATETIME(6) NULL,

    -- Données de démonstration (scripts/seed_demo.py), exclues des statistiques par défaut
    is_demo          BOOLEAN NOT NULL DEFAULT FALSE,

    created_at       DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),

    PRIMARY KEY (id),
    KEY ix_disease_analyses_user_id (user_id),
    KEY ix_disease_analyses_parcel_id (parcel_id),
    KEY ix_disease_analyses_created_at (created_at),
    KEY ix_disease_analyses_sha256 (image_sha256),
    KEY ix_disease_analyses_mission_cell (mission_id, cell_index),
    KEY ix_disease_analyses_green_data (consent_dataset, is_demo, created_at),
    -- Export du dataset (index partiel sous PostgreSQL, complet sous MySQL)
    KEY ix_disease_analyses_dataset (plant_type, detected_disease),
    CONSTRAINT disease_analyses_user_id_fkey     FOREIGN KEY (user_id)     REFERENCES users (id)    ON DELETE CASCADE,
    CONSTRAINT disease_analyses_parcel_id_fkey   FOREIGN KEY (parcel_id)   REFERENCES parcels (id)  ON DELETE CASCADE,
    CONSTRAINT disease_analyses_mission_id_fkey  FOREIGN KEY (mission_id)  REFERENCES missions (id) ON DELETE SET NULL,
    CONSTRAINT disease_analyses_verified_by_fkey FOREIGN KEY (verified_by) REFERENCES users (id)    ON DELETE SET NULL,
    CONSTRAINT disease_analyses_confidence_check CHECK (confidence BETWEEN 0 AND 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- CHAT_SESSIONS — Conversations GreenBot
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chat_sessions (
    id         INT NOT NULL AUTO_INCREMENT,
    user_id    INT NOT NULL,
    title      VARCHAR(255) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY ix_chat_sessions_user_id (user_id),
    CONSTRAINT chat_sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- CHAT_MESSAGES — Messages d'une conversation
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chat_messages (
    id          INT NOT NULL AUTO_INCREMENT,
    session_id  INT NOT NULL,
    role        VARCHAR(20) NOT NULL,
    content     MEDIUMTEXT NOT NULL,
    -- Supprimer une analyse ne doit pas casser l'historique du chat
    analysis_id INT NULL,
    created_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY ix_chat_messages_session_id (session_id),
    CONSTRAINT chat_messages_session_id_fkey  FOREIGN KEY (session_id)  REFERENCES chat_sessions (id)    ON DELETE CASCADE,
    CONSTRAINT chat_messages_analysis_id_fkey FOREIGN KEY (analysis_id) REFERENCES disease_analyses (id) ON DELETE SET NULL,
    CONSTRAINT chat_messages_role_check CHECK (role IN ('user', 'assistant'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- ALEMBIC_VERSION — Révision du schéma (lue au démarrage de l'API et par
-- scripts/db_check.py). À mettre à jour à chaque nouvelle révision.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL,
    PRIMARY KEY (version_num)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO alembic_version (version_num)
SELECT '0004_green_data' FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM alembic_version);
