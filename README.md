# OVICUE  
## Observatorio de Violencia e Incidencia en Cuernavaca

OVICUE es una aplicación web estática de visualización geoespacial que muestra **zonas de incidencia reciente de hechos violentos reportados por la prensa** en Cuernavaca, Morelos.

Su objetivo es ofrecer una **herramienta informativa y exploratoria** para observar patrones espaciales aproximados de reportes periodísticos recientes, sin pretender sustituir fuentes oficiales, investigación de campo, peritajes, denuncias formales o sistemas institucionales de seguridad pública.

---

## Estado del proyecto

**Beta pública**  
El proyecto se encuentra en desarrollo activo y su metodología puede cambiar conforme se mejore la calidad del pipeline, la georreferenciación, el filtrado de notas y la presentación visual de resultados.

---

## ¿Qué hace la app?

OVICUE toma notas periodísticas recientes sobre hechos violentos ocurridos en Cuernavaca, extrae información estructurada, estima una ubicación referencial a nivel de colonia y genera una visualización espacial de intensidad reciente.

La aplicación:

- consulta automáticamente una fuente periodística configurada,
- identifica notas candidatas relacionadas con violencia,
- usa extracción asistida por IA para clasificar y estructurar los datos,
- georreferencia la colonia mencionada,
- asigna un nivel inicial de incidencia,
- aplica un decaimiento temporal,
- construye una capa geoespacial agregada,
- y publica el resultado como un mapa interactivo.

Además del flujo automático, el administrador puede agregar **notas manuales** al sistema para corregir o complementar eventos no capturados por el scraper.

---

## Qué **no** hace la app

OVICUE **no**:

- representa estadísticas oficiales de criminalidad,
- muestra ubicaciones exactas de víctimas, domicilios o escenas del hecho,
- verifica judicialmente la verdad de cada nota,
- sustituye reportes a autoridades o servicios de emergencia,
- produce predicción criminal individual,
- ni debe usarse como base única para decisiones de seguridad, inversión, movilidad o reputación territorial.

---

## Metodología general

### 1. Fuente de información
La app consulta notas periodísticas de la sección de seguridad de una fuente configurada, actualmente:

- **Diario de Morelos**  
  `https://www.diariodemorelos.com/noticias/categories/sos`

### 2. Selección de notas candidatas
El sistema filtra encabezados usando raíces léxicas y términos asociados con violencia, por ejemplo:

- `homicid`
- `asesin`
- `ejecut`
- `balacer`
- `dispar`
- `secuestr`
- `feminicid`
- `sin vida`
- `hallazg`
- `cadaver`
- `muert`

Este filtro inicial sirve para reducir ruido y limitar el número de notas enviadas al paso de extracción estructurada.

### 3. Clasificación y extracción asistida por IA
Las notas candidatas se procesan con un modelo de IA para responder preguntas estructuradas como:

- si el hecho es violento,
- si ocurrió en Cuernavaca,
- tipo de delito aproximado,
- colonia mencionada,
- hora aproximada,
- resumen breve.

La IA **no se considera fuente primaria de verdad**, sino una herramienta de apoyo para estructurar datos de notas periodísticas.

### 4. Georreferenciación
La app intenta resolver la colonia mencionada mediante este orden:

1. un catálogo local de colonias (`colonias_cuernavaca.json`),
2. caché local de geocodificación,
3. geocodificación externa cuando es necesario.

Si una colonia no puede resolverse de forma razonable, el evento puede quedar fuera del mapa o almacenarse para revisión manual. El sistema está diseñado para **evitar coordenadas inventadas por defecto**.

### 5. Asignación de nivel inicial
Cada evento recibe un nivel inicial base:

- **5** por defecto,
- **6** si el evento ocurrió entre las **22:00 y las 06:00**.

### 6. Decaimiento temporal
El nivel disminuye con el tiempo usando una regla simple:

```text
nivel_actual = max(0, nivel_inicial - floor(días_transcurridos / 30))
````

Esto permite que eventos antiguos pierdan peso progresivamente hasta desaparecer de la visualización activa.

### 7. Agregación espacial

Cada evento se convierte en un buffer de **500 metros** y se proyecta a un sistema métrico adecuado para la zona.

Después, la app construye una **grilla regular** sobre el área cubierta por los eventos y calcula, para cada celda:

* nivel final,
* número de eventos activos,
* número de eventos de mayor intensidad,
* colonias relacionadas,
* delitos relacionados,
* fuentes visibles en el popup.

La “sinergia” espacial se aproxima por celda, elevando el nivel cuando múltiples eventos intensos convergen en la misma zona.

---

## Arquitectura del proyecto

OVICUE usa una arquitectura **serverless / flat-data**, diseñada para minimizar costos y complejidad operativa.

### Frontend

* HTML
* CSS
* JavaScript
* Leaflet.js

### Procesamiento

* Python
* GeoPandas
* Shapely
* Pandas
* NumPy

### Automatización

* GitHub Actions

### Publicación

* GitHub Pages

### Datos

* `data/events.json` → eventos capturados automáticamente
* `data/manual_events.json` → eventos agregados manualmente
* `data/map_layers.json` → capa geoespacial final que consume el frontend
* `data/colonias_cuernavaca.json` → catálogo local de colonias y alias
* `data/geocode_cache.json` → caché local de geocodificación
* `data/unresolved_events.json` → eventos no resueltos o pendientes de revisión

---

## Flujo diario de actualización

El mapa se actualiza automáticamente mediante GitHub Actions.

### Pipeline

1. el workflow se ejecuta diariamente,
2. corre `scripts/scraper.py`,
3. actualiza `events.json` y la caché de geocodificación,
4. corre `scripts/logic.py`,
5. genera un nuevo `map_layers.json`,
6. y publica los cambios en el repositorio.

### Flujo manual

El administrador también puede agregar una nota manualmente mediante:

```bash
python scripts/add_manual_note.py "URL_DE_LA_NOTA"
python scripts/logic.py
```

---

## Estructura del repositorio

```text
.
├── .github/
│   └── workflows/
│       └── update.yml
├── data/
│   ├── colonias_cuernavaca.json
│   ├── events.json
│   ├── geocode_cache.json
│   ├── manual_events.json
│   ├── map_layers.json
│   └── unresolved_events.json
├── scripts/
│   ├── add_manual_note.py
│   ├── logic.py
│   └── scraper.py
├── app.js
├── index.html
├── style.css
├── README.md
└── LICENSE
```

---

## Ejecución local

### 1. Crear entorno virtual

```bash
python -m venv venv
source venv/bin/activate
```

### 2. Instalar dependencias

```bash
pip install pandas numpy requests beautifulsoup4 google-genai geopy geopandas shapely pyproj
```

### 3. Configurar variable de entorno

```bash
export GOOGLE_API_KEY="TU_API_KEY"
```

### 4. Correr pipeline

```bash
python scripts/scraper.py
python scripts/logic.py
python -m http.server 8000
```

Luego abre:

```text
http://localhost:8000
```

---

## Limitaciones metodológicas

OVICUE tiene limitaciones importantes que deben entenderse antes de interpretar el mapa:

1. **Sesgo de fuente**
   El mapa depende de lo que publica un medio concreto. No representa todos los hechos ocurridos ni todos los reportados oficialmente.

2. **Sesgo de cobertura periodística**
   Hay colonias, tipos de hecho o contextos que pueden recibir más o menos cobertura mediática.

3. **Georreferenciación aproximada**
   La ubicación corresponde normalmente a una colonia o referencia general, no al punto real del evento.

4. **Clasificación imperfecta**
   El pipeline puede cometer errores al filtrar, clasificar o resumir notas.

5. **Temporalidad simplificada**
   El modelo de decaimiento es una regla operativa, no una validación criminológica exhaustiva.

6. **No equivale a riesgo real**
   La visualización debe entenderse como una representación aproximada de **intensidad reciente de reportes periodísticos**, no como una medición definitiva de peligrosidad.

---

## Aviso legal y de responsabilidad

### Naturaleza informativa

OVICUE es una herramienta de visualización informativa y experimental basada en fuentes periodísticas de acceso público y procesamiento automatizado.

### No oficialidad

OVICUE **no es una fuente oficial de seguridad pública** y no sustituye la información emitida por autoridades, fiscalías, instancias municipales, estatales o federales, ni por el Secretariado Ejecutivo del Sistema Nacional de Seguridad Pública.

### No exactitud garantizada

Aunque se realizan esfuerzos razonables para estructurar y visualizar los datos de manera consistente, **no se garantiza la exactitud, integridad, actualidad, exhaustividad o precisión geográfica** de la información mostrada.

### Sin imputación individual

La app no tiene por objeto imputar responsabilidad penal, civil o administrativa a persona alguna, ni afirmar hechos jurídicamente probados. La información visualizada deriva de reportes periodísticos y procesos automatizados de extracción y agregación.

### Sin uso para emergencia

OVICUE **no debe utilizarse para atención de emergencias** ni como sustituto de llamadas a servicios de emergencia, denuncia formal o contacto con autoridades competentes.

### Sin garantía de aptitud para decisiones

Los desarrolladores y administradores no asumen responsabilidad por decisiones personales, comerciales, patrimoniales, territoriales, de movilidad, reputación o seguridad tomadas con base exclusiva o principal en esta herramienta.

### Ubicación aproximada y protección de terceros

La plataforma emplea ubicaciones aproximadas y agregación espacial deliberada con el fin de reducir precisión puntual y evitar exposición innecesaria de víctimas, domicilios o terceros.

### Correcciones y retiro

Si una nota, geolocalización o representación requiere corrección, revisión o retiro, el proyecto podrá modificar, reclasificar o eliminar registros cuando resulte procedente.

---

## Privacidad y datos sensibles

OVICUE busca evitar la publicación de datos personales sensibles o ubicaciones puntuales exactas.
La aplicación está diseñada para mostrar información agregada o referencial a nivel de zona/celda, y no para exponer datos privados de víctimas, testigos o domicilios particulares.

Si detectas contenido sensible, información errónea o una representación que deba corregirse, se recomienda solicitar revisión mediante el canal de contacto del proyecto.

---

## Propiedad intelectual y fuentes

Las notas periodísticas enlazadas pertenecen a sus respectivos medios y autores.
OVICUE **no reproduce íntegramente** el contenido de las notas como producto principal, sino que enlaza la fuente original y usa metadatos o resúmenes operativos para fines de visualización e investigación aplicada.

Todas las marcas, nombres comerciales y contenidos enlazados pertenecen a sus titulares respectivos.

---

## Gobernanza editorial

Los eventos pueden entrar al mapa por dos rutas:

1. **Automática**
   Cuando son detectados y estructurados por el pipeline.

2. **Manual**
   Cuando el administrador los agrega directamente para corrección, validación o incorporación puntual.

La existencia de revisión manual no implica validación forense o judicial del hecho, sino curaduría operativa del dataset.

---

## Roadmap

Líneas de mejora previstas:

* ampliar y depurar catálogo de colonias,
* fortalecer deduplicación temporal y espacial,
* mejorar el diseño del frontend,
* añadir metadata de actualización visible,
* incorporar más fuentes,
* refinar el modelo de extracción y clasificación,
* documentar mejor trazabilidad y métricas de calidad del pipeline.

---

## Contacto

**Administrador / responsable del proyecto:**
Emiliano Balderas Ramírez

---

## Licencia

Este repositorio se distribuye bajo la licencia incluida en `LICENSE`.

---

## Descargo final

El uso de este repositorio, del sitio publicado y de sus datos implica la aceptación de que se trata de una herramienta informativa, experimental y no oficial, basada en agregación automatizada de reportes periodísticos con geolocalización aproximada.
