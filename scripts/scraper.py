from __future__ import annotations

"""
OVICUE - scraper.py

Versión sin IA.

Qué hace:
1. Entra a la sección de seguridad de Diario de Morelos
2. Toma solo las primeras 12 notas
3. Descarga cada nota
4. Usa reglas basadas en palabras clave para decidir si:
   - es un hecho violento
   - pertenece al área objetivo
5. Detecta si el hecho ocurrió en:
   - Cuernavaca
   - o un municipio / zona conurbada configurada
6. Resuelve ubicación usando el gazetteer local
7. Construye eventos y los guarda en data/events.json

Sin IA:
- no usa Gemini
- no requiere GOOGLE_API_KEY
- no consume cuota de modelos
"""

import hashlib
import json
import re
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup


# =============================================================================
# RUTAS Y CONFIGURACIÓN
# =============================================================================

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

EVENTS_PATH = DATA_DIR / "events.json"
GEOCODE_CACHE_PATH = DATA_DIR / "geocode_cache.json"
GAZETTEER_PATH = DATA_DIR / "colonias_cuernavaca.json"
UNRESOLVED_PATH = DATA_DIR / "unresolved_events.json"

HEADERS = {
    "User-Agent": "OVICUE/0.6 (deterministic keyword pipeline)"
}

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_VIEWBOX = "-99.33,19.01,-99.11,18.79"
NOMINATIM_RESULT_TYPES = {
    "borough",
    "city_block",
    "hamlet",
    "isolated_dwelling",
    "locality",
    "neighbourhood",
    "quarter",
    "residential",
    "suburb",
    "village",
}

SETTLEMENT_TYPE_PREFIXES = {
    "ampliacion": ("ampliacion",),
    "barrio": ("barrio",),
    "colonia": ("colonia", "col.", "col"),
    "condominio": ("condominio",),
    "fraccionamiento": ("fraccionamiento", "fracc.", "fracc"),
    "rinconada": ("rinconada",),
    "seccion": ("seccion", "sección"),
    "unidad habitacional": ("unidad habitacional", "unidad"),
    "zona militar": ("zona militar",),
}


# =============================================================================
# FUENTES
# =============================================================================

SOURCES = [
    {
        "name": "Diario de Morelos",
        "url": "https://www.diariodemorelos.com/noticias/categories/sos",
        "selector": 'h3 a[href*="/noticias/"]',
        "base_url": "https://www.diariodemorelos.com",
    }
]

# Solo procesar las primeras 12 notas visibles
MAX_ARTICLES_PER_RUN = 12


# =============================================================================
# ÁREA OBJETIVO
# =============================================================================

CONURBADO_AREAS = {
    "jiutepec": "Jiutepec",
    "emiliano zapata": "Emiliano Zapata",
    "temixco": "Temixco",
    "civac": "CIVAC",
    "yautepec": "Yautepec",
    "xochitepec": "Xochitepec",
}

# Municipios de Morelos que NO pertenecen al área conurbada de Cuernavaca.
# Si aparecen en el texto, descartamos detecciones ambiguas de conurbado
# (ej: "colonia Emiliano Zapata de Cuautla" no es el municipio conurbado).
MORELOS_EXCLUDED_MUNICIPALITIES = [
    "cuautla",
    "tepoztlan",
    "yecapixtla",
    "ayala",
    "jojutla",
    "puente de ixtla",
    "zacatepec",
    "tlaltizapan",
    "tlayacapan",
    "totolapan",
    "mazatepec",
    "miacatlan",
    "coatetelco",
    "amacuzac",
    "tetela del volcan",
    "ocuituco",
    "temoac",
    "jantetelco",
    "jonacatepec",
    "tepalcingo",
    "axochiapan",
    "huitzilac",
    "tres marias",
]

DEFAULT_BUFFER_METERS = 500
CONURBADO_BUFFER_METERS = 1000

AMBIGUOUS_COLONIA_NAMES = {
    "centro",
    "civac",
    "emiliano zapata",
    "jiutepec",
    "morelos",
    "temixco",
}

LOCATION_CONTEXT_PREFIXES = (
    "ampliacion",
    "barrio",
    "col",
    "colonia",
    "delegacion",
    "ejido",
    "fracc",
    "fraccionamiento",
    "localidad",
    "poblado",
    "privada",
    "pueblo",
    "unidad",
    "unidad habitacional",
)

# Prefijos compuestos con preposición "de": "poblado de X", "localidad de X"
# Se usan para dar bono de precisión en el scoring sin requerir que estén
# directamente antes del nombre (sin preposición).
GEO_COMPOUND_PREFIXES = (
    "poblado de",
    "localidad de",
    "pueblo de",
    "comunidad de",
)


# =============================================================================
# PALABRAS CLAVE Y HEURÍSTICAS
# =============================================================================

# Raíces para detectar violencia en texto normalizado
VIOLENT_STEMS = [
    "homicid",
    "asesin",
    "ejecut",
    "ultim",
    "balacer",
    "balaz",
    "balea",
    "dispar",
    "secuestr",
    "feminicid",
    "cadaver",
    "cuerpo",
    "sin vida",
    "hallan",
    "hallazg",
    "apunal",
    "arma de fuego",
    "muert",
    "violenc",
    "ataque armado",
]

# Señales de violencia intencional/criminal (subconjunto fuerte de VIOLENT_STEMS).
# Si el texto solo contiene stems débiles ("muert", "cuerpo", etc.) y además
# hay NEGATIVE_HINTS, probablemente es un accidente y lo descartamos.
STRONG_VIOLENT_STEMS = {
    "homicid",
    "asesin",
    "ejecut",
    "ultim",
    "balacer",
    "balaz",
    "balea",
    "dispar",
    "secuestr",
    "feminicid",
    "apunal",
    "arma de fuego",
    "ataque armado",
}

# Términos que suelen corresponder a accidentes / sucesos no violentos
NEGATIVE_HINTS = [
    "volcadura",
    "choque",
    "accidente",
    "motoneta",
    "trailer",
    "incendio",
    "caos vial",
    "atropell",
    "colision",
    "derrumbe",
    "fuga de gas",
    "cortocircuito",
    "violencia vial",
    "percance vial",
]

# Términos que indican nota judicial o de seguimiento (no un crimen nuevo).
# Un artículo con estos términos reporta sobre un proceso legal existente,
# no sobre un nuevo hecho violento.
JUDICIAL_STEMS = [
    "vinculan a proceso",
    "vinculado a proceso",
    "ratifican",
    "dictan sentencia",
    "sentenciaron",
    "no vinculacion a proceso",
    "vinculacion a proceso",
    "audiencia inicial",
    "medida cautelar",
]

# Términos que indican operativo policial, captura o actividad institucional.
# Estos artículos no reportan un nuevo crimen contra civiles.
OPERATIONAL_STEMS = [
    "imparte taller",
    "dia naranja",
    "narcotienda",
    "golpe al narcomenudeo",
    "golpe al narco",
    "caen con arsenal",
    "supervision de exhum",
    "exhumacion",
]


# =============================================================================
# UTILIDADES BÁSICAS
# =============================================================================

def load_json(path: Path, default: Any):
    """
    Carga JSON desde disco.
    Si no existe o falla, regresa `default`.
    """
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data: Any) -> None:
    """
    Guarda un objeto como JSON UTF-8 con indentación.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def stable_id(text: str) -> str:
    """
    Genera un ID estable a partir de texto.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def normalize_text(text: str | None) -> str:
    """
    Normaliza texto para matching:
    - quita acentos
    - pasa a minúsculas
    - elimina puntuación
    - colapsa espacios
    """
    text = text or ""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_url(url: str, base_url: str) -> str:
    """
    Convierte una URL relativa en absoluta.
    """
    if not url:
        return ""
    if url.startswith("http"):
        return url
    return base_url.rstrip("/") + "/" + url.lstrip("/")


def normalize_date_str(value: str | None) -> str | None:
    """
    Convierte múltiples formatos de fecha a YYYY-MM-DD.
    """
    if not value:
        return None

    value = str(value).strip()

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except Exception:
        pass

    for fmt in (
        "%b %d, %Y %I:%M %p",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(value[:25], fmt).strftime("%Y-%m-%d")
        except Exception:
            continue

    return None


# =============================================================================
# SELECCIÓN DE NOTAS
# =============================================================================

def first_n_unique_note_links(links, base_url: str, limit: int) -> list[tuple[str, str]]:
    """
    Toma nodos <a>, normaliza URLs, elimina duplicados
    y devuelve solo las primeras N notas.
    """
    selected: list[tuple[str, str]] = []
    seen: set[str] = set()

    for link in links:
        href = link.get("href", "")
        url = normalize_url(href, base_url)
        title = link.get_text(" ", strip=True)

        if not url or url in seen:
            continue
        if "/noticias/" not in url:
            continue

        seen.add(url)
        selected.append((url, title))

        if len(selected) >= limit:
            break

    return selected


# =============================================================================
# EXTRACCIÓN DE ARTÍCULO
# =============================================================================

def extract_article(url: str) -> dict[str, Any]:
    """
    Descarga una nota y extrae:
    - título
    - fecha publicada
    - cuerpo aproximado (primeros párrafos útiles)
    """
    response = requests.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    title = soup.title.get_text(" ", strip=True) if soup.title else ""

    published_at = None
    meta_candidates = [
        soup.find("meta", attrs={"property": "article:published_time"}),
        soup.find("meta", attrs={"name": "pubdate"}),
        soup.find("meta", attrs={"name": "publish-date"}),
        soup.find("meta", attrs={"itemprop": "datePublished"}),
    ]

    for tag in meta_candidates:
        if tag and tag.get("content"):
            published_at = tag.get("content")
            break

    if not published_at:
        time_tag = soup.find("time")
        if time_tag:
            published_at = time_tag.get("datetime") or time_tag.get_text(" ", strip=True)

    paragraphs: list[str] = []
    for selector in ["article p", ".field-items p", ".node p", "main p"]:
        found = [p.get_text(" ", strip=True) for p in soup.select(selector)]
        found = [p for p in found if len(p) > 40]
        if found:
            paragraphs = found
            break

    article_text = "\n".join([title, *paragraphs[:12]]).strip()

    return {
        "title": title,
        "text": article_text[:8000],
        "published_at": published_at,
    }


# =============================================================================
# DETECCIÓN DELITOS / HORA / ÁREA
# =============================================================================

def is_candidate_text(text: str) -> bool:
    """
    Decide si el texto contiene señales de violencia intencional/criminal.

    Lógica:
    1. Si hay términos de seguimiento judicial → rechazar.
    2. Si hay términos de operativo policiaco o actividad institucional → rechazar.
    3. Si no hay ningún stem violento → rechazar.
    4. Si hay NEGATIVE_HINTS (accidente, incendio, etc.) → solo aceptar si
       hay al menos un STRONG_VIOLENT_STEM (violencia intencional clara).
       Esto evita que muertes en accidentes ("muert", "cuerpo") pasen el filtro.
    5. En cualquier otro caso → aceptar.
    """
    t = normalize_text(text)

    # Descartar notas de seguimiento judicial (no es un crimen nuevo)
    if any(stem in t for stem in JUDICIAL_STEMS):
        return False

    # Descartar operativos policiales o actividades institucionales
    if any(stem in t for stem in OPERATIONAL_STEMS):
        return False

    if not any(stem in t for stem in VIOLENT_STEMS):
        return False

    if any(h in t for h in NEGATIVE_HINTS):
        return any(stem in t for stem in STRONG_VIOLENT_STEMS)

    return True


def detect_conurbado_area(text: str | None) -> str | None:
    """
    Busca municipios/zonas conurbadas en el texto.

    Antes de detectar un conurbado, verifica que el texto no mencione
    explícitamente un municipio fuera del área de interés. Esto evita
    falsos positivos como "colonia Emiliano Zapata, Cuautla" o eventos
    de Tepoztlán que se cuelen como si fueran del municipio Emiliano Zapata.

    Nota: este filtro solo aplica cuando el texto NO menciona Cuernavaca
    directamente (la detección de `es_en_cuernavaca` es independiente).
    """
    t = normalize_text(text)

    # Si el texto menciona un municipio excluido, descartamos el conurbado.
    # Un artículo de Cuautla que diga "colonia Emiliano Zapata" no debe
    # confundirse con el municipio conurbado Emiliano Zapata.
    for excl in MORELOS_EXCLUDED_MUNICIPALITIES:
        if excl in t:
            return None

    for needle, canonical in CONURBADO_AREAS.items():
        if needle in t:
            return canonical

    return None


def infer_delito(text: str) -> str:
    """
    Infere un tipo de delito aproximado usando reglas simples.
    """
    t = normalize_text(text)

    if "feminicid" in t:
        return "feminicidio"
    if "secuestr" in t:
        return "secuestro"
    if "asalto" in t and ("balaz" in t or "arma de fuego" in t or "balea" in t):
        return "asalto con violencia"
    if any(x in t for x in ["homicid", "asesin", "ejecut", "ultim", "sin vida", "muert"]):
        return "homicidio"
    if any(x in t for x in ["balacer", "balaz", "dispar", "ataque armado", "arma de fuego", "balea"]):
        return "ataque armado"

    return "violencia"


def extract_hour(text: str) -> str | None:
    """
    Busca una hora explícita tipo 18:02 o 6.30.
    Si no encuentra, intenta inferir una aproximada por frases.
    """
    # Horas tipo 18:02 o 18.02
    match = re.search(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b", text)
    if match:
        hh = int(match.group(1))
        mm = int(match.group(2))
        return f"{hh:02d}:{mm:02d}"

    t = normalize_text(text)

    # Heurísticas simples
    if "madrugada" in t:
        return "02:00"
    if "anoche" in t or "por la noche" in t or "durante la noche" in t:
        return "23:00"
    if "por la tarde" in t or "durante la tarde" in t:
        return "18:00"
    if "por la manana" in t or "durante la manana" in t:
        return "08:00"

    return None


# =============================================================================
# GAZETTEER Y GEOCODIFICACIÓN
# =============================================================================

def load_gazetteer() -> list[dict[str, Any]]:
    """
    Carga el catálogo local de colonias / municipios / aliases.
    """
    return load_json(GAZETTEER_PATH, [])


def build_gazetteer_index(
    gazetteer: list[dict[str, Any]],
) -> dict[str, tuple[str, list[float]]]:
    """
    Construye un índice normalizado nombre/alias → (canonical_name, coords)
    para búsquedas rápidas por nombre exacto.
    """
    index: dict[str, tuple[str, list[float]]] = {}
    for item in gazetteer:
        canonical = item.get("name")
        coords = item.get("coords")
        if not canonical or not isinstance(coords, list) or len(coords) != 2:
            continue
        for variant in [canonical, *(item.get("aliases") or [])]:
            key = normalize_text(variant)
            if key:
                index[key] = (canonical, coords)
    return index


def find_colonia_in_text(
    text_norm: str,
    gazetteer_index: dict[str, tuple[str, list[float]]],
) -> tuple[str | None, list[float] | None]:
    """
    Busca la palabra 'colonia' en el texto normalizado y toma las 1–3 palabras
    siguientes como nombre de colonia. Devuelve la primera coincidencia válida
    en el gazetteer (más larga primero).

    La primera aparición de 'colonia X' en el artículo suele ser el lugar
    del crimen; las siguientes mencionan hospitales u otras referencias.
    """
    words = text_norm.split()
    for i, word in enumerate(words):
        if word != "colonia":
            continue
        for length in (3, 2, 1):
            if i + 1 + length > len(words):
                continue
            candidate = " ".join(words[i + 1 : i + 1 + length])
            if candidate in gazetteer_index:
                canonical, coords = gazetteer_index[candidate]
                return canonical, coords
    return None, None


def get_settlement_prefixes(item: dict[str, Any]) -> tuple[str, ...]:
    settlement_type = normalize_text(item.get("settlement_type"))
    return SETTLEMENT_TYPE_PREFIXES.get(settlement_type, ())


def resolve_gazetteer_name(name: str | None, gazetteer: list[dict[str, Any]]) -> tuple[list[float] | None, str]:
    """
    Busca una entrada exacta por nombre o alias en el gazetteer.
    Ideal para municipios y zonas conurbadas.
    """
    if not name:
        return None, "none"

    target = normalize_text(name)

    for item in gazetteer:
        canonical = normalize_text(item.get("name"))
        aliases = [normalize_text(x) for x in item.get("aliases", [])]

        if target == canonical or target in aliases:
            coords = item.get("coords")
            if isinstance(coords, list) and len(coords) == 2:
                return coords, "gazetteer"

    return None, "none"


def find_best_gazetteer_match_in_text(
    text: str,
    gazetteer: list[dict[str, Any]],
    excluded_names: set[str] | None = None,
) -> tuple[str | None, list[float] | None, str]:
    """
    Busca la mejor coincidencia de colonia dentro del texto completo,
    usando nombres y aliases del gazetteer.

    Estrategia:
    - normaliza texto
    - busca matches exactos por frase
    - elige la coincidencia más larga
    - permite excluir municipios/zona conurbada para no confundirlos con colonias
    """
    text_norm = normalize_text(text)
    padded_text = f" {text_norm} "

    excluded_norm = {normalize_text(x) for x in (excluded_names or set())}

    best_name = None
    best_coords = None
    best_score = -1

    for item in gazetteer:
        canonical_name = item.get("name")
        canonical_norm = normalize_text(canonical_name)

        if canonical_norm in excluded_norm:
            continue

        variants = [canonical_name, *(item.get("aliases", []) or [])]
        prefixes = get_settlement_prefixes(item)

        for variant in variants:
            variant_norm = normalize_text(variant)
            if not variant_norm:
                continue

            # Match por frase completa en texto normalizado
            if f" {variant_norm} " in padded_text:
                # Si el nombre canónico O el alias en uso son ambiguos,
                # se requiere contexto explícito (ej. "colonia Morelos").
                # Esto evita que "Morelos" (alias de Unidad Habitacional Morelos)
                # coincida con "Policía Morelos" o "Jiutepec, Morelos".
                is_ambiguous = (
                    canonical_norm in AMBIGUOUS_COLONIA_NAMES
                    or variant_norm in AMBIGUOUS_COLONIA_NAMES
                )
                if is_ambiguous and not has_explicit_location_context(text_norm, variant_norm):
                    continue
                coords = item.get("coords")
                if isinstance(coords, list) and len(coords) == 2:
                    score = len(variant_norm)
                    if variant_norm == canonical_norm:
                        score += 10
                    # Bono por prefijo de tipo de asentamiento directo
                    # (ej. "colonia Lagunilla", "barrio San Miguel")
                    if prefixes:
                        for prefix in prefixes:
                            if re.search(rf"\b{re.escape(prefix)}\s+{re.escape(variant_norm)}\b", text_norm):
                                score += 25
                                break
                    # Bono por prefijo compuesto con preposición
                    # (ej. "poblado de Tejalpa", "localidad de Ahuatepec")
                    for cpfx in GEO_COMPOUND_PREFIXES:
                        if re.search(rf"\b{re.escape(cpfx)}\s+{re.escape(variant_norm)}\b", text_norm):
                            score += 25
                            break
                    if score > best_score:
                        best_name = canonical_name
                        best_coords = coords
                        best_score = score

    if best_name and best_coords:
        return best_name, best_coords, "gazetteer_text"

    return None, None, "none"


def has_explicit_location_context(text_norm: str, place_norm: str) -> bool:
    """
    Exige pistas como "colonia Morelos" para nombres demasiado ambiguos.
    """
    for prefix in LOCATION_CONTEXT_PREFIXES:
        pattern = rf"\b{re.escape(prefix)}\s+{re.escape(place_norm)}\b"
        if re.search(pattern, text_norm):
            return True

    # Caso útil para "Centro de Cuernavaca", pero evita aceptar "Morelos"
    # solo por referencia al estado.
    if place_norm == "centro" and re.search(r"\bcentro\s+de\s+cuernavaca\b", text_norm):
        return True

    return False


def nominatim_lookup(name: str, cache: dict[str, Any]) -> tuple[list[float] | None, str]:
    """
    Respaldo con Nominatim cuando una colonia concreta no aparece
    en el gazetteer local.
    """
    if not name:
        return None, "none"

    key = normalize_text(name)

    if key in cache and cache[key].get("coords"):
        return cache[key]["coords"], cache[key]["geo_confidence"]

    queries = [
        f"{name}, Cuernavaca, Morelos, Mexico",
        f"colonia {name}, Cuernavaca, Morelos, Mexico",
        f"{name}, Morelos, Mexico",
    ]

    def score_result(result: dict[str, Any]) -> int:
        display_norm = normalize_text(result.get("display_name"))
        result_type = normalize_text(result.get("type"))
        result_name = normalize_text(result.get("name"))
        address = result.get("address") or {}
        score = 0

        if "cuernavaca" in display_norm or normalize_text(address.get("city")) == "cuernavaca":
            score += 40
        if normalize_text(address.get("state")) == "morelos":
            score += 10
        if result_type in NOMINATIM_RESULT_TYPES:
            score += 25
        if result_name == key:
            score += 25
        elif key and key in result_name:
            score += 15

        importance = result.get("importance")
        if isinstance(importance, (int, float)):
            score += int(importance * 10)

        return score

    for query in queries:
        for bounded in (True, False):
            try:
                params = {
                    "q": query,
                    "format": "jsonv2",
                    "limit": 5,
                    "addressdetails": 1,
                    "countrycodes": "mx",
                    "dedupe": 1,
                }
                if bounded:
                    params["viewbox"] = NOMINATIM_VIEWBOX
                    params["bounded"] = 1

                response = requests.get(
                    NOMINATIM_URL,
                    params=params,
                    headers=HEADERS,
                    timeout=20,
                )
                response.raise_for_status()
                candidates = response.json()
            except Exception:
                candidates = []
            finally:
                time.sleep(1.1)

            if not isinstance(candidates, list):
                continue

            best = None
            best_score = -1
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                score = score_result(candidate)
                if score > best_score:
                    best = candidate
                    best_score = score

            if best and best_score >= 50:
                try:
                    coords = [float(best["lat"]), float(best["lon"])]
                except (KeyError, TypeError, ValueError):
                    coords = None

                if coords:
                    source = "nominatim_bounded" if bounded else "nominatim_context"
                    cache[key] = {"coords": coords, "geo_confidence": source}
                    return coords, source

    cache[key] = {"coords": None, "geo_confidence": "none"}
    return None, "none"


def resolve_location(
    colonia: str | None,
    gazetteer: list[dict[str, Any]],
    cache: dict[str, Any],
) -> tuple[list[float] | None, str]:
    """
    Resuelve una colonia usando:
    1. gazetteer local
    2. Nominatim
    """
    if not colonia:
        return None, "none"

    coords, source = resolve_gazetteer_name(colonia, gazetteer)
    if coords:
        return coords, source

    coords, source = nominatim_lookup(colonia, cache)
    if coords:
        return coords, source

    return None, "none"


# =============================================================================
# CLASIFICACIÓN DETERMINISTA
# =============================================================================

def validate_and_extract(title: str, article_text: str) -> dict[str, Any]:
    """
    Sustituto determinista de la antigua extracción con IA.

    Regresa un diccionario compatible con el resto del proyecto:
    {
      es_violento,
      es_en_cuernavaca,
      delito,
      hora_aprox,
      resumen,
      confidence
    }

    Aquí, `es_en_cuernavaca` debe entenderse como:
    "el hecho pertenece al área objetivo principal del proyecto"
    y se activa si el texto menciona Cuernavaca.
    Los conurbados y la colonia se detectan aparte en run_scraper().
    """
    combined_text = f"{title}\n{article_text}"
    text_norm = normalize_text(combined_text)

    es_violento = is_candidate_text(combined_text)
    es_en_cuernavaca = "cuernavaca" in text_norm
    delito = infer_delito(combined_text)
    hora_aprox = extract_hour(article_text)

    # Resumen simple: usar título limpio
    resumen = title.strip() if title else None

    # Confianza simple basada en señales
    confidence = 0.0
    if es_violento:
        confidence += 0.4
    if es_en_cuernavaca:
        confidence += 0.2
    if hora_aprox:
        confidence += 0.1
    if delito and delito != "violencia":
        confidence += 0.1

    confidence = min(1.0, round(confidence, 2))

    return {
        "es_violento": es_violento,
        "es_en_cuernavaca": es_en_cuernavaca,
        "delito": delito,
        "hora_aprox": hora_aprox,
        "resumen": resumen,
        "confidence": confidence,
    }


# =============================================================================
# UTILIDADES DE EVENTOS
# =============================================================================

def register_unresolved(event_stub: dict[str, Any]) -> None:
    """
    Guarda un caso no resuelto para revisión manual posterior.
    """
    unresolved = load_json(UNRESOLVED_PATH, [])
    key = event_stub.get("fuente") or event_stub.get("id")
    replaced = False

    if key:
        for idx, existing in enumerate(unresolved):
            existing_key = existing.get("fuente") or existing.get("id")
            if existing_key == key:
                unresolved[idx] = event_stub
                replaced = True
                break

    if not replaced:
        unresolved.append(event_stub)

    save_json(UNRESOLVED_PATH, unresolved)


def event_level(hour_text: str | None) -> int:
    """
    Asigna nivel inicial:
    - 6 si cae entre 22:00 y 06:00
    - 5 en otro caso o si no hay hora
    """
    if not hour_text:
        return 5

    match = re.match(r"^\s*(\d{1,2})", str(hour_text))
    if not match:
        return 5

    hour = int(match.group(1))
    return 6 if (hour >= 22 or hour < 6) else 5


def dedupe_group_id(delito: str | None, location_name: str | None, fecha: str | None) -> str:
    """
    ID de deduplicación por:
    - delito
    - ubicación efectiva (colonia o municipio)
    - fecha
    """
    payload = f"{normalize_text(delito)}|{normalize_text(location_name)}|{(fecha or '').strip()}"
    return stable_id(payload)


# =============================================================================
# PIPELINE PRINCIPAL
# =============================================================================

def run_scraper() -> None:
    """
    Flujo principal:
    - descarga primeras 12 notas
    - clasifica por reglas
    - resuelve ubicación
    - guarda eventos nuevos
    """
    print("🚀 OVICUE: iniciando scraping determinista...")

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    existing_events = load_json(EVENTS_PATH, [])
    geocode_cache = load_json(GEOCODE_CACHE_PATH, {})
    gazetteer = load_gazetteer()
    gazetteer_index = build_gazetteer_index(gazetteer)

    existing_urls = {e.get("fuente") for e in existing_events if e.get("fuente")}
    existing_groups = {e.get("dedupe_group_id") for e in existing_events if e.get("dedupe_group_id")}

    new_events: list[dict[str, Any]] = []

    for source in SOURCES:
        try:
            response = requests.get(source["url"], headers=HEADERS, timeout=20)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            links = soup.select(source["selector"])
            print(f"📊 {source['name']}: {len(links)} enlaces detectados")

            top_notes = first_n_unique_note_links(
                links=links,
                base_url=source["base_url"],
                limit=MAX_ARTICLES_PER_RUN,
            )
            print(f"🧾 Se procesarán solo las primeras {len(top_notes)} notas")

            for url, title in top_notes:
                if not url or url in existing_urls:
                    continue

                try:
                    article = extract_article(url)
                    if not article["text"]:
                        continue

                    # Clasificación determinista basada en keywords
                    extracted = validate_and_extract(
                        title=article["title"] or title,
                        article_text=article["text"],
                    )

                    if not extracted.get("es_violento"):
                        continue

                    full_text_for_scope = f"{title}\n{article['text']}"
                    conurbado = detect_conurbado_area(full_text_for_scope)
                    text_norm_full = normalize_text(full_text_for_scope)

                    # Si el texto menciona un municipio excluido y no menciona
                    # Cuernavaca ni ningún conurbado válido, descartar el evento.
                    if (
                        not extracted.get("es_en_cuernavaca")
                        and conurbado is None
                        and any(excl in text_norm_full for excl in MORELOS_EXCLUDED_MUNICIPALITIES)
                    ):
                        print(f"⚠️ Descartado: municipio excluido detectado sin área objetivo")
                        continue

                    # Algoritmo de ubicación en dos pasos:
                    # Paso 1: conurbado encontrado y NO se menciona Cuernavaca
                    #         → centroide del municipio conurbado.
                    # Paso 2: se menciona Cuernavaca (o no hay conurbado)
                    #         → buscar "colonia X" en el texto y resolver en gazetteer.
                    coords = None
                    geo_source = "none"
                    location_name = None
                    location_scope = "colonia"
                    buffer_meters = DEFAULT_BUFFER_METERS

                    if conurbado is not None and not extracted.get("es_en_cuernavaca"):
                        coords, geo_source = resolve_gazetteer_name(conurbado, gazetteer)
                        location_name = conurbado
                        location_scope = "municipio"
                        buffer_meters = CONURBADO_BUFFER_METERS
                    else:
                        colonia_name, colonia_coords = find_colonia_in_text(
                            text_norm_full, gazetteer_index
                        )
                        if colonia_name:
                            location_name = colonia_name
                            coords = colonia_coords
                            geo_source = "gazetteer_text"

                    if coords is None:
                        register_unresolved(
                            {
                                "id": stable_id(url),
                                "source_name": source["name"],
                                "source_title": title,
                                "fuente": url,
                                "resumen": extracted.get("resumen") or title,
                                "tipo_delito": extracted.get("delito") or "No especificado",
                                "hora": extracted.get("hora_aprox"),
                                "es_violento": True,
                                "es_en_cuernavaca": extracted.get("es_en_cuernavaca"),
                                "location_scope": location_scope,
                                "location_name": location_name,
                                "municipio_detectado": conurbado,
                                "geo_confidence": geo_source,
                                "extraction_confidence": extracted.get("confidence", 0.0),
                                "article_excerpt": article.get("text", "")[:2000],
                                "published_at": article.get("published_at"),
                                "scraped_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                            }
                        )
                        print(f"⚠️ Sin geocodificación para: {location_name!r}")
                        continue

                    fecha_evento = normalize_date_str(article.get("published_at")) or datetime.now().strftime("%Y-%m-%d")
                    delito = extracted.get("delito") or "No especificado"
                    hora_aprox = extracted.get("hora_aprox")
                    resumen = extracted.get("resumen") or title

                    group_id = dedupe_group_id(delito, location_name, fecha_evento)
                    if group_id in existing_groups:
                        print("ℹ️ Evento deduplicado por delito + ubicación + fecha")
                        continue

                    event = {
                        "id": stable_id(url),
                        "fecha": fecha_evento,
                        "hora": hora_aprox,
                        "municipio_detectado": conurbado,
                        "location_scope": location_scope,
                        "location_name": location_name,
                        "coordenadas": coords,
                        "buffer_meters": buffer_meters,
                        "tipo_delito": delito,
                        "nivel_inicial": event_level(hora_aprox),
                        "fuente": url,
                        "resumen": resumen,
                        "source_name": source["name"],
                        "source_title": title,
                        "published_at": article.get("published_at"),
                        "scraped_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                        "geo_confidence": geo_source,
                        "extraction_confidence": extracted.get("confidence", 0.0),
                        "dedupe_group_id": group_id,
                    }

                    print(f"✅ Evento nuevo: {title[:80]}")
                    new_events.append(event)
                    existing_urls.add(url)
                    existing_groups.add(group_id)

                except Exception as inner_exc:
                    print(f"⚠️ Error procesando nota {url}: {inner_exc}")

        except Exception as exc:
            print(f"❌ Error en fuente {source['name']}: {exc}")

    if new_events:
        save_json(EVENTS_PATH, existing_events + new_events)
        print(f"✅ Nuevos eventos guardados: {len(new_events)}")
    else:
        print("ℹ️ No se encontraron nuevos eventos válidos")

    save_json(GEOCODE_CACHE_PATH, geocode_cache)


# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================

if __name__ == "__main__":
    run_scraper()
