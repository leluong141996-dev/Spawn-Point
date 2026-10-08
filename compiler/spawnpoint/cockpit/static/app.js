// Spawn Point Studio — cockpit page. Plain JS, no build step.
"use strict";

const state = { projects: [], current: null, detail: null, status: null, selected: null, running: 0 };
const $ = (sel) => document.querySelector(sel);

// Builds DOM without innerHTML (names and text may come from an LLM).
function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "text") el.textContent = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

async function api(path, body) {
  const opts = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function log(text, cls = "") {
  const box = $("#log");
  box.append(h("div", { class: cls, text: `${new Date().toLocaleTimeString()}  ${text}` }));
  while (box.childElementCount > 400) box.firstChild.remove();
  box.scrollTop = box.scrollHeight;
}

async function submitJob(promise, label) {
  try {
    const job = await promise;
    log(`#${job.id} ${label} — queued`, "start");
  } catch (e) {
    log(`${label}: ${e.message}`, "error");
  }
}

// --- status ---------------------------------------------------------------------------------

async function refreshStatus() {
  try {
    state.status = await api("/api/status");
  } catch { return; }
  const s = state.status;
  const llm = $("#pill-llm");
  llm.textContent = s.llm ? `LLM ${s.model || ""}` : "LLM offline";
  llm.className = `pill ${s.llm ? "ok" : "down"}`;
  llm.title = s.llm ? s.base_url : `No LLM at ${s.base_url}. Start one with scripts/llm-up.sh — parameter edits and playtests still work.`;
  const gd = $("#pill-godot");
  gd.textContent = s.godot ? "Godot ready" : "Godot missing";
  gd.className = `pill ${s.godot ? "ok" : "down"}`;
  document.querySelectorAll("button.llm").forEach((b) => { b.disabled = !s.llm; b.title = s.llm ? "" : llm.title; });
}

function setBusy(delta) {
  state.running = Math.max(0, state.running + delta);
  const p = $("#pill-job");
  p.textContent = state.running ? `working… (${state.running})` : "idle";
  p.className = `pill ${state.running ? "busy" : "idle"}`;
}

// --- projects -------------------------------------------------------------------------------

async function loadProjects() {
  state.projects = await api("/api/projects");
  const ul = $("#project-list");
  ul.replaceChildren(...state.projects.map((p) =>
    h("li", { class: p.name === state.current ? "active" : "", onclick: () => openProject(p.name), "data-name": p.name },
      h("span", { text: p.title }),
      h("span", { class: "badge", text: `${p.genre}${p.studio ? "" : " · graph"}` }))));
  if (!state.projects.length) ul.append(h("li", { class: "muted", text: "No games yet." }));
}

async function openProject(name, { keepGame = false } = {}) {
  const changed = state.current !== name;
  state.current = name;
  document.querySelectorAll("#project-list li").forEach((li) => li.classList.toggle("active", li.dataset.name === name));
  state.detail = await api(`/api/projects/${encodeURIComponent(name)}`);
  const d = state.detail;
  $("#stage-empty").hidden = true;
  $("#stage-noweb").hidden = d.web;
  const frame = $("#game");
  if (d.web && (changed || !keepGame || !frame.src)) frame.src = `/game/${encodeURIComponent(name)}/`;
  if (!d.web) frame.removeAttribute("src");
  if (changed) clearSelection();
  renderDesks();
}

// --- desks ----------------------------------------------------------------------------------

function renderDesks() {
  renderDesigner();
  renderArtist();
  renderDeveloper();
  renderQA();
  if (state.selected) renderSelection();
}

function chips(items) {
  return h("div", { class: "chips" }, items.map((t) => h("span", { class: "chip", text: t })));
}

function renderDesigner() {
  const d = state.detail;
  const box = $("#tab-designer");
  if (!d) return box.replaceChildren();
  const rows = [];
  const kv = (k, v) => rows.push(h("dt", { text: k }), h("dd", {}, v));
  if (d.brief) {
    const b = d.brief;
    kv("Title", b.title);
    kv("Genre", `${b.genre} · ${b.palette} palette`);
    kv("Goal", b.goal + (b.goal === "score_target" ? ` (${b.score_target})` : b.goal === "survive" ? ` (${b.survive_seconds}s)` : ""));
    kv("Player", chips([b.player.character, ...b.player.abilities, `jump ${b.player.jump_tiles} tiles`, `${b.player.speed}`, `${b.player.health} hp`]));
    kv("Enemies", chips(b.enemies.map((e) => `${e.count}× ${e.name} (${e.archetype})`)));
    kv("Pickups", `${b.collectible.count}× ${b.collectible.name}` + (b.health_pickups ? ` · ${b.health_pickups} hearts` : ""));
    kv("Level", `${b.length} · difficulty ${b.difficulty} · ${b.hazards.join(", ") || "no hazards"}`);
    kv("Feel", `${b.feel} · juice ${b.juice}`);
    kv("Intro", b.intro);
  } else {
    kv("Title", d.title);
    kv("Genre", d.genre);
    kv("Entities", chips(Object.keys(d.entities)));
  }
  const parts = [h("dl", { class: "kv" }, rows), h("h2", { text: "Rules" }),
    h("ul", { class: "changes" }, d.rules.map((r) => h("li", { text: `on ${r.on}${r.if ? ` if ${r.if}` : ""} → ${[].concat(r.do).join(", ")}` })))];
  if (d.history.length) parts.push(h("h2", { text: "Tweaks" }), h("ul", { class: "changes" }, d.history.map((x) => h("li", {}, h("b", { text: x.request }), h("div", { class: "muted", text: x.changes.join(" · ") || "no change" })))));
  if (d.overrides.length) parts.push(h("h2", { text: `Studio edits (${d.overrides.length})` }), h("ul", { class: "changes" }, d.overrides.map((o) => h("li", { class: "muted", text: describePatch(o) }))));
  if (d.tuning.length) parts.push(h("h2", { text: "Playtest tuning" }), h("ul", { class: "changes" }, d.tuning.map((t) => h("li", { class: "muted", text: `${t.entity}.${t.component}.${t.param} = ${t.value}` }))));
  box.replaceChildren(...parts);
}

function describePatch(p) {
  const out = [];
  (p.set_params || []).forEach((s) => out.push(`${s.entity}.${s.component}.${s.param} = ${s.value}`));
  (p.add_components || []).forEach((a) => out.push(`+${a.component} on ${a.entity}`));
  Object.keys(p.add_entities || {}).forEach((n) => out.push(`+entity ${n}`));
  (p.add_rules || []).forEach((r) => out.push(`+rule on ${r.on}`));
  return out.join(" · ");
}

function renderArtist() {
  const d = state.detail;
  const box = $("#tab-artist");
  if (!d) return box.replaceChildren();
  const cards = Object.entries(d.entities).map(([name, e]) =>
    h("div", { class: "sprite-card", onclick: () => select(name) },
      h("div", { class: "thumb" }, e.sprite
        ? h("img", { src: `/files/${encodeURIComponent(d.name)}/sprites/${encodeURIComponent(name)}.png?t=${Date.now()}`, alt: name })
        : h("span", { class: "muted", text: "shape" })),
      h("div", { text: name })));
  box.replaceChildren(h("p", { class: "muted", text: "Sprite sheets, one row per animation. Click one to select the entity." }), h("div", { class: "gallery" }, cards));
}

function paramInput(entity, comp, p) {
  const send = (value) => submitJob(api(`/api/projects/${encodeURIComponent(state.current)}/params`, { entity, component: comp, param: p.name, value }), `${entity}.${comp}.${p.name} = ${value}`);
  let input;
  if (p.type === "bool") {
    input = h("input", { type: "checkbox", onchange: (e) => send(e.target.checked) });
    input.checked = !!p.value;
  } else if (p.choices) {
    input = h("select", { onchange: (e) => send(e.target.value) }, p.choices.map((c) => h("option", { value: c, text: c, selected: c === p.value })));
  } else if (p.type === "int" || p.type === "float") {
    const step = p.type === "int" ? 1 : (Math.abs(p.max ?? 1) > 50 ? 1 : 0.01);
    input = h("input", { type: "number", value: p.value, min: p.min ?? null, max: p.max ?? null, step,
      onchange: (e) => { const v = p.type === "int" ? parseInt(e.target.value, 10) : parseFloat(e.target.value); if (!Number.isNaN(v)) send(v); } });
  } else {
    input = h("input", { type: "text", value: p.value ?? "", onchange: (e) => send(e.target.value) });
  }
  return h("div", { class: `param ${p.set ? "set" : ""}`, title: p.doc || "" }, h("label", { text: p.name }), input);
}

function renderDeveloper() {
  const d = state.detail;
  const box = $("#tab-developer");
  if (!d) return box.replaceChildren();
  const items = Object.entries(d.entities).map(([name, e]) => {
    const det = h("details", { class: `entity ${state.selected === name ? "selected" : ""}`, "data-entity": name, open: state.selected === name },
      h("summary", {}, h("span", { text: name }), h("span", { class: "badge", text: `${e.body}${e.team ? " · " + e.team : ""}` })),
      Object.entries(e.components).map(([cname, c]) => h("div", { class: "component" },
        h("h4", { text: cname, title: c.doc }),
        c.params.length ? c.params.map((p) => paramInput(name, cname, p)) : h("div", { class: "muted", text: "no parameters" }))));
    return det;
  });
  box.replaceChildren(h("p", { class: "muted", text: "Edit any parameter: the game rebuilds and reloads (no LLM needed). Bold = set by the game, grey = default." }), ...items);
}

function renderQA() {
  const d = state.detail;
  const box = $("#tab-qa");
  if (!d) return box.replaceChildren();
  const run = (tune) => submitJob(api(`/api/projects/${encodeURIComponent(d.name)}/playtest`, { tune }), tune ? "playtest + tune" : "playtest");
  const parts = [h("div", { class: "row" },
    h("button", { onclick: () => run(false), text: "Run playtest" }),
    h("button", { class: "primary", onclick: () => run(true), text: "Run + tune" }))];
  const pt = d.playtest;
  if (!pt) {
    parts.push(h("p", { class: "muted", text: "Bots (novice / average / expert) play the game headless, report where and why they die, and can tune parameters within safe bounds." }));
  } else {
    const prof = pt.final.profiles;
    parts.push(h("table", { class: "stats" },
      h("tr", {}, ["profile", "won", "deaths", "top causes", "pickups"].map((t) => h("th", { text: t }))),
      Object.values(prof).map((p) => h("tr", {},
        h("td", { text: p.profile }), h("td", { text: `${p.wins}/${p.runs}` }), h("td", { text: p.deaths }),
        h("td", { text: Object.entries(p.causes).slice(0, 3).map(([k, v]) => `${k} ${v}`).join(", ") || "—" }),
        h("td", { text: `${Math.round(p.pickup_rate * 100)}%` })))));
    parts.push(h("p", { class: "muted", text: `score ${pt.score.baseline} → ${pt.score.final} (lower is better) · difficulty ${pt.difficulty} · targets ${JSON.stringify(pt.targets)}` }));
    if (pt.changes.length) parts.push(h("h2", { text: "Tuning applied" }), h("ul", { class: "changes" }, pt.changes.map((c) => h("li", {}, h("b", { text: `${c.entity}.${c.component}.${c.param} = ${c.value}` }), h("div", { class: "muted", text: c.reason })))));
    if (pt.final.level_issues.length) parts.push(h("h2", { text: "Level issues" }), h("ul", { class: "issues" }, pt.final.level_issues.map((i) => h("li", { text: i }))));
    parts.push(h("img", { class: "heatmap", src: `/files/${encodeURIComponent(d.name)}/playtest/heatmap.png?t=${Date.now()}`, alt: "death heatmap" }));
  }
  box.replaceChildren(...parts);
}

// --- selection (click-to-edit) --------------------------------------------------------------

function select(entity) {
  if (!state.detail || !state.detail.entities[entity]) return;
  state.selected = entity;
  renderSelection();
  renderDeveloper();
  showTab("developer");
  const el = document.querySelector(`details[data-entity="${CSS.escape(entity)}"]`);
  if (el) el.scrollIntoView({ block: "nearest", behavior: "smooth" });
  $("#ask-input").focus();
}

function renderSelection() {
  const e = state.detail && state.detail.entities[state.selected];
  if (!e) return clearSelection();
  $("#selection").hidden = false;
  $("#sel-name").textContent = state.selected;
  $("#sel-summary").textContent = Object.keys(e.components).join(" · ") || "no components";
}

function clearSelection() {
  state.selected = null;
  $("#selection").hidden = true;
}

window.addEventListener("message", (ev) => {
  const data = ev.data;
  if (data && data.spawnpoint === "select" && typeof data.entity === "string") {
    log(`selected ${data.entity} (${data.node}) in the game`);
    select(data.entity);
  }
});

// --- tabs & forms ---------------------------------------------------------------------------

function showTab(name) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".desk").forEach((d) => { d.hidden = d.id !== `tab-${name}`; });
}
document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => showTab(t.dataset.tab)));

$("#new-game").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const prompt = $("#prompt").value.trim();
  if (!prompt) return;
  submitJob(api("/api/create", { prompt, playtest: $("#opt-playtest").checked, creative: $("#opt-creative").checked }), `create “${prompt}”`);
});

$("#tweak").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const request = $("#tweak-input").value.trim();
  if (!request || !state.current) return;
  submitJob(api(`/api/projects/${encodeURIComponent(state.current)}/tweak`, { request }), `tweak “${request}”`);
  $("#tweak-input").value = "";
});

$("#ask").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const request = $("#ask-input").value.trim();
  if (!request || !state.current || !state.selected) return;
  submitJob(api(`/api/projects/${encodeURIComponent(state.current)}/entity`, { entity: state.selected, request }), `${state.selected}: “${request}”`);
  $("#ask-input").value = "";
});

$("#sel-close").addEventListener("click", () => { clearSelection(); renderDeveloper(); });
$("#btn-export").addEventListener("click", () => state.current && submitJob(api(`/api/projects/${encodeURIComponent(state.current)}/export`, {}), "web build"));

// --- live events ----------------------------------------------------------------------------

function connectEvents() {
  const es = new EventSource("/api/events");
  es.onmessage = async (msg) => {
    const ev = JSON.parse(msg.data);
    const job = ev.job;
    switch (ev.type) {
      case "started": setBusy(+1); log(`#${job.id} ${job.kind}${job.project ? " " + job.project : ""} — running`, "start"); break;
      case "log": log(`#${ev.job}  ${ev.message}`); break;
      case "reload":
        await loadProjects();
        if (!state.current) await openProject(ev.project);
        else if (ev.project === state.current) await openProject(ev.project, { keepGame: true });
        break;
      case "done":
        setBusy(-1);
        log(`#${job.id} ${job.kind} — done`, "done");
        await loadProjects();
        if (job.kind === "create" && job.result && job.result.project) await openProject(job.result.project);
        else if (job.project && job.project === state.current) await openProject(job.project, { keepGame: true });
        break;
      case "error": setBusy(-1); log(`#${job.id} ${job.kind} — failed: ${job.error}`, "error"); break;
    }
  };
  es.onerror = () => { /* EventSource reconnects by itself */ };
}

(async function main() {
  connectEvents();
  await refreshStatus();
  setInterval(refreshStatus, 30000);
  await loadProjects();
  if (state.projects.length) await openProject(state.projects[0].name);
})();
