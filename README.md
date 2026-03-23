<div align="center">

# OVICUE

### Observatory of Violence and Incident Reporting in Cuernavaca

<br>

**[→ Open the live map](https://ebalderasr.github.io/cuernavaca-risk-map/)**

<br>

[![Status](https://img.shields.io/badge/Status-Public_Beta-orange?style=for-the-badge)]()
[![License](https://img.shields.io/badge/License-See_LICENSE-blue?style=for-the-badge)](./LICENSE)
[![Data Source](https://img.shields.io/badge/Source-Diario_de_Morelos-555555?style=for-the-badge)]()

</div>

---

## What is OVICUE?

OVICUE is a static, serverless web application that aggregates and maps **recent violent incident reports published by local press** in Cuernavaca, Morelos, Mexico.

> **This project does not generate, produce, or verify information.**
> It collects publicly available news articles and visualizes their geographic content on an interactive map. All underlying data comes from third-party journalism sources.

The goal is to provide an **informative and exploratory tool** for observing approximate spatial patterns in recent press coverage — not to replace official sources, field investigations, legal proceedings, or public safety institutions.

---

## Why it matters

Cuernavaca lacks publicly accessible, neighborhood-level visualizations of press-reported security incidents. OVICUE fills that gap by:

- transforming unstructured news text into structured, mappable data,
- applying transparent spatial and temporal weighting,
- publishing results as a freely accessible interactive map.

This gives residents, researchers, and journalists a low-cost reference layer for situational awareness based on what the press is already reporting.

---

## How it works

### 1. News collection
A Python scraper fetches headlines from the security section of a configured press source:

- **Diario de Morelos** — `https://www.diariodemorelos.com/noticias/categories/sos`

### 2. Candidate filtering
Headlines are filtered using lexical roots associated with violent incidents (e.g., `homicid`, `balacer`, `feminicid`, `hallazg`, `cadaver`). This reduces noise before structured extraction.

### 3. AI-assisted structured extraction
Candidate articles are processed by an AI model that extracts:

| Field | Description |
|-------|-------------|
| Incident type | Approximate crime category |
| Location | Neighborhood (*colonia*) mentioned |
| Time | Approximate time of day |
| Summary | Brief description |

> The AI model is a processing aid, not a source of truth. It structures information already present in the news article.

### 4. Geocoding
The mentioned neighborhood is resolved using:
1. A local catalog of Cuernavaca *colonias* (`colonias_cuernavaca.json`)
2. An optional polygon layer of official colonia boundaries (`colonias_cuernavaca_polygons.geojson`)
3. A local geocoding cache
4. External geocoding as a fallback

If a location cannot be resolved reliably, the event is excluded from the map or held for manual review. **Coordinates are never invented.**

### 5. Temporal weighting & decay
Each event receives an initial severity level (default: **5**, or **6** if it occurred between 22:00–06:00). This level decays over time:

```
current_level = max(0, initial_level - floor(days_elapsed / 30))
```

Events gradually lose weight until they disappear from the active visualization.

### 6. Spatial aggregation
Each event is buffered to **500 meters** and projected into a metric coordinate system. A regular grid is built over the covered area; each cell aggregates:

- final level
- active event count
- high-intensity event count
- related *colonias* and crime types
- source links

If official colonia polygons are available, the map can render the colonia boundary directly instead of an approximate circular buffer.

---

## Tech stack

**Frontend**

![HTML5](https://img.shields.io/badge/HTML5-E34F26?style=flat-square&logo=html5&logoColor=white)
![CSS3](https://img.shields.io/badge/CSS3-1572B6?style=flat-square&logo=css3&logoColor=white)
![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?style=flat-square&logo=javascript&logoColor=black)
![Leaflet](https://img.shields.io/badge/Leaflet.js-199900?style=flat-square&logo=leaflet&logoColor=white)

**Data pipeline**

![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)
![GeoPandas](https://img.shields.io/badge/GeoPandas-139C5A?style=flat-square&logo=python&logoColor=white)
![Pandas](https://img.shields.io/badge/Pandas-150458?style=flat-square&logo=pandas&logoColor=white)
![NumPy](https://img.shields.io/badge/NumPy-013243?style=flat-square&logo=numpy&logoColor=white)
![Shapely](https://img.shields.io/badge/Shapely-2C7BB6?style=flat-square&logo=python&logoColor=white)

**Automation & publishing**

![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?style=flat-square&logo=githubactions&logoColor=white)
![GitHub Pages](https://img.shields.io/badge/GitHub_Pages-222222?style=flat-square&logo=github&logoColor=white)

---

## Architecture

OVICUE uses a **flat-data / serverless** architecture — no backend server, no database. All data lives as static JSON files committed to the repository and served via GitHub Pages.

```text
.
├── .github/workflows/update.yml     ← Daily automation (GitHub Actions)
├── data/
│   ├── events.json                  ← Automatically captured events
│   ├── manual_events.json           ← Manually curated events
│   ├── map_layers.json              ← Final geospatial layer (consumed by frontend)
│   ├── colonias_cuernavaca.json     ← Local neighborhood catalog
│   ├── colonias_cuernavaca_polygons.geojson ← Optional official colonia polygons
│   ├── geocode_cache.json           ← Geocoding cache
│   └── unresolved_events.json       ← Events pending review
├── scripts/
│   ├── scraper.py                   ← News scraper + extractor
│   ├── logic.py                     ← Spatial aggregation pipeline
│   ├── import_colonias_geojson.py   ← Import official colonia polygons / centroids
│   └── add_manual_note.py           ← Manual event ingestion
├── app.js
├── index.html
├── style.css
└── LICENSE
```

---

## Daily update pipeline

The map updates automatically via GitHub Actions:

1. Workflow triggers daily
2. `scripts/scraper.py` runs → updates `events.json` and geocoding cache
3. `scripts/logic.py` runs → generates a new `map_layers.json`
4. Changes are committed and published to GitHub Pages

### Manual ingestion

An administrator can also add a note manually:

```bash
python scripts/add_manual_note.py "ARTICLE_URL"
python scripts/logic.py
```

---

## Local setup

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install pandas numpy requests beautifulsoup4 google-genai geopy geopandas shapely pyproj

# 3. Set API key
export GOOGLE_API_KEY="YOUR_API_KEY"

# 4. Run pipeline and serve
python scripts/scraper.py
python scripts/logic.py
python -m http.server 8000
# Open: http://localhost:8000
```

### Importing official colonia geometry

If you obtain an official or curated GeoJSON of Cuernavaca colonias, you can import it with:

```bash
python scripts/import_colonias_geojson.py /path/to/colonias.geojson
python scripts/logic.py
```

---

## Known limitations

| Limitation | Description |
|------------|-------------|
| **Source bias** | The map reflects what a single outlet publishes — not all incidents, nor all official records |
| **Coverage bias** | Some neighborhoods or crime types receive more media attention than others |
| **Approximate location** | Coordinates correspond to a neighborhood centroid, not the exact incident location |
| **Imperfect classification** | The pipeline may misclassify or miss some articles |
| **Simplified temporality** | The decay model is an operational heuristic, not a criminological model |
| **Not a risk score** | The visualization represents **intensity of recent press coverage**, not actual danger |

---

## Legal disclaimer

### Nature of this project

OVICUE is an **informational and experimental visualization tool**. It collects publicly available news articles and maps their geographic content. **It does not produce, generate, verify, or validate any information** — all data originates from third-party journalism sources that are publicly accessible.

### Not an official source

OVICUE is **not affiliated with** and does not substitute information from public security authorities, prosecutors (*fiscalías*), municipal or state governments, or the *Secretariado Ejecutivo del Sistema Nacional de Seguridad Pública (SESNSP)*.

### No accuracy guarantee

While reasonable efforts are made to structure and present data consistently, **no guarantee is made regarding accuracy, completeness, timeliness, or geographic precision** of the displayed information.

### No individual imputation

This application does not impute criminal, civil, or administrative liability to any person. Visualized information derives from press reports and automated extraction and aggregation processes.

### Not for emergencies

**OVICUE must not be used for emergency response.** In any emergency, contact the appropriate authorities directly (911 or equivalent).

### No liability for decisions

The developers and administrators assume no responsibility for personal, commercial, property, mobility, or safety decisions made based solely or primarily on this tool.

### Privacy and approximate location

The platform deliberately uses approximate locations and spatial aggregation to reduce point-level precision and minimize unnecessary exposure of victims, addresses, or third parties.

### Corrections and takedowns

If a specific report, geolocation, or representation requires correction or removal, the project may modify, reclassify, or delete records when appropriate. Contact the project administrator to request a review.

---

## Intellectual property

Linked news articles belong to their respective outlets and authors. OVICUE **does not reproduce article content in full** as its primary output — it links to original sources and uses operational summaries and metadata for visualization and applied research purposes. All trademarks and linked content belong to their respective owners.

---

## Contact

**Project administrator:** Emiliano Balderas Ramírez
- GitHub: [@ebalderasr](https://github.com/ebalderasr)
- Email: [ebalderas@live.com.mx](mailto:ebalderas@live.com.mx)

---

<div align="center"><i>OVICUE visualizes what the press reports — it does not create, verify, or certify any information.</i></div>
