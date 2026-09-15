// Solar Inspector dashboard. Talks only to the local service at this origin;
// the service talks to the camera. The one exception is the live MJPEG view,
// which an <img> loads straight from the camera.

const $ = (id) => document.getElementById(id);

const TYPE = {
  possible_surface_crack: "Surface crack", discoloration: "Discoloration", soiling: "Soiling",
  burn_mark: "Burn mark", shading: "Shading", snail_trail: "Snail trail",
  delamination: "Delamination", other_visible_anomaly: "Other anomaly",
};
const VERDICT = {
  defect_suspected: "Defects found", no_visible_defect: "No visible defects",
  uncertain: "Uncertain result", retake_required: "Retake needed",
};
const PLABEL = { none: "No action", low: "Low", medium: "Medium", high: "High", urgent: "Urgent" };
const OVERLAY = { urgent: "#FF6B5B", high: "#FF9F43", medium: "#FFD23F", low: "#5EE0A0", none: "#C9D2DB" };
const MODE_LABEL = { openai: "Vision model", mock: "Demo mode" };

const state = {
  status: null,
  current: null,        // latest inspection this session
  selected: 0,
  showingStill: false,
  busy: false,
  records: [], nextBefore: 0, total: 0, loadedOnce: false, filter: "all",
  record: null, recordSelected: 0,
};

/* ---- helpers ------------------------------------------------------------ */
function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
}
function chip(priority, text, large) {
  return el("span", `chip p-${priority}${large ? " chip-lg" : ""}`, text);
}
function when(iso) {
  if (!iso) return "Time not recorded";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "Time not recorded";
  return date.toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}
function urgencyOf(defect) { return defect.root_cause?.urgency || defect.severity || "none"; }
function modeLabel(meta) { return meta?.mode_label || MODE_LABEL[meta?.mode] || "Vision model"; }

async function getJSON(url, options) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(body?.error?.message || `The request failed (${response.status}).`);
    error.code = body?.error?.code;
    throw error;
  }
  return body;
}

/* ---- status ------------------------------------------------------------- */
async function refreshStatus(search = false) {
  try {
    state.status = await getJSON(`/api/status${search ? "?search=true" : ""}`);
  } catch {
    state.status = { analysis: { ready: false, label: "Unavailable" }, camera: { reachable: false } };
  }
  renderStatus();
}

function renderStatus() {
  const { analysis, camera } = state.status;
  const dot = $("status-dot"), label = $("status-label");
  const ok = camera.reachable && analysis.ready;
  const colour = ok ? "low" : camera.reachable || analysis.ready ? "medium" : "urgent";
  dot.style.background = `var(--${colour})`;
  dot.style.boxShadow = `0 0 0 3px var(--${colour}-soft)`;
  label.textContent = ok ? "Camera and analysis ready"
    : !camera.reachable ? "Camera not found" : "Analysis not configured";

  const list = $("status-list");
  list.innerHTML = "";
  const row = (term, value, mono) => {
    list.appendChild(el("dt", null, term));
    list.appendChild(el("dd", mono ? "mono" : null, value));
  };
  if (camera.reachable) {
    const sd = camera.sd || {};
    row("Camera", camera.address, true);
    row("Signal", camera.rssi != null ? `${camera.rssi} dBm` : "—", true);
    row("Firmware", camera.firmware || "—", true);
    row("Storage", sd.present ? `microSD · ${(sd.free_mb / 1024).toFixed(1)} GB free` : "No SD card");
    row("Saved inspections", sd.present ? String(sd.records) : "—", true);
  } else {
    row("Camera", "Not found");
  }
  row("Analysis", analysis.ready ? `${analysis.label} · ready` : "Not configured");
  $("find-camera").hidden = camera.reachable;

  $("offline").hidden = camera.reachable;
  if (!camera.reachable && camera.error) $("offline-text").textContent = camera.error.message;
  $("capture").disabled = state.busy || !camera.reachable;
  if (camera.reachable && !state.showingStill && !state.busy) startLive();
}

async function findCamera(button) {
  const buttons = [$("find-camera"), $("offline-find")];
  buttons.forEach((b) => { b.disabled = true; b.textContent = "Searching…"; });
  await refreshStatus(true);
  buttons.forEach((b) => { b.disabled = false; b.textContent = "Find camera"; });
}

/* ---- live view ---------------------------------------------------------- */
function startLive() {
  const url = state.status?.camera?.stream_url;
  const live = $("live");
  if (!url || location.hash.startsWith("#/record") || location.hash === "#/history") return;
  live.hidden = false;
  if (live.dataset.src !== url) { live.dataset.src = url; live.src = url; }
}
function stopLive() {
  const live = $("live");
  live.removeAttribute("src");
  delete live.dataset.src;
}
$("live").addEventListener("error", () => {
  // Wi-Fi hiccups drop the stream; retry quietly while it's still wanted.
  const live = $("live");
  delete live.dataset.src;
  setTimeout(() => { if (!state.showingStill && !state.busy) startLive(); }, 3000);
});

/* ---- regions ------------------------------------------------------------ */
function drawBoxes(svg, result, selected, visible) {
  svg.innerHTML = "";
  if (!result) return;
  svg.setAttribute("viewBox", `0 0 ${result.image_width || 1600} ${result.image_height || 1200}`);
  if (!visible) return;
  result.defects.forEach((d, i) => {
    const b = d.bounding_box, on = selected === i, colour = OVERLAY[urgencyOf(d)] || OVERLAY.none;
    const tagY = b.y_min - 70 < 0 ? b.y_min + 8 : b.y_min - 70;
    const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
    group.setAttribute("opacity", selected !== null && !on ? ".62" : "1");
    const w = b.x_max - b.x_min, h = b.y_max - b.y_min;
    group.innerHTML =
      `<rect x="${b.x_min}" y="${b.y_min}" width="${w}" height="${h}" fill="none" stroke="rgba(0,0,0,.55)" stroke-width="${on ? 12 : 9}"/>` +
      `<rect x="${b.x_min}" y="${b.y_min}" width="${w}" height="${h}" fill="none" stroke="${colour}" stroke-width="${on ? 7 : 4}"/>` +
      `<rect x="${b.x_min}" y="${tagY}" width="68" height="64" fill="${colour}"/>` +
      `<text x="${b.x_min + 34}" y="${tagY + 46}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="42" font-weight="500" fill="#10161D">${i + 1}</text>`;
    svg.appendChild(group);
  });
}

/* ---- findings ----------------------------------------------------------- */
function renderFindings(root, view, selected, onSelect) {
  root.innerHTML = "";
  const { result } = view;
  const priority = result.priority || "none";

  const verdict = el("section", "verdict");
  verdict.appendChild(el("p", "eyebrow",
    view.recordId ? `Inspection ${view.recordId} · ${when(result.inspected_at)}` : `Not saved · ${when(result.inspected_at)}`));
  const heading = el("div", "verdict-row");
  heading.appendChild(el("h2", null, VERDICT[result.status] || "Result"));
  heading.appendChild(chip(priority, priority === "none" ? "No action" : `${PLABEL[priority]} priority`, true));
  verdict.appendChild(heading);
  verdict.appendChild(el("p", "summary", result.summary));
  root.appendChild(verdict);

  if (view.saveError) {
    const notice = el("div", "notice warn");
    notice.appendChild(el("strong", null, "Not saved to the camera"));
    notice.appendChild(document.createTextNode(view.saveError.message));
    root.appendChild(notice);
  }

  if (!result.defects.length) {
    root.appendChild(el("div", "empty", result.status === "retake_required"
      ? "Nothing can be judged from this image. Improve the lighting, move closer to the module, then capture again."
      : "No regions were marked. This record serves as a clean baseline for the module."));
    return;
  }

  const list = el("ol", "defects");
  list.setAttribute("aria-label", "Marked regions");
  result.defects.forEach((d, i) => {
    const item = el("li"), button = el("button", "defect");
    button.type = "button";
    button.setAttribute("aria-pressed", String(selected === i));
    const index = el("span", "idx", String(i + 1));
    index.style.background = OVERLAY[urgencyOf(d)] || OVERLAY.none;
    const text = el("span");
    text.appendChild(el("span", "name", TYPE[d.type] || d.type));
    text.appendChild(el("span", "cause-line", d.root_cause?.title || "Cause not recorded"));
    button.append(index, text, chip(urgencyOf(d), PLABEL[urgencyOf(d)] || urgencyOf(d)));
    button.addEventListener("click", () => onSelect(selected === i ? null : i));
    item.appendChild(button);
    list.appendChild(item);
  });
  root.appendChild(list);

  const i = selected ?? 0, d = result.defects[i], cause = d.root_cause;
  const panel = el("section", "cause");
  panel.appendChild(el("p", "kicker", `Region ${i + 1} · ${TYPE[d.type] || d.type} · probable cause`));
  panel.appendChild(el("h3", null, cause?.title || "Cause not recorded"));
  const chips = el("div", "chips");
  chips.append(chip(urgencyOf(d), `${PLABEL[urgencyOf(d)] || urgencyOf(d)} urgency`));
  if (cause?.confidence) chips.append(chip("none", `${cause.confidence} confidence`));
  panel.appendChild(chips);

  const details = el("dl");
  const add = (term, node) => {
    const wrap = el("div");
    wrap.appendChild(el("dt", null, term));
    const dd = el("dd");
    dd.appendChild(node);
    wrap.appendChild(dd);
    details.appendChild(wrap);
  };
  add("What was seen", document.createTextNode(d.description));
  if (cause) {
    add("Why we think so", el("span", "evidence", cause.evidence || "No specific evidence was given."));
    add("About this cause", document.createTextNode(cause.explanation));
    const confirm = el("ul");
    (cause.verify_with || []).forEach((step) => confirm.appendChild(el("li", null, step)));
    add("How to confirm", confirm);
    add("What to do", document.createTextNode(cause.action));
  }
  panel.appendChild(details);
  if (cause?.corrected) {
    panel.appendChild(el("p", "note",
      "The model's first suggestion didn't fit this kind of defect, so the cause is marked as not determinable."));
  }
  panel.appendChild(el("p", "note", "Inferred from visible evidence in one photograph. Confirm on site before replacing equipment."));
  root.appendChild(panel);
}

/* ---- inspect ------------------------------------------------------------ */
function renderInspectIdle() {
  const root = $("findings-inspect");
  root.innerHTML = "";
  const card = el("section", "verdict");
  card.appendChild(el("p", "eyebrow", "Ready"));
  card.appendChild(el("h2", null, "No inspection yet"));
  card.appendChild(el("p", "summary",
    "Frame one module in the live view, then press Capture and analyze. Each result is saved to the camera's SD card and appears in History."));
  root.appendChild(card);
}

function renderProgress(stage) {
  const steps = [["capturing", "Taking the picture"], ["analyzing", "Analysing with the vision model"], ["saving", "Saving to the camera"]];
  const order = steps.map(([key]) => key);
  const root = $("findings-inspect");
  root.innerHTML = "";
  const card = el("section", "verdict");
  card.appendChild(el("p", "eyebrow", "Inspection in progress"));
  card.appendChild(el("h2", null, "Working…"));
  const list = el("ol", "progress-list");
  steps.forEach(([key, text]) => {
    const item = el("li", null, text);
    const position = order.indexOf(stage), mine = order.indexOf(key);
    if (mine < position) item.className = "done";
    if (mine === position) item.className = "active";
    list.appendChild(item);
  });
  card.appendChild(list);
  root.appendChild(card);
}

function renderInspectError(error) {
  const root = $("findings-inspect");
  root.innerHTML = "";
  const card = el("div", "notice bad");
  card.appendChild(el("strong", null, "The inspection didn't complete"));
  card.appendChild(document.createTextNode(error.message));
  root.appendChild(card);
}

function paintInspect() {
  const current = state.current;
  drawBoxes($("boxes-inspect"), state.showingStill ? current?.result : null, state.selected, $("regions-inspect").checked);
  if (!current) return;
  renderFindings($("findings-inspect"), current, state.selected, (i) => { state.selected = i; paintInspect(); });
  const latency = current.result.meta?.latency_ms;
  $("meta-inspect").textContent = `${modeLabel(current.result.meta)}${latency ? ` · ${(latency / 1000).toFixed(1)} s` : ""}`;
}

function showStill(url) {
  state.showingStill = true;
  stopLive();
  $("live").hidden = true;
  const still = $("still-inspect");
  still.hidden = false;
  still.src = url;
  $("badge-inspect").textContent = "Captured still";
  $("back-live").hidden = false;
}

function showLiveView() {
  state.showingStill = false;
  $("still-inspect").hidden = true;
  $("boxes-inspect").innerHTML = "";
  $("badge-inspect").textContent = "Live view";
  $("back-live").hidden = true;
  startLive();
}

function setProgress(text) {
  $("progress").hidden = !text;
  $("progress-text").textContent = text || "";
  $("capture-label").textContent = text || "Capture and analyze";
}

async function inspect() {
  if (state.busy) return;
  state.busy = true;
  $("capture").disabled = true;
  $("back-live").hidden = true;
  stopLive();  // free the Wi-Fi link for the full-resolution capture
  setProgress("Capturing…");
  renderProgress("capturing");

  try {
    const response = await fetch("/api/inspect", { method: "POST" });
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let newline;
      while ((newline = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, newline).trim();
        buffer = buffer.slice(newline + 1);
        if (line) handleStage(JSON.parse(line));
      }
    }
  } catch {
    handleStage({ stage: "error", error: { message: "Lost contact with the analysis service. Check the launcher window is still open." } });
  } finally {
    state.busy = false;
    setProgress("");
    $("capture").disabled = !state.status?.camera?.reachable;
  }
}

function handleStage(event) {
  if (event.stage === "capturing") {
    setProgress("Capturing…");
    renderProgress("capturing");
  } else if (event.stage === "analyzing") {
    showStill(`/api/captures/${event.capture}.jpg`);
    setProgress("Analysing…");
    renderProgress("analyzing");
  } else if (event.stage === "saving") {
    setProgress("Saving…");
    renderProgress("saving");
  } else if (event.stage === "done") {
    state.current = { result: event.result, recordId: event.record_id, saveError: event.save_error };
    state.selected = event.result.defects.length ? 0 : null;
    state.loadedOnce = false;  // History refreshes next time it opens
    setProgress("");
    paintInspect();
    $("back-live").hidden = false;
    refreshStatus();
  } else if (event.stage === "error") {
    setProgress("");
    renderInspectError(event.error);
    if (event.capture) { $("back-live").hidden = false; } else { showLiveView(); }
  }
}

$("capture").addEventListener("click", inspect);
$("back-live").addEventListener("click", () => {
  showLiveView();
  if (state.current) paintInspect();
});
$("regions-inspect").addEventListener("change", paintInspect);

/* ---- history ------------------------------------------------------------ */
const FILTERS = [["all", "All"], ["urgent", "Urgent"], ["high", "High"], ["medium", "Medium"], ["low", "Low"], ["none", "No action"]];
FILTERS.forEach(([key, label]) => {
  const button = el("button", "filter", label);
  button.type = "button";
  button.id = `filter-${key}`;
  button.setAttribute("aria-pressed", String(key === state.filter));
  button.addEventListener("click", () => {
    state.filter = key;
    document.querySelectorAll(".filter").forEach((f) => f.setAttribute("aria-pressed", String(f === button)));
    renderRows();
  });
  $("filters").appendChild(button);
});

async function loadRecords(reset) {
  if (reset) { state.records = []; state.nextBefore = 0; }
  const rows = $("rows");
  if (reset) rows.replaceChildren(el("div", "nores", "Loading inspections from the camera…"));
  try {
    const query = state.nextBefore ? `&before=${state.nextBefore}` : "";
    const data = await getJSON(`/api/records?limit=24${query}`);
    state.records.push(...data.records);
    state.nextBefore = data.next_before;
    state.total = data.total;
    state.loadedOnce = true;
    renderRows();
  } catch (error) {
    rows.replaceChildren(el("div", "nores", error.code === "no_sd_card"
      ? "There's no SD card in the camera, so inspections can't be saved or listed. Insert a card and restart the camera."
      : error.message));
    $("more-wrap").hidden = true;
  }
}

function renderRows() {
  const rows = $("rows");
  rows.innerHTML = "";
  const shown = state.records.filter((r) => state.filter === "all" || (r.priority || "none") === state.filter);
  $("history-count").textContent = `${state.total} inspection${state.total === 1 ? "" : "s"} saved on the camera`;
  if (!shown.length) {
    rows.appendChild(el("div", "nores", state.records.length
      ? "No loaded inspections at this priority."
      : "No inspections saved yet. Run one from Inspect."));
  }
  for (const record of shown) {
    const priority = record.priority || "none";
    const button = el("button", "row");
    button.type = "button";
    const thumbCell = el("span", "c-thumb");
    const thumb = el("img", "thumb");
    thumb.loading = "lazy";
    thumb.alt = "";
    thumb.src = `/api/records/${record.id}/${record.thumb ? "thumb" : "image"}.jpg`;
    thumbCell.appendChild(thumb);
    const idCell = el("span", "c-id");
    idCell.appendChild(el("span", "id", record.id));
    idCell.appendChild(el("span", "when", when(record.created)));
    const n = record.defects;
    button.append(thumbCell, idCell,
      el("span", "c-verdict", record.analyzed ? VERDICT[record.status] || "Result" : "Not analysed"),
      el("span", "c-count count", n ? `${n} region${n > 1 ? "s" : ""}` : "—"));
    const priorityCell = el("span", "c-pri");
    priorityCell.appendChild(chip(priority, PLABEL[priority] || priority));
    button.appendChild(priorityCell);
    button.addEventListener("click", () => { location.hash = `#/record/${record.id}`; });
    rows.appendChild(button);
  }
  $("more-wrap").hidden = !state.nextBefore;
}
$("more").addEventListener("click", () => loadRecords(false));

/* ---- record ------------------------------------------------------------- */
function paintRecord() {
  const record = state.record;
  if (!record) return;
  drawBoxes($("boxes-record"), record.result, state.recordSelected, $("regions-record").checked);
  renderFindings($("findings-record"), record, state.recordSelected, (i) => { state.recordSelected = i; paintRecord(); });
}

async function openRecord(id) {
  $("h-record").textContent = `Inspection ${id}`;
  $("record-when").textContent = "";
  $("findings-record").replaceChildren(el("div", "empty", "Loading the inspection from the camera…"));
  $("boxes-record").innerHTML = "";
  const still = $("still-record");
  still.hidden = true;
  $("record-loading").hidden = false;
  try {
    const result = await getJSON(`/api/records/${id}`);
    state.record = { result, recordId: id };
    state.recordSelected = result.defects.length ? 0 : null;
    $("record-when").textContent = when(result.inspected_at);
    $("meta-record").textContent = modeLabel(result.meta);
    still.onload = () => { $("record-loading").hidden = true; still.hidden = false; };
    still.src = `/api/records/${id}/image.jpg`;
    paintRecord();
  } catch (error) {
    $("record-loading").hidden = true;
    $("findings-record").replaceChildren(el("div", "notice bad", error.message));
  }
}

$("regions-record").addEventListener("change", paintRecord);
$("back").addEventListener("click", () => { location.hash = "#/history"; });
$("print").addEventListener("click", () => window.print());
$("delete").addEventListener("click", async () => {
  const id = state.record?.recordId;
  if (!id || !confirm(`Delete inspection ${id} from the camera? This can't be undone.`)) return;
  try {
    await getJSON(`/api/records/${id}`, { method: "DELETE" });
    state.records = state.records.filter((r) => r.id !== id);
    state.total = Math.max(0, state.total - 1);
    location.hash = "#/history";
  } catch (error) {
    alert(error.message);
  }
});

/* ---- routing ------------------------------------------------------------ */
function show(view) {
  for (const name of ["inspect", "history", "record"]) $(`view-${name}`).hidden = name !== view;
  $("nav-inspect").toggleAttribute("aria-current", view === "inspect");
  $("nav-history").toggleAttribute("aria-current", view !== "inspect");
  (view === "inspect" ? $("nav-inspect") : $("nav-history")).setAttribute("aria-current", "page");
}

function route() {
  const hash = location.hash || "#/inspect";
  if (hash.startsWith("#/record/")) {
    stopLive();
    show("record");
    openRecord(hash.slice("#/record/".length));
  } else if (hash === "#/history") {
    stopLive();
    show("history");
    if (!state.loadedOnce) loadRecords(true); else renderRows();
  } else {
    show("inspect");
    if (!state.showingStill) startLive();
  }
  window.scrollTo(0, 0);
}

document.querySelectorAll(".nav").forEach((nav) => nav.addEventListener("click", () => { location.hash = nav.dataset.route; }));
$("find-camera").addEventListener("click", findCamera);
$("offline-find").addEventListener("click", findCamera);
window.addEventListener("hashchange", route);

renderInspectIdle();
route();
refreshStatus();
setInterval(() => { if (!state.busy) refreshStatus(); }, 15000);
