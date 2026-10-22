# ============================================================
# GREEN App — Server-side translations (French / English)
#
# Routers raise HTTPException with an English message; the exception
# handlers below translate it according to the request language:
#   ?lang=fr|en  >  Accept-Language  >  English (scripts, curl).
# 422 validation errors are flattened into the same {"detail": str}
# shape, field names and messages translated.
# ============================================================

import re
from typing import Optional

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

SUPPORTED = ("fr", "en")
DEFAULT_LANG = "en"


def request_lang(request: Optional[Request]) -> str:
    if request is None:
        return DEFAULT_LANG
    q = (request.query_params.get("lang") or "").lower()
    if q in SUPPORTED:
        return q
    for part in (request.headers.get("accept-language") or "").split(","):
        tag = part.split(";")[0].strip().lower()[:2]
        if tag in SUPPORTED:
            return tag
    return DEFAULT_LANG


# ---- Error messages (English source → French) ---------------
MESSAGES_FR = {
    # auth
    "This phone number is already registered.": "Ce numéro de téléphone est déjà enregistré.",
    "This email address is already registered.": "Cette adresse e-mail est déjà enregistrée.",
    "Incorrect phone/email or password.": "Téléphone/e-mail ou mot de passe incorrect.",
    "This account has been deactivated.": "Ce compte a été désactivé.",
    "This email is already used by another account.": "Cette adresse e-mail est déjà utilisée par un autre compte.",
    "Current password is incorrect.": "Le mot de passe actuel est incorrect.",
    "Invalid or expired token. Please sign in again.": "Session invalide ou expirée. Veuillez vous reconnecter.",
    "Authentication required.": "Authentification requise.",
    "You do not have access to this page.": "Vous n'avez pas accès à cette page.",
    "Invalid phone number format.": "Format de numéro de téléphone invalide.",
    "Invalid email address.": "Adresse e-mail invalide.",
    "This field cannot be empty.": "Ce champ ne peut pas être vide.",
    # resources
    "Analysis not found.": "Analyse introuvable.",
    "Parcel not found.": "Parcelle introuvable.",
    "Mission not found.": "Mission introuvable.",
    "Session not found.": "Conversation introuvable.",
    "Not found.": "Introuvable.",
    # media / upload
    "Empty file.": "Fichier vide.",
    "Unsupported image format (JPEG, PNG or WebP).": "Format d'image non pris en charge (JPEG, PNG ou WebP).",
    "The file is not a valid image.": "Le fichier n'est pas une image valide.",
    "Expired or invalid image link.": "Lien d'image expiré ou invalide.",
    "You do not have access to this image.": "Vous n'avez pas accès à cette image.",
    # camera / rover
    "No JPEG frame found in stream.": "Aucune image JPEG trouvée dans le flux.",
    # GreenBot
    "GreenBot is not configured on this server.": "GreenBot n'est pas configuré sur ce serveur.",
    "GreenBot is busy (usage quota reached). Please try again in a few minutes.":
        "GreenBot est saturé (quota d'utilisation atteint). Veuillez réessayer dans quelques minutes.",
    "GreenBot is temporarily unavailable. Please try again later.":
        "GreenBot est temporairement indisponible. Veuillez réessayer plus tard.",
    "Could not create the conversation. Please try again.":
        "Impossible de créer la conversation. Veuillez réessayer.",
    # weather
    "The weather service is not configured on this server.": "Le service météo n'est pas configuré sur ce serveur.",
    "The weather service is unavailable.": "Le service météo est indisponible.",
    # GREEN Map: parcels and missions
    "The parcel geometry must be a GeoJSON Polygon.": "La géométrie de la parcelle doit être un polygone GeoJSON.",
    "Parcels with holes are not supported.": "Les parcelles trouées ne sont pas prises en charge.",
    "Each point must be [longitude, latitude].": "Chaque point doit être [longitude, latitude].",
    "A parcel needs at least 3 points.": "Une parcelle doit compter au moins 3 points.",
    "Coordinates out of range: expected [longitude, latitude].":
        "Coordonnées hors limites : [longitude, latitude] attendu.",
    "Latitude and longitude seem swapped: GeoJSON expects [longitude, latitude].":
        "La latitude et la longitude semblent inversées : GeoJSON attend [longitude, latitude].",
    "The parcel outline crosses itself.": "Le contour de la parcelle se croise lui-même.",
    "The parcel is too small.": "La parcelle est trop petite.",
    "The cell size must be between 1 and 50 m.": "La taille de cellule doit être comprise entre 1 et 50 m.",
    "The parcel is smaller than one cell: choose a smaller cell size.":
        "La parcelle est plus petite qu'une cellule : choisissez une taille de cellule plus petite.",
    "This parcel was changed elsewhere in the meantime: the server version is kept.":
        "Cette parcelle a été modifiée ailleurs entre-temps : la version du serveur est conservée.",
    "This parcel has no outline: draw it on the map first.":
        "Cette parcelle n'a pas de contour : tracez-la d'abord sur la carte.",
    "The cell is not part of this mission.": "Cette cellule ne fait pas partie de la mission.",
    "The mission does not belong to this parcel.": "La mission n'appartient pas à cette parcelle.",
    # generic
    "Internal server error.": "Erreur interne du serveur.",
}

# Messages with a variable part: (English regex, French template)
PATTERNS_FR = [
    (re.compile(r"^Image too large\. Maximum (\d+) MB\.$"), "Image trop volumineuse. Maximum {0} Mo."),
    (re.compile(r"^Disease '(.+)' not found\.$"), "Maladie « {0} » introuvable."),
    (re.compile(r"^A parcel can have at most (\d+) points\.$"), "Une parcelle peut compter au plus {0} points."),
    (re.compile(r"^The parcel is too large \(more than (\d+) ha\)\.$"),
     "La parcelle est trop grande (plus de {0} ha)."),
    (re.compile(r"^Too many cells \(more than (\d+)\): use cells of at least (\d+) m\.$"),
     "Trop de cellules (plus de {0}) : utilisez des cellules d'au moins {1} m."),
    (re.compile(r"^Password must be at least (\d+) characters\.$"),
     "Le mot de passe doit contenir au moins {0} caractères."),
    (re.compile(r"^New password must be at least (\d+) characters\.$"),
     "Le nouveau mot de passe doit contenir au moins {0} caractères."),
    (re.compile(r"^City not found: (.+)$"), "Ville introuvable : {0}"),
    (re.compile(r"^Could not reach the camera stream at (.+)\. Check the rover Wi-Fi and the IP/port\.$"),
     "Impossible de joindre le flux caméra à {0}. Vérifiez le Wi-Fi du rover et l'adresse IP/le port."),
    (re.compile(r"^Could not grab a frame from the stream at (.+)\. Check the rover Wi-Fi and the IP/port\.$"),
     "Impossible de récupérer une image du flux à {0}. Vérifiez le Wi-Fi du rover et l'adresse IP/le port."),
]


def translate(message: str, lang: str) -> str:
    if lang != "fr" or not isinstance(message, str):
        return message
    if message in MESSAGES_FR:
        return MESSAGES_FR[message]
    for pattern, template in PATTERNS_FR:
        m = pattern.match(message)
        if m:
            return template.format(*m.groups())
    return message


# ---- Validation errors (pydantic v2) -------------------------
FIELD_NAMES = {
    "fr": {
        "first_name": "prénom", "last_name": "nom", "phone": "téléphone", "email": "e-mail",
        "password": "mot de passe", "new_password": "nouveau mot de passe",
        "current_password": "mot de passe actuel", "identifier": "identifiant",
        "name": "nom", "geometry": "géométrie", "file": "fichier", "cell_size_m": "taille de cellule",
        "region": "région", "crop_type": "culture", "area_ha": "surface",
    },
    "en": {
        "first_name": "first name", "last_name": "last name", "new_password": "new password",
        "current_password": "current password", "cell_size_m": "cell size", "crop_type": "crop",
        "area_ha": "area",
    },
}

VALIDATION_FR = [
    (re.compile(r"^Field required$"), "champ obligatoire"),
    (re.compile(r"^String should have at least (\d+) characters?$"), "au moins {0} caractères"),
    (re.compile(r"^String should have at most (\d+) characters?$"), "au plus {0} caractères"),
    (re.compile(r"^Input should be a valid number.*$"), "doit être un nombre"),
    (re.compile(r"^Input should be a valid integer.*$"), "doit être un nombre entier"),
    (re.compile(r"^Input should be a valid boolean.*$"), "doit être vrai ou faux"),
    (re.compile(r"^Input should be greater than or equal to (.+)$"), "doit être supérieur ou égal à {0}"),
    (re.compile(r"^Input should be less than or equal to (.+)$"), "doit être inférieur ou égal à {0}"),
    (re.compile(r"^Input should be greater than (.+)$"), "doit être supérieur à {0}"),
    (re.compile(r"^Input should be less than (.+)$"), "doit être inférieur à {0}"),
    (re.compile(r"^value is not a valid email address.*$"), "adresse e-mail invalide"),
    (re.compile(r"^Value error, (.+)$"), "{0}"),
]


def _validation_message(err: dict, lang: str) -> str:
    loc = [str(x) for x in err.get("loc", []) if x not in ("body", "query", "path", "form")]
    field = loc[-1] if loc else ""
    field = FIELD_NAMES.get(lang, {}).get(field, field.replace("_", " "))
    msg = err.get("msg", "")
    if lang == "fr":
        for pattern, template in VALIDATION_FR:
            m = pattern.match(msg)
            if m:
                msg = translate(template.format(*m.groups()), "fr")
                break
    elif msg.startswith("Value error, "):
        msg = msg[len("Value error, "):]
    return f"{field} : {msg}" if (field and lang == "fr") else (f"{field}: {msg}" if field else msg)


def validation_detail(errors: list, lang: str) -> str:
    parts = [_validation_message(e, lang) for e in errors]
    prefix = "Veuillez vérifier le formulaire" if lang == "fr" else "Please check the form"
    sep = " ; " if lang == "fr" else "; "
    return f"{prefix}{' ' if lang == 'fr' else ''}: {sep.join(parts)}"


# ---- Handlers ------------------------------------------------
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    lang = request_lang(request)
    detail = translate(exc.detail, lang) if isinstance(exc.detail, str) else exc.detail
    return JSONResponse({"detail": detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None))


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    lang = request_lang(request)
    return JSONResponse(
        {"detail": validation_detail(exc.errors(), lang), "errors": [
            {"loc": list(e.get("loc", [])), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()
        ]},
        status_code=422,
    )


def install(app) -> None:
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
