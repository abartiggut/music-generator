// Oberflächensprache: Deutsch / Englisch. Statische Texte tragen data-i18n (Text), data-i18n-title,
// data-i18n-ph (Platzhalter) oder data-i18n-aria; dynamische Texte kommen über t("schlüssel").
const I18N = {
  de: {
    drop_aria: "Song hochladen und analysieren",
    drop_title: "Song hierher ziehen oder klicken — Stil und Tempo werden übernommen",
    brand_title: "Zur Alphatester-Webseite",
    title: "Titel", title_tip: "Nur zum Wiederfinden, hat keinen Einfluss auf die Musik.",
    title_ph: "optional", title_dice: "Zufälligen Titel würfeln",
    prompt: "Prompt", prompt_tip: "Deine Idee für den Song: Stimmung, Szene, Klang. Wird zusammen mit dem Stil ans Modell geschickt.",
    prompt_ph: "nächtliche Autofahrt durch eine Neonstadt, langsam und hypnotisch", prompt_dice: "Zufälligen Prompt würfeln",
    style: "Stil", style_tip: "Stilrichtung: Genre, Instrumente, Sound. Der Würfel mischt einen Stil, unter „Stile“ liegen Karten zum Anklicken.",
    style_dice: "Zufälligen Stil würfeln", styles: "Stile",
    length: "Länge", length_tip: "0:10 bis 5:00",
    bpm_tip: "Ganz links = Auto: Das Modell wählt das Tempo.",
    lyrics: "Lyrics", lyrics_tip: "Leer lassen: Das Modell schreibt eigene Lyrics. Die Sprache wählst du darunter (Standard: Englisch).",
    lyrics_dice: "Lyrics automatisch schreiben lassen (erst beim Generieren)",
    language: "Sprache", language_aria: "Sprache der Lyrics",
    en: "Englisch", de: "Deutsch", fr: "Französisch", es: "Spanisch", it: "Italienisch", pt: "Portugiesisch", ja: "Japanisch", ko: "Koreanisch", zh: "Chinesisch", ru: "Russisch",
    advanced: "Erweitert",
    iterations: "Iterationen", iterations_tip: "Diffusionsschritte der Klangerzeugung. Mehr = langsamer, ab etwa 50 kaum noch hörbar besser (Modell-Vorgabe: 50).",
    variance: "Varianz", variance_tip: "Wie mutig das Sprachmodell den Song plant. Niedriger = vorhersehbar, höher = abwechslungsreicher, zu hoch = zerfahren (Modell-Vorgabe: 0.85).",
    key: "Tonart", timesig: "Takt", ts_default: "4/4 (Standard)", ts_waltz: "3/4 (Walzer)", ts_march: "2/4 (Marsch)",
    seed_tip: "Gleicher Seed + gleiche Einstellungen = gleicher Song", seed_ph: "zufällig",
    versions: "Versionen", versions_tip: "Anzahl Versionen desselben Prompts, jede mit eigenem Seed. In der Bibliothek heißen sie A, B, C …",
    generate: "GENERIEREN", generate_n: (n) => `${n}× GENERIEREN`,
    library: "Bibliothek", search: "Suchen", only_fav: "Nur Favoriten zeigen", play: "Abspielen",
    auto_lbl: "[Automatisch]", own_lyrics: "eigene Lyrics",
    auto_ph: "[Automatisch]\nDas Modell schreibt die Lyrics erst beim Generieren, hier erscheint kein Text. Eigene Lyrics kannst du hier eintippen.",
    // Einstellungen
    connection: "Verbindung", connection_locked: "Zum Wechseln die App stoppen und Install erneut mit dem gewünschten Modus ausführen.",
    runtime_mock: "Testmodus · ohne KI-Modell", runtime_remote: "Musik-Engine auf Rechenserver", runtime_local: "Lokale Musik-Engine", runtime_direct: "Manuell gestartete Web-App",
    runtime_unmanaged: "Start-/Stoppsteuerung ist bei manuellem Start nicht verfügbar.",
    synth_srv: "Synthese-Server", synth_tip: "Lokale oder entfernte Musik-Engine (CUDA, Metal oder CPU)",
    lm_srv: "Sprachmodell-Server", lm_tip: "Leer = gleicher Server wie Synthese.", lm_ph: "Leer = gleicher Server",
    timeout: "Timeout (Min.)", mock: "Mock (Testton)",
    layout: "Anordnung", stacked: "Untereinander", side: "Nebeneinander", side_tip: "Generator links, Bibliothek rechts (ab ca. 1000 px Breite)",
    version: "Version", upd_check: "Nach Updates suchen", upd_apply: "JETZT AKTUALISIEREN",
    github: "GitHub", cancel: "Abbrechen", save: "SPEICHERN",
    offline: "Offline", backend_offline: "Backend offline",
    models: "Modelle", model_server: "Modellserver",
    // Upload
    analyzing: (n) => `Analysiere „${n}“ …`, analyzed: (n) => `„${n}“ analysiert — Stil übernommen.`, error: "Fehler",
    // Bibliothek
    empty: "Noch leer", waiting: "Wartet", cancelled: "Abgebrochen", created_in: "Erstellt in",
    fav: "Favorit", download: "Download", more: "Weitere Variante (neuer Seed)", reuse: "Einstellungen ins Formular übernehmen",
    show_lyrics: "Lyrics des Modells zeigen", retry: "Erneut versuchen", del: "Löschen", del_q: "Song löschen?", rename: "Klicken zum Umbenennen",
    meta_tip: "IT = Iterationen · VAR = Varianz",
    err_offline: "Server offline", err_codes: "Keine Codes", err_timeout: "Timeout", err_details: "Details im Tooltip",
    // Ordner
    f_all: "Alle", f_none: "Unsortiert", f_new: "Neuer Ordner", f_rename: "Umbenennen", f_delete: "Ordner löschen",
    f_zip: "Ordner laden", f_zip_all: "Alle laden", f_zip_tip: "Alle fertigen Songs dieser Ansicht als ZIP herunterladen",
    f_name_q: "Name des Ordners:", f_delete_q: (n) => `Ordner „${n}“ löschen? Die Songs bleiben erhalten und werden unsortiert.`,
    move: "In Ordner verschieben",
    servers: "Server", stop: "Server stoppen", github_info: "Repository im Browser öffnen",
    stop_q: "Die App und ihre lokalen Verbindungen stoppen? Eine entfernte Musik-Engine läuft weiter. Starten geht wieder mit „Music Generator ON“.",
    stop_q_busy: "Es laufen oder warten noch Songs. Trotzdem stoppen? Diese Aufträge werden abgebrochen und können später erneut gestartet werden.",
    stopped: "Gestoppt. Neu starten mit „Music Generator ON“.",
    mute: "Stumm", unmute: "Ton an", volume: "Lautstärke",
    // Updates
    upd_search: "Suche …", upd_current: (v) => `Aktuell (${v})`,
    upd_new: (n, a, b) => `${n} ${n > 1 ? "neue Updates" : "neues Update"} (${a} → ${b})`,
    upd_dirty: " · eigene Dateiänderungen, automatisch nicht möglich", upd_install: " · danach bitte einmal Install starten",
    upd_loading: "Lade herunter …", upd_restart: "Installiert, App startet neu …",
    upd_restart_install: "Aktualisiert. Bitte einmal Install starten (neue Modellversion), dann diese Seite neu laden.",
    upd_slow: "Neustart dauert ungewöhnlich lang. Bitte Music Generator ON starten.",
  },
  en: {
    drop_aria: "Upload and analyze a song",
    drop_title: "Drop a song here or click — style and tempo are picked up",
    brand_title: "Go to the Alphatester website",
    title: "Title", title_tip: "Only for finding it again, has no effect on the music.",
    title_ph: "optional", title_dice: "Roll a random title",
    prompt: "Prompt", prompt_tip: "Your idea for the song: mood, scene, sound. Sent to the model together with the style.",
    prompt_ph: "a night drive through a neon city, slow and hypnotic", prompt_dice: "Roll a random prompt",
    style: "Style", style_tip: "Style: genre, instruments, sound. The dice mixes a style, the cards under “Styles” can be clicked.",
    style_dice: "Roll a random style", styles: "Styles",
    length: "Length", length_tip: "0:10 to 5:00",
    bpm_tip: "Far left = Auto: the model picks the tempo.",
    lyrics: "Lyrics", lyrics_tip: "Leave empty: the model writes its own lyrics. Pick the language below (default: English).",
    lyrics_dice: "Let the model write the lyrics automatically (when generating)",
    language: "Language", language_aria: "Language of the lyrics",
    en: "English", de: "German", fr: "French", es: "Spanish", it: "Italian", pt: "Portuguese", ja: "Japanese", ko: "Korean", zh: "Chinese", ru: "Russian",
    advanced: "Advanced",
    iterations: "Iterations", iterations_tip: "Diffusion steps of the sound generation. More = slower, above about 50 hardly audibly better (model default: 50).",
    variance: "Variance", variance_tip: "How adventurous the language model plans the song. Lower = predictable, higher = more varied, too high = scattered (model default: 0.85).",
    key: "Key", timesig: "Time signature", ts_default: "4/4 (default)", ts_waltz: "3/4 (waltz)", ts_march: "2/4 (march)",
    seed_tip: "Same seed + same settings = same song", seed_ph: "random",
    versions: "Versions", versions_tip: "Number of versions of the same prompt, each with its own seed. In the library they are named A, B, C …",
    generate: "GENERATE", generate_n: (n) => `${n}× GENERATE`,
    library: "Library", search: "Search", only_fav: "Show favorites only", play: "Play",
    auto_lbl: "[Automatic]", own_lyrics: "own lyrics",
    auto_ph: "[Automatic]\nThe model writes the lyrics only when generating, no text appears here. You can type your own lyrics here.",
    connection: "Connection", connection_locked: "To switch, stop the app and run Install again with the desired mode.",
    runtime_mock: "Test mode · no AI model", runtime_remote: "Music engine on a compute server", runtime_local: "Local music engine", runtime_direct: "Manually started web app",
    runtime_unmanaged: "Start/stop controls are unavailable when started manually.",
    synth_srv: "Synthesis server", synth_tip: "Local or remote music engine (CUDA, Metal or CPU)",
    lm_srv: "Language model server", lm_tip: "Empty = same server as synthesis.", lm_ph: "Empty = same server",
    timeout: "Timeout (min.)", mock: "Mock (test tone)",
    layout: "Layout", stacked: "Stacked", side: "Side by side", side_tip: "Generator on the left, library on the right (from about 1000 px width)",
    version: "Version", upd_check: "Check for updates", upd_apply: "UPDATE NOW",
    github: "GitHub", cancel: "Cancel", save: "SAVE",
    offline: "Offline", backend_offline: "Backend offline",
    models: "Models", model_server: "Model server",
    analyzing: (n) => `Analyzing “${n}” …`, analyzed: (n) => `“${n}” analyzed — style applied.`, error: "Error",
    empty: "Nothing yet", waiting: "Waiting", cancelled: "Cancelled", created_in: "Created in",
    fav: "Favorite", download: "Download", more: "Another variant (new seed)", reuse: "Copy settings to the form",
    show_lyrics: "Show the lyrics the model wrote", retry: "Retry", del: "Delete", del_q: "Delete song?", rename: "Click to rename",
    meta_tip: "IT = iterations · VAR = variance",
    err_offline: "Server offline", err_codes: "No codes", err_timeout: "Timeout", err_details: "Details in tooltip",
    f_all: "All", f_none: "Unsorted", f_new: "New folder", f_rename: "Rename", f_delete: "Delete folder",
    f_zip: "Download folder", f_zip_all: "Download all", f_zip_tip: "Download all finished songs of this view as a ZIP",
    f_name_q: "Folder name:", f_delete_q: (n) => `Delete folder “${n}”? The songs are kept and become unsorted.`,
    move: "Move to folder",
    servers: "Servers", stop: "Stop servers", github_info: "Open repository in browser",
    stop_q: "Stop the app and its local connections? A remote music engine keeps running. Start again with “Music Generator ON”.",
    stop_q_busy: "Songs are running or queued. Stop anyway? These jobs will be cancelled and can be retried later.",
    stopped: "Stopped. Start again with “Music Generator ON”.",
    mute: "Mute", unmute: "Unmute", volume: "Volume",
    upd_search: "Searching …", upd_current: (v) => `Up to date (${v})`,
    upd_new: (n, a, b) => `${n} new ${n > 1 ? "updates" : "update"} (${a} → ${b})`,
    upd_dirty: " · local file changes, automatic update not possible", upd_install: " · then run Install once",
    upd_loading: "Downloading …", upd_restart: "Installed, app is restarting …",
    upd_restart_install: "Updated. Please run Install once (new model version), then reload this page.",
    upd_slow: "Restart is taking unusually long. Please start Music Generator ON.",
  },
};

let LANG = "de";
try {
  const saved = localStorage.getItem("ui_lang");
  LANG = saved === "en" || saved === "de" ? saved : (navigator.language || "de").toLowerCase().startsWith("de") ? "de" : "en";
} catch {}

const t = (k, ...a) => {
  const v = I18N[LANG][k] ?? I18N.de[k] ?? k;
  return typeof v === "function" ? v(...a) : v;
};

function applyI18n() {
  document.documentElement.lang = LANG;
  document.querySelectorAll("[data-i18n]").forEach((e) => { e.textContent = t(e.dataset.i18n); });
  for (const [data, attr] of [["i18nTitle", "title"], ["i18nPh", "placeholder"], ["i18nAria", "aria-label"]])
    document.querySelectorAll(`[data-i18n-${data.slice(4).toLowerCase()}]`).forEach((e) => e.setAttribute(attr, t(e.dataset[data])));
  document.querySelectorAll("[data-lang]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === LANG)));
}

function setLang(l) {
  LANG = l;
  try { localStorage.setItem("ui_lang", l); } catch {}
  applyI18n();
  document.dispatchEvent(new Event("langchange"));
}
applyI18n();
