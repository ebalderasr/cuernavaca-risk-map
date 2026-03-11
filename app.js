const map = L.map("map", {
  zoomControl: false,
}).setView([18.9218, -99.2347], 13);

L.control.zoom({ position: "bottomright" }).addTo(map);

L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
  attribution: "&copy; OpenStreetMap &copy; CARTO",
}).addTo(map);

// =============================================================================
// HELPERS
// =============================================================================

function getColor(nivel) {
  return nivel >= 7 ? "#dc2626" :
         nivel >= 4 ? "#f97316" :
                      "#eab308";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function joinList(items, fallback = "No disponible") {
  if (!Array.isArray(items) || items.length === 0) return fallback;
  return items.map((x) => escapeHtml(x)).join(", ");
}

function safeUrl(url) {
  try {
    return new URL(url).toString();
  } catch {
    return "#";
  }
}

function archivedSquareIcon() {
  return L.divIcon({
    className: "",
    html: `<div class="archived-square-marker"></div>`,
    iconSize: [10, 10],
    iconAnchor: [5, 5],
  });
}

function metricCard(label, value) {
  return `
    <div class="metric-card">
      <div class="metric-label">${escapeHtml(label)}</div>
      <div class="metric-value">${escapeHtml(value)}</div>
    </div>
  `;
}

function isMobileViewport() {
  return window.matchMedia("(max-width: 768px)").matches;
}

// =============================================================================
// PANEL LATERAL
// =============================================================================

function ensurePanel() {
  let panel = document.getElementById("info-panel");
  if (panel) return panel;

  panel = document.createElement("aside");
  panel.id = "info-panel";
  panel.className = isMobileViewport() ? "panel-collapsed" : "";
  panel.innerHTML = `
    <div class="panel-header">
      <div class="panel-header-text">
        <div class="panel-eyebrow">OVICUE</div>
        <h1 class="panel-title">Observatorio de Violencia e Incidencia en Cuernavaca</h1>
      </div>

      <div class="panel-header-actions">
        <span class="panel-badge">Beta</span>
        <button id="panel-collapse-btn" class="panel-icon-btn" type="button" aria-label="Minimizar panel" title="Minimizar panel">—</button>
        <button id="panel-hide-btn" class="panel-icon-btn" type="button" aria-label="Ocultar panel" title="Ocultar panel">✕</button>
      </div>
    </div>

    <div id="panel-body" class="panel-body">
      <p class="panel-lead">
        Visualización aproximada de reportes periodísticos recientes de violencia con ubicación referencial.
      </p>

      <div id="panel-status" class="panel-status">Cargando datos…</div>

      <div id="panel-summary" class="panel-summary"></div>

      <div class="panel-section">
        <div class="panel-section-title">Leyenda</div>

        <div class="legend-card">
          <div class="legend-row">
            <span class="legend-dot legend-red"></span>
            <div>
              <strong>Nivel 7–10</strong>
              <div>Incidencia reciente alta</div>
            </div>
          </div>

          <div class="legend-row">
            <span class="legend-dot legend-orange"></span>
            <div>
              <strong>Nivel 4–6</strong>
              <div>Incidencia reciente media</div>
            </div>
          </div>

          <div class="legend-row">
            <span class="legend-dot legend-yellow"></span>
            <div>
              <strong>Nivel 1–3</strong>
              <div>Incidencia reciente baja</div>
            </div>
          </div>

          <div class="legend-row">
            <span class="legend-square"></span>
            <div>
              <strong>Evento archivado</strong>
              <div>Hecho histórico que ya no forma parte del “calor” actual</div>
            </div>
          </div>
        </div>
      </div>

      <div class="panel-section">
        <div class="panel-section-title">Cómo leer el mapa</div>
        <div class="panel-note">
          <strong>Marcas de color:</strong> representan zonas activas construidas a partir de eventos recientes que aún conservan peso temporal.
        </div>
        <div class="panel-note">
          <strong>Cuadrados negros:</strong> representan eventos archivados. Se conservan como memoria histórica, pero ya no cuentan como incidencia reciente.
        </div>
      </div>

      <div id="panel-selected" class="panel-section">
        <div class="panel-section-title">Selección</div>
        <div class="panel-note">
          Haz click en una zona o en un evento archivado para ver detalles.
        </div>
      </div>

      <div class="panel-footer-note">
        Este mapa es informativo. Se basa en notas periodísticas y geolocalización aproximada. No sustituye fuentes oficiales.
      </div>
    </div>
  `;

  document.body.appendChild(panel);
  return panel;
}

function ensurePanelFab() {
  let fab = document.getElementById("panel-fab");
  if (fab) return fab;

  fab = document.createElement("button");
  fab.id = "panel-fab";
  fab.type = "button";
  fab.className = "panel-fab hidden";
  fab.setAttribute("aria-label", "Mostrar panel de información");
  fab.title = "Mostrar información";
  fab.textContent = "ℹ";
  document.body.appendChild(fab);
  return fab;
}

const infoPanel = ensurePanel();
const panelFab = ensurePanelFab();

const panelBody = document.getElementById("panel-body");
const statusEl = document.getElementById("panel-status");
const summaryEl = document.getElementById("panel-summary");
const selectedEl = document.getElementById("panel-selected");
const collapseBtn = document.getElementById("panel-collapse-btn");
const hideBtn = document.getElementById("panel-hide-btn");

function collapsePanel() {
  infoPanel.classList.add("panel-collapsed");
}

function expandPanel() {
  infoPanel.classList.remove("panel-collapsed");
  infoPanel.classList.remove("panel-hidden");
  panelFab.classList.add("hidden");
}

function hidePanel() {
  infoPanel.classList.add("panel-hidden");
  panelFab.classList.remove("hidden");
}

function toggleCollapsePanel() {
  if (infoPanel.classList.contains("panel-collapsed")) {
    expandPanel();
  } else {
    collapsePanel();
  }
}

collapseBtn.addEventListener("click", () => {
  toggleCollapsePanel();
});

hideBtn.addEventListener("click", () => {
  hidePanel();
});

panelFab.addEventListener("click", () => {
  expandPanel();
});

window.addEventListener("resize", () => {
  if (isMobileViewport()) {
    if (!infoPanel.classList.contains("panel-hidden")) {
      infoPanel.classList.add("panel-collapsed");
    }
  }
});

// =============================================================================
// POPUPS Y PANEL DE DETALLE
// =============================================================================

function buildHotPopup(props) {
  const fuentes = Array.isArray(props.fuentes) ? props.fuentes : [];

  const fuentesHtml = fuentes.length
    ? `<ul style="padding-left:18px;margin:8px 0 0;">
        ${fuentes.map((f) => {
          const title = escapeHtml((f && f.title) || "Fuente");
          const url = safeUrl((f && f.url) || "#");
          return `<li><a href="${url}" target="_blank" rel="noopener noreferrer">${title}</a></li>`;
        }).join("")}
      </ul>`
    : "<div>Sin fuentes enlazadas.</div>";

  return `
    <div style="min-width:240px;line-height:1.45;">
      <div style="font-size:16px;font-weight:700;margin-bottom:8px;color:#0f172a;">
        Nivel ${escapeHtml(props.nivel)}
      </div>
      <div><strong>Eventos activos:</strong> ${escapeHtml(props.n_eventos)}</div>
      <div><strong>Eventos ≥ 5:</strong> ${escapeHtml(props.n_eventos_ge5)}</div>
      <div><strong>Colonias:</strong> ${joinList(props.colonias)}</div>
      <div><strong>Municipios:</strong> ${joinList(props.municipios, "No aplica")}</div>
      <div><strong>Delitos:</strong> ${joinList(props.delitos)}</div>
      <div style="margin-top:8px;color:#475569;">
        ${escapeHtml(props.info || "")}
      </div>
      <div style="margin-top:10px;">
        <strong>Fuentes:</strong>
        ${fuentesHtml}
      </div>
    </div>
  `;
}

function buildArchivedPopup(props) {
  return `
    <div style="min-width:240px;line-height:1.45;">
      <div style="font-size:15px;font-weight:700;margin-bottom:8px;color:#111827;">
        Evento archivado
      </div>
      <div><strong>Ubicación:</strong> ${escapeHtml(props.location_name || props.colonia || "No disponible")}</div>
      <div><strong>Ámbito:</strong> ${escapeHtml(props.location_scope || "No disponible")}</div>
      <div><strong>Tipo:</strong> ${escapeHtml(props.tipo_delito || "No disponible")}</div>
      <div><strong>Fecha:</strong> ${escapeHtml(props.fecha || "No disponible")}</div>
      <div style="margin-top:8px;color:#475569;">
        ${escapeHtml(props.resumen || "")}
      </div>
      <div style="margin-top:10px;">
        ${
          props.fuente
            ? `<a href="${safeUrl(props.fuente)}" target="_blank" rel="noopener noreferrer">Abrir fuente</a>`
            : "<span>Sin fuente</span>"
        }
      </div>
    </div>
  `;
}

function renderSelectedHot(props) {
  const fuentes = Array.isArray(props.fuentes) ? props.fuentes : [];

  selectedEl.innerHTML = `
    <div class="panel-section-title">Zona activa</div>

    <div class="selected-grid">
      <div class="selected-card">
        <div class="selected-label">Nivel final</div>
        <div class="selected-big-value">${escapeHtml(props.nivel)}</div>
      </div>

      <div class="selected-card">
        <div class="selected-label">Eventos activos</div>
        <div class="selected-value">${escapeHtml(props.n_eventos)}</div>
      </div>

      <div class="selected-card">
        <div class="selected-label">Colonias</div>
        <div class="selected-text">${joinList(props.colonias)}</div>
      </div>

      <div class="selected-card">
        <div class="selected-label">Municipios</div>
        <div class="selected-text">${joinList(props.municipios, "No aplica")}</div>
      </div>

      <div class="selected-card">
        <div class="selected-label">Delitos</div>
        <div class="selected-text">${joinList(props.delitos)}</div>
      </div>

      <div class="selected-card">
        <div class="selected-label">Fuentes</div>
        <div class="selected-text">
          ${
            fuentes.length
              ? fuentes.map((f) => {
                  const title = escapeHtml((f && f.title) || "Fuente");
                  const url = safeUrl((f && f.url) || "#");
                  return `<div><a href="${url}" target="_blank" rel="noopener noreferrer">${title}</a></div>`;
                }).join("")
              : '<span class="muted-text">Sin fuentes enlazadas.</span>'
          }
        </div>
      </div>
    </div>
  `;
}

function renderSelectedArchived(props) {
  selectedEl.innerHTML = `
    <div class="panel-section-title">Evento archivado</div>

    <div class="selected-grid">
      <div class="selected-card">
        <div class="selected-label">Ubicación</div>
        <div class="selected-value">${escapeHtml(props.location_name || props.colonia || "No disponible")}</div>
      </div>

      <div class="selected-card">
        <div class="selected-label">Ámbito</div>
        <div class="selected-value">${escapeHtml(props.location_scope || "No disponible")}</div>
      </div>

      <div class="selected-card">
        <div class="selected-label">Delito</div>
        <div class="selected-value">${escapeHtml(props.tipo_delito || "No disponible")}</div>
      </div>

      <div class="selected-card">
        <div class="selected-label">Fecha</div>
        <div class="selected-value">${escapeHtml(props.fecha || "No disponible")}</div>
      </div>

      <div class="selected-card">
        <div class="selected-label">Resumen</div>
        <div class="selected-text">${escapeHtml(props.resumen || "Sin resumen")}</div>
      </div>

      <div class="selected-card">
        <div class="selected-label">Fuente</div>
        <div class="selected-text">
          ${
            props.fuente
              ? `<a href="${safeUrl(props.fuente)}" target="_blank" rel="noopener noreferrer">Abrir fuente</a>`
              : '<span class="muted-text">Sin fuente</span>'
          }
        </div>
      </div>
    </div>
  `;
}

// =============================================================================
// CARGA DE DATOS
// =============================================================================

Promise.all([
  fetch(`data/map_layers.json?v=${Date.now()}`, { cache: "no-store" }).then((r) => {
    if (!r.ok) throw new Error(`Hot layer HTTP ${r.status}`);
    return r.json();
  }),
  fetch(`data/archive_points.json?v=${Date.now()}`, { cache: "no-store" }).then((r) => {
    if (!r.ok) throw new Error(`Archive layer HTTP ${r.status}`);
    return r.json();
  }),
])
  .then(([hotData, archiveData]) => {
    const hotFeatures = Array.isArray(hotData.features) ? hotData.features : [];
    const archiveFeatures = Array.isArray(archiveData.features) ? archiveData.features : [];

    let maxNivel = 0;
    let totalEventosHot = 0;

    hotFeatures.forEach((feature) => {
      const p = feature.properties || {};
      maxNivel = Math.max(maxNivel, Number(p.nivel || 0));
      totalEventosHot += Number(p.n_eventos || 0);
    });

    summaryEl.innerHTML = [
      metricCard("Zonas recientes", hotFeatures.length),
      metricCard("Nivel máximo", maxNivel),
      metricCard("Eventos recientes", totalEventosHot),
      metricCard("Archivados", archiveFeatures.length),
    ].join("");

    if (hotFeatures.length === 0 && archiveFeatures.length === 0) {
      statusEl.textContent = "No hay datos visibles en este momento.";
    } else if (hotFeatures.length === 0 && archiveFeatures.length > 0) {
      statusEl.textContent = "No hay zonas recientes activas. Solo se muestran eventos archivados.";
    } else {
      statusEl.textContent =
        `Datos cargados correctamente. ${hotFeatures.length} zonas recientes y ${archiveFeatures.length} eventos archivados.`;
    }

    let hotLayer = null;

    if (hotFeatures.length > 0) {
      hotLayer = L.geoJSON(hotData, {
        style: function (feature) {
          const nivel = feature.properties.nivel || 0;
          return {
            fillColor: getColor(nivel),
            weight: 1,
            opacity: 1,
            color: "#ffffff",
            fillOpacity: 0.62,
          };
        },
        onEachFeature: function (feature, layer) {
          const props = feature.properties || {};
          layer.bindPopup(buildHotPopup(props), { maxWidth: 340 });

          layer.on("click", () => {
            renderSelectedHot(props);
            if (isMobileViewport()) infoPanel.classList.add("panel-collapsed");
          });

          layer.on("mouseover", () => {
            layer.setStyle({
              weight: 2,
              fillOpacity: 0.78,
            });
          });

          layer.on("mouseout", () => {
            if (hotLayer) hotLayer.resetStyle(layer);
          });
        },
      }).addTo(map);
    }

    let archiveLayer = null;

    if (archiveFeatures.length > 0) {
      archiveLayer = L.geoJSON(archiveData, {
        pointToLayer: function (feature, latlng) {
          return L.marker(latlng, {
            icon: archivedSquareIcon(),
          });
        },
        onEachFeature: function (feature, layer) {
          const props = feature.properties || {};
          layer.bindPopup(buildArchivedPopup(props), { maxWidth: 320 });

          layer.on("click", () => {
            renderSelectedArchived(props);
            if (isMobileViewport()) infoPanel.classList.add("panel-collapsed");
          });
        },
      }).addTo(map);
    }

    let bounds = null;

    if (hotLayer && hotLayer.getBounds && hotLayer.getBounds().isValid()) {
      bounds = hotLayer.getBounds();
    }

    if (archiveLayer) {
      const archiveBounds = archiveLayer.getBounds();
      if (archiveBounds.isValid()) {
        bounds = bounds ? bounds.extend(archiveBounds) : archiveBounds;
      }
    }

    if (bounds && bounds.isValid()) {
      map.fitBounds(bounds, { padding: [24, 24] });
    }
  })
  .catch((error) => {
    console.error("Error cargando capas del mapa:", error);

    statusEl.textContent = "No se pudieron cargar los datos del mapa.";
    summaryEl.innerHTML = [
      metricCard("Zonas recientes", "—"),
      metricCard("Nivel máximo", "—"),
      metricCard("Eventos recientes", "—"),
      metricCard("Archivados", "—"),
    ].join("");
  });