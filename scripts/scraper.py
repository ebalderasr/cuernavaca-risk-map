from __future__ import annotations

import hashlib
import json
import os
import re
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup
from geopy.exc import GeocoderTimedOut
from geopy.geocoders import Nominatim
from google import genai

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
EVENTS_PATH = DATA_DIR / "events.json"
GEOCODE_CACHE_PATH = DATA_DIR / "geocode_cache.json"
GAZETTEER_PATH = DATA_DIR / "colonias_cuernavaca.json"
UNRESOLVED_PATH = DATA_DIR / "unresolved_events.json"

API_KEY = os.environ.get("GOOGLE_API_KEY")
if not API_KEY:
    raise RuntimeError("Falta GOOGLE_API_KEY en variables de entorno")

client = genai.Client(api_key=API_KEY)
GEMINI_MODEL = "models/gemini-2.5-flash"

HEADERS = {
    "User-Agent": "OVICUE/0.3 (academic civic project; contacto local)"
}

geolocator = Nominatim(user_agent="ovicue/0.3-academic-project")

SOURCES = [
    {
        "name": "Diario de Morelos",
        "url": "https://www.diariodemorelos.com/noticias/categories/sos",
        "selector": 'h3 a[href*="/noticias/"]',
        "base_url": "https://www.diariodemorelos.com",
    }
]

# Raíces / stems: más tolerantes a género, número y conjugación.
STEM_PATTERNS = [
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
    "apuñal",
    "arma de fuego",
    "muert",
    "violenc",
]

# Términos que suelen meter ruido; NO bloquean solos, solo ayudan a priorizar.
NOISE_HINTS = [
    "volcadura",
    "choque",
    "accidente",
    "motoneta",
    "trailer",
    "incendio",
    "caos vial",
]


def load_json(path: Path, default: Any):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def stable_id(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def normalize_text(text: str | None) -> str:
    text = text or ""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_url(url: str, base_url: str) -> str:
    if not url:
        return ""
    if url.startswith("http"):
        return url
    return base_url.rstrip("/") + "/" + url.lstrip("/")


def is_candidate_title(title: str) -> bool:
    t = normalize_text(title)
    return any(stem in t for stem in STEM_PATTERNS)


def looks_mostly_noise(title: str) -> bool:
    t = normalize_text(title)
    return any(hint in t for hint in NOISE_HINTS)


def extract_json_object(raw_text: str) -> dict[str, Any]:
    if not raw_text:
        return {}

    text = raw_text.strip()
    text = text.replace("```json", "").replace("```", "").strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)

    if not match:
        return {}

    try:
        return json.loads(match.group(0))
    except Exception:
        return {}


def normalize_date_str(value: str | None) -> str | None:
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


def extract_article(url: str) -> dict[str, Any]:
    response = requests.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    title = ""
    if soup.title:
        title = soup.title.get_text(" ", strip=True)

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

    paragraphs = []
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


def validate_and_extract(title: str, article_text: str) -> dict[str, Any]:
    prompt = f"""
Analiza la siguiente nota periodística y responde ÚNICAMENTE con un objeto JSON válido.

Objetivo:
- Identificar si es un hecho violento relevante para un mapa cívico basado en prensa.
- Confirmar si ocurrió en Cuernavaca.
- Extraer colonia, hora aproximada y un resumen breve.
- Si falta algo, usa null.
- confidence debe ser un número entre 0 y 1.

JSON esperado:
{{
  "es_violento": true,
  "es_en_cuernavaca": true,
  "delito": "homicidio",
  "colonia": "Nueva Jerusalen",
  "hora_aprox": "18:02",
  "resumen": "Joven asesinada localizada en zona boscosa",
  "confidence": 0.91
}}

Título:
{title}

Texto:
{article_text}
""".strip()

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        data = extract_json_object(response.text)

        data.setdefault("es_violento", False)
        data.setdefault("es_en_cuernavaca", False)
        data.setdefault("delito", None)
        data.setdefault("colonia", None)
        data.setdefault("hora_aprox", None)
        data.setdefault("resumen", None)
        data.setdefault("confidence", 0.0)

        return data
    except Exception as e:
        print(f"⚠️ Error en IA: {e}")
        return {
            "es_violento": False,
            "es_en_cuernavaca": False,
            "delito": None,
            "colonia": None,
            "hora_aprox": None,
            "resumen": None,
            "confidence": 0.0,
        }


def load_gazetteer() -> list[dict[str, Any]]:
    return load_json(GAZETTEER_PATH, [])


def gazetteer_lookup(colonia: str, gazetteer: list[dict[str, Any]]) -> tuple[list[float] | None, str]:
    target = normalize_text(colonia)
    if not target:
        return None, "none"

    for item in gazetteer:
        name = normalize_text(item.get("name"))
        aliases = [normalize_text(x) for x in item.get("aliases", [])]
        if target == name or target in aliases:
            coords = item.get("coords")
            if isinstance(coords, list) and len(coords) == 2:
                return coords, "gazetteer"

    return None, "none"


def nominatim_lookup(colonia: str, cache: dict[str, Any]) -> tuple[list[float] | None, str]:
    if not colonia:
        return None, "none"

    key = normalize_text(colonia)
    if key in cache:
        return cache[key]["coords"], cache[key]["geo_confidence"]

    query = f"{colonia}, Cuernavaca, Morelos, Mexico"

    try:
        location = geolocator.geocode(query, timeout=10)
        time.sleep(1.1)

        if location:
            coords = [location.latitude, location.longitude]
            cache[key] = {"coords": coords, "geo_confidence": "nominatim"}
            return coords, "nominatim"

        cache[key] = {"coords": None, "geo_confidence": "none"}
        return None, "none"

    except (GeocoderTimedOut, Exception):
        cache[key] = {"coords": None, "geo_confidence": "none"}
        return None, "none"


def resolve_location(colonia: str | None, gazetteer: list[dict[str, Any]], cache: dict[str, Any]) -> tuple[list[float] | None, str]:
    if not colonia:
        return None, "none"

    coords, source = gazetteer_lookup(colonia, gazetteer)
    if coords:
        return coords, source

    coords, source = nominatim_lookup(colonia, cache)
    if coords:
        return coords, source

    return None, "none"


def register_unresolved(event_stub: dict[str, Any]) -> None:
    unresolved = load_json(UNRESOLVED_PATH, [])
    unresolved.append(event_stub)
    save_json(UNRESOLVED_PATH, unresolved)


def event_level(hour_text: str | None) -> int:
    if not hour_text:
        return 5

    match = re.match(r"^\s*(\d{1,2})", str(hour_text))
    if not match:
        return 5

    hour = int(match.group(1))
    return 6 if (hour >= 22 or hour < 6) else 5


def dedupe_group_id(delito: str | None, colonia: str | None, fecha: str | None) -> str:
    payload = f"{normalize_text(delito)}|{normalize_text(colonia)}|{(fecha or '').strip()}"
    return stable_id(payload)


def run_scraper() -> None:
    print("🚀 OVICUE: iniciando scraping...")

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    existing_events = load_json(EVENTS_PATH, [])
    geocode_cache = load_json(GEOCODE_CACHE_PATH, {})
    gazetteer = load_gazetteer()

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

            for link in links:
                href = link.get("href", "")
                url = normalize_url(href, source["base_url"])
                title = link.get_text(" ", strip=True)

                if not url or url in existing_urls:
                    continue

                if not is_candidate_title(title):
                    continue

                print(f"🎯 Candidata: {title[:100]}")
                if looks_mostly_noise(title):
                    print("   · título potencialmente ruidoso, pasa a IA de todos modos")

                try:
                    article = extract_article(url)
                    if not article["text"]:
                        continue

                    extracted = validate_and_extract(
                        title=article["title"] or title,
                        article_text=article["text"],
                    )

                    if not extracted.get("es_violento"):
                        continue
                    if not extracted.get("es_en_cuernavaca"):
                        continue

                    colonia = extracted.get("colonia")
                    coords, geo_source = resolve_location(colonia, gazetteer, geocode_cache)

                    if coords is None:
                        register_unresolved(
                            {
                                "source_name": source["name"],
                                "source_title": title,
                                "fuente": url,
                                "colonia": colonia,
                                "published_at": article.get("published_at"),
                                "scraped_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                            }
                        )
                        print(f"⚠️ Sin geocodificación confiable para: {colonia!r}. Se manda a unresolved_events.json")
                        continue

                    fecha_evento = normalize_date_str(article.get("published_at")) or datetime.now().strftime("%Y-%m-%d")
                    delito = extracted.get("delito") or "No especificado"
                    hora_aprox = extracted.get("hora_aprox")
                    resumen = extracted.get("resumen") or title

                    group_id = dedupe_group_id(delito, colonia, fecha_evento)
                    if group_id in existing_groups:
                        print("ℹ️ Evento deduplicado por delito + colonia + fecha")
                        continue

                    event = {
                        "id": stable_id(url),
                        "fecha": fecha_evento,
                        "hora": hora_aprox,
                        "colonia": colonia,
                        "coordenadas": coords,
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


if __name__ == "__main__":
    run_scraper()