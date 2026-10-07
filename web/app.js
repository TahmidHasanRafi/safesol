// SafeSol frontend. All science runs in the API (src/compute); this file only draws and asks.

const $ = (s) => document.querySelector(s);
const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const api = (path) => new URL(`api/${path}`, window.location.href).href;
const ROVER_FIELDS = ["mass_kg", "speed_m_s", "slope_limit_deg", "base_power_w", "energy_per_sol_wh", "drive_hours_per_sol"];
const EMPTY = { type: "FeatureCollection", features: [] };
const BLANK_PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABpfZFQAAAAABJRU5ErkJggg=="; // 1x1 fully transparent

const state = {
  meta: null, shelters: [], storms: [],
  route: [], drawing: false, analysis: null, contingency: null,
  chart: null, stormShown: false, busy: false,
};
let map;

// ---------- formatting ----------
const km = (m) => `${(m / 1000).toFixed(2)} km`;
const pct = (v) => `${Math.round(v * 100)}%`;
const wh = (v) => (v >= 10000 ? `${(v / 1000).toFixed(1)} kWh` : `${Math.round(v)} Wh`);
function duration(s) {
  if (!Number.isFinite(s)) return "unreachable";
  if (s < 3600) return `${Math.max(1, Math.round(s / 60))} min`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ${Math.round((s % 3600) / 60)} min`;
  return `${Math.floor(s / 86400)} d ${Math.round((s % 86400) / 3600)} h`;
}
const line = (coords) => ({ type: "Feature", geometry: { type: "LineString", coordinates: coords }, properties: {} });
const point = (c, props = {}) => ({ type: "Feature", geometry: { type: "Point", coordinates: c }, properties: props });
const fc = (features) => ({ type: "FeatureCollection", features });
const setData = (id, data) => map.getSource(id) && map.getSource(id).setData(data);

// ---------- API ----------
async function getJSON(path) {
  const r = await fetch(api(path));
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}
async function postJSON(path, body) {
  const r = await fetch(api(path), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) {
    const detail = await r.json().catch(() => ({}));
    throw new Error(detail.detail ? JSON.stringify(detail.detail) : `${path}: ${r.status}`);
  }
  return r.json();
}

function readRover() {
  const o = {};
  for (const k of ROVER_FIELDS) o[k] = parseFloat($(`#${k}`).value);
  return o;
}
function applyPreset(name) {
  for (const [k, v] of Object.entries(state.meta.presets[name])) $(`#${k}`).value = v;
}
const spacing = () => Math.max(5, parseFloat($("#spacing").value) || 25);
const hazardUrl = () => api(`overlay/hazard.png?limit=${readRover().slope_limit_deg}`);

// ---------- map ----------
function initMap() {
  const corners = state.meta.corners_lonlat;
  const lons = corners.map((c) => c[0]);
  const lats = corners.map((c) => c[1]);
  const bounds = [[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]];
  const pad = (Math.max(...lons) - Math.min(...lons)) * 0.3;

  map = new maplibregl.Map({
    container: "map",
    style: { version: 8, sources: {}, layers: [{ id: "bg", type: "background", paint: { "background-color": "#2b211b" } }] },
    bounds, fitBoundsOptions: { padding: 20 },
    maxBounds: [[bounds[0][0] - pad, bounds[0][1] - pad], [bounds[1][0] + pad, bounds[1][1] + pad]],
    doubleClickZoom: false, dragRotate: false, pitchWithRotate: false, attributionControl: false,
  });
  map.touchZoomRotate.disableRotation();
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");
  map.addControl(new maplibregl.AttributionControl({
    compact: false,
    customAttribution: state.meta.attribution || (state.meta.synthetic ? "Synthetic test terrain" : `Terrain: ${state.meta.source.file}`),
  }));

  map.on("load", () => {
    const img = (id, url, coords, opacity, visible = true) => {
      map.addSource(id, { type: "image", url, coordinates: coords });
      map.addLayer({ id, type: "raster", source: id, paint: { "raster-opacity": opacity, "raster-fade-duration": 0, "raster-resampling": "linear" },
        layout: { visibility: visible ? "visible" : "none" } });
    };
    img("basemap", api("tiles/basemap.png"), corners, 1);
    img("hazard", hazardUrl(), corners, 1, $("#layerHazard").checked);
    img("shielding", api("tiles/shielding.png"), corners, 0.75, $("#layerShield").checked);
    img("zone", BLANK_PNG, state.meta.routing_corners_lonlat, 1);

    const geo = (id) => map.addSource(id, { type: "geojson", data: EMPTY });
    ["route", "vertices", "failed", "contingency", "escape", "shelters", "target", "vehicle", "cursor", "exposed"].forEach(geo);

    map.addLayer({ id: "contingency", type: "line", source: "contingency", paint: { "line-color": css("--pass"), "line-width": 4, "line-dasharray": [2, 1.5] } });
    map.addLayer({ id: "route", type: "line", source: "route", paint: { "line-color": css("--route"), "line-width": 4 } });
    map.addLayer({ id: "failed", type: "line", source: "failed", paint: { "line-color": css("--fail"), "line-width": 7 } });
    map.addLayer({ id: "vertices", type: "circle", source: "vertices", paint: { "circle-radius": 3.5, "circle-color": css("--route") } });
    map.addLayer({ id: "exposed", type: "circle", source: "exposed", paint: {
      "circle-radius": 7, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": css("--fail"), "circle-stroke-width": 3 } });
    map.addLayer({ id: "escape", type: "line", source: "escape", paint: { "line-color": css("--rad-yellow"), "line-width": 5 } });
    map.addLayer({ id: "shelters", type: "circle", source: "shelters", paint: {
      "circle-radius": ["case", ["==", ["get", "type"], "habitat"], 9, 6],
      "circle-color": ["case", ["==", ["get", "type"], "habitat"], css("--ink"), css("--rad-yellow")],
      "circle-stroke-color": css("--rad-magenta"), "circle-stroke-width": 2.5 } });
    map.addLayer({ id: "target", type: "circle", source: "target", paint: {
      "circle-radius": 11, "circle-color": css("--rad-yellow"), "circle-stroke-color": css("--rad-magenta"), "circle-stroke-width": 4 } });
    map.addLayer({ id: "vehicle", type: "circle", source: "vehicle", paint: {
      "circle-radius": 8, "circle-color": css("--night"), "circle-stroke-color": css("--ink"), "circle-stroke-width": 3 } });
    map.addLayer({ id: "cursor", type: "circle", source: "cursor", paint: {
      "circle-radius": 6, "circle-color": css("--route"), "circle-stroke-color": css("--ink"), "circle-stroke-width": 2 } });

    setData("shelters", fc(state.shelters.map((s) => point([s.lon, s.lat], { name: s.name, type: s.type, shielding: s.shielding }))));
    $("#layerShelters").checked || map.setLayoutProperty("shelters", "visibility", "none");

    const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false });
    map.on("mouseenter", "shelters", (e) => {
      const p = e.features[0].properties;
      const shield = p.type === "habitat" ? "assumed full" : `${pct(p.shielding)} (relative index)`;
      popup.setLngLat(e.features[0].geometry.coordinates).setHTML(`<strong>${p.name}</strong><br>Shielding ${shield}`).addTo(map);
    });
    map.on("mouseleave", "shelters", () => popup.remove());
  });

  map.on("click", (e) => {
    if (!state.drawing) return;
    state.route.push([e.lngLat.lng, e.lngLat.lat]);
    drawRoute();
    $("#btnFinish").disabled = state.route.length < 2;
    $("#btnClear").disabled = false;
  });
  map.on("dblclick", () => { if (state.drawing && state.route.length >= 2) finishRoute(); });
}

function drawRoute() {
  setData("route", state.route.length >= 2 ? fc([line(state.route)]) : EMPTY);
  setData("vertices", fc(state.route.map((c) => point(c))));
  const a = state.analysis;
  setData("failed", a && a.ok ? fc(a.failed.map((f) => line(f.line))) : EMPTY);
  const c = state.contingency;
  setData("contingency", c && c.ok ? fc([line(c.path)]) : EMPTY);
  const me = a && a.ok && a.safety && a.safety.most_exposed;
  setData("exposed", me ? fc([point([me.lon, me.lat])]) : EMPTY);
}

// ---------- route workflow ----------
function setDrawing(on) {
  state.drawing = on;
  map.getCanvasContainer().classList.toggle("drawing", on);
  $("#btnDraw").classList.toggle("active", on);
  $("#btnFinish").disabled = !on || state.route.length < 2;
}

function clearAll() {
  state.route = [];
  state.analysis = state.contingency = null;
  setDrawing(false);
  $("#btnClear").disabled = true;
  $("#btnContingency").disabled = true;
  $("#btnStorm").disabled = true;
  clearStorm();
  drawRoute();
  renderCard();
  renderProfile();
}

function startDrawing() { clearAll(); setDrawing(true); }

function finishRoute() {
  setDrawing(false);
  $("#btnContingency").disabled = state.route.length < 2;
  analyze();
}

async function analyze() {
  if (state.route.length < 2) return;
  try {
    const body = { points: state.route, rover: readRover(), spacing_m: spacing() };
    state.analysis = await postJSON("route/analyze", body);
    if (state.contingency && state.contingency.ok) state.contingency = await postJSON("route/contingency", body);
  } catch (err) {
    state.analysis = { ok: false, error: `The server could not analyse the route: ${err.message}` };
  }
  $("#btnStorm").disabled = !(state.analysis && state.analysis.ok);
  drawRoute();
  renderCard();
  renderProfile();
  updateVehicle();
}

async function suggestContingency() {
  if (state.route.length < 2) return;
  $("#btnContingency").disabled = true;
  try {
    state.contingency = await postJSON("route/contingency", { points: state.route, rover: readRover(), spacing_m: spacing() });
  } catch (err) {
    state.contingency = { ok: false, error: err.message };
  }
  $("#btnContingency").disabled = false;
  drawRoute();
  renderCard();
  renderProfile();
}

// ---------- survival card ----------
function renderCard() {
  const el = $("#card");
  const a = state.analysis;
  if (!a) {
    el.innerHTML = `<h2>Survival card</h2><p class="empty">Draw a route to see distance, time, energy and whether the vehicle can drive it.</p>`;
    return;
  }
  if (!a.ok) { el.innerHTML = `<h2>Survival card</h2><p class="reason">${a.error}</p>`; return; }

  const rover = readRover();
  const pass = a.status === "PASS";
  const w = a.worst;
  let html = `<h2>Survival card</h2>
    <div class="status ${pass ? "pass" : "fail"}"><span>${pass ? "Route passes" : "Route fails"}</span><span>${pass ? "✓" : "✕"}</span></div>
    <dl class="metrics">
      <dt>Distance</dt><dd>${km(a.distance_m)}</dd>
      <dt>Driving time</dt><dd>${duration(a.time_s)}</dd>
      <dt>Driving sols</dt><dd>${a.driving_sols.toFixed(1)}</dd>
      <dt>Energy</dt><dd>${wh(a.energy_wh)}</dd>
      <dt>Energy per driving sol</dt><dd>${wh(a.wh_per_sol)}</dd>
      <dt>Total climb</dt><dd>${Math.round(a.total_climb_m)} m</dd>
      <dt>Max slope on route</dt><dd>${a.max_slope_deg.toFixed(1)}°</dd>
      <dt>Max ground slope</dt><dd>${a.max_ground_slope_deg == null ? "n/a" : a.max_ground_slope_deg.toFixed(1) + "°"}</dd>
    </dl>`;
  if (!pass) {
    html += `<p class="reason">Segment ${w.index} (${km(w.from_m)} to ${km(w.to_m)}) is ${Math.abs(w.slope_deg).toFixed(1)}°.
      The limit is ${rover.slope_limit_deg.toFixed(1)}°, so it is ${w.exceed_deg.toFixed(1)}° too steep.
      ${a.failed.length > 1 ? `${a.failed.length} segments exceed the limit in total.` : ""}
      ${state.contingency ? "" : "Press Suggest safe route for a contingency route."}</p>`;
  }
  if (!a.energy_ok) html += `<p class="reason warn">Energy per driving sol (${wh(a.wh_per_sol)}) is above the assumed ${wh(rover.energy_per_sol_wh)}. Plan extra stops to recharge.</p>`;
  if (pass && a.max_ground_slope_deg > rover.slope_limit_deg) {
    html += `<p class="reason warn">The route stays under the limit, but crosses ground up to ${a.max_ground_slope_deg.toFixed(1)}° sideways. Check for side-slope tipping.</p>`;
  }
  const c = state.contingency;
  if (c && !c.ok) html += `<p class="reason">${c.error}</p>`;
  if (c && c.ok) {
    const b = c.analysis;
    html += `<table class="compare">
      <tr><th></th><th>Your route</th><th>Contingency</th></tr>
      <tr><td>Status</td><td>${a.status}</td><td>${b.status}</td></tr>
      <tr><td>Distance</td><td>${km(a.distance_m)}</td><td>${km(b.distance_m)}</td></tr>
      <tr><td>Max slope</td><td>${a.max_slope_deg.toFixed(1)}°</td><td>${b.max_slope_deg.toFixed(1)}°</td></tr>
      <tr><td>Climb</td><td>${Math.round(a.total_climb_m)} m</td><td>${Math.round(b.total_climb_m)} m</td></tr>
      <tr><td>Time</td><td>${duration(a.time_s)}</td><td>${duration(b.time_s)}</td></tr>
      <tr><td>Energy</td><td>${wh(a.energy_wh)}</td><td>${wh(b.energy_wh)}</td></tr>
    </table>
    <p class="note">Contingency route: Dijkstra on a ${Math.round(c.routing_res_m)} m grid, steps limited to ${c.planning_limit_deg.toFixed(1)}°, then re-checked on the full DEM. A computed suggestion, not a NASA-approved route.</p>`;
  }
  html += safetyHtml(a, rover);
  html += `<p class="note">Simplified model: constant speed, base power plus climbing energy. No wheel slip, rolling resistance or solar charging.</p>`;
  el.innerHTML = html;
}

function safetyHtml(a, rover) {
  const s = a.safety || {};
  const stops = s.safe_stops || [];
  const me = s.most_exposed;
  let h = `<h3>Safe stops on this route</h3>`;
  h += stops.length
    ? `<ul>${stops.map((t) => `<li>km ${(t.at_m / 1000).toFixed(1)}: ${t.name}, ${(t.off_route_m / 1000).toFixed(2)} km off the route, shielding ${t.type === "habitat" ? "assumed full" : pct(t.shielding)}</li>`).join("")}</ul>`
    : `<p class="assume">No shelter lies within ${((s.stop_radius_m || 1000) / 1000).toFixed(1)} km of this route.</p>`;
  h += `<h3>If something fails</h3><ul>`;
  if (me) {
    h += `<li><strong>Vehicle breakdown:</strong> the most exposed point is km ${(me.at_m / 1000).toFixed(1)} (red ring on the map).
      Nearest shelter from there: ${me.nearest_shelter}, ${km(me.distance_m)} in a straight line.</li>`;
  }
  h += a.status === "FAIL"
    ? `<li><strong>Too steep:</strong> do not drive segment ${a.worst.index}. Use Suggest safe route for a route under the limit.</li>`
    : `<li><strong>Terrain:</strong> every segment stays under the ${rover.slope_limit_deg}° limit.</li>`;
  h += a.energy_ok
    ? `<li><strong>Energy:</strong> ${wh(a.wh_per_sol)} per driving sol fits the assumed ${wh(rover.energy_per_sol_wh)}.</li>`
    : `<li><strong>Energy:</strong> ${wh(a.wh_per_sol)} per driving sol is over the assumed ${wh(rover.energy_per_sol_wh)}. Add recharge stops.</li>`;
  h += `<li><strong>Solar storm alert:</strong> run the storm drill below from the vehicle's position.</li></ul>`;
  h += `<h3>Assumptions used</h3><p class="assume">Mass ${rover.mass_kg} kg, speed ${rover.speed_m_s} m/s, slope limit ${rover.slope_limit_deg}°,
    base power ${rover.base_power_w} W, energy budget ${wh(rover.energy_per_sol_wh)} per sol, ${rover.drive_hours_per_sol} h driving per sol,
    terrain sampled every ${spacing()} m, Mars gravity 3.72 m/s².</p>`;
  return h;
}

// ---------- provenance drawer ----------
const esc = (t) => String(t ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const linkTo = (u) => (u ? `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(u)}</a>` : "n/a");

function renderProvenance() {
  const p = state.provenance;
  if (!p) return;
  const t = p.terrain;
  const pv = t.provenance || {};
  const ev = state.storms.find((s) => s.id === $("#stormEvent").value);
  $("#provBody").innerHTML = `
    <dl>
      <dt>Terrain</dt><dd>${esc(pv.dataset || t.attribution)}</dd>
      <dt>Product id</dt><dd>${esc((t.source || {}).product)}</dd>
      <dt>Mission</dt><dd>${esc(pv.mission || "n/a")}</dd>
      <dt>DTM file</dt><dd>${linkTo(pv.dtm_href)}</dd>
      <dt>Catalog</dt><dd>${linkTo(pv.stac_search)}</dd>
      <dt>Processed</dt><dd>${esc(t.crs)}, ${esc(t.res_m)} m cells, ${esc(t.generated_utc)} (read from ${esc(t.read_from)})</dd>
      <dt>Storms</dt><dd>NASA DONKI SEP, ${p.storms.count} events (read from ${esc(p.storms.read_from)})</dd>
      <dt>API</dt><dd>${linkTo(p.storms.api)}</dd>
      <dt>Selected event</dt><dd>${ev ? `${esc(ev.id)}<br>${linkTo(ev.link)}` : "Demo scenario"}</dd>
    </dl>
    <pre>${esc(JSON.stringify({ terrain: t, selected_storm: ev || null, method: p.method }, null, 2))}</pre>`;
}

// ---------- profile ----------
function renderProfile() {
  const a = state.analysis;
  const has = a && a.ok;
  $("#profileEmpty").hidden = has;
  if (state.chart) { state.chart.destroy(); state.chart = null; }
  if (!has) return;
  const prof = a.profile;
  const datasets = [{
    label: "Your route",
    data: prof.map((p) => ({ x: p.d_km, y: p.z_m })),
    borderColor: css("--route"), borderWidth: 2, pointRadius: 0,
    fill: { target: "origin", above: "rgba(201,168,130,0.12)" },
    segment: {
      borderColor: (ctx) => (prof[ctx.p1DataIndex].over ? css("--fail") : css("--route")),
      borderWidth: (ctx) => (prof[ctx.p1DataIndex].over ? 4 : 2),
    },
  }];
  const c = state.contingency;
  if (c && c.ok) {
    datasets.push({ label: "Contingency", data: c.analysis.profile.map((p) => ({ x: p.d_km, y: p.z_m })),
      borderColor: css("--pass"), borderDash: [6, 4], borderWidth: 2, pointRadius: 0 });
  }
  const tick = { color: css("--dust") };
  const grid = { color: "rgba(255,255,255,0.06)" };
  state.chart = new Chart($("#profile"), {
    type: "line",
    data: { datasets },
    options: {
      animation: false, maintainAspectRatio: false, parsing: false,
      interaction: { mode: "nearest", axis: "x", intersect: false },
      scales: {
        x: { type: "linear", title: { display: true, text: "Distance (km)", color: css("--dust") }, ticks: tick, grid },
        y: { title: { display: true, text: "Elevation (m)", color: css("--dust") }, ticks: tick, grid },
      },
      plugins: {
        legend: { display: datasets.length > 1, labels: { color: css("--ink") } },
        tooltip: { callbacks: { label: (t) => `${t.dataset.label}: ${t.parsed.y.toFixed(0)} m at ${t.parsed.x.toFixed(2)} km` } },
      },
      onHover: (_, els) => {
        if (!els.length || els[0].datasetIndex !== 0) { setData("cursor", EMPTY); return; }
        const p = prof[els[0].index];
        setData("cursor", fc([point([p.lon, p.lat])]));
      },
    },
  });
}

// ---------- solar storm drill ----------
function fillStorms() {
  const sel = $("#stormEvent");
  sel.innerHTML = "";
  if (!state.storms.length) {
    sel.add(new Option("Demo scenario (not a real event)", "demo"));
    return;
  }
  for (const s of state.storms) sel.add(new Option(`SEP ${(s.time || "").replace("T", " ").replace("Z", " UTC")}`, s.id));
}

function vehiclePosition() {
  const a = state.analysis;
  if (!a || !a.ok) return null;
  const target = (parseFloat($("#position").value) / 100) * (a.distance_m / 1000);
  return a.profile.reduce((best, p) => (Math.abs(p.d_km - target) < Math.abs(best.d_km - target) ? p : best), a.profile[0]);
}

function updateVehicle() {
  $("#posOut").textContent = `${$("#position").value}%`;
  $("#warnOut").textContent = `${$("#warning").value} min`;
  const p = vehiclePosition();
  setData("vehicle", p ? fc([point([p.lon, p.lat])]) : EMPTY);
}

async function triggerStorm() {
  const p = vehiclePosition();
  if (!p) return;
  const rover = readRover();
  $("#btnStorm").disabled = true;
  let plan;
  try {
    plan = await postJSON("storm/escape", { position: [p.lon, p.lat], warning_min: parseFloat($("#warning").value), rover });
  } catch (err) {
    plan = { ok: false, error: err.message };
  }
  $("#btnStorm").disabled = false;
  state.stormShown = true;

  const ev = state.storms.find((s) => s.id === $("#stormEvent").value);
  const src = ev
    ? `Replaying NASA DONKI event ${ev.id}${ev.instruments && ev.instruments.length ? `, detected by ${ev.instruments.join(", ")}` : ""}. Detected near Earth; replayed here as a Mars scenario.`
    : "Demo scenario, not a real event. Run make cache to load real DONKI events.";

  let title, body;
  if (!plan.ok) {
    title = "Storm alert";
    body = plan.error;
  } else {
    map.getSource("zone").updateImage({ url: plan.zone.image, coordinates: plan.zone.corners });
    setData("escape", plan.path.length >= 2 ? fc([line(plan.path)]) : EMPTY);
    setData("target", plan.best ? fc([point([plan.best.lon, plan.best.lat])]) : EMPTY);
    const t = plan.best;
    const spare = t ? Math.round((plan.warning_s - t.time_s) / 60) : 0;
    if (plan.mode === "shelter") {
      title = `Go to ${t.name}`;
      body = `${km(plan.path_length_m)} away, ${duration(t.time_s)} at ${plan.speed_m_s} m/s. Arrive with ${spare} min to spare.
        Shielding: ${t.type === "habitat" ? "assumed full" : `${pct(t.shielding)} (relative index)`}.`;
    } else if (plan.mode === "spot") {
      const f = plan.fastest;
      title = "No shelter reachable in time";
      body = `${f ? `Nearest shelter is ${f.name}, ${duration(f.time_s)} away. ` : ""}Move to the best protected spot in reach instead:
        ${km(plan.path_length_m)}, ${duration(t.time_s)}, shielding ${pct(t.shielding)} (relative index).`;
    } else {
      title = "Shelter in place";
      body = "No better protected spot is reachable within the warning time. Stay in the vehicle.";
    }
  }
  const box = $("#alert");
  box.innerHTML = `<h3><span class="trefoil" aria-hidden="true">☢</span>${title}</h3><p>${body}</p><p class="src">${src}</p>`;
  box.hidden = false;
  box.classList.remove("enter"); void box.offsetWidth; box.classList.add("enter");
  $("#btnStormClear").hidden = false;
}

function clearStorm() {
  state.stormShown = false;
  if (map && map.getSource("zone")) {
    map.getSource("zone").updateImage({ url: BLANK_PNG, coordinates: state.meta.routing_corners_lonlat });
    setData("escape", EMPTY);
    setData("target", EMPTY);
  }
  $("#alert").hidden = true;
  $("#btnStormClear").hidden = true;
}

// ---------- wiring ----------
function toggleLayer(checkbox, layer) {
  $(checkbox).onchange = (e) => map.setLayoutProperty(layer, "visibility", e.target.checked ? "visible" : "none");
}

function wire() {
  $("#btnDraw").onclick = startDrawing;
  $("#btnFinish").onclick = finishRoute;
  $("#btnClear").onclick = clearAll;
  $("#btnContingency").onclick = suggestContingency;
  $("#btnStorm").onclick = triggerStorm;
  $("#btnStormClear").onclick = clearStorm;
  $("#preset").onchange = (e) => {
    applyPreset(e.target.value);
    map.getSource("hazard").updateImage({ url: hazardUrl() });
    clearStorm();
    analyze();
  };
  for (const id of [...ROVER_FIELDS, "spacing"]) {
    $(`#${id}`).addEventListener("change", () => {
      if (id === "slope_limit_deg") map.getSource("hazard").updateImage({ url: hazardUrl() });
      clearStorm();
      analyze();
    });
  }
  $("#stormEvent").onchange = () => { clearStorm(); renderProvenance(); };
  $("#warning").oninput = () => { $("#warnOut").textContent = `${$("#warning").value} min`; };
  $("#position").oninput = () => { clearStorm(); updateVehicle(); };
  toggleLayer("#layerHazard", "hazard");
  toggleLayer("#layerShield", "shielding");
  toggleLayer("#layerShelters", "shelters");
}

async function main() {
  try {
    const [meta, shelters, storms, prov] = await Promise.all([getJSON("meta"), getJSON("shelters"), getJSON("storms"), getJSON("provenance")]);
    state.provenance = prov;
    state.meta = meta;
    state.shelters = shelters;
    state.storms = storms.events || [];
    $("#region").textContent = `${meta.name}, ${(meta.width * meta.res_m / 1000).toFixed(1)} × ${(meta.height * meta.res_m / 1000).toFixed(1)} km at ${meta.res_m} m per cell`;
    $("#sourceTag").textContent = `terrain: ${meta.data_source}`;
    $("#dataBadge").hidden = !meta.synthetic;
    applyPreset("crewed");
    initMap();
    fillStorms();
    wire();
    renderProvenance();
  } catch (err) {
    $("#region").textContent = `Cannot reach the SafeSol API (${err.message}). Start it with: uvicorn src.api.main:app`;
  }
}

main();
