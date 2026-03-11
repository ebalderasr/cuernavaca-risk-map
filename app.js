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
    html: `
      <div style="
        width: 10px;
        height: 10px;
        background: #111111;
        border: 1px solid #000000;
        box-shadow: 0 0 0 1px rgba(255,255,255,0.45);
      "></div>
    `,
    iconSize: [10, 10],
    iconAnchor: [5, 5],
  });
}

function metricCard(label, value) {
  return `
    <div style="
      padding: 12px;
      border: 1px solid #e2e8f0;
      border-radius: 14px;
      background: #f8fafc;
    ">
      <div style="
        font-size: 12px;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: .06em;
        font-weight: 700;
      ">
        ${escapeHtml(label)}
      </div>
      <div style="
        margin-top: 6px;
        font-size: 22px;
        font-weight: 700;
        color: #0f172a;
      ">
        ${escapeHtml(value)}
      </div>
    </div>
  `;
}

// =============================================================================
// PANEL LATERAL
// =============================================================================

function ensurePanel() {
  let panel = document.getElementById("info-panel");
  if (panel) return panel;

  panel = document.createElement("aside");
  panel.id = "info-panel";
  panel.style.position = "absolute";
  panel.style.top = "16px";
  panel.style.left = "16px";
  panel.style.zIndex = "1000";
  panel.style.width = "380px";
  panel.style.maxWidth = "calc(100vw - 32px)";
  panel.style.maxHeight = "calc(100vh - 32px)";
  panel.style.overflowY = "auto";
  panel.style.background = "rgba(255,255,255,0.94)";
  panel.style.backdropFilter = "blur(12px)";
  panel.style.border = "1px solid rgba(15,23,42,0.08)";
  panel.style.borderRadius = "18px";
  panel.style.padding = "16px";
  panel.style.boxShadow = "0 16px 40px rgba(15,23,42,0.12)";
  panel.style.color = "#0f172a";
  panel.style.fontFamily = "Inter, system-ui, sans-serif";

  document.body.appendChild(panel);
  return panel;
}

const infoPanel = ensurePanel();

infoPanel.innerHTML = `
  <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;">
    <div>
      <div style="
        font-size:12px;
        letter-spacing:.14em;
        text-transform:uppercase;
        font-weight:700;
        color:#2563eb;
        margin-bottom:6px;
      ">
        OVICUE
      </div>
      <h1 style="
        margin:0;
        font-size:18px;
        line-height:1.15;
        color:#0f172a;
      ">
        Observatorio de Violencia e Incidencia en Cuernavaca
      </h1>
    </div>
    <div style="
      font-size:12px;
      padding:6px 10px;
      border-radius:999px;
      background:#eff6ff;
      color:#1d4ed8;
      border:1px solid #bfdbfe;
    ">
      Beta
    </div>
  </div>

  <p style="
    margin:12px 0 0;
    color:#475569;
    font-size:14px;
    line-height:1.5;
  ">
    Visualización aproximada de reportes periodísticos recientes de violencia con ubicación referencial.
  </p>

  <div id="panel-status" style="
    margin-top:12px;
    font-size:13px;
    color:#475569;
  ">
    Cargando datos…
  </div>

  <div id="panel-summary" style="
    margin-top:14px;
    display:grid;
    grid-template-columns:1fr 1fr;
    gap:10px;
  "></div>

  <div style="
    margin-top:16px;
    padding-top:14px;
    border-top:1px solid #e2e8f0;
  ">
    <div style="
      font-size:12px;
      font-weight:700;
      letter-spacing:.08em;
      text-transform:uppercase;
      color:#64748b;
      margin-bottom:8px;
    ">
      Leyenda
    </div>

    <div style="display:grid;gap:8px;">
      <div style="display:flex;align-items:center;gap:10px;">
        <span style="width:12px;height:12px;border-radius:999px;background:#dc2626;display:inline-block;"></span>
        <span style="font-size:14px;color:#334155;">Nivel 7–10 · Crítico</span>
      </div>
      <div style="display:flex;align-items:center;gap:10px;">
        <span style="width:12px;height:12px;border-radius:999px;background:#f97316;display:inline-block;"></span>
        <span style="font-size:14px;color:#334155;">Nivel 4–6 · Riesgo</span>
      </div>
      <div style="display:flex;align-items:center;gap:10px;">
        <span style="width:12px;height:12px;border-radius:999px;background:#eab308;display:inline-block;"></span>
        <span style="font-size:14px;color:#334155;">Nivel 1–3 · Precaución</span>
      </div>
      <div style="display:flex;align-items:center;gap:10px;">
        <span style="width:10px;height:10px;background:#111111;display:inline-block;border:1px solid #000;"></span>
        <span style="font-size:14px;color:#334155;">Evento archivado</span>
      </div>
    </div>
  </div>

  <div id="panel-selected" style="
    margin-top:16px;
    padding-top:14px;
    border-top:1px solid #e2e8f0;
  ">
    <div style="
      font-size:12px;
      font-weight:700;
      letter-spacing:.08em;
      text-transform:uppercase;
      color:#64748b;
      margin-bottom:8px;
    ">
      Selección
    </div>
    <div style="
      font-size:14px;
      color:#64748b;
      line-height:1.5;
    ">
      Haz click en una zona o en un evento archivado para ver detalles.
    </div>
  </div>

  <div style="
    margin-top:16px;
    padding-top:14px;
    border-top:1px solid #e2e8f0;
    font-size:12px;
    line-height:1.5;
    color:#64748b;
  ">
    Este mapa es informativo. Se basa en notas periodísticas y geolocalización aproximada. No sustituye fuentes oficiales.
  </div>
`;

const statusEl = document.getElementById("panel-status");
const summaryEl = document.getElementById("panel-summary");
const selectedEl = document.getElementById("panel-selected");

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
    <div style="
      font-size:12px;
      font-weight:700;
      letter-spacing:.08em;
      text-transform:uppercase;
      color:#64748b;
      margin-bottom:8px;
    ">
      Zona activa
    </div>

    <div style="display:grid;gap:10px;">
      <div style="padding:12px;border:1px solid #e2e8f0;border-radius:14px;background:#fff;">
        <div style="font-size:14px;color:#64748b;">Nivel final</div>
        <div style="font-size:28px;font-weight:800;color:#0f172a;margin-top:4px;">
          ${escapeHtml(props.nivel)}
        </div>
      </div>

      <div style="padding:12px;border:1px solid #e2e8f0;border-radius:14px;background:#fff;">
        <div style="font-size:14px;color:#64748b;">Eventos activos</div>
        <div style="font-size:22px;font-weight:700;color:#0f172a;margin-top:4px;">
          ${escapeHtml(props.n_eventos)}
        </div>
      </div>

      <div style="padding:12px;border:1px solid #e2e8f0;border-radius:14px;background:#fff;">
        <div style="font-size:14px;color:#64748b;">Colonias</div>
        <div style="margin-top:6px;font-size:14px;line-height:1.5;color:#0f172a;">
          ${joinList(props.colonias)}
        </div>
      </div>

      <div style="padding:12px;border:1px solid #e2e8f0;border-radius:14px;background:#fff;">
        <div style="font-size:14px;color:#64748b;">Municipios</div>
        <div style="margin-top:6px;font-size:14px;line-height:1.5;color:#0f172a;">
          ${joinList(props.municipios, "No aplica")}
        </div>
      </div>

      <div style="padding:12px;border:1px solid #e2e8f0;border-radius:14px;background:#fff;">
        <div style="font-size:14px;color:#64748b;">Delitos</div>
        <div style="margin-top:6px;font-size:14px;line-height:1.5;color:#0f172a;">
          ${joinList(props.delitos)}
        </div>
      </div>

      <div style="padding:12px;border:1px solid #e2e8f0;border-radius:14px;background:#fff;">
        <div style="font-size:14px;color:#64748b;">Fuentes</div>
        <div style="margin-top:6px;font-size:14px;line-height:1.6;">
          ${
            fuentes.length
              ? fuentes.map((f) => {
                  const title = escapeHtml((f && f.title) || "Fuente");
                  const url = safeUrl((f && f.url) || "#");
                  return `<div><a href="${url}" target="_blank" rel="noopener noreferrer">${title}</a></div>`;
                }).join("")
              : '<span style="color:#64748b;">Sin fuentes enlazadas.</span>'
          }
        </div>
      </div>
    </div>
  `;
}

function renderSelectedArchived(props) {
  selectedEl.innerHTML = `
    <div style="
      font-size:12px;
      font-weight:700;
      letter-spacing:.08em;
      text-transform:uppercase;
      color:#64748b;
      margin-bottom:8px;
    ">
      Evento archivado
    </div>

    <div style="display:grid;gap:10px;">
      <div style="padding:12px;border:1px solid #e2e8f0;border-radius:14px;background:#fff;">
        <div style="font-size:14px;color:#64748b;">Ubicación</div>
        <div style="font-size:20px;font-weight:700;color:#0f172a;margin-top:4px;">
          ${escapeHtml(props.location_name || props.colonia || "No disponible")}
        </div>
      </div>

      <div style="padding:12px;border:1px solid #e2e8f0;border-radius:14px;background:#fff;">
        <div style="font-size:14px;color:#64748b;">Ámbito</div>
        <div style="font-size:16px;font-weight:600;color:#0f172a;margin-top:4px;">
          ${escapeHtml(props.location_scope || "No disponible")}
        </div>
      </div>

      <div style="padding:12px;border:1px solid #e2e8f0;border-radius:14px;background:#fff;">
        <div style="font-size:14px;color:#64748b;">Delito</div>
        <div style="font-size:16px;font-weight:600;color:#0f172a;margin-top:4px;">
          ${escapeHtml(props.tipo_delito || "No disponible")}
        </div>
      </div>

      <div style="padding:12px;border:1px solid #e2e8f0;border-radius:14px;background:#fff;">
        <div style="font-size:14px;color:#64748b;">Fecha</div>
        <div style="font-size:16px;font-weight:600;color:#0f172a;margin-top:4px;">
          ${escapeHtml(props.fecha || "No disponible")}
        </div>
      </div>

      <div style="padding:12px;border:1px solid #e2e8f0;border-radius:14px;background:#fff;">
        <div style="font-size:14px;color:#64748b;">Resumen</div>
        <div style="margin-top:6px;font-size:14px;line-height:1.5;color:#0f172a;">
          ${escapeHtml(props.resumen || "Sin resumen")}
        </div>
      </div>

      <div style="padding:12px;border:1px solid #e2e8f0;border-radius:14px;background:#fff;">
        <div style="font-size:14px;color:#64748b;">Fuente</div>
        <div style="margin-top:6px;font-size:14px;line-height:1.6;">
          ${
            props.fuente
              ? `<a href="${safeUrl(props.fuente)}" target="_blank" rel="noopener noreferrer">Abrir fuente</a>`
              : '<span style="color:#64748b;">Sin fuente</span>'
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

    // -------------------------------------------------------------------------
    // Resumen general
    // -------------------------------------------------------------------------
    let maxNivel = 0;
    let totalEventosHot = 0;
    const coloniasSet = new Set();
    const municipiosSet = new Set();

    hotFeatures.forEach((feature) => {
      const p = feature.properties || {};
      maxNivel = Math.max(maxNivel, Number(p.nivel || 0));
      totalEventosHot += Number(p.n_eventos || 0);

      (p.colonias || []).forEach((c) => coloniasSet.add(c));
      (p.municipios || []).forEach((m) => municipiosSet.add(m));
    });

    summaryEl.innerHTML = [
      metricCard("Zonas activas", hotFeatures.length),
      metricCard("Nivel máximo", maxNivel),
      metricCard("Eventos activos", totalEventosHot),
      metricCard("Archivados", archiveFeatures.length),
    ].join("");

    if (hotFeatures.length === 0 && archiveFeatures.length === 0) {
      statusEl.textContent = "No hay datos visibles en este momento.";
    } else if (hotFeatures.length === 0 && archiveFeatures.length > 0) {
      statusEl.textContent = "No hay zonas activas. Solo se muestran eventos archivados.";
    } else {
      statusEl.textContent =
        `Datos cargados correctamente. ${hotFeatures.length} zonas activas y ${archiveFeatures.length} eventos archivados.`;
    }

    // -------------------------------------------------------------------------
    // Capa caliente
    // -------------------------------------------------------------------------
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

    // -------------------------------------------------------------------------
    // Capa archivada
    // -------------------------------------------------------------------------
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
          });
        },
      }).addTo(map);
    }

    // -------------------------------------------------------------------------
    // Ajuste automático del mapa
    // -------------------------------------------------------------------------
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
      metricCard("Nivel máximo", "—"),
      metricCard("Eventos activos", "—"),
      metricCard("Archivados", "—"),
    ].join("");
  });