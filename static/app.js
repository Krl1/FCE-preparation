"use strict";

// --- i18n --------------------------------------------------------------------

const I18N = {
  pl: {
    "app.title": "FCE Trener",
    "tab.practice": "Ćwicz zadania",
    "tab.tips": "Ćwicz błędy",
    "tab.external": "Sprawdź z zewnątrz",
    "tab.errors": "Moje błędy",
    "tab.stats": "Statystyki",
    "practice.type": "Typ ćwiczenia",
    "practice.topic": "Temat (opcjonalnie)",
    "practice.topic.auto": "— dobierz automatycznie (wg moich błędów) —",
    "btn.generate": "Generuj zadanie",
    "btn.grade": "Sprawdź odpowiedź",
    "external.intro": "Wklej zadanie z książki lub od korepetytora oraz swoją odpowiedź — sprawdzę je i zapiszę błędy.",
    "external.type": "Typ ćwiczenia",
    "external.keyword": "Słowo-klucz (key word)",
    "external.question": "Treść zadania",
    "external.question.ph": "Wklej treść / polecenie zadania…",
    "external.answer": "Twoja odpowiedź",
    "external.answer.ph": "Wpisz swoją odpowiedź…",
    "btn.gradeExternal": "Sprawdź",
    "errors.weak": "Słabe punkty",
    "errors.journal": "Dziennik błędów",
    "errors.practiceThis": "Ćwicz ten błąd",
    "errors.add": "Dodaj do dziennika",
    "errors.added": "W dzienniku",
    "errors.addAll": "Dodaj wszystkie",
    "errors.pending": "Nic nie trafia do dziennika automatycznie — zatwierdź to, co chcesz ćwiczyć.",
    "errors.delete": "Usuń błąd",
    "errors.deleteConfirm": "Usunąć na stałe?",
    "errors.deleteYes": "Tak, usuń",
    "errors.deleteCancel": "Anuluj",
    "errors.deleted": "Błąd usunięty z dziennika.",
    "dispute.button": "Nie zgadzam się",
    "dispute.placeholder": "Co jest nie tak z tym wyjaśnieniem? (opcjonalnie)",
    "dispute.send": "Sprawdź ponownie",
    "dispute.upheld": "Zastrzeżenie uznane — wyjaśnienie było błędne",
    "dispute.rejected": "Wyjaśnienie utrzymane",
    "dispute.willChange": "Zatwierdzenie wprowadzi:",
    "dispute.apply": "Zastosuj poprawkę",
    "dispute.applied": "Wprowadzono:",
    "btn.refresh": "Odśwież",
    "loader.default": "Pracuję…",
    "loader.generating": "Generuję zadanie…",
    "loader.grading": "Sprawdzam odpowiedź…",
    "loader.gradingExt": "Sprawdzam zadanie…",
    "loader.loading": "Wczytuję…",
    "loader.dispute": "Weryfikuję zastrzeżenie…",
    "loader.deleting": "Usuwam…",
    "loader.saving": "Zapisuję…",
    "topic.prefix": "Temat: ",
    "kw.label": "Słowo-klucz: ",
    "answer.ph": "Twoja odpowiedź…",
    "writing.ph": "Napisz swój tekst po angielsku…",
    "alert.answer": "Wpisz lub wybierz odpowiedź.",
    "alert.answerAll": "Odpowiedz na wszystkie luki.",
    "alert.fillExternal": "Uzupełnij treść zadania i odpowiedź.",
    "verdict.score": "Wynik:",
    "verdict.correct": "✓ Poprawnie",
    "verdict.incorrect": "✗ Do poprawy",
    "band.prefix": "Orientacyjna ocena: ",
    "corrected.label": "Poprawna wersja:",
    "result.optionNotes": "Dlaczego pozostałe warianty",
    "errors.detected": "Wykryte błędy",
    "noErrors": "Brak błędów. Świetna robota!",
    "error.prefix": "Błąd: ",
    "severity.minor": "drobny",
    "severity.major": "poważny",
    "stats.emptyErrors": "Brak błędów w dzienniku — rozwiąż kilka zadań.",
    "journal.empty": "Dziennik jest pusty.",
    "taxonomy.fail": "Nie udało się wczytać taksonomii: ",
    "tips.today": "dzisiaj",
    "tips.goalLabel": "Dzienny cel",
    "tips.goalSave": "Zapisz cel",
    "tips.newError": "Inny błąd",
    "tips.generate": "Ćwiczenie",
    "tips.more": "Kolejne ćwiczenie",
    "tips.streakDays": "dni w serii",
    "tips.debtNote": "Zaległość z {days} — zalicz dziś {n} różnych błędów, inaczej seria przepada.",
    "tips.debtOneDay": "1 dnia",
    "tips.debtManyDays": "{days} dni",
    "tips.drillProgress": "Poprawne ćwiczenia do zaliczenia tego błędu:",
    "tips.empty": "Dziennik błędów jest pusty — rozwiąż lub wklej kilka zadań, a pojawią się tu błędy do przećwiczenia.",
    "stats.learning": "Nauka",
    "stats.usage": "Zużycie Claude",
    "stats.usageNote": "Koszt liczony wg stawek API. Tryb headless niesie narzut systemowego promptu Claude Code, więc to górna granica — aplikacja na API zużyłaby mniej.",
    "stats.emptyUsage": "Brak danych — zacznij korzystać z aplikacji.",
    "stats.exercisesGenerated": "Wygenerowane ćwiczenia",
    "stats.queued": "Gotowe w kolejce",
    "stats.attempts": "Sprawdzone odpowiedzi",
    "stats.accuracy": "Skuteczność",
    "stats.reviews": "Przerobione powtórki",
    "stats.errorsLogged": "Błędy w dzienniku",
    "stats.byType": "Wg typu zadania",
    "stats.calls": "Wywołania modelu",
    "stats.tokensIn": "Tokeny wejściowe",
    "stats.tokensOut": "Tokeny wyjściowe",
    "stats.tokensCacheWrite": "Tokeny cache (zapis)",
    "stats.tokensCacheRead": "Tokeny cache (odczyt)",
    "stats.cost": "Koszt trybu headless (górna granica)",
    "stats.avgTime": "Średni czas odpowiedzi",
    "stats.leanTitle": "Szacunek na API (bez narzutu)",
    "stats.leanUsed": "Przy tym samym modelu",
    "stats.leanSonnet": "Na tańszym modelu (Sonnet 5)",
    "stats.leanNote": "Liczone tylko z realnego promptu i odpowiedzi (bez narzutu Claude Code, ~4 znaki/token). Z cache'owaniem promptu na API będzie jeszcze taniej.",
    "stats.assumedNote": "Uwaga: brak potwierdzonej stawki dla modelu ",
    "stats.byKind": "Wg rodzaju wywołania",
    "kind.generate": "Generowanie zadań",
    "kind.grade": "Sprawdzanie",
    "kind.drill": "Ćwiczenia do błędów",
    "kind.explain": "Wyjaśnienia",
    "kind.extract": "Import (ekstrakcja)",
    "kind.other": "Inne",
    "groups.modeItems": "Wpisy",
    "groups.modeGroups": "Grupy",
    "groups.drillErrors": "Pojedyncze błędy",
    "groups.drillGroups": "Grupy",
    "groups.assign": "Scal nowe",
    "groups.regroup": "Przegrupuj wszystko",
    "groups.regroupConfirm": "Przegrupowanie liczy wszystko od nowa i kasuje ręczne poprawki oraz puste grupy. Na pewno?",
    "groups.ungrouped": "Nieprzypisane wpisy: {n}",
    "groups.members": "{n} wpisów",
    "groups.empty": "Brak grup — użyj „Scal nowe\", żeby je utworzyć.",
    "groups.noneYet": "Nie ma jeszcze grup — użyj „Scal nowe\" w zakładce Moje błędy.",
    "groups.emptyGroup": "Grupa bez wpisów",
    "groups.rename": "Zmień nazwę",
    "groups.renameSave": "Zapisz",
    "groups.delete": "Usuń grupę",
    "groups.detach": "Odepnij",
    "groups.practiceThis": "Ćwicz tę grupę",
    "groups.orphaned": "Grupa „{rule}\" została bez wpisów. Usunąć ją także?",
    "groups.orphanKeep": "Zostaw",
    "groups.orphanDelete": "Usuń grupę",
    "groups.assigned": "Dopięto: {assigned}, nowych grup: {created}, bez przypisania: {unassigned}",
  },
  en: {
    "app.title": "FCE Trainer",
    "tab.practice": "Practice tasks",
    "tab.tips": "Practice mistakes",
    "tab.external": "Check external",
    "tab.errors": "My mistakes",
    "tab.stats": "Statistics",
    "practice.type": "Exercise type",
    "practice.topic": "Topic (optional)",
    "practice.topic.auto": "— auto-select (by my mistakes) —",
    "btn.generate": "Generate exercise",
    "btn.grade": "Check answer",
    "external.intro": "Paste an exercise from a book or your tutor together with your answer — I'll check it and log the mistakes.",
    "external.type": "Exercise type",
    "external.keyword": "Key word",
    "external.question": "Exercise text",
    "external.question.ph": "Paste the exercise / prompt…",
    "external.answer": "Your answer",
    "external.answer.ph": "Type your answer…",
    "btn.gradeExternal": "Check",
    "errors.weak": "Weak points",
    "errors.journal": "Mistake log",
    "errors.practiceThis": "Practice this mistake",
    "errors.add": "Add to log",
    "errors.added": "In the log",
    "errors.addAll": "Add all",
    "errors.pending": "Nothing is logged automatically — confirm what you want to practise.",
    "errors.delete": "Delete mistake",
    "errors.deleteConfirm": "Delete permanently?",
    "errors.deleteYes": "Yes, delete",
    "errors.deleteCancel": "Cancel",
    "errors.deleted": "Mistake removed from the log.",
    "dispute.button": "I disagree",
    "dispute.placeholder": "What is wrong with this explanation? (optional)",
    "dispute.send": "Re-check",
    "dispute.upheld": "Objection accepted — the explanation was wrong",
    "dispute.rejected": "Explanation upheld",
    "dispute.willChange": "Confirming will:",
    "dispute.apply": "Apply correction",
    "dispute.applied": "Applied:",
    "btn.refresh": "Refresh",
    "loader.default": "Working…",
    "loader.generating": "Generating exercise…",
    "loader.grading": "Checking answer…",
    "loader.gradingExt": "Checking…",
    "loader.loading": "Loading…",
    "loader.dispute": "Re-checking…",
    "loader.deleting": "Deleting…",
    "loader.saving": "Saving…",
    "topic.prefix": "Topic: ",
    "kw.label": "Key word: ",
    "answer.ph": "Your answer…",
    "writing.ph": "Write your text in English…",
    "alert.answer": "Enter or select an answer.",
    "alert.answerAll": "Answer every gap.",
    "alert.fillExternal": "Fill in the exercise text and your answer.",
    "verdict.score": "Score:",
    "verdict.correct": "✓ Correct",
    "verdict.incorrect": "✗ Needs work",
    "band.prefix": "Estimated band: ",
    "corrected.label": "Correct version:",
    "result.optionNotes": "Why the other options",
    "errors.detected": "Detected mistakes",
    "noErrors": "No mistakes. Great job!",
    "error.prefix": "Error: ",
    "severity.minor": "minor",
    "severity.major": "major",
    "stats.emptyErrors": "No mistakes logged yet — do a few exercises.",
    "journal.empty": "The log is empty.",
    "taxonomy.fail": "Failed to load taxonomy: ",
    "tips.today": "today",
    "tips.goalLabel": "Daily goal",
    "tips.goalSave": "Save goal",
    "tips.newError": "Another mistake",
    "tips.generate": "Exercise",
    "tips.more": "Another exercise",
    "tips.streakDays": "day streak",
    "tips.debtNote": "{days} to make up — clear {n} different mistakes today or the streak is gone.",
    "tips.debtOneDay": "1 missed day",
    "tips.debtManyDays": "{days} missed days",
    "tips.drillProgress": "Correct exercises needed for this mistake:",
    "tips.empty": "Your mistake log is empty — do or paste a few exercises and mistakes to practise will appear here.",
    "stats.learning": "Learning",
    "stats.usage": "Claude usage",
    "stats.usageNote": "Cost is at API rates. Headless mode carries Claude Code's system-prompt overhead, so this is an upper bound — an API app would use less.",
    "stats.emptyUsage": "No data yet — start using the app.",
    "stats.exercisesGenerated": "Exercises generated",
    "stats.queued": "Ready in queue",
    "stats.attempts": "Answers checked",
    "stats.accuracy": "Accuracy",
    "stats.reviews": "Reviews completed",
    "stats.errorsLogged": "Mistakes logged",
    "stats.byType": "By exercise type",
    "stats.calls": "Model calls",
    "stats.tokensIn": "Input tokens",
    "stats.tokensOut": "Output tokens",
    "stats.tokensCacheWrite": "Cache tokens (write)",
    "stats.tokensCacheRead": "Cache tokens (read)",
    "stats.cost": "Headless cost (upper bound)",
    "stats.avgTime": "Avg response time",
    "stats.leanTitle": "API estimate (no overhead)",
    "stats.leanUsed": "Same model as used",
    "stats.leanSonnet": "On a cheaper model (Sonnet 5)",
    "stats.leanNote": "Counted from the real prompt and response only (no Claude Code overhead, ~4 chars/token). With API prompt caching it would be even lower.",
    "stats.assumedNote": "Note: no confirmed rate for model ",
    "stats.byKind": "By call type",
    "kind.generate": "Exercise generation",
    "kind.grade": "Grading",
    "kind.drill": "Mistake drills",
    "kind.explain": "Explanations",
    "kind.extract": "Import (extraction)",
    "kind.other": "Other",
    "groups.modeItems": "Entries",
    "groups.modeGroups": "Groups",
    "groups.drillErrors": "Individual mistakes",
    "groups.drillGroups": "Groups",
    "groups.assign": "Merge new",
    "groups.regroup": "Regroup everything",
    "groups.regroupConfirm": "Regrouping recomputes from scratch and discards manual edits and empty groups. Are you sure?",
    "groups.ungrouped": "Unassigned entries: {n}",
    "groups.members": "{n} entries",
    "groups.empty": "No groups yet — use \"Merge new\" to create them.",
    "groups.noneYet": "No groups yet — use \"Merge new\" in the My mistakes tab.",
    "groups.emptyGroup": "Group with no entries",
    "groups.rename": "Rename",
    "groups.renameSave": "Save",
    "groups.delete": "Delete group",
    "groups.detach": "Detach",
    "groups.practiceThis": "Practise this group",
    "groups.orphaned": "Group \"{rule}\" is now empty. Delete it as well?",
    "groups.orphanKeep": "Keep",
    "groups.orphanDelete": "Delete group",
    "groups.assigned": "Attached: {assigned}, new groups: {created}, unassigned: {unassigned}",
  },
};

let LANG = localStorage.getItem("fce_lang") === "en" ? "en" : "pl";
const t = (key) => (I18N[LANG] && I18N[LANG][key]) || I18N.pl[key] || key;

// --- Stan i pomocnicze -------------------------------------------------------

let TAXONOMY = { exercise_types: [], topics: [] };
let TOPIC_LABELS = {}; // id -> {pl, en}
let currentExercise = null;
let tipsError = null;
let tipsExercise = null;
let tipsMode = "error";   // "error" | "group"
let tipsGroup = null;

const $ = (sel) => document.querySelector(sel);

/** Element z treścią TEKSTOWĄ (bezpieczny domyślny wybór). */
const elem = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
};

/** Element z treścią HTML — wolno użyć tylko z danymi przepuszczonymi przez esc(). */
const elHtml = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html !== undefined) n.innerHTML = html;
  return n;
};

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const topicLabel = (id) => (TOPIC_LABELS[id] && TOPIC_LABELS[id][LANG]) || id;
const typeLabelOf = (typ) => (LANG === "en" ? typ.label_en : typ.label) || typ.label;
const severityLabel = (s) => t("severity." + (s === "major" ? "major" : "minor"));

// Licznik równoległych operacji — nakładka znika dopiero, gdy skończy się ostatnia.
let busyCount = 0;
function showLoader(key) {
  $("#loader-text").textContent = t(key || "loader.default");
  $("#loader").classList.remove("hidden");
}
function hideLoader() { $("#loader").classList.add("hidden"); }

/** Wykonuje operację blokując przycisk (chroni przed podwójnym wywołaniem modelu,
 *  także przy aktywacji klawiaturą, której nakładka nie zatrzymuje). */
async function withBusy(loaderKey, btn, fn) {
  if (btn && btn.disabled) return undefined;
  if (btn) btn.disabled = true;
  busyCount += 1;
  showLoader(loaderKey);
  try {
    return await fn();
  } finally {
    if (btn) btn.disabled = false;
    busyCount -= 1;
    if (busyCount === 0) hideLoader();
  }
}

async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

function isWritingType(typeId) {
  const typ = TAXONOMY.exercise_types.find((x) => x.id === typeId);
  return Boolean(typ && typ.area === "writing");
}

/** Banner błędu w kontenerze WYNIKOWYM (nigdy w kontenerze ze statycznym markupem). */
function showError(sel, msg) {
  const box = $(sel);
  box.classList.remove("hidden");
  box.innerHTML = "";
  const banner = elem("div", "error-banner", t("error.prefix") + msg);
  banner.setAttribute("role", "alert");
  box.appendChild(banner);
}

/** Komunikat walidacyjny przy polu — zamiast blokującego alert(). */
function fieldError(containerSel, msg) {
  const box = $(containerSel);
  if (!box) return;
  box.querySelectorAll(".field-error").forEach((n) => n.remove());
  const p = elem("p", "field-error", msg);
  p.setAttribute("role", "alert");
  box.appendChild(p);
  const focusable = box.querySelector("input, textarea, select");
  if (focusable) focusable.focus();
}

function clearFieldErrors(containerSel) {
  const box = $(containerSel);
  if (box) box.querySelectorAll(".field-error").forEach((n) => n.remove());
}

// --- Przełącznik języka ------------------------------------------------------

function applyStaticI18n() {
  document.documentElement.lang = LANG;
  document.title = t("app.title");
  document.querySelectorAll("[data-i18n]").forEach((n) => { n.textContent = t(n.dataset.i18n); });
  document.querySelectorAll("[data-i18n-ph]").forEach((n) => { n.placeholder = t(n.dataset.i18nPh); });
}

function markLangButtons() {
  document.querySelectorAll(".lang").forEach((b) => {
    const on = b.dataset.lang === LANG;
    b.classList.toggle("is-active", on);
    b.setAttribute("aria-pressed", String(on));
  });
}

function setLang(lang) {
  LANG = lang === "en" ? "en" : "pl";
  localStorage.setItem("fce_lang", LANG);
  markLangButtons();
  applyStaticI18n();
  fillTypeSelects();
  populateTopics();
  if ($("#view-errors").classList.contains("is-active")) {
    loadErrors();
    // Panel grup ma własne etykiety tematów i liczniki wpisów — bez tego zostałyby
    // w poprzednim języku, bo `loadErrors` go nie dotyka.
    if (!$("#groups-pane").classList.contains("hidden")) loadGroups();
  }
  if ($("#view-stats").classList.contains("is-active")) loadStats();
  if ($("#view-tips").classList.contains("is-active")) {
    // Nie pobieramy nowej jednostki — to zgubiłoby rozwiązywane ćwiczenie.
    // Przerysowujemy tylko etykiety bieżącego fokusu — w OBU trybach, bo w trybie
    // grupowym `tipsError` jest zawsze null i sam warunek na nim odesłałby po nową grupę.
    const unit = tipsError || tipsGroup;
    if (unit) {
      $("#tips-topic").textContent = topicLabel(unit.topic);
      $("#tips-generate").textContent = tipsExercise ? t("tips.more") : t("tips.generate");
      refreshProgress();
    } else {
      loadTips();
    }
  }
}

document.querySelectorAll(".lang").forEach((b) =>
  b.addEventListener("click", () => setLang(b.dataset.lang)));

// --- Nawigacja zakładek ------------------------------------------------------

function activateTab(view) {
  document.querySelectorAll(".tab").forEach((x) => {
    const on = x.dataset.view === view;
    x.classList.toggle("is-active", on);
    x.setAttribute("aria-selected", String(on));
  });
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("is-active"));
  $("#view-" + view).classList.add("is-active");
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    activateTab(tab.dataset.view);
    if (tab.dataset.view === "errors") loadErrors();
    if (tab.dataset.view === "tips") loadTips();
    if (tab.dataset.view === "stats") loadStats();
  });
});

// --- Inicjalizacja -----------------------------------------------------------

async function init() {
  markLangButtons();
  applyStaticI18n();
  try {
    TAXONOMY = await api("/api/taxonomy");
  } catch (e) {
    document.body.prepend(elem("div", "error-banner", t("taxonomy.fail") + e.message));
    return;
  }
  TAXONOMY.topics.forEach((tp) => { TOPIC_LABELS[tp.id] = { pl: tp.label, en: tp.label_en }; });

  fillTypeSelects();
  $("#practice-type").addEventListener("change", populateTopics);
  $("#external-type").addEventListener("change", toggleExternalKeyword);
  populateTopics();
  toggleExternalKeyword();
}

function fillTypeSelects() {
  ["#practice-type", "#external-type"].forEach((sel) => {
    const node = $(sel);
    if (!node) return;
    const prev = node.value;
    node.innerHTML = "";
    TAXONOMY.exercise_types.forEach((typ) => {
      const opt = elem("option", null, typeLabelOf(typ));
      opt.value = typ.id;
      node.appendChild(opt);
    });
    if (prev) node.value = prev;
    if (node.selectedIndex < 0) node.selectedIndex = 0;
  });
}

function populateTopics() {
  const typ = TAXONOMY.exercise_types.find((x) => x.id === $("#practice-type").value);
  const sel = $("#practice-topic");
  const prev = sel.value;
  sel.innerHTML = "";
  const auto = elem("option", null, t("practice.topic.auto"));
  auto.value = "";
  sel.appendChild(auto);
  (typ ? typ.topics : []).forEach((topicId) => {
    const opt = elem("option", null, topicLabel(topicId));
    opt.value = topicId;
    sel.appendChild(opt);
  });
  if (prev) sel.value = prev;
  // Temat z poprzedniego typu może nie istnieć w nowym — bez tego select byłby pusty.
  if (sel.selectedIndex < 0) sel.selectedIndex = 0;
}

function toggleExternalKeyword() {
  const isKwt = $("#external-type").value === "uoe_part4_key_word_transformation";
  $("#external-keyword-wrap").classList.toggle("hidden", !isKwt);
}

// --- Wspólne renderowanie zadania („Ćwicz zadania" i „Ćwicz błędy") -----------------------------

const PRACTICE_UI = {
  card: "#exercise-area", topic: "#exercise-topic", instr: "#exercise-instructions",
  question: "#exercise-question", area: "#answer-area", result: "#practice-result",
  radio: "mcq", inputId: "practice-answer", gradeBtn: "#btn-grade", allowWriting: true,
};

const TIPS_UI = {
  card: "#tips-exercise-area", topic: null, instr: "#tips-instructions",
  question: "#tips-question", area: "#tips-answer-area", result: "#tips-result",
  radio: "tips-mcq", inputId: "tips-answer", gradeBtn: "#tips-grade", allowWriting: false,
};

function renderExerciseInto(ui, ex) {
  if (ui.topic) $(ui.topic).textContent = t("topic.prefix") + topicLabel(ex.topic);
  $(ui.instr).textContent = ex.instructions || "";

  let q = esc(ex.question_text || "");
  if (ex.key_word) q += `\n\n${esc(t("kw.label"))}<span class="kw">${esc(ex.key_word)}</span>`;
  $(ui.question).innerHTML = q;

  const area = $(ui.area);
  area.innerHTML = "";

  if (ex.items && ex.items.length) {
    // Zadanie wieloczęściowe. Pozycja ma albo warianty (multiple choice), albo pole
    // tekstowe; części 2–4 mają dodatkowo własne zdanie, rdzeń lub słowo-klucz.
    const wrap = elem("div", "gap-items");
    ex.items.forEach((item) => {
      const block = elem("div", "gap-item");
      block.appendChild(elem("span", "gap-num", String(item.number)));
      const bodyEl = elem("div", "gap-body");

      if (item.question_text) bodyEl.appendChild(elem("div", "gap-text", item.question_text));
      if (item.stem) bodyEl.appendChild(elem("span", "chip stem", item.stem));
      if (item.key_word) {
        bodyEl.appendChild(elem("span", "chip kw", t("kw.label") + item.key_word));
      }

      if (item.options && item.options.length) {
        const opts = elem("div", "options options-inline");
        item.options.forEach((opt) => {
          const lbl = elHtml("label", null,
            `<input type="radio" name="${esc(ui.radio)}-${esc(String(item.number))}" ` +
            `value="${esc(opt)}"> ${esc(opt)}`);
          opts.appendChild(lbl);
        });
        bodyEl.appendChild(opts);
      } else {
        const input = elem("input");
        input.type = "text";
        input.id = `${ui.inputId}-${item.number}`;
        input.className = "gap-input";
        input.placeholder = t("answer.ph");
        input.setAttribute("aria-label", `${item.number}. ${t("answer.ph")}`);
        input.addEventListener("keydown", (e) => {
          if (e.key === "Enter") { e.preventDefault(); $(ui.gradeBtn).click(); }
        });
        bodyEl.appendChild(input);
      }
      block.appendChild(bodyEl);
      wrap.appendChild(block);
    });
    area.appendChild(wrap);
  } else if (ex.options && ex.options.length) {
    const wrap = elem("div", "options");
    ex.options.forEach((opt) => {
      const lbl = elHtml("label", null,
        `<input type="radio" name="${esc(ui.radio)}" value="${esc(opt)}"> ${esc(opt)}`);
      wrap.appendChild(lbl);
    });
    area.appendChild(wrap);
  } else {
    const writing = ui.allowWriting && isWritingType(ex.type);
    const input = elem(writing ? "textarea" : "input");
    input.id = ui.inputId;
    input.setAttribute("aria-label", writing ? t("writing.ph") : t("answer.ph"));
    if (writing) { input.rows = 10; input.placeholder = t("writing.ph"); }
    else {
      input.type = "text";
      input.placeholder = t("answer.ph");
      // Enter zatwierdza — przy dziesiątkach powtórzeń oszczędza sięganie po mysz.
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); $(ui.gradeBtn).click(); }
      });
    }
    area.appendChild(input);
  }

  $(ui.card).classList.remove("hidden");
  const first = area.querySelector("input, textarea");
  if (first) first.focus();
}

/** Zbiera odpowiedź(i) i buduje ciało żądania oceny. Zwraca null, gdy brak odpowiedzi. */
function collectGradeBody(ui, ex) {
  clearFieldErrors(ui.area);
  const body = { type: ex.type, exercise_id: ex.id, lang: LANG };

  if (ex.items && ex.items.length) {
    const answers = ex.items.map((item) => {
      if (item.options && item.options.length) {
        const c = document.querySelector(`input[name="${ui.radio}-${item.number}"]:checked`);
        return c ? c.value : "";
      }
      const inp = $(`#${ui.inputId}-${item.number}`);
      return inp ? inp.value.trim() : "";
    });
    if (answers.some((a) => !a)) { fieldError(ui.area, t("alert.answerAll")); return null; }
    body.student_answers = answers;
    return body;
  }

  const checked = document.querySelector(`input[name="${ui.radio}"]:checked`);
  const inp = $("#" + ui.inputId);
  const answer = checked ? checked.value : (inp ? inp.value.trim() : "");
  if (!answer) { fieldError(ui.area, t("alert.answer")); return null; }
  body.student_answer = answer;
  return body;
}

async function gradeExercise(ui, ex) {
  const body = collectGradeBody(ui, ex);
  if (!body) return null;
  return withBusy("loader.grading", $(ui.gradeBtn), async () => {
    const result = await api("/api/grade", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    renderResult(ui.result, result, ex);
    return result;
  });
}

// --- Ćwicz -------------------------------------------------------------------

$("#btn-generate").addEventListener("click", () =>
  withBusy("loader.generating", $("#btn-generate"), async () => {
    $("#practice-result").classList.add("hidden");
    currentExercise = null; // po nieudanym generowaniu nie zostawiamy starego zadania
    try {
      currentExercise = await api("/api/exercise", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          type: $("#practice-type").value,
          topic: $("#practice-topic").value || null,
          lang: LANG,
        }),
      });
      renderExerciseInto(PRACTICE_UI, currentExercise);
    } catch (e) {
      // Kontener wynikowy — NIE karta zadania, której markup trzeba zachować.
      showError("#practice-result", e.message);
    }
  }));

$("#btn-grade").addEventListener("click", async () => {
  if (!currentExercise) return;
  try {
    await gradeExercise(PRACTICE_UI, currentExercise);
  } catch (e) {
    showError("#practice-result", e.message);
  }
});

// --- Sprawdź z zewnątrz ------------------------------------------------------

$("#btn-grade-external").addEventListener("click", () =>
  withBusy("loader.gradingExt", $("#btn-grade-external"), async () => {
    const question_text = $("#external-question").value.trim();
    const student_answer = $("#external-answer").value.trim();
    clearFieldErrors("#view-external .card");
    if (!question_text || !student_answer) {
      fieldError("#view-external .card", t("alert.fillExternal"));
      return;
    }
    try {
      const result = await api("/api/grade", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          type: $("#external-type").value,
          question_text,
          student_answer,
          key_word: $("#external-keyword").value.trim() || null,
          lang: LANG,
        }),
      });
      renderResult("#external-result", result);
    } catch (e) {
      showError("#external-result", e.message);
    }
  }));

// --- Renderowanie wyniku oceny ----------------------------------------------

// --- Zastrzeżenia do wyjaśnień -----------------------------------------------

/** Przycisk „Nie zgadzam się" z panelem: opcjonalny komentarz → ponowna weryfikacja.
 *  `payload` identyfikuje kwestionowane wyjaśnienie (pozycja zadania albo wpis w dzienniku). */
function disputeWidget(payload) {
  const wrap = elem("div", "dispute");
  const btn = elem("button", "dispute-btn", "⚠ " + t("dispute.button"));
  const panel = elem("div", "dispute-panel hidden");
  const comment = elem("textarea", "dispute-comment");
  comment.rows = 2;
  comment.placeholder = t("dispute.placeholder");
  comment.setAttribute("aria-label", t("dispute.placeholder"));
  const send = elem("button", "primary dispute-send", t("dispute.send"));
  const out = elem("div", "dispute-out");
  panel.appendChild(comment);
  panel.appendChild(send);
  panel.appendChild(out);

  btn.addEventListener("click", () => {
    const opening = panel.classList.contains("hidden");
    panel.classList.toggle("hidden", !opening);
    if (opening) comment.focus();
  });

  send.addEventListener("click", () => withBusy("loader.dispute", send, async () => {
    out.innerHTML = "";
    try {
      const res = await api("/api/dispute", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...payload, comment: comment.value.trim(), lang: LANG }),
      });
      renderDisputeOutcome(out, res);
    } catch (e) {
      out.appendChild(elem("div", "error-banner", t("error.prefix") + e.message));
    }
  }));

  wrap.appendChild(btn);
  wrap.appendChild(panel);
  return wrap;
}

/** Zatwierdzenie wykrytego błędu do dziennika. Ocena sama nic nie zapisuje —
 *  wpis powstaje dopiero po tym kliknięciu.
 *  `disputePayload` (jeśli podany) dostaje `error_id`, żeby zastrzeżenie zgłoszone
 *  PO zatwierdzeniu wiedziało, który wpis usunąć.
 *  `collect` zbiera akcje dla przycisku „Dodaj wszystkie". */
function addErrorWidget(candidate, exerciseId, disputePayload, collect) {
  const wrap = elem("div", "err-add");
  const btn = elem("button", "add-btn", "+ " + t("errors.add"));

  const doAdd = () => withBusy("loader.saving", btn, async () => {
    if (candidate.id) return;                     // już zatwierdzony
    try {
      const res = await api("/api/errors?lang=" + LANG, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic: candidate.topic,
          student_text: candidate.student_text,
          correct_text: candidate.correct_text,
          explanation: candidate.explanation || "",
          severity: candidate.severity || "minor",
          exercise_id: exerciseId || null,
        }),
      });
      candidate.id = res.id;
      if (disputePayload) disputePayload.error_id = res.id;
      btn.remove();
      wrap.appendChild(elem("span", "add-done", "✓ " + t("errors.added")));
    } catch (e) {
      wrap.appendChild(elem("div", "error-banner", t("error.prefix") + e.message));
    }
  });

  btn.addEventListener("click", doAdd);
  if (collect) collect.push(doAdd);
  wrap.appendChild(btn);
  return wrap;
}

/** Usunięcie wpisu z dziennika, dwustopniowo (klik → potwierdzenie).
 *  Świadomie bez `window.confirm` — modal blokuje wątek i nie da się go
 *  przetestować bez przeglądarki, a potwierdzenie w miejscu wystarcza,
 *  by przypadkowe kliknięcie nie skasowało danych. */
function deleteErrorWidget(errorId, onDone) {
  const wrap = elem("div", "err-delete");
  const btn = elem("button", "delete-btn", "🗑 " + t("errors.delete"));
  const confirmBox = elem("span", "delete-confirm hidden");
  const yes = elem("button", "delete-yes", t("errors.deleteYes"));
  const no = elem("button", "delete-no", t("errors.deleteCancel"));
  confirmBox.appendChild(elem("span", "delete-q", t("errors.deleteConfirm")));
  confirmBox.appendChild(yes);
  confirmBox.appendChild(no);

  btn.addEventListener("click", () => {
    btn.classList.add("hidden");
    confirmBox.classList.remove("hidden");
    yes.focus();
  });
  no.addEventListener("click", () => {
    confirmBox.classList.add("hidden");
    btn.classList.remove("hidden");
  });
  // Pytanie o osieroconą grupę zadajemy PO wyjściu z `withBusy` — nakładka ładowania
  // jest `position: fixed; inset: 0` i przechwyciłaby kliknięcia w „Zostaw" / „Usuń grupę",
  // więc pytanie zadane wewnątrz busy nie dałoby się odkliknąć myszą.
  yes.addEventListener("click", async () => {
    let out;
    try {
      out = await withBusy("loader.deleting", yes, () =>
        api("/api/errors/" + errorId, { method: "DELETE" }));
    } catch (e) {
      wrap.appendChild(elem("div", "error-banner", t("error.prefix") + e.message));
      return;
    }
    if (!out) return;   // withBusy zwraca undefined przy podwójnym kliknięciu
    await offerOrphanCleanup(out.emptied_group_id, out.emptied_group_rule, wrap);
    if (onDone) onDone();
  });

  wrap.appendChild(btn);
  wrap.appendChild(confirmBox);
  return wrap;
}

function renderDisputeOutcome(out, res) {
  const upheld = res.verdict === "upheld";
  out.appendChild(elem("div", "dispute-verdict " + (upheld ? "upheld" : "rejected"),
    (upheld ? "✎ " : "✓ ") + t(upheld ? "dispute.upheld" : "dispute.rejected")));
  if (res.revised_explanation) out.appendChild(elem("p", "dispute-revised", res.revised_explanation));
  if (res.reasoning) out.appendChild(elem("p", "why", res.reasoning));

  // Dane zmieniamy TYLKO po zatwierdzeniu — pokazujemy wprost, co się zmieni.
  if (Array.isArray(res.proposed_changes) && res.proposed_changes.length) {
    out.appendChild(elem("p", "muted", t("dispute.willChange") + " " + res.proposed_changes.join("; ")));
    const apply = elem("button", "primary dispute-apply", t("dispute.apply"));
    apply.addEventListener("click", () => withBusy("loader.dispute", apply, async () => {
      try {
        const done = await api(`/api/dispute/${res.dispute_id}/apply`, { method: "POST" });
        apply.remove();
        out.appendChild(elem("p", "dispute-applied", t("dispute.applied") + " " + done.applied.join("; ")));
        // Dziennik i licznik mogły się zmienić — odśwież widoki, jeśli są otwarte.
        if ($("#view-errors").classList.contains("is-active")) loadErrors();
        if ($("#view-tips").classList.contains("is-active")) refreshProgress();
      } catch (e) {
        out.appendChild(elem("div", "error-banner", t("error.prefix") + e.message));
      }
    }));
    out.appendChild(apply);
  }
}

function optionNotesEl(notes) {
  const wrap = elem("div", "opt-notes");
  notes.forEach((o) => {
    const note = elHtml("div", "opt-note " + (o.is_correct ? "ok" : "bad"),
      `<span class="opt">${o.is_correct ? "✓" : "✗"} ${esc(o.option)}</span>` +
      `<span class="opt-why">${esc(o.comment)}</span>`);
    wrap.appendChild(note);
  });
  return wrap;
}

function errItemEl(err, opts = {}) {
  const item = elHtml("div", "err-item",
    `<div class="topic">${esc(topicLabel(err.topic))}` +
    `<span class="badge ${err.severity === "major" ? "major" : "minor"}">` +
    `${esc(severityLabel(err.severity))}</span>` +
    (opts.date ? `<span class="date">${esc(String(err.created_at || "").slice(0, 10))}</span>` : "") +
    `</div>` +
    `<div class="diff"><span class="from">${esc(err.student_text)}</span> → ` +
    `<span class="to">${esc(err.correct_text)}</span></div>` +
    `<div class="why">${esc(err.explanation)}</div>`);
  if (opts.practiceBtn || opts.deleteBtn || opts.addBtn) {
    const row = elem("div", "err-actions");
    if (opts.practiceBtn) {
      const btn = elem("button", "practice-btn", t("errors.practiceThis"));
      btn.addEventListener("click", () => focusOnError(err));
      row.appendChild(btn);
    }
    // Propozycja z oceny — do dziennika trafia dopiero po zatwierdzeniu.
    if (opts.addBtn && !err.id) {
      row.appendChild(addErrorWidget(err, opts.exerciseId, null, opts.collect));
    }
    // Usunięcie zmienia też „słabe punkty", więc przeładowujemy całą zakładkę.
    if (opts.deleteBtn && err.id) row.appendChild(deleteErrorWidget(err.id, loadErrors));
    item.appendChild(row);
  }
  // Zakwestionować da się wpis, który JEST w dzienniku — propozycji nie trzeba
  // podważać, wystarczy jej nie zatwierdzać.
  if (err.id) {
    item.appendChild(disputeWidget({
      scope: "error", error_id: err.id, disputed_text: err.explanation || "",
    }));
  }
  return item;
}

function barRow(name, ratio, countText) {
  const row = elHtml("div", "stat-row",
    `<span class="name">${esc(name)}</span>` +
    `<span class="bar"><span></span></span>` +
    `<span class="count">${esc(countText)}</span>`);
  row.querySelector(".bar > span").style.width = Math.max(0, Math.min(1, ratio)) * 100 + "%";
  return row;
}

function renderResult(sel, r, ex) {
  const box = $(sel);
  box.innerHTML = "";
  box.classList.remove("hidden");
  box.setAttribute("role", "status");

  if (r.score) {
    box.appendChild(elem("div", "verdict " + (r.correct ? "good" : "partial"),
      t("verdict.score") + " " + r.score));
  } else if (r.correct !== null && r.correct !== undefined) {
    box.appendChild(elem("div", "verdict " + (r.correct ? "good" : "bad"),
      r.correct ? t("verdict.correct") : t("verdict.incorrect")));
  }

  if (r.band) box.appendChild(elem("p", "band", t("band.prefix") + r.band));

  if (Array.isArray(r.scores) && r.scores.length) {
    const wrap = elem("div", "scores");
    r.scores.forEach((s) => {
      wrap.appendChild(barRow(topicLabel(s.criterion), s.score / 5, s.score + "/5"));
      if (s.comment) wrap.appendChild(elem("p", "why", s.comment));
    });
    box.appendChild(wrap);
  }

  if (r.corrected) {
    box.appendChild(elHtml("div", "corrected",
      `<strong>${esc(t("corrected.label"))}</strong> ${esc(r.corrected)}`));
  }
  if (r.feedback) box.appendChild(elem("p", "feedback", r.feedback));

  // Pasek zatwierdzania — wypełniany na końcu, gdy wiadomo, ile jest propozycji,
  // ale umieszczony NAD nimi, żeby od razu było jasne, że nic nie zapisało się samo.
  const pendingBar = elem("div", "pending-bar hidden");
  box.appendChild(pendingBar);
  const pendingAdds = [];
  // Propozycje pokazane już przy konkretnej luce — reszta idzie do sekcji zbiorczej.
  // Liczymy je jawnie (a nie po numerze pozycji), żeby żadna propozycja nie została
  // pokazana dwa razy ani nie zniknęła, nawet gdy serwer przypisze numery dziwnie.
  const shownErrors = new Set();

  // Zadanie wieloczęściowe: wynik i omówienie każdej luki.
  const hasItems = Array.isArray(r.items) && r.items.length;
  if (hasItems) {
    r.items.forEach((item) => {
      const block = elem("div", "res-item " + (item.correct ? "ok" : "bad"));
      const head = item.correct
        ? `<span class="to">${esc(item.correct_option)}</span>`
        : `<span class="from">${esc(item.student_option || "—")}</span> → ` +
          `<span class="to">${esc(item.correct_option)}</span>`;
      block.appendChild(elHtml("div", "ri-head",
        `<span class="ri-num">${esc(String(item.number))}</span>` +
        `<span class="ri-mark">${item.correct ? "✓" : "✗"}</span>${head}`));
      if (item.comment) block.appendChild(elem("div", "why", item.comment));
      if (Array.isArray(item.option_notes) && item.option_notes.length) {
        block.appendChild(optionNotesEl(item.option_notes));
      }
      // Propozycja błędu dla tej luki: zatwierdzasz ją tam, gdzie widzisz omówienie.
      const linked = (r.errors || []).find(
        (e) => e.item_number === item.number && !shownErrors.has(e));
      if (linked) shownErrors.add(linked);
      // Payload zastrzeżenia jest wspólnym obiektem: po zatwierdzeniu wpada w niego
      // `error_id`, więc korekta usunie dokładnie ten wpis, bez zgadywania.
      const payload = ex && ex.id ? {
        scope: "item", exercise_id: ex.id, item_number: item.number,
        disputed_text: item.comment || "", error_id: linked ? linked.id : null,
      } : null;
      if (linked) {
        block.appendChild(addErrorWidget(linked, ex && ex.id, payload, pendingAdds));
      }
      if (payload && item.comment) block.appendChild(disputeWidget(payload));
      box.appendChild(block);
    });
  }

  if (Array.isArray(r.option_notes) && r.option_notes.length) {
    box.appendChild(elem("h2", null, t("result.optionNotes")));
    box.appendChild(optionNotesEl(r.option_notes));
  }

  // Błędy nieprzypisane do żadnej luki (albo zadanie jednoczęściowe) — pokazujemy
  // osobno, żeby żadna propozycja nie przepadła po cichu.
  const loose = (r.errors || []).filter((e) => !shownErrors.has(e));
  if (loose.length) {
    box.appendChild(elem("h2", null, t("errors.detected") + " (" + loose.length + ")"));
    loose.forEach((err) => box.appendChild(errItemEl(err, {
      addBtn: true, exerciseId: ex && ex.id, collect: pendingAdds,
    })));
  } else if (r.correct && !hasItems) {
    box.appendChild(elem("p", "muted", t("noErrors")));
  }

  if (pendingAdds.length) {
    pendingBar.classList.remove("hidden");
    pendingBar.appendChild(elem("span", "pending-note", t("errors.pending")));
    if (pendingAdds.length > 1) {
      const all = elem("button", "add-all", "+ " + t("errors.addAll") +
        " (" + pendingAdds.length + ")");
      all.addEventListener("click", () => withBusy("loader.saving", all, async () => {
        for (const add of pendingAdds) await add();
        all.remove();
      }));
      pendingBar.appendChild(all);
    }
  }
}

// --- Moje błędy --------------------------------------------------------------

$("#btn-refresh-errors").addEventListener("click", loadErrors);

function loadErrors() {
  return withBusy("loader.loading", null, async () => {
    try {
      const [stats, errors] = await Promise.all([
        api("/api/stats/topics?lang=" + LANG),
        api("/api/errors?lang=" + LANG),
      ]);
      renderTopicStats(stats);
      renderErrorsList(errors);
    } catch (e) {
      showError("#errors-list", e.message);
    }
  });
}

function renderTopicStats(stats) {
  const box = $("#stats");
  box.innerHTML = "";
  if (!stats.length) { box.appendChild(elem("p", "stat-empty", t("stats.emptyErrors"))); return; }
  const max = Math.max(...stats.map((s) => s.count));
  stats.forEach((s) => {
    box.appendChild(barRow(s.topic_label || topicLabel(s.topic), s.count / max, s.count + "×"));
  });
}

function renderErrorsList(errors) {
  const box = $("#errors-list");
  box.innerHTML = "";
  if (!errors.length) { box.appendChild(elem("p", "stat-empty", t("journal.empty"))); return; }
  errors.forEach((err) => box.appendChild(
    errItemEl(err, { date: true, practiceBtn: true, deleteBtn: true })));
}

// --- Grupy błędów -------------------------------------------------------------

function loadGroups() {
  return withBusy("loader.loading", null, async () => {
    try {
      renderGroupsList(await api("/api/groups?lang=" + LANG));
    } catch (e) {
      showError("#groups-list", e.message);
    }
  });
}

function renderGroupsList(body) {
  $("#groups-ungrouped").textContent =
    t("groups.ungrouped").replace("{n}", body.ungrouped);
  const box = $("#groups-list");
  box.innerHTML = "";
  if (!body.groups.length) {
    box.appendChild(elem("p", "stat-empty", t("groups.empty")));
    return;
  }
  body.groups.forEach((g) => box.appendChild(groupItemEl(g)));
}

function groupItemEl(group) {
  const count = group.member_count === 0
    ? t("groups.emptyGroup")
    : t("groups.members").replace("{n}", group.member_count);
  const item = elHtml("div", "group-item",
    `<div class="topic">${esc(group.topic_label || topicLabel(group.topic))}` +
    `<span class="badge minor">${esc(count)}</span></div>` +
    `<div class="rule">${esc(group.rule)}</div>` +
    `<div class="why">${esc(group.explanation)}</div>`);

  const row = elem("div", "err-actions");

  const practise = elem("button", "practice-btn", t("groups.practiceThis"));
  practise.addEventListener("click", () => focusOnGroup(group));
  row.insertBefore(practise, row.firstChild);

  const rename = elem("button", "btn-sm", t("groups.rename"));
  rename.addEventListener("click", () => {
    const input = elem("input", "rule-input");
    input.value = group.rule;
    const save = elem("button", "btn-sm", t("groups.renameSave"));
    save.addEventListener("click", () => withBusy("loader.saving", save, async () => {
      try {
        await api(`/api/groups/${group.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ rule: input.value, explanation: group.explanation }),
        });
        loadGroups();
      } catch (e) {
        item.appendChild(elem("div", "error-banner", t("error.prefix") + e.message));
      }
    }));
    rename.replaceWith(input, save);
    input.focus();
  });
  row.appendChild(rename);

  row.appendChild(deleteGroupWidget(group));

  item.appendChild(row);
  return item;
}

/** Usunięcie grupy, dwustopniowo (klik → potwierdzenie) — ten sam wzorzec
 *  co `deleteErrorWidget`, żeby kasowanie grupy nie różniło się zachowaniem
 *  od kasowania wpisu. */
function deleteGroupWidget(group) {
  const wrap = elem("div", "err-delete");
  const btn = elem("button", "delete-btn", "🗑 " + t("groups.delete"));
  const confirmBox = elem("span", "delete-confirm hidden");
  const yes = elem("button", "delete-yes", t("errors.deleteYes"));
  const no = elem("button", "delete-no", t("errors.deleteCancel"));
  confirmBox.appendChild(elem("span", "delete-q", t("errors.deleteConfirm")));
  confirmBox.appendChild(yes);
  confirmBox.appendChild(no);

  btn.addEventListener("click", () => {
    btn.classList.add("hidden");
    confirmBox.classList.remove("hidden");
    yes.focus();
  });
  no.addEventListener("click", () => {
    confirmBox.classList.add("hidden");
    btn.classList.remove("hidden");
  });
  yes.addEventListener("click", () => withBusy("loader.deleting", yes, async () => {
    try {
      await api(`/api/groups/${group.id}`, { method: "DELETE" });
      loadGroups();
    } catch (e) {
      wrap.appendChild(elem("div", "error-banner", t("error.prefix") + e.message));
    }
  }));

  wrap.appendChild(btn);
  wrap.appendChild(confirmBox);
  return wrap;
}

// Pusta grupa ZOSTAJE — pytamy, zamiast kasować po cichu. `container` to WYMAGANY
// widoczny element, obok którego wstawiamy pytanie — #groups-list bywa ukryty (tryb
// "Wpisy" albo zupełnie inna zakładka), a niewidoczne przyciski zablokowałyby
// nakładkę ładowania na zawsze. Brak awaryjnego fallbacku na #groups-list jest
// celowy: przyszły wołający, który pominie `container`, ma dostać głośny błąd
// zamiast po cichu odtworzyć to samo zawieszenie.
function offerOrphanCleanup(groupId, rule, container) {
  if (groupId === null || groupId === undefined) return Promise.resolve();
  return new Promise((resolve) => {
    const ask = elem("div", "orphan-ask");
    ask.appendChild(elem("span", "", t("groups.orphaned").replace("{rule}", rule || "")));
    const keep = elem("button", "btn-sm", t("groups.orphanKeep"));
    const drop = elem("button", "btn-sm danger", t("groups.orphanDelete"));
    keep.addEventListener("click", () => { ask.remove(); resolve(); });
    drop.addEventListener("click", () => withBusy("loader.deleting", drop, async () => {
      try {
        await api(`/api/groups/${groupId}`, { method: "DELETE" });
        ask.remove();
      } catch (e) {
        ask.appendChild(elem("div", "error-banner", t("error.prefix") + e.message));
      } finally {
        // ZAWSZE rozwiązujemy: nierozwiązana obietnica zawiesiłaby wołającego
        // (i jego nakładkę) na zawsze, a nieudane usunięcie grupy to zwykły błąd.
        resolve();
      }
    }));
    ask.appendChild(keep);
    ask.appendChild(drop);
    container.prepend(ask);
  });
}

$("#btn-group-assign").addEventListener("click", () =>
  withBusy("loader.loading", $("#btn-group-assign"), async () => {
    try {
      const out = await api("/api/groups/assign?lang=" + LANG, { method: "POST" });
      await loadGroups();
      $("#groups-ungrouped").textContent = t("groups.assigned")
        .replace("{assigned}", out.assigned)
        .replace("{created}", out.created)
        .replace("{unassigned}", out.unassigned);
    } catch (e) {
      showError("#groups-list", e.message);
    }
  }));

$("#btn-group-regroup").addEventListener("click", () => {
  if (!window.confirm(t("groups.regroupConfirm"))) return;
  return withBusy("loader.loading", $("#btn-group-regroup"), async () => {
    try {
      await api("/api/groups/regroup?lang=" + LANG, { method: "POST" });
      await loadGroups();
    } catch (e) {
      showError("#groups-list", e.message);
    }
  });
});

function setErrorsMode(mode) {
  const groups = mode === "groups";
  $("#errors-list").classList.toggle("hidden", groups);
  $("#groups-pane").classList.toggle("hidden", !groups);
  $("#errors-mode-items").classList.toggle("is-active", !groups);
  $("#errors-mode-groups").classList.toggle("is-active", groups);
  if (groups) loadGroups();
}

$("#errors-mode-items").addEventListener("click", () => setErrorsMode("items"));
$("#errors-mode-groups").addEventListener("click", () => setErrorsMode("groups"));

// --- Ćwicz błędy (tryb skupienia) ---------------------------------------------------

function loadTips(exclude) {
  return withBusy("loader.loading", null, async () => {
    try {
      const qs = `/api/tips/focus?lang=${LANG}&mode=${tipsMode}` +
        (exclude ? `&exclude=${exclude}` : "");
      const body = await api(qs);
      if (tipsMode === "group") {
        tipsGroup = body.group;
        tipsError = null;
        setFocusGroup(body.group);
      } else {
        tipsError = body.error;
        tipsGroup = null;
        setFocus(body.error);
      }
      renderGoal(body.progress);
    } catch (e) {
      showError("#tips-result", e.message);
    }
  });
}

function renderGoal(progress) {
  // `required_today` to cel dnia razem z zaległościami z opuszczonych dni — postęp i pasek
  // liczymy właśnie do niego, a pole „Dzienny cel" pokazuje samą stawkę bazową.
  const required = progress.required_today || progress.goal;
  $("#tips-done").textContent = progress.done;
  $("#tips-goal").textContent = required;
  $("#tips-goal-input").value = progress.goal;
  $("#tips-goal-bar").style.width =
    (required ? Math.min(100, (progress.done / required) * 100) : 0) + "%";
  const streak = progress.streak || 0;
  const streakEl = $("#tips-streak");
  streakEl.textContent = "🔥 " + streak + " " + t("tips.streakDays");
  streakEl.classList.toggle("is-zero", streak === 0);
  renderStreakDebt(progress, required);
  renderDrillProgress(progress.drill);
}

/** Ostrzeżenie o zaległym celu: przespane dni można odrobić tylko w całości i tylko dziś. */
function renderStreakDebt(progress, required) {
  const box = $("#tips-debt");
  if (!box) return;
  const days = progress.overdue_days || 0;
  if (!progress.at_risk || !days) {
    box.textContent = "";
    box.classList.add("hidden");
    return;
  }
  const label = days === 1
    ? t("tips.debtOneDay")
    : t("tips.debtManyDays").replace("{days}", days);
  box.textContent = "⚠️ " + t("tips.debtNote").replace("{days}", label).replace("{n}", required);
  box.classList.remove("hidden");
}

/** Postęp ćwiczeń wymaganych do zaliczenia bieżącego błędu (np. 3/5). */
function renderDrillProgress(drill) {
  const box = $("#tips-drill");
  if (!box) return;
  if (!drill) { box.textContent = ""; box.classList.add("hidden"); return; }
  box.classList.remove("hidden");
  box.textContent = `${t("tips.drillProgress")} ${drill.correct}/${drill.target}`;
  box.classList.toggle("is-done", drill.correct >= drill.target);
}

async function refreshProgress() {
  try { renderGoal(await api("/api/tips/progress")); } catch (_) { /* nieistotne dla pracy */ }
}

function setFocus(err) {
  tipsError = err;
  tipsExercise = null;
  $("#tips-exercise-area").classList.add("hidden");
  $("#tips-result").classList.add("hidden");
  $("#tips-generate").textContent = t("tips.generate");
  // Karta wraca do wyglądu „błędnie → poprawnie" (patrz `setFocusGroup`).
  $("#tips-focus").classList.toggle("is-group", false);
  if (!err) {
    $("#tips-empty-text").textContent = t("tips.empty");
    $("#tips-focus").classList.add("hidden");
    $("#tips-empty").classList.remove("hidden");
    return;
  }
  $("#tips-empty").classList.add("hidden");
  $("#tips-topic").textContent = err.topic_label || topicLabel(err.topic);
  $("#tips-from").textContent = err.student_text;
  $("#tips-to").textContent = err.correct_text;
  $("#tips-why").textContent = err.explanation || "";
  renderFocusFeedback(err);
  $("#tips-focus").classList.remove("hidden");
}

/** Zastrzeżenie do wyjaśnienia i usunięcie błędu, którego właśnie ćwiczysz. */
function renderFocusFeedback(err) {
  const box = $("#tips-feedback");
  if (!box) return;
  box.innerHTML = "";
  if (!err.id) return;
  box.appendChild(disputeWidget({
    scope: "error", error_id: err.id, disputed_text: err.explanation || "",
  }));
  // Po usunięciu nie ma czego ćwiczyć — od razu podstawiamy kolejny błąd.
  box.appendChild(deleteErrorWidget(err.id, () => loadTips()));
}

/** Odpowiednik `setFocus` dla trybu grupowego — wypełnia te same sloty karty
 *  `#tips-focus`, bez podmiany innerHTML (żeby nie zagnieździć .focus-card w sobie
 *  i nie zgubić przycisków "Inny błąd" / "Ćwiczenie"). */
function setFocusGroup(group) {
  tipsGroup = group;
  tipsExercise = null;
  $("#tips-exercise-area").classList.add("hidden");
  $("#tips-result").classList.add("hidden");
  $("#tips-generate").textContent = t("tips.generate");
  // Karta trzyma REGUŁĘ, a nie parę „błędnie → poprawnie": klasa zdejmuje ze slotu
  // `.from` czerwień i przekreślenie, a ze slotu `.to` wyróżnienie na zielono.
  $("#tips-focus").classList.toggle("is-group", true);
  if (!group) {
    // NIE „dziennik jest pusty" — błędów może być dwieście, brakuje tylko grup.
    $("#tips-empty-text").textContent = t("groups.noneYet");
    $("#tips-focus").classList.add("hidden");
    $("#tips-empty").classList.remove("hidden");
    return;
  }
  $("#tips-empty").classList.add("hidden");
  $("#tips-topic").textContent = group.topic_label || topicLabel(group.topic);
  // Grupa to reguła, nie para "błędnie → poprawnie": w polu docelowym pokazujemy,
  // ile kontekstów ma grupa, a pusta grupa mówi o tym wprost.
  $("#tips-from").textContent = group.rule;
  $("#tips-to").textContent = group.member_count === 0
    ? t("groups.emptyGroup")
    : t("groups.members").replace("{n}", group.member_count);
  $("#tips-why").textContent = group.explanation || "";
  // Zastrzeżenia dotyczą wpisów w dzienniku, nie grup — slot zostaje pusty.
  $("#tips-feedback").innerHTML = "";
  $("#tips-focus").classList.remove("hidden");
}

/** Skok z „Moje błędy" do „Ćwicz błędy" z konkretnym błędem + od razu ćwiczenie.
 *  Wymusza tryb pojedynczych błędów — inaczej mógłby zostać w trybie grupowym
 *  z nieaktualną grupą, a "Ćwiczenie" wysłałoby zapytanie o tę starą grupę. */
async function focusOnError(err) {
  tipsMode = "error";
  $("#tips-mode-errors").classList.add("is-active");
  $("#tips-mode-groups").classList.remove("is-active");
  activateTab("tips");
  tipsGroup = null;
  setFocus(err);
  await refreshProgress();
  $("#tips-generate").click();
}

/** Skok z widoku grup do „Ćwicz błędy" w trybie grupowym z konkretną grupą. */
async function focusOnGroup(group) {
  tipsMode = "group";
  $("#tips-mode-errors").classList.remove("is-active");
  $("#tips-mode-groups").classList.add("is-active");
  activateTab("tips");
  tipsGroup = group;
  tipsError = null;
  setFocusGroup(group);
  await refreshProgress();
}

/** Przełącznik trybu ćwiczenia: pojedyncze błędy vs. grupy. Czyści stan drugiego
 *  trybu, żeby nieaktualny błąd/grupa nie przeciekł do zapytań nowego trybu. */
function setTipsMode(mode) {
  tipsMode = mode;
  tipsError = null;
  tipsGroup = null;
  $("#tips-mode-errors").classList.toggle("is-active", mode === "error");
  $("#tips-mode-groups").classList.toggle("is-active", mode === "group");
  loadTips();
}

$("#tips-mode-errors").addEventListener("click", () => setTipsMode("error"));
$("#tips-mode-groups").addEventListener("click", () => setTipsMode("group"));

/** Jednostka do WYGENEROWANIA ćwiczenia — czytana z bieżącego fokusu. */
function tipsUnitBody() {
  return tipsMode === "group" ? { group_id: tipsGroup && tipsGroup.id }
                              : { error_id: tipsError && tipsError.id };
}

/** Jednostka do ZALICZENIA — brana z ĆWICZENIA, nie z bieżącego fokusu.
 *  Zaliczamy tę jednostkę, dla której zadanie powstało: między wygenerowaniem
 *  a sprawdzeniem fokus mógł się zmienić (przełącznik trybu zeruje go synchronicznie,
 *  zanim loadTips zdąży się rozwiązać), a praca ucznia ma zostać policzona. */
function tipsGradeBody(ex) {
  return ex && ex._unit ? { ...ex._unit } : tipsUnitBody();
}

/** Id jednostki aktualnie na ekranie — do pominięcia przy losowaniu następnej. */
function tipsCurrentId() {
  const unit = tipsMode === "group" ? tipsGroup : tipsError;
  return unit ? unit.id : undefined;
}

$("#tips-new").addEventListener("click", () => loadTips(tipsCurrentId()));

$("#tips-goal-save").addEventListener("click", () =>
  withBusy("loader.loading", $("#tips-goal-save"), async () => {
    try {
      renderGoal(await api("/api/tips/goal", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal: parseInt($("#tips-goal-input").value, 10) || 1 }),
      }));
    } catch (e) { showError("#tips-result", e.message); }
  }));

$("#tips-generate").addEventListener("click", () =>
  withBusy("loader.generating", $("#tips-generate"), async () => {
    if (tipsMode === "group" ? !tipsGroup : !tipsError) return;
    tipsExercise = null;
    // Czytamy jednostkę PRZED `await` — fokus mógłby się zmienić w trakcie oczekiwania
    // na odpowiedź, a zaliczyć trzeba tę jednostkę, dla której zadanie faktycznie powstało.
    const unit = tipsUnitBody();
    try {
      const ex = await api("/api/tips/exercise", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...unit, lang: LANG }),
      });
      // Zapamiętujemy jednostkę źródłową — do celu zaliczamy TĘ jednostkę, nie bieżący fokus.
      ex._unit = unit;
      tipsExercise = ex;
      $("#tips-result").classList.add("hidden");
      renderExerciseInto(TIPS_UI, ex);
    } catch (e) { showError("#tips-result", e.message); }
  }));

$("#tips-grade").addEventListener("click", async () => {
  if (!tipsExercise) return;
  // Migawka PRZED `await` — globalny `tipsExercise` mógłby się zmienić w trakcie
  // oceniania (np. przełącznik trybu kończy się dopiero teraz), a zaliczyć trzeba
  // dokładnie to ćwiczenie, które właśnie oceniamy, nie to, co jest globalnie aktualne.
  const ex = tipsExercise;
  let result;
  try {
    result = await gradeExercise(TIPS_UI, ex);
  } catch (e) {
    showError("#tips-result", e.message);
    return;
  }
  if (!result) return;
  $("#tips-generate").textContent = t("tips.more");

  // Zestaw ćwiczeń dolicza się do progu zaliczenia błędu (narastająco w obrębie dnia).
  // Osobny try — potknięcie księgowe nie może wymazać wyświetlonej oceny.
  const total = Array.isArray(result.items) && result.items.length ? result.items.length : 1;
  const correct = Array.isArray(result.items) && result.items.length
    ? result.items.filter((i) => i.correct).length
    : (result.correct === true ? 1 : 0);
  try {
    const progress = await api("/api/tips/complete", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...tipsGradeBody(ex), correct_items: correct, total_items: total }),
    });
    renderGoal(progress);
  } catch (_) { /* ocena jest ważniejsza niż licznik */ }
});

// --- Statystyki --------------------------------------------------------------

const kindLabel = (k) => (t("kind." + k) !== "kind." + k ? t("kind." + k) : k);
const fmtNum = (n) => Number(n || 0).toLocaleString(LANG === "en" ? "en-US" : "pl-PL");
const fmtCost = (c) => "$" + Number(c || 0).toFixed(Number(c) < 1 ? 4 : 2);

function statLine(label, value) {
  const row = elem("div", "stat-line");
  row.appendChild(elem("span", "sl-label", label));
  row.appendChild(elem("span", "sl-value", value));
  return row;
}

function loadStats() {
  return withBusy("loader.loading", null, async () => {
    try {
      const [learning, usage] = await Promise.all([
        api("/api/stats/learning?lang=" + LANG),
        api("/api/stats/usage"),
      ]);
      renderLearning(learning);
      renderUsage(usage);
    } catch (e) {
      showError("#stats-usage", e.message);
    }
  });
}

function renderLearning(d) {
  const box = $("#stats-learning");
  box.innerHTML = "";
  const acc = d.accuracy == null ? "—" : Math.round(d.accuracy * 100) + "%";
  box.appendChild(statLine(t("stats.exercisesGenerated"), fmtNum(d.exercises_generated)));
  if (d.exercises_queued) {
    box.appendChild(statLine(t("stats.queued"), fmtNum(d.exercises_queued)));
  }
  box.appendChild(statLine(t("stats.attempts"), fmtNum(d.attempts_total)));
  box.appendChild(statLine(t("stats.accuracy"),
    acc + (d.attempts_graded ? ` (${d.attempts_correct}/${d.attempts_graded})` : "")));
  box.appendChild(statLine(t("stats.reviews"), fmtNum(d.reviews_total)));
  box.appendChild(statLine(t("stats.errorsLogged"), fmtNum(d.errors_logged)));

  if (d.by_type && d.by_type.length) {
    box.appendChild(elem("h3", "stat-sub", t("stats.byType")));
    const max = Math.max(...d.by_type.map((r) => r.attempts));
    d.by_type.forEach((r) => {
      box.appendChild(barRow(r.label || r.type, r.attempts / max, r.correct + "/" + r.attempts));
    });
  }
}

function renderUsage(d) {
  const box = $("#stats-usage");
  box.innerHTML = "";
  const total = d.total || {};
  if (!total.calls) {
    box.appendChild(elem("p", "stat-empty", t("stats.emptyUsage")));
    return;
  }
  box.appendChild(statLine(t("stats.calls"), fmtNum(total.calls)));
  const costLine = statLine(t("stats.cost"), fmtCost(total.cost_usd));
  costLine.classList.add("cost-highlight");
  box.appendChild(costLine);
  box.appendChild(statLine(t("stats.tokensIn"), fmtNum(total.input_tokens)));
  box.appendChild(statLine(t("stats.tokensOut"), fmtNum(total.output_tokens)));
  box.appendChild(statLine(t("stats.tokensCacheWrite"), fmtNum(total.cache_creation_input_tokens)));
  box.appendChild(statLine(t("stats.tokensCacheRead"), fmtNum(total.cache_read_input_tokens)));
  box.appendChild(statLine(t("stats.avgTime"), Math.round(total.avg_duration_ms) + " ms"));

  if (d.lean) {
    box.appendChild(elem("h3", "stat-sub", t("stats.leanTitle")));
    const leanUsed = statLine(t("stats.leanUsed"), fmtCost(d.lean.used_model));
    leanUsed.classList.add("cost-highlight");
    box.appendChild(leanUsed);
    box.appendChild(statLine(t("stats.leanSonnet"), fmtCost(d.lean.sonnet)));
    box.appendChild(elem("p", "muted", t("stats.leanNote")));
    if (Array.isArray(d.lean.assumed_models) && d.lean.assumed_models.length) {
      box.appendChild(elem("p", "muted",
        t("stats.assumedNote") + d.lean.assumed_models.join(", ") + " — stawka założona."));
    }
  }

  if (d.by_kind && d.by_kind.length) {
    box.appendChild(elem("h3", "stat-sub", t("stats.byKind")));
    d.by_kind.forEach((r) => {
      box.appendChild(statLine(`${kindLabel(r.kind)} (${r.calls}×)`, fmtCost(r.cost_usd)));
    });
  }
}

init();
