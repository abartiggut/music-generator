const $ = (s) => document.querySelector(s);
const api = async (path, opts = {}) => {
  // Bei FormData (Datei-Upload) setzt der Browser Content-Type inkl. Boundary selbst — nicht überschreiben.
  // X-Lang: Meldungen des Servers (z. B. beim Update) kommen in der gewählten Sprache zurück.
  const headers = { "X-Lang": LANG, ...(opts.body instanceof FormData ? opts.headers : { "Content-Type": "application/json", ...opts.headers }) };
  const r = await fetch(path, { ...opts, headers });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail) || r.statusText);
  }
  return r.json();
};
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmt = (sec) => (isFinite(sec) ? `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, "0")}` : "");

// Stil-Karten, nach Art gruppiert; der Würfel mischt daraus einen Stil
const STYLE_GROUPS = {
  genre: ["trip hop", "downtempo", "dub", "deep house", "techno", "drum and bass", "post-rock", "neo-soul", "dark ambient", "boom bap", "orchestral",
    "pop", "rock", "hip hop", "electronic", "lo-fi", "jazz", "ambient", "synthwave", "acoustic", "cinematic"],
  vocals: ["female vocals", "male vocals"],
  instr: ["piano", "guitar", "808 bass"],
  mood: ["upbeat", "melancholic", "dreamy"],
};
const STYLE_TAGS = [...STYLE_GROUPS.genre, ...STYLE_GROUPS.vocals, ...STYLE_GROUPS.instr, ...STYLE_GROUPS.mood];
const SECTIONS = ["[intro]", "[verse]", "[pre-chorus]", "[chorus]", "[bridge]", "[outro]", "[instrumental]"];

let songs = [];
let currentId = null;
let onlyFav = false;       // Favoriten-Filter der Bibliothek
const openLyrics = new Set();   // Songs, deren generierte Lyrics gerade aufgeklappt sind
let folders = { folders: [], all: 0, none: 0 };
let curFolder = "";      // "" = alle, "none" = unsortiert, sonst Ordner-ID
try { curFolder = localStorage.getItem("folder") || ""; } catch {}
let dragging = false;    // während des Ziehens nicht neu zeichnen
let editingId = null;   // id des Songs, dessen Titel gerade bearbeitet wird

// Erstellungszeit anzeigen, bis ein Song zum ersten Mal abgespielt wurde (danach dauerhaft ausgeblendet)
let played = new Set();
try { played = new Set(JSON.parse(localStorage.getItem("played") || "[]")); } catch {}
const markPlayed = (id) => { played.add(id); try { localStorage.setItem("played", JSON.stringify([...played])); } catch {} };
const genTime = (s) => { const t = (Date.parse(s.finished_at) - Date.parse(s.created_at)) / 1000; return isFinite(t) && t >= 0 ? fmt(t) : null; };

// Würfel: zufälliger Prompt (Stimmung, Szene, Detail); der Stil bleibt deine Wahl
const R = {
  mood: ["dark", "dreamy", "melancholic", "hypnotic", "warm", "tense", "nostalgic", "euphoric", "lonely", "mysterious", "hopeful", "gritty", "serene", "haunting"],
  scene: ["a late night drive through a neon city", "a rainy afternoon in an empty café", "walking through fog at dawn", "an abandoned space station",
    "a quiet forest after snowfall", "a crowded market at sunset", "floating above the clouds", "a smoky club after midnight", "a desert road at sunrise",
    "an old arcade at closing time", "a lighthouse during a storm", "the last train home", "a rooftop above a sleeping city", "an underwater research lab"],
  detail: ["slow and spacious", "building gradually", "with a steady pulse", "sparse and minimal", "with swelling strings", "slightly dusty and worn",
    "with a soft melodic hook", "with a hypnotic repeating motif", "with deep warm bass", "with distant echoing textures"],
};
const pick = (a) => a[Math.floor(Math.random() * a.length)];
const randomPrompt = () => `${pick(R.mood)}, ${pick(R.scene)}, ${pick(R.detail)}`;

// ---------------------------------------------------------------- Formular
const form = $("#genForm");
function addChips(el, items, onClick) {
  el.innerHTML = items.map((t) => `<span class="chip">${esc(t)}</span>`).join("");
  el.querySelectorAll(".chip").forEach((c, i) => c.addEventListener("click", () => onClick(items[i])));
}
// Stil-Karten sind Schalter: an = steht im Stil-Feld (gold umrandet), aus = wird dort wieder entfernt
const styleParts = () => form.style.value.split(",").map((x) => x.trim()).filter(Boolean);
function syncStyleChips() {
  const have = new Set(styleParts().map((x) => x.toLowerCase()));
  $("#tagChips").querySelectorAll(".chip").forEach((c) => {
    const on = have.has(c.textContent.toLowerCase());
    c.classList.toggle("on", on); c.setAttribute("aria-pressed", on);
  });
}
addChips($("#tagChips"), STYLE_TAGS, (tag) => {
  const parts = styleParts(), rest = parts.filter((x) => x.toLowerCase() !== tag.toLowerCase());
  form.style.value = (rest.length < parts.length ? rest : [...parts, tag]).join(", ");
  syncStyleChips();
});
form.style.addEventListener("input", syncStyleChips);
addChips($("#sectionChips"), SECTIONS, (t) => {
  if (t === "[instrumental]") { form.instrumental.checked = true; syncLyrics(); return; }   // zurück zu ohne Gesang
  const f = form.lyrics, pos = f.selectionStart ?? f.value.length;
  const before = f.value.slice(0, pos), ins = (before && !before.endsWith("\n") ? "\n\n" : "") + t + "\n";
  f.value = before + ins + f.value.slice(pos);
  f.focus(); f.selectionStart = f.selectionEnd = pos + ins.length;
});
// Bubble-Slider: Füllstand + Wert im Knopf (BPM ganz links = Auto)
const SLIDER_FMT = { dur: (v) => fmt(v), int: (v) => String(v), temp: (v) => v.toFixed(2), bpm: (v, min) => (v <= min ? ["AUTO", true] : String(v)) };
function updateSlider(box) {
  const inp = box.querySelector("input"), min = +inp.min, max = +inp.max, v = +inp.value;
  box.style.setProperty("--p", (v - min) / (max - min));
  const out = SLIDER_FMT[box.dataset.fmt](v, min), span = box.querySelector(".knob span");
  span.textContent = Array.isArray(out) ? out[0] : out;
  span.classList.toggle("small", Array.isArray(out));
  if (inp.name === "variants") $("#genBtn").textContent = v > 1 ? t("generate_n", v) : t("generate");
}
const showDur = () => document.querySelectorAll(".slider").forEach(updateSlider);
document.querySelectorAll(".slider").forEach((b) => { b.querySelector("input").addEventListener("input", () => updateSlider(b)); updateSlider(b); });
// Lyrics: eingeklappt; bei Instrumental steht "[Instrumental]" im Feld, Klick ins Feld schaltet Instrumental aus
const LYRICS_PLACEHOLDER = "[verse]\n…\n\n[chorus]\n…";
let lyricsStash = "";
function syncLyrics() {
  const on = form.instrumental.checked, f = form.lyrics;
  if (on) { if (f.value !== "[Instrumental]") lyricsStash = f.value; f.value = "[Instrumental]"; }
  else if (f.value === "[Instrumental]") f.value = lyricsStash;
  f.classList.toggle("dim", on);
  // Leeres Feld ohne Instrumental = automatisch: das Modell schreibt die Lyrics erst beim Generieren
  const auto = !on && !f.value.trim();
  f.classList.toggle("auto", auto);
  f.placeholder = auto ? t("auto_ph") : LYRICS_PLACEHOLDER;
  $("#lyricsHint").textContent = on ? "[Instrumental]" : auto ? t("auto_lbl") : t("own_lyrics");
}
const TITLE = {
  adj: ["Midnight", "Velvet", "Neon", "Silent", "Golden", "Hollow", "Electric", "Faded", "Distant", "Crimson", "Slow", "Lunar", "Paper", "Glass", "Amber"],
  noun: ["Static", "Horizon", "Rain", "Echoes", "Signal", "Drift", "Skyline", "Mirror", "Ember", "Tide", "Orbit", "Harbor", "Afterglow", "Motel", "Garden"],
};
// ein bis zwei Genres, ein Instrument, eine Stimmung; Gesang nur, wenn der Song nicht instrumental ist
const randomStyle = () => {
  const parts = [pick(STYLE_GROUPS.genre)];
  if (Math.random() < 0.6) {
    let second;
    do second = pick(STYLE_GROUPS.genre); while (second === parts[0]);
    parts.push(second);
  }
  parts.push(pick(STYLE_GROUPS.instr), pick(STYLE_GROUPS.mood));
  if (!form.instrumental.checked) parts.push(pick(STYLE_GROUPS.vocals));
  return parts.join(", ");
};
const randomTitle = () => `${pick(TITLE.adj)} ${pick(TITLE.noun)}`;
function rollAnim(btn) { btn.classList.remove("roll"); void btn.offsetWidth; btn.classList.add("roll"); }
function rollDice(btn, field, gen) { field.value = gen(); rollAnim(btn); }
$("#diceBtn").addEventListener("click", (e) => { rollDice(e.currentTarget, form.prompt, randomPrompt); });
$("#titleDice").addEventListener("click", (e) => rollDice(e.currentTarget, form.title, randomTitle));
$("#styleDice").addEventListener("click", (e) => { rollDice(e.currentTarget, form.style, randomStyle); syncStyleChips(); });

// Lyrics-Würfel: lässt das Modell bei der Generierung eigene Lyrics schreiben (kein Text hier, nur "auto"),
// geht nur mit vorhandenem Prompt, weil das Modell sonst nichts hat, worüber es schreiben kann.
const lyricsDice = $("#lyricsDice");
lyricsDice.addEventListener("click", (e) => {
  e.preventDefault(); e.stopPropagation();   // <summary> soll dabei nicht auf-/zuklappen
  form.instrumental.checked = false; lyricsStash = ""; form.lyrics.value = "";
  syncLyrics();
  rollAnim(e.currentTarget);
});
form.instrumental.addEventListener("change", () => { syncLyrics(); if (!form.instrumental.checked) $("#lyricsBox").open = true; });
form.lyrics.addEventListener("focus", () => { if (form.instrumental.checked) { form.instrumental.checked = false; syncLyrics(); } });
form.lyrics.addEventListener("input", syncLyrics);
syncLyrics();

function readForm() {
  const d = Object.fromEntries(new FormData(form));
  const num = (k, def) => (d[k] === "" || d[k] == null ? def : Number(d[k]));
  return {
    folder_id: curFolder && curFolder !== "none" ? curFolder : null,
    title: d.title || "", prompt: d.prompt || "", style: d.style || "", lyrics: form.instrumental.checked ? "" : d.lyrics || "", instrumental: form.instrumental.checked, keep_caption: form.keep_caption.checked,
    duration: Number(form.duration.value), bpm: Number(form.bpm.value) <= Number(form.bpm.min) ? 0 : Number(form.bpm.value), keyscale: d.keyscale || "", timesignature: d.timesignature || "", vocal_language: form.instrumental.checked ? "" : d.vocal_language || "en",
    seed: num("seed", -1), variants: num("variants", 1),
    inference_steps: Number(form.inference_steps.value), lm_temperature: Number(form.lm_temperature.value),
  };
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!form.prompt.value.trim() && !form.style.value.trim()) { form.prompt.focus(); return; }
  const btn = $("#genBtn");
  if (btn.disabled) return;
  btn.disabled = true;
  try {
    await api("/api/generate", { method: "POST", body: JSON.stringify(readForm()) });
    refresh();
  } catch (err) { alert(t("error") + ": " + err.message); }
  setTimeout(() => { btn.disabled = false; }, 600);
});
form.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target.tagName === "INPUT") e.preventDefault(); });

// Auswahlfeld setzen; unbekannte Werte werden ergänzt (Tonart aus der Analyse) oder fallen auf Auto zurück
function setSelect(sel, val, add = false) {
  val = val || "";
  if (![...sel.options].some((o) => o.value === val)) {
    if (add) sel.add(new Option(val, val)); else val = "";
  }
  sel.value = val;
}

function fillForm(s) {
  const p = s.params;
  form.title.value = s.title || "";
  form.style.value = p.style ?? p.caption;   // ältere Songs haben nur einen Text
  form.prompt.value = p.prompt ?? ""; syncStyleChips();
  form.instrumental.checked = p.lyrics === "[Instrumental]";
  form.keep_caption.checked = true;   // Prompt wörtlich ist fest die Vorgabe
  lyricsStash = ""; form.lyrics.value = form.instrumental.checked ? "" : p.lyrics || "";
  syncLyrics(); $("#lyricsBox").open = !form.instrumental.checked && !!(p.lyrics || "").trim();
  form.duration.value = p.duration || 90;
  form.bpm.value = p.bpm || form.bpm.min;
  form.inference_steps.value = p.inference_steps || 50;
  form.lm_temperature.value = p.lm_temperature ?? 0.85;   // ältere Songs liefen mit der Modell-Vorgabe
  showDur();
  setSelect(form.keyscale, p.keyscale, true);
  setSelect(form.timesignature, p.timesignature);
  form.vocal_language.value = p.vocal_language || "en";
  form.seed.value = p.seed;
  form.variants.value = 1; showDur();
  $("#advBox").open = true;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// ---------------------------------------------------------------- Song-Upload (Analyse)
// Geheime Dropzone: das Logo. Unauffällig, bis man draufzeigt, zieht oder es gerade etwas tut.
const dz = $("#dropzone"), bubble = $("#dzBubble"), fileInput = $("#fileInput");
let dzHideTimer = null;
function dzState(cls, text) {
  clearTimeout(dzHideTimer);
  dz.className = "logo-wrap" + (cls ? ` ${cls}` : "");
  bubble.textContent = text || "";
  bubble.classList.toggle("show", !!text);
  if (cls === "ok") dzHideTimer = setTimeout(() => { dz.className = "logo-wrap"; bubble.classList.remove("show"); }, 4000);
}
async function analyzeFile(file) {
  if (!file) return;
  dzState("busy", t("analyzing", file.name));
  const body = new FormData(); body.append("audio", file);
  try {
    const r = await api("/api/analyze", { method: "POST", body });
    form.prompt.value = r.caption || "";
    form.style.value = ""; syncStyleChips();
    form.title.value = randomTitle();
   
    // Nur echter Text außerhalb von [Strukturmarkern] zählt als Gesang — sonst schreibt das
    // Modell manchmal Dinge wie "[Acoustic guitar intro]" gefolgt von "[Instrumental]".
    const hasVocals = (r.lyrics || "").replace(/\[[^\]]*\]/g, "").trim().length > 0;
    if (hasVocals) {
      // Song hat Gesang: nicht den transkribierten Text übernehmen, sondern wie beim Lyrics-Würfel
      // das Modell bei der Generierung selbst welche schreiben lassen (Prompt ist ja gerade gesetzt).
      form.instrumental.checked = false; lyricsStash = ""; form.lyrics.value = "";
      $("#lyricsBox").open = true;
      const lang = (r.vocal_language || "").toLowerCase();
      if ([...form.vocal_language.options].some(o => o.value === lang)) form.vocal_language.value = lang;
    } else { form.instrumental.checked = true; }
    syncLyrics();
    if (r.bpm) { form.bpm.value = r.bpm; }
    if (r.duration) form.duration.value = Math.min(+form.duration.max, Math.max(+form.duration.min, Math.round(r.duration / 5) * 5));
    showDur();
    setSelect(form.keyscale, r.keyscale, true);
    setSelect(form.timesignature, String(r.timesignature || ""));
    dzState("ok", t("analyzed", file.name));
    window.scrollTo({ top: 0, behavior: "smooth" });
  } catch (err) {
    dzState("err", `${t("error")}: ${err.message}`);
  }
}
dz.addEventListener("click", () => fileInput.click());
dz.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); } });
fileInput.addEventListener("change", () => analyzeFile(fileInput.files[0]));
["dragenter", "dragover"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("drag"); }));
["dragleave", "dragend"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("drag"); }));
dz.addEventListener("drop", (e) => { e.preventDefault(); dz.classList.remove("drag"); analyzeFile(e.dataTransfer.files[0]); });

// ---------------------------------------------------------------- Bibliothek
async function refresh() {
  let busy = true;   // bei einem Fehler (Server startet gerade neu) zügig erneut versuchen
  try {
    folders = await api("/api/folders");
    if (curFolder && curFolder !== "none" && !folders.folders.some((f) => f.id === curFolder)) setFolder("", false);
    if (!dragging) renderFolders();
    const q = new URLSearchParams({ q: $("#search").value, favorites: onlyFav, folder: curFolder });
    songs = await api("/api/songs?" + q);
    if (!editingId && !dragging) render();   // während des Umbenennens nicht neu zeichnen, sonst verliert das Feld den Fokus
    const qu = await api("/api/queue");
    busy = qu.running.length || qu.queued;
    libStats = qu.library; showLibStats();
  } catch {}
  clearTimeout(refresh.t);
  refresh.t = setTimeout(refresh, busy ? 1500 : 8000);
}

let libStats = null;
function showLibStats() {
  if (!libStats) return;
  const mb = libStats.bytes / 1048576, nf = (v, d) => v.toLocaleString(LANG, { maximumFractionDigits: d });
  $("#libStats").textContent = libStats.count ? `${libStats.count} Songs · ${mb >= 1024 ? nf(mb / 1024, 1) + " GB" : nf(mb, 0) + " MB"}` : "";
}

function render() {
  const lib = $("#library");
  if (!songs.length) { lib.innerHTML = `<div class="empty">${t("empty")}</div>`; return; }
  lib.innerHTML = songs.map((s, i) => {
    const m = s.result_meta || {}, p = s.params || {};
    const newGroup = i > 0 && songs[i - 1].group_id !== s.group_id;
    const title = (s.title || s.caption.split(",").slice(0, 3).join(",")) + (s.letter ? ` ${s.letter}` : "");
    const meta = [
      m.bpm && `${m.bpm}BPM`,
      p.inference_steps ? `${p.inference_steps}IT` : null,
      p.lm_temperature != null ? `${(+p.lm_temperature).toFixed(1)}VAR` : null,
      m.keyscale, m.duration && fmt(m.duration),
    ].filter(Boolean).join(" · ");
    const playing = s.id === currentId && ws?.isPlaying();
    let left, state = "";
    if (s.status === "done") left = `<button class="aktion round" data-a="play" aria-label="${t("play")}">${playing ? "❚❚" : "▶"}</button>`;
    else if (s.status === "error") left = `<div class="slot err" title="${esc(s.message)}">!</div>`;
    else if (s.status === "running") left = `<div class="slot run">♪</div>`;
    else left = `<div class="slot">${s.status === "cancelled" ? "✕" : "…"}</div>`;
    if (s.status === "running") state = `<div class="s run">${esc(s.message || "0:00")}</div><div class="mini-bar"></div>`;
    if (s.status === "queued") state = `<div class="s">${t("waiting")}</div>`;
    if (s.status === "cancelled") state = `<div class="s">${t("cancelled")}</div>`;
    if (s.status === "error") state = `<div class="s err" title="${esc(s.message)}">${t("error")} · ${esc(shortErr(s.message))}</div>`;
    if (s.status === "done" && !played.has(s.id)) { const tm = genTime(s); if (tm) state = `<div class="s took">${t("created_in")} ${tm}</div>`; }
    // Vom Modell geschriebener Text (nur bei Songs mit Gesang)
    const lyr = s.status === "done" && s.lyrics !== "[Instrumental]" && /[^\s\[\]]/.test((m.lyrics || "").replace(/\[[^\]]*\]/g, "")) ? m.lyrics.trim() : "";
    const actions = [
      s.status === "done" && `<button class="sek icon ${s.favorite ? "on" : ""}" data-a="fav" title="${t("fav")}">${s.favorite ? "★" : "☆"}</button>`,
      s.status === "done" && `<a class="download icon fmt" href="${s.url}?download=1" title="${t("download")}">${s.file.endsWith(".wav") ? "WAV" : "MP3"}</a>`,
      lyr && `<button class="sek icon txt ${openLyrics.has(s.id) ? "on" : ""}" data-a="lyrics" title="${t("show_lyrics")}">TXT</button>`,
      folders.folders.length > 0 && `<button class="sek icon" data-a="move" title="${t("move")}"><svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg></button>`,
      `<button class="sek icon" data-a="more" title="${t("more")}">＋</button>`,
      `<button class="sek icon" data-a="reuse" title="${t("reuse")}"><svg viewBox="0 0 24 24" width="15" height="15" fill="currentColor" aria-hidden="true"><path d="M12 3l7 7h-4v10h-6V10H5l7-7z"/></svg></button>`,
      ["error", "cancelled"].includes(s.status) && `<button class="sek icon" data-a="retry" title="${t("retry")}">↻</button>`,
      `<button class="sek icon del" data-a="del" title="${["queued", "running"].includes(s.status) ? t("cancel") : t("del")}">✕</button>`,
    ].filter(Boolean).join("");
    return `<div class="song ${s.id === currentId ? "playing" : ""}${newGroup ? " new-group" : ""}" data-id="${s.id}" draggable="${folders.folders.length > 0 && s.id !== editingId}">
      ${left}
      <div style="min-width:0">${s.id === editingId
        ? `<input class="t-edit" data-id="${s.id}" value="${esc(s.title || "")}" placeholder="${esc(s.caption.split(",").slice(0, 3).join(","))}">`
        : `<div class="t" data-a="rename" title="${t("rename")}">${esc(title)}</div>`
      }<div class="m" title="${t("meta_tip")}">${esc(meta)}</div>${state}</div>
      <div class="actions">${actions}</div>${lyr && openLyrics.has(s.id) ? `<pre class="lyr">${esc(lyr)}</pre>` : ""}</div>`;
  }).join("");
  // Symbolknöpfe: Tooltip auch als Name für Screenreader
  lib.querySelectorAll("button[title]:not([aria-label]), a[title]:not([aria-label])")
    .forEach((el) => el.setAttribute("aria-label", el.title));
}
function shortErr(msg = "") {
  if (/nicht erreichbar/i.test(msg)) return t("err_offline");
  if (/Codes/i.test(msg)) return t("err_codes");
  if (/Zeitüberschreitung/i.test(msg)) return t("err_timeout");
  return t("err_details");
}

$("#library").addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-a]");
  if (!btn) return;
  const id = btn.closest(".song").dataset.id, s = songs.find((x) => x.id === id);
  const a = btn.dataset.a;
  if (a === "play") return play(s);
  if (a === "rename") { editingId = id; render(); const inp = $(`.t-edit[data-id="${id}"]`); inp?.focus(); inp?.select(); return; }
  if (a === "fav") await api(`/api/songs/${id}`, { method: "PATCH", body: JSON.stringify({ favorite: !s.favorite }) });
  if (a === "reuse") return fillForm(s);
  if (a === "move") return moveMenu(btn, id);
  if (a === "lyrics") { openLyrics.has(id) ? openLyrics.delete(id) : openLyrics.add(id); return render(); }
  if (a === "retry") await api(`/api/songs/${id}/retry`, { method: "POST" });
  if (a === "more") {
    const p = s.params;
    await api("/api/generate", { method: "POST", body: JSON.stringify({ ...p, instrumental: false, keep_caption: p.use_cot_caption !== true, title: s.title || "", seed: -1, variants: 1, group_id: s.group_id, folder_id: s.folder_id }) });
  }
  if (a === "del") {
    if (!["queued", "running"].includes(s.status) && !confirm(t("del_q"))) return;
    await api(`/api/songs/${id}`, { method: "DELETE" }).catch((err) => alert(err.message));
  }
  refresh();
});
// ---------------------------------------------------------------- Ordner
function setFolder(id, reload = true) {
  curFolder = id;
  try { localStorage.setItem("folder", id); } catch {}
  if (reload) refresh();
}
function renderFolders() {
  const chip = (id, name, n) => `<span class="chip fold${id === curFolder ? " on" : ""}" data-f="${id}" title="${esc(name)}">${esc(name)} <b>${n}</b></span>`;
  const cur = folders.folders.find((f) => f.id === curFolder);
  $("#folderBar").innerHTML =
    chip("", t("f_all"), folders.all) +
    (folders.folders.length ? chip("none", t("f_none"), folders.none) : "") +
    folders.folders.map((f) => chip(f.id, f.name, f.count)).join("") +
    `<button type="button" class="chip add" data-fa="new" title="${t("f_new")}" aria-label="${t("f_new")}">＋</button>` +
    `<span class="fold-actions">` +
    (cur ? `<button type="button" class="sek mini" data-fa="rename">${t("f_rename")}</button><button type="button" class="sek mini" data-fa="delete">${t("f_delete")}</button>` : "") +
    `<a class="download mini" data-fa="zip" href="/api/download?folder=${encodeURIComponent(curFolder)}" title="${t("f_zip_tip")}">${cur ? t("f_zip") : t("f_zip_all")}</a></span>`;
}
async function moveSong(id, folderId) {
  await api(`/api/songs/${id}`, { method: "PATCH", body: JSON.stringify({ folder_id: folderId === "none" ? null : folderId }) }).catch((e) => alert(e.message));
  refresh();
}
$("#folderBar").addEventListener("click", async (e) => {
  const c = e.target.closest("[data-f]");
  if (c) return setFolder(c.dataset.f);
  const a = e.target.closest("[data-fa]")?.dataset.fa;
  const cur = folders.folders.find((f) => f.id === curFolder);
  try {
    if (a === "new") {
      const name = prompt(t("f_name_q"));
      if (name?.trim()) setFolder((await api("/api/folders", { method: "POST", body: JSON.stringify({ name }) })).id);
    } else if (a === "rename" && cur) {
      const name = prompt(t("f_name_q"), cur.name);
      if (name?.trim()) { await api(`/api/folders/${cur.id}`, { method: "PATCH", body: JSON.stringify({ name }) }); refresh(); }
    } else if (a === "delete" && cur) {
      if (confirm(t("f_delete_q", cur.name))) { await api(`/api/folders/${cur.id}`, { method: "DELETE" }); setFolder(""); }
    } else if (a === "zip" && !songs.some((s) => s.status === "done")) { e.preventDefault(); }
  } catch (err) { alert(t("error") + ": " + err.message); }
});
// Song auf einen Ordner ziehen
// (Text in den Lyrics soll markierbar bleiben, Knöpfe sollen klicken statt ziehen)
$("#library").addEventListener("mousedown", (e) => {
  const row = e.target.closest(".song");
  if (row) row.draggable = folders.folders.length > 0 && !e.target.closest(".lyr, .t-edit, button, a");
});
$("#library").addEventListener("dragstart", (e) => {
  const row = e.target.closest?.(".song");
  if (!row) return;
  dragging = true;
  e.dataTransfer.setData("text/song", row.dataset.id);
  e.dataTransfer.effectAllowed = "move";
});
document.addEventListener("dragend", () => { dragging = false; document.querySelectorAll(".chip.drop").forEach((c) => c.classList.remove("drop")); });
const dropChip = (e) => (e.dataTransfer.types.includes("text/song") ? e.target.closest?.(".chip.fold:not([data-f=''])") : null);
$("#folderBar").addEventListener("dragover", (e) => { const c = dropChip(e); if (c) { e.preventDefault(); c.classList.add("drop"); } });
$("#folderBar").addEventListener("dragleave", (e) => e.target.closest?.(".chip")?.classList.remove("drop"));
$("#folderBar").addEventListener("drop", (e) => {
  const c = dropChip(e);
  if (!c) return;
  e.preventDefault(); dragging = false;
  moveSong(e.dataTransfer.getData("text/song"), c.dataset.f);
});
// Ordner-Knopf in der Songzeile: kleines Menü mit allen Ordnern
function moveMenu(btn, id) {
  document.querySelector(".movemenu")?.remove();
  const s = songs.find((x) => x.id === id), m = document.createElement("div");
  m.className = "movemenu";
  m.innerHTML = [["none", t("f_none")], ...folders.folders.map((f) => [f.id, f.name])]
    .map(([fid, name]) => `<button type="button" data-f="${fid}" class="${(s.folder_id || "none") === fid ? "on" : ""}">${esc(name)}</button>`).join("");
  document.body.append(m);
  const r = btn.getBoundingClientRect();
  m.style.top = `${Math.min(r.bottom + 4, innerHeight - m.offsetHeight - 8)}px`;
  m.style.left = `${Math.max(8, Math.min(r.left, innerWidth - m.offsetWidth - 8))}px`;
  m.addEventListener("click", (e) => { const b = e.target.closest("[data-f]"); if (b) { m.remove(); moveSong(id, b.dataset.f); } });
  setTimeout(() => document.addEventListener("click", function close(e) { if (!m.contains(e.target)) { m.remove(); document.removeEventListener("click", close); } }), 0);
}
window.addEventListener("scroll", () => document.querySelector(".movemenu")?.remove(), true);

async function commitRename(inp) {
  const id = inp.dataset.id;
  if (editingId !== id) return;   // per Escape schon abgebrochen
  editingId = null;
  const s = songs.find((x) => x.id === id), title = inp.value.trim();
  if (s && title !== (s.title || "")) await api(`/api/songs/${id}`, { method: "PATCH", body: JSON.stringify({ title }) });
  refresh();
}
$("#library").addEventListener("focusout", (e) => { const inp = e.target.closest(".t-edit"); if (inp) commitRename(inp); });
$("#library").addEventListener("keydown", (e) => {
  const inp = e.target.closest(".t-edit");
  if (!inp) return;
  if (e.key === "Enter") { e.preventDefault(); inp.blur(); }
  if (e.key === "Escape") { e.preventDefault(); editingId = null; render(); }
});
$("#search").addEventListener("input", () => { clearTimeout(refresh.s); refresh.s = setTimeout(refresh, 250); });
$("#onlyFav").addEventListener("click", (e) => {
  onlyFav = !onlyFav;
  e.currentTarget.setAttribute("aria-pressed", onlyFav);
  e.currentTarget.textContent = onlyFav ? "★" : "☆";
  refresh();
});

// ---------------------------------------------------------------- Player
let ws = null;
function initPlayer() {
  const css = getComputedStyle(document.documentElement);
  ws = WaveSurfer.create({
    container: "#waveform", height: 44, barWidth: 2, barGap: 1, barRadius: 2,
    waveColor: css.getPropertyValue("--border").trim() || "#2a2e38",
    progressColor: css.getPropertyValue("--accent2").trim() || "#d1a75c", cursorWidth: 0,
  });
  const upd = () => { $("#pTime").textContent = `${fmt(ws.getCurrentTime())} / ${fmt(ws.getDuration())}`; };
  ws.on("timeupdate", upd); ws.on("ready", upd);
  ws.on("play", () => { $("#playBtn").textContent = "❚❚"; render(); });
  ws.on("pause", () => { $("#playBtn").textContent = "▶"; render(); });
  ws.on("finish", () => { $("#playBtn").textContent = "▶"; render(); });
  $("#playBtn").onclick = () => ws.playPause();
  initVolume();
  document.addEventListener("keydown", (e) => {
    if (e.code === "Space" && !["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(e.target.tagName) && currentId) { e.preventDefault(); ws.playPause(); }
  });
}
// Lautstärke: Regler klappt beim Zeigen auf den Lautsprecher aus; Klick auf den Lautsprecher = stumm
let volume = 1, muted = false;
try {
  const saved = localStorage.getItem("volume");
  if (saved !== null && isFinite(+saved)) volume = Math.min(1, Math.max(0, +saved));
  muted = localStorage.getItem("muted") === "1";
} catch {}
function applyVolume() {
  ws?.setVolume(muted ? 0 : volume);
  const v = muted ? 0 : volume;
  $("#vol").dataset.level = v === 0 ? "off" : v < 0.5 ? "low" : "high";
  $("#volRange").value = Math.round(volume * 100);
  $("#vol").style.setProperty("--v", volume);
  $("#volBtn").title = $("#volBtn").ariaLabel = t(muted ? "unmute" : "mute");
  try { localStorage.setItem("volume", String(volume)); localStorage.setItem("muted", muted ? "1" : "0"); } catch {}
}
function initVolume() {
  $("#volRange").addEventListener("input", (e) => { volume = e.target.value / 100; muted = false; applyVolume(); });
  $("#volBtn").addEventListener("click", () => { muted = !muted; if (!muted && volume === 0) volume = 0.5; applyVolume(); });
  applyVolume();
}

async function play(s) {
  if (!ws) initPlayer();
  if (currentId === s.id) return ws.playPause();
  if (!played.has(s.id)) { markPlayed(s.id); render(); }
  currentId = s.id;
  $("#player").hidden = false;
  if (!play.ro) {   // Höhe des Players ändert sich, sobald die Wellenform geladen ist
    play.ro = new ResizeObserver(() => document.documentElement.style.setProperty("--player-h", $("#player").offsetHeight + "px"));
    play.ro.observe($("#player"));
  }
  $("#pTitle").textContent = s.title || s.caption;
  $("#pTitle").title = `Seed ${s.seed}` + (s.result_meta?.keyscale ? ` · ${s.result_meta.keyscale}` : "");
  await ws.load(s.url);
  ws.play();
  render();
}

// ---------------------------------------------------------------- Einstellungen & Status
async function checkHealth() {
  const el = $("#status");
  try {
    const h = await api("/api/health");
    el.className = "box small " + (h.ok ? "" : "err");
    el.textContent = h.engine === "mock" ? "Mock" : h.ok ? "" : t("offline");   // bei "alles ok" nichts anzeigen
    el.title = h.error || (h.props ? `${t("models")}: ${Object.values(h.props.models || {}).flat().join(", ")}` : t("model_server"));
    return h;
  } catch { el.className = "box small err"; el.textContent = t("backend_offline"); }
}
const dlg = $("#settingsDlg"), sf = $("#settingsForm");
let runtime = { capabilities: {} };
async function loadRuntime() {
  runtime = await api("/api/runtime").catch(() => ({ mode: "direct", capabilities: {} }));
  $("#runtimeInfo").textContent = t(`runtime_${runtime.mode || "direct"}`);
  $("#connectionHint").hidden = !runtime.connection_locked;
  for (const k of ["engine", "server_url", "lm_url"]) sf[k].disabled = !!runtime.connection_locked;
  $("#stopBtn").disabled = !runtime.capabilities?.shutdown;
  $("#stopBtn").title = runtime.capabilities?.shutdown ? "" : t("runtime_unmanaged");
}
$("#btnSettings").onclick = async () => {
  const s = await api("/api/settings");
  for (const k of ["engine", "server_url", "lm_url", "timeout_minutes"]) sf[k].value = s[k];
  $("#settingsError").hidden = true;
  await loadRuntime();
  dlg.showModal();
};
const saveSettings = () => api("/api/settings", { method: "PUT", body: JSON.stringify({
  engine: sf.engine.value, server_url: sf.server_url.value.trim(), lm_url: sf.lm_url.value.trim(), timeout_minutes: Number(sf.timeout_minutes.value) || 30 }) });
// Anordnung: untereinander oder Generator links / Bibliothek rechts
function setLayout(l) {
  document.querySelector(".wrap").classList.toggle("side", l === "side");
  document.documentElement.classList.toggle("side", l === "side");
  document.querySelectorAll("[data-layout]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.layout === l)));
  try { localStorage.setItem("layout", l); } catch {}
}
document.querySelectorAll("[data-layout]").forEach(b => b.onclick = () => setLayout(b.dataset.layout));
try { setLayout(localStorage.getItem("layout") === "side" ? "side" : "stack"); } catch { setLayout("stack"); }

// Updates von GitHub
const updInfo = $("#updInfo"), updList = $("#updList"), updApply = $("#updApply");
async function updCheck() {
  updApply.hidden = true; updList.hidden = true; updInfo.className = "small"; updInfo.textContent = t("upd_search");
  const r = await api("/api/update/check").catch(e => ({ ok: false, error: e.message }));
  if (!r.ok) { updInfo.className = "small err-t"; updInfo.textContent = r.error; return; }
  if (!r.behind) { updInfo.textContent = t("upd_current", r.current); return; }
  updInfo.textContent = t("upd_new", r.behind, r.current, r.latest);
  updList.replaceChildren(...r.changes.map(c => Object.assign(document.createElement("li"), { textContent: c })));
  updList.hidden = false;
  if (r.dirty) { updInfo.className = "small err-t"; updInfo.textContent += t("upd_dirty"); return; }
  if (!runtime.capabilities?.update) { updInfo.textContent += " · " + t("runtime_unmanaged"); return; }
  if (r.needs_install) updInfo.textContent += t("upd_install");
  updApply.hidden = false;
}
$("#updCheck").onclick = updCheck;
updApply.onclick = async () => {
  updApply.disabled = true; updInfo.className = "small"; updInfo.textContent = t("upd_loading");
  let res;
  try {
    res = await api("/api/update/apply", { method: "POST" });
  } catch (e) { updInfo.className = "small err-t"; updInfo.textContent = e.message; updApply.disabled = false; return; }
  updInfo.textContent = t("upd_restart");
  for (let i = 0; i < 60; i++) {   // warten, bis der neue Server antwortet
    await new Promise(r => setTimeout(r, 1000));
    try { const h = await fetch("/api/queue", { cache: "no-store" }); if (h.ok && i > 1) { if (res.needs_install) { updInfo.textContent = t("upd_restart_install"); return; } return location.reload(); } } catch {}
  }
  updInfo.className = "small err-t"; updInfo.textContent = t("upd_slow");
};
$("#btnSettings").addEventListener("click", () => { updInfo.textContent = ""; updList.hidden = true; updApply.hidden = true; updApply.disabled = false; });

// Server stoppen = „Music Generator OFF“ ausführen
$("#stopBtn").onclick = async () => {
  const qu = await api("/api/queue").catch(() => null);
  const busy = qu && (qu.running.length || qu.queued);
  if (!confirm(t(busy ? "stop_q_busy" : "stop_q"))) return;
  clearTimeout(refresh.t);
  try {
    await api("/api/shutdown", { method: "POST" });
    $("#stopBtn").disabled = true;
    $("#stopInfo").textContent = t("stopped");
  } catch (e) { $("#stopInfo").className = "small err-t"; $("#stopInfo").textContent = e.message; refresh(); }
};

sf.addEventListener("submit", async (event) => {
  if (event.submitter?.value !== "save") return;
  event.preventDefault();
  const button = $("#saveBtn");
  button.disabled = true;
  $("#settingsError").hidden = true;
  try {
    await saveSettings();
    dlg.close("save");
    checkHealth();
  } catch (error) {
    $("#settingsError").textContent = error.message;
    $("#settingsError").hidden = false;
  } finally { button.disabled = false; }
});

// Sprachumschalter (DE | EN)
document.querySelectorAll("[data-lang]").forEach((b) => b.addEventListener("click", () => setLang(b.dataset.lang)));
document.addEventListener("langchange", () => {
  showDur(); syncLyrics(); render(); renderFolders(); showLibStats(); checkHealth();
  updInfo.textContent = ""; updList.hidden = true; updApply.hidden = true;
  loadRuntime();
});

checkHealth();
setInterval(checkHealth, 15000);
refresh();
