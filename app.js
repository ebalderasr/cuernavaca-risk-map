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

function getColor(level) {
  if (level === "rojo")     return "#dc2626";
  if (level === "naranja")  return "#f97316";
  if (level === "amarillo") return "#eab308";
  return "#eab308";
}

function levelLabel(level) {
  if (level === "rojo")     return "Muy peligroso";
  if (level === "naranja")  return "Peligroso";
  if (level === "amarillo") return "Peligro moderado";
  return "—";
}

function diasSinHechosText(dias) {
  if (dias === null || dias === undefined) return "";
  const n = Number(dias);
  if (isNaN(n)) return "";
  if (n === 0) return "Hecho violento hoy";
  if (n === 1) return "1 día sin hechos violentos";
  return `${n} días sin hechos violentos`;
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
              <strong>Muy peligroso</strong>
              <div>2 hechos violentos en menos de 3 días, o 3 o más hechos en la zona</div>
            </div>
          </div>

          <div class="legend-row">
            <span class="legend-dot legend-orange"></span>
            <div>
              <strong>Peligroso</strong>
              <div>Un hecho violento registrado recientemente</div>
            </div>
          </div>

          <div class="legend-row">
            <span class="legend-dot legend-yellow"></span>
            <div>
              <strong>Peligro moderado</strong>
              <div>Entre 30 y 60 días sin nuevos hechos en la zona</div>
            </div>
          </div>

          <div class="legend-row">
            <span class="legend-square"></span>
            <div>
              <strong>Zona histórica</strong>
              <div>Más de 60 días sin hechos; ya no se considera peligrosa</div>
            </div>
          </div>
        </div>
      </div>

      <div class="panel-section">
        <div class="panel-section-title">Cómo se calcula la peligrosidad</div>

        <div class="panel-note">
          <strong>Paso 1 — Primer hecho:</strong>
          Cuando se registra un hecho violento en una colonia, aparece una zona <span class="inline-dot inline-orange"></span> <strong>naranja</strong> (Peligroso) y comienza un contador de días.
        </div>

        <div class="panel-note">
          <strong>Paso 2 — Segundo hecho en 3 días:</strong>
          Si ocurre un segundo hecho dentro de los primeros 3 días, la zona escala a <span class="inline-dot inline-red"></span> <strong>rojo</strong> (Muy peligroso) y el contador se reinicia.
        </div>

        <div class="panel-note">
          <strong>Paso 3 — Hechos adicionales:</strong>
          Cada nuevo hecho en la misma zona mantiene el nivel rojo, reinicia el contador y amplía el diámetro de la zona en 50 m.
        </div>

        <div class="panel-note">
          <strong>Enfriamiento:</strong>
          Si pasan <strong>30 días</strong> sin hechos, la zona baja a <span class="inline-dot inline-yellow"></span> <strong>amarillo</strong> (Peligro moderado). Si pasan <strong>30 días más</strong> sin hechos, se convierte en un <span class="inline-square"></span> cuadrado negro de registro histórico.
        </div>

        <div class="panel-note panel-note-muted">
          Los datos provienen de notas periodísticas. La ubicación es aproximada (nivel colonia o municipio). No sustituye fuentes oficiales.
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
  const dias = props.dias_sin_hechos_violentos;

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
      <div style="font-size:16px;font-weight:700;margin-bottom:4px;color:#0f172a;">
        ${escapeHtml(levelLabel(props.level))}
      </div>
      <div style="font-size:12px;font-weight:600;color:#64748b;margin-bottom:8px;">
        ${escapeHtml(diasSinHechosText(dias))}
      </div>
      <div><strong>Zona:</strong> ${escapeHtml(props.location_name || "No disponible")}</div>
      <div><strong>Hechos registrados:</strong> ${escapeHtml(props.n_incidents)}</div>
      <div><strong>Radio:</strong> ${escapeHtml(props.radius_meters)} m</div>
      <div><strong>Delitos:</strong> ${joinList(props.delitos)}</div>
      <div style="margin-top:10px;">
        <strong>Fuentes:</strong>
        ${fuentesHtml}
      </div>
    </div>
  `;
}

function buildArchivedPopup(props) {
  const fuentes = Array.isArray(props.fuentes) ? props.fuentes : [];

  const fuentesHtml = fuentes.length
    ? fuentes.map((f) => {
        const title = escapeHtml((f && f.title) || "Fuente");
        const url = safeUrl((f && f.url) || "#");
        return `<div><a href="${url}" target="_blank" rel="noopener noreferrer">${title}</a></div>`;
      }).join("")
    : "<div>Sin fuentes enlazadas.</div>";

  return `
    <div style="min-width:240px;line-height:1.45;">
      <div style="font-size:15px;font-weight:700;margin-bottom:8px;color:#111827;">
        Zona histórica
      </div>
      <div><strong>Zona:</strong> ${escapeHtml(props.location_name || "No disponible")}</div>
      <div><strong>Hechos registrados:</strong> ${escapeHtml(props.n_incidents)}</div>
      <div><strong>Delitos:</strong> ${joinList(props.delitos)}</div>
      <div><strong>Último hecho:</strong> ${escapeHtml(props.last_incident_date || "No disponible")}</div>
      <div style="font-size:12px;color:#64748b;margin-top:4px;">
        ${escapeHtml(diasSinHechosText(props.dias_sin_hechos_violentos))}
      </div>
      <div style="margin-top:10px;">
        <strong>Fuentes:</strong>
        ${fuentesHtml}
      </div>
    </div>
  `;
}

function renderSelectedHot(props) {
  const fuentes = Array.isArray(props.fuentes) ? props.fuentes : [];
  const dias = props.dias_sin_hechos_violentos;

  selectedEl.innerHTML = `
    <div class="panel-section-title">Zona activa</div>

    <div class="selected-grid">
      <div class="selected-card">
        <div class="selected-label">Nivel</div>
        <div class="selected-big-value">${escapeHtml(levelLabel(props.level))}</div>
      </div>

      <div class="selected-card">
        <div class="selected-label">Contador</div>
        <div class="selected-value">${escapeHtml(diasSinHechosText(dias))}</div>
      </div>

      <div class="selected-card">
        <div class="selected-label">Zona</div>
        <div class="selected-text">${escapeHtml(props.location_name || "No disponible")}</div>
      </div>

      <div class="selected-card">
        <div class="selected-label">Hechos registrados</div>
        <div class="selected-value">${escapeHtml(props.n_incidents)}</div>
      </div>

      <div class="selected-card">
        <div class="selected-label">Radio de zona</div>
        <div class="selected-value">${escapeHtml(props.radius_meters)} m</div>
      </div>

      <div class="selected-card">
        <div class="selected-label">Primer hecho</div>
        <div class="selected-value">${escapeHtml(props.first_incident_date || "No disponible")}</div>
      </div>

      <div class="selected-card">
        <div class="selected-label">Último hecho</div>
        <div class="selected-value">${escapeHtml(props.last_incident_date || "No disponible")}</div>
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
  const fuentes = Array.isArray(props.fuentes) ? props.fuentes : [];

  selectedEl.innerHTML = `
    <div class="panel-section-title">Zona histórica</div>

    <div class="selected-grid">
      <div class="selected-card">
        <div class="selected-label">Zona</div>
        <div class="selected-value">${escapeHtml(props.location_name || "No disponible")}</div>
      </div>

      <div class="selected-card">
        <div class="selected-label">Hechos registrados</div>
        <div class="selected-value">${escapeHtml(props.n_incidents)}</div>
      </div>

      <div class="selected-card">
        <div class="selected-label">Delitos</div>
        <div class="selected-text">${joinList(props.delitos)}</div>
      </div>

      <div class="selected-card">
        <div class="selected-label">Último hecho</div>
        <div class="selected-value">${escapeHtml(props.last_incident_date || "No disponible")}</div>
      </div>

      <div class="selected-card">
        <div class="selected-label">Primer hecho</div>
        <div class="selected-value">${escapeHtml(props.first_incident_date || "No disponible")}</div>
      </div>

      <div class="selected-card">
        <div class="selected-label">Días sin hechos</div>
        <div class="selected-value">${escapeHtml(diasSinHechosText(props.dias_sin_hechos_violentos))}</div>
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

    // Calcular estadísticas
    const levelPriority = { rojo: 3, naranja: 2, amarillo: 1 };
    let nActivas = 0;
    let nAmarillas = 0;
    let maxPriority = 0;

    hotFeatures.forEach((feature) => {
      const level = (feature.properties || {}).level;
      if (level === "naranja" || level === "rojo") nActivas++;
      else if (level === "amarillo") nAmarillas++;
      maxPriority = Math.max(maxPriority, levelPriority[level] || 0);
    });

    const maxLevelLabel =
      maxPriority === 3 ? "Muy peligroso" :
      maxPriority === 2 ? "Peligroso" :
      maxPriority === 1 ? "Peligro moderado" : "—";

    summaryEl.innerHTML = [
      metricCard("Zonas activas", nActivas),
      metricCard("En vigilancia", nAmarillas),
      metricCard("Nivel máximo", maxLevelLabel),
      metricCard("Zonas históricas", archiveFeatures.length),
    ].join("");

    if (hotFeatures.length === 0 && archiveFeatures.length === 0) {
      statusEl.textContent = "No hay datos visibles en este momento.";
    } else if (hotFeatures.length === 0 && archiveFeatures.length > 0) {
      statusEl.textContent = "No hay zonas recientes activas. Solo se muestran zonas históricas.";
    } else {
      statusEl.textContent =
        `Datos cargados. ${nActivas} zona(s) activa(s), ${nAmarillas} en vigilancia, ${archiveFeatures.length} histórica(s).`;
    }

    let hotLayer = null;

    if (hotFeatures.length > 0) {
      hotLayer = L.geoJSON(hotData, {
        style: function (feature) {
          const level = (feature.properties || {}).level;
          return {
            fillColor: getColor(level),
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
      metricCard("Zonas activas", "—"),
      metricCard("En vigilancia", "—"),
      metricCard("Nivel máximo", "—"),
      metricCard("Zonas históricas", "—"),
    ].join("");
  });
