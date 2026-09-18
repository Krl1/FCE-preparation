/**
 * Smoke test frontendu bez przeglądarki: szkieletowy DOM + podstawiony fetch.
 *
 * Uruchomienie (z katalogu projektu):
 *   node tests/smoke_frontend.js
 *
 * Wykonuje realne przepływy aplikacji (generowanie, ocena, ćwiczenie błędów, zastrzeżenia,
 * statystyki, zmiana języka) na atrapach odpowiedzi API i wyłapuje błędy wykonania:
 * literówki w nazwach funkcji, selektory bez odpowiednika w HTML, nieobsłużone
 * kształty danych. Nie sprawdza wyglądu — do tego trzeba przeglądarki.
 */
"use strict";

const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const APP = path.join(ROOT, "static", "app.js");
const HTML = path.join(ROOT, "static", "index.html");
const html = fs.readFileSync(HTML, "utf8");

const htmlIds = new Set([...html.matchAll(/id="([^"]+)"/g)].map((m) => m[1]));
// Pola odpowiedzi są tworzone dynamicznie, więc nie ma ich w HTML.
const DYNAMIC_IDS = /^(practice|tips)-answer(-\d+)?$/;

const VIEWS = ["practice", "tips", "external", "errors", "stats", "cards"];

const handlers = {};        // "klucz|zdarzenie" -> [fn]
const nodes = new Map();    // klucz -> atrapa elementu
const created = [];         // elementy tworzone dynamicznie (przyciski zastrzeżeń itp.)
let radioChecked = {};      // name -> wartość zaznaczonego radio
const failures = [];

function makeNode(key) {
  if (nodes.has(key)) return nodes.get(key);
  const children = [];
  // Klasy są prawdziwym zbiorem, a `className` go przepisuje — dzięki temu warunki
  // `classList.contains(...)` w aplikacji (która zakładka jest aktywna, czy panel
  // grup jest schowany, czy nakładka ładowania zniknęła) znaczą w teście to samo,
  // co w przeglądarce. Węzły ze statycznego HTML dostają klasy startowe niżej.
  const classes = new Set();
  const node = {
    __key: key, __classes: classes,
    dataset: {}, style: {}, children,
    textContent: "", value: key.includes("type") ? "uoe_part1_mcq_cloze" : "",
    selectedIndex: 0, disabled: false, rows: 0, placeholder: "", type: "",
    classList: {
      add(...cls) { cls.forEach((c) => classes.add(c)); },
      remove(...cls) { cls.forEach((c) => classes.delete(c)); },
      toggle(c, force) {
        const on = force === undefined ? !classes.has(c) : Boolean(force);
        if (on) classes.add(c); else classes.delete(c);
        return on;
      },
      contains: (c) => classes.has(c),
    },
    set innerHTML(_v) {}, get innerHTML() { return ""; },
    appendChild(c) { children.push(c); return c; },
    // `insertBefore` jest realne: bez niego kafel grupy wywalał się w połowie budowy,
    // a błąd znikał w `catch` ładowania listy — czyli widok grup nie był naprawdę testowany.
    insertBefore(c, ref) {
      const at = ref ? children.indexOf(ref) : -1;
      if (at >= 0) children.splice(at, 0, c); else children.push(c);
      return c;
    },
    get firstChild() { return children.length ? children[0] : null; },
    prepend() {}, remove() {}, focus() {},
    click() { (handlers[key + "|click"] || []).forEach((fn) => fn({ preventDefault() {} })); },
    setAttribute() {}, getAttribute: () => null,
    addEventListener(ev, fn) { (handlers[key + "|" + ev] ||= []).push(fn); },
    querySelector: (s) => makeNode(key + " " + s),
    querySelectorAll: () => [],
    closest: () => null,
  };
  // Elementy tworzone dynamicznie (pola odpowiedzi) dostają `id` już po utworzeniu.
  // Rejestrujemy je wtedy pod selektorem `#id`, żeby `querySelector` zwracał TEN sam
  // obiekt — inaczej test nie mógłby wpisać do nich wartości i cicho sprawdzałby
  // wyłącznie ścieżkę „brak odpowiedzi".
  let classNameValue = "";
  Object.defineProperty(node, "className", {
    get: () => classNameValue,
    set(value) {
      classNameValue = String(value ?? "");
      classes.clear();
      classNameValue.split(/\s+/).filter(Boolean).forEach((c) => classes.add(c));
    },
  });
  let elementId = "";
  Object.defineProperty(node, "id", {
    get: () => elementId,
    set(value) { elementId = value; nodes.set("#" + value, node); },
  });

  nodes.set(key, node);
  return node;
}

global.document = {
  documentElement: makeNode("html"),
  body: makeNode("body"),
  title: "",
  // Jeden globalny handler klawiatury (skróty fiszek) — rejestrowany na `document`,
  // nie na konkretnym węźle, więc trzyma się osobno od handlerów per-element.
  addEventListener(ev, fn) { (handlers["document|" + ev] ||= []).push(fn); },
  createElement: (tag) => {
    const n = makeNode(`new:${tag}:${created.length}`);
    created.push(n);
    return n;
  },
  querySelector(sel) {
    const byId = /^#([a-z0-9-]+)$/.exec(sel);
    if (byId && !htmlIds.has(byId[1]) && !DYNAMIC_IDS.test(byId[1])) {
      failures.push("selektor bez odpowiednika w HTML: " + sel);
    }
    if (/input\[name=/.test(sel)) {
      const nm = /name="([^"]+)"/.exec(sel);
      const val = nm ? radioChecked[nm[1]] : undefined;
      return val === undefined ? null : { value: val };
    }
    return makeNode(sel);
  },
  querySelectorAll(sel) {
    if (sel === ".tab") {
      return VIEWS.map((v) => {
        const n = makeNode(".tab:" + v); n.dataset.view = v; return n;
      });
    }
    if (sel === ".view") {
      return VIEWS.map((v) => makeNode("#view-" + v));
    }
    if (sel === ".lang") {
      return ["pl", "en"].map((l) => {
        const n = makeNode(".lang:" + l); n.dataset.lang = l; return n;
      });
    }
    return [];
  },
};
// Klasy startowe z HTML: bez nich „schowany" panel byłby w atrapie widoczny,
// a żadna zakładka nie byłaby aktywna.
for (const tag of html.match(/<[a-zA-Z][^>]*>/g) || []) {
  const id = /\sid="([^"]+)"/.exec(tag);
  const cls = /\sclass="([^"]+)"/.exec(tag);
  if (id && cls) makeNode("#" + id[1]).className = cls[1];
}

global.localStorage = { getItem: () => "pl", setItem() {} };
global.window = global;

// --- atrapy odpowiedzi API ---------------------------------------------------

const TAXONOMY = {
  exercise_types: [
    { id: "uoe_part1_mcq_cloze", label: "MCQ", label_en: "MCQ", area: "use_of_english", topics: ["collocations"] },
    { id: "uoe_part3_word_formation", label: "WF", label_en: "WF", area: "use_of_english", topics: ["word_formation"] },
    { id: "writing_essay", label: "Essay", label_en: "Essay", area: "writing", topics: ["content"] },
  ],
  topics: [
    { id: "collocations", label: "Kolokacje", label_en: "Collocations" },
    { id: "word_formation", label: "Słowotwórstwo", label_en: "Word formation" },
    { id: "content", label: "Treść", label_en: "Content" },
  ],
};

const MCQ_EX = {
  id: 1, type: "uoe_part1_mcq_cloze", topic: "collocations", instructions: "Wybierz wariant",
  question_text: "Tekst (1) ______ i (2) ______.",
  items: [{ number: 1, options: ["A a", "B b"] }, { number: 2, options: ["A c", "B d"] }],
};
const OPEN_EX = {
  id: 5, type: "uoe_part3_word_formation", topic: "word_formation", instructions: "Utwórz formę",
  items: [
    { number: 1, question_text: "It was a great ______.", stem: "CONVENIENT" },
    { number: 2, question_text: "She acted ______.", stem: "PROFESSION" },
  ],
};
const KWT_EX = {
  id: 6, type: "uoe_part1_mcq_cloze", topic: "collocations", instructions: "Przekształć",
  items: [
    { number: 1, question_text: "Someone stole it.\nIt ______ yesterday.", key_word: "WAS" },
    { number: 2, question_text: "They will finish.\nIt ______ soon.", key_word: "BE" },
  ],
};
const MULTI_RESULT = {
  correct: false, score: "1/2", feedback: "Wynik 1/2.",
  errors: [{ id: null, item_number: 2, topic: "collocations", student_text: "A c",
             correct_text: "B d", explanation: "e", severity: "major" }],
  items: [
    { number: 1, correct: true, student_option: "A a", correct_option: "A a", comment: "ok", option_notes: null },
    { number: 2, correct: false, student_option: "A c", correct_option: "B d", comment: "źle",
      option_notes: [{ option: "B d", is_correct: true, comment: "pasuje" },
                     { option: "A c", is_correct: false, comment: "nie pasuje" }] },
  ],
};
const WRITING_RESULT = {
  correct: null, feedback: "fb", band: "Band 3", errors: [],
  scores: [{ criterion: "content", score: 3, comment: "c" }],
};
const FIVE_GAPS_EX = {
  id: 9, type: "uoe_part3_word_formation", topic: "word_formation", instructions: "Uzupełnij",
  items: [1, 2, 3, 4, 5].map((n) => ({ number: n, question_text: `zdanie ${n} ______` })),
};
/** Pięć luk, cztery błędne z IDENTYCZNĄ odpowiedzią „-" — zgłoszony przypadek. */
const FIVE_GAPS_RESULT = {
  correct: false, score: "1/5", feedback: "f",
  errors: [1, 2, 4, 5].map((n) => ({ id: null, item_number: n, topic: "articles",
    student_text: "-", correct_text: "the", explanation: "e" + n, severity: "minor" })),
  items: [1, 2, 3, 4, 5].map((n) => ({ number: n, correct: n === 3, student_option: n === 3 ? "a" : "-",
    correct_option: n === 3 ? "a" : "the", comment: "c" + n, option_notes: null })),
};
/** Dwie propozycje niepowiązane z lukami — dla przycisku „Dodaj wszystkie". */
const TWO_CANDIDATES_RESULT = {
  correct: false, feedback: "fb",
  errors: [
    { id: null, item_number: null, topic: "tenses", student_text: "a1",
      correct_text: "b1", explanation: "e1", severity: "minor" },
    { id: null, item_number: null, topic: "articles", student_text: "a2",
      correct_text: "b2", explanation: "e2", severity: "major" },
  ],
};

const routes = {
  "/api/taxonomy": TAXONOMY,
  "/api/exercise": MCQ_EX,
  "/api/grade": MULTI_RESULT,
  "/api/tips/focus": {
    error: { id: 7, topic: "collocations", topic_label: "Kolokacje", student_text: "x",
             correct_text: "y", explanation: "z" },
    // Atrapa nie czyta `mode` z zapytania (routing tnie na "?"), więc `group` jest
    // obecne zawsze — w trybie błędów `loadTips` i tak go ignoruje.
    group: { id: 1, rule: "depend + on", explanation: "e", topic: "prepositions",
             topic_label: "Przyimki", member_count: 2 },
    progress: { done: 1, goal: 5, streak: 2, required_today: 5, overdue_days: 0,
               at_risk: false, drill: { correct: 0, target: 5 } },
  },
  "/api/tips/progress": { done: 1, goal: 5, streak: 2, required_today: 5, overdue_days: 0,
                          at_risk: false, drill: { correct: 1, target: 5 } },
  "/api/tips/exercise": {
    id: 2, type: "uoe_part3_word_formation", topic: "collocations", instructions: "i",
    items: [1, 2, 3, 4, 5].map((n) => ({ number: n, question_text: `zdanie ${n} ______` })),
  },
  "/api/tips/complete": { done: 2, goal: 5, streak: 2, required_today: 5, overdue_days: 0,
                          at_risk: false, drill: { correct: 3, target: 5 } },
  "/api/tips/goal": { done: 1, goal: 3, streak: 2, required_today: 3, overdue_days: 0,
                      at_risk: false, drill: { correct: 0, target: 5 } },
  "/api/errors": [{ id: 1, item_number: null, topic: "collocations", topic_label: "Kolokacje",
                    student_text: "a", correct_text: "b", explanation: "c", severity: "minor",
                    created_at: "2026-07-28T10:00:00+02:00" }],
  "/api/stats/topics": [{ topic: "collocations", topic_label: "Kolokacje", count: 3 }],
  "/api/stats/learning": {
    exercises_generated: 5, exercises_queued: 2, attempts_total: 4, attempts_graded: 4,
    attempts_correct: 2, accuracy: 0.5, reviews_total: 1, errors_logged: 3,
    by_type: [{ type: "uoe_part1_mcq_cloze", label: "MCQ", attempts: 4, correct: 2 }],
    disputes: { total: 1, upheld: 1, applied: 0 },
  },
  "/api/stats/usage": {
    total: { calls: 2, input_tokens: 4, output_tokens: 100, cache_creation_input_tokens: 20,
             cache_read_input_tokens: 10, est_input_tokens: 300, cost_usd: 0.5, avg_duration_ms: 3000 },
    // `kind: "cards"` to nazwa, którą naprawdę wysyła `llm_client.generate_cards` —
    // rozliczenie kosztów musi mieć dla niej etykietę, a nie surowy klucz.
    by_kind: [{ kind: "generate", calls: 1, cost_usd: 0.3 },
              { kind: "cards", calls: 3, cost_usd: 0.2 }],
    by_model: [], by_day: [],
    lean: { used_model: 0.03, sonnet: 0.02, assumed_models: ["claude-opus-5"] },
  },
  "/api/dispute": {
    dispute_id: 5, verdict: "upheld", revised_explanation: "Poprawione wyjaśnienie.",
    reasoning: "Cytowane słowo nie występowało w zadaniu.", student_was_right: true,
    proposed_changes: ["usunięcie tego wpisu z dziennika błędów"],
  },
  "/api/dispute/5/apply": { applied: ["usunięto wpis z dziennika błędów"] },
  "POST /api/errors": { id: 42, topic: "collocations", topic_label: "Kolokacje" },
  "/api/errors/1": { deleted: 1 },   // ręczne usunięcie wpisu z dziennika (DELETE)
  "/api/errors/7": { deleted: 7 },   // ręczne usunięcie błędu w „Ćwicz błędy"
  "/api/groups": { groups: [{ id: 1, rule: "depend + on", explanation: "e",
                              topic: "prepositions", topic_label: "Przyimki",
                              member_count: 2 }], ungrouped: 3 },
  "/api/groups/1/members": [
    { id: 11, topic: "collocations", topic_label: "Kolokacje", student_text: "depends from",
      correct_text: "depends on", explanation: "kalka z polskiego", severity: "minor" },
  ],
  // Odpięcie ostatniego wpisu osieraca grupę — odpowiedź niesie też nazwę reguły.
  "/api/errors/11/group": { error_id: 11, group_id: null, emptied_group_id: 1,
                            emptied_group_rule: "depend + on" },
  "/api/groups/assign": { assigned: 1, created: 1, unassigned: 0 },
  "/api/groups/regroup": { assigned: 0, created: 1, unassigned: 0 },
  // Dziedzina zna DWA kształty: "translate" i "gap" — żadnego "cloze". Przód karty
  // tłumaczeniowej to zdanie POLSKIE, a forma błędna ucznia ("depends from") nie ma
  // prawa pojawić się na żadnej stronie karty; żyje wyłącznie w `source`, czyli we
  // wpisie z dziennika. Fikstura z formą błędną na przodzie dokumentowałaby dokładnie
  // to, czego zakazuje prompt.
  // Kształt `source` odpowiada realnej odpowiedzi backendu: dla `source_kind: "error"`
  // to pełny wpis z dziennika, dla `"group"` — pełny obiekt grupy. Atrapa BEZ tego pola
  // ukrywałaby błędy w gałęzi pijawki (`revealCard` czyta `card.source` dopiero po kliknięciu
  // „Ćwicz ten błąd/tę grupę”).
  "/api/cards/session": { cards: [
    { card_id: 1, source_kind: "error", source_id: 1, topic: "prepositions",
      topic_label: "Przyimki", front: "To zależy od pogody.",
      back: "It depends on the weather.\n\nkalka z polskiego",
      shape: "translate", leech: false,
      source: { id: 1, created_at: "2026-09-17T10:00:00+02:00", source: "external",
                exercise_type: "external", topic: "prepositions", topic_label: "Przyimki",
                student_text: "depends from", correct_text: "depends on",
                explanation: "kalka z polskiego", severity: "minor", group_id: null } },
    // Karta-pijawka: reguła wraca uparcie, więc backend proponuje skok do grupy.
    { card_id: 9, source_kind: "group", source_id: 1, topic: "prepositions",
      topic_label: "Przyimki", front: "You can ______ on him.", back: "depend",
      shape: "gap", hint: "możesz na nim polegać", leech: true,
      source: { id: 1, rule: "depend + on", explanation: "kalka z polskiego",
                topic: "prepositions", topic_label: "Przyimki", member_count: 2 } },
  ],
    progress: { done_today: 0, overdue: 0, due_now: 2, new_limit: 20, total_sources: 2,
               unprepared: 0 } },
  "/api/cards/prepare": { prepared: 2, unprepared: 0, remaining: 0 },
  // Każda karta w kolejce ma teraz `card_id` — trasa `/1/grade` odpowiada karcie ID 1
  // z fikstury sesji powyżej.
  "/api/cards/1/grade": { card_id: 1, interval_days: 1, due_on: "2026-09-18",
    leech: false, progress: { done_today: 1, overdue: 0, due_now: 1, new_limit: 20,
                              total_sources: 2, unprepared: 0 } },
  // Karta 7 to karta z LUKĄ ze scenariusza podpowiedzi — ocenienie jej przewija sesję
  // na kartę tłumaczeniową, co pozwala sprawdzić, czy podpowiedź została wyczyszczona.
  "/api/cards/7/grade": { card_id: 7, interval_days: 1, due_on: "2026-09-19",
    leech: false, progress: { done_today: 1, overdue: 0, due_now: 1, new_limit: 20,
                              total_sources: 2, unprepared: 0 } },
  // Karty 11 i 12 obsługują scenariusz rund: 11 zostaje pomylona i musi wrócić.
  "/api/cards/11/grade": { card_id: 11, interval_days: 0, due_on: "2026-09-18",
    leech: false, progress: { done_today: 1, overdue: 0, due_now: 1, new_limit: 20,
                              total_sources: 2, unprepared: 0 } },
  "/api/cards/12/grade": { card_id: 12, interval_days: 1, due_on: "2026-09-19",
    leech: false, progress: { done_today: 2, overdue: 0, due_now: 0, new_limit: 20,
                              total_sources: 2, unprepared: 0 } },
  "/api/cards/progress": { done_today: 0, overdue: 0, due_now: 1, new_limit: 20,
                           total_sources: 2, unprepared: 0 },
  // „Przegeneruj" to jedyny przycisk w sesji wołający płatny model. Odpowiedź ma
  // kształt `_card_content`: front/back/shape i nic więcej.
  "/api/cards/1/regenerate": { front: "Wszystko zależy od ciebie.",
                               back: "It all depends on you.\n\nkalka z polskiego",
                               shape: "translate" },
};

const calls = [];
// Ścieżki, które mają ODPOWIEDZIEĆ BŁĘDEM (klucz jak w `routes`: „METODA ścieżka"
// albo sama ścieżka). Bez tego nie da się sprawdzić, co interfejs robi PO nieudanej
// operacji — a właśnie tam mieszka stan „część się zapisała, część nie".
const failing = new Map();
global.fetch = async (url, options) => {
  const method = (options && options.method) || "GET";
  const body = options && options.body;
  // Doklejamy ciało żądania (jeśli jest) — potrzebne do sprawdzenia, JAKĄ jednostkę
  // (group_id/error_id) wysłało zaliczenie, nie tylko na jaką ścieżkę.
  calls.push(method + " " + url + (body ? " " + body : ""));
  const p = url.split("?")[0];
  // Klucz „METODA ścieżka" ma pierwszeństwo — POST /api/errors zwraca coś innego niż GET.
  const broken = [method + " " + p, p].find((k) => failing.has(k));
  if (broken) {
    const detail = failing.get(broken);
    return { ok: false, statusText: detail, json: async () => ({ detail }) };
  }
  const key = [method + " " + p, p].find((k) => k in routes);
  if (!key) failures.push("nieznana ścieżka API: " + method + " " + p);
  return { ok: true, json: async () => (key ? routes[key] : {}) };
};

// --- uruchomienie -----------------------------------------------------------

process.on("unhandledRejection", (e) => failures.push("unhandledRejection: " + e.message));
eval(fs.readFileSync(APP, "utf8"));

const settle = () => new Promise((r) => setTimeout(r, 15));

const nodeText = (key) => String((nodes.get(key) || {}).textContent ?? "");

const hasClass = (key, cls) => Boolean(nodes.get(key) && nodes.get(key).__classes.has(cls));

const fire = async (key, ev = "click") => {
  const fns = handlers[key + "|" + ev] || [];
  if (!fns.length) { failures.push("brak handlera dla " + key); return; }
  for (const fn of fns) await fn({ preventDefault() {} });
};

/** Symuluje `keydown` na `document` (skróty fiszek) — `tag` udaje `e.target.tagName`,
 *  żeby sprawdzić, że skrót nie odpala się w polu tekstowym. */
const fireKey = async (key, tag = "BODY") => {
  const fns = handlers["document|keydown"] || [];
  for (const fn of fns) await fn({ key, target: { tagName: tag }, preventDefault() {} });
};

/** Dwa naciśnięcia klawisza JEDNO PO DRUGIM, bez czekania na pierwsze — dokładnie tak
 *  wypada szybkie dwukrotne uderzenie w spację. Osobny helper, bo `fireKey` czeka na
 *  handler, a samo to czekanie przepuściłoby odpowiedź serwera i schowało błąd. */
const fireKeyTwice = (key, tag = "BODY") => {
  const fns = handlers["document|keydown"] || [];
  for (const fn of fns) fn({ key, target: { tagName: tag }, preventDefault() {} });
  for (const fn of fns) fn({ key, target: { tagName: tag }, preventDefault() {} });
};

/** Klika element tworzony dynamicznie, wskazany przez klasę (np. przycisk zastrzeżenia). */
const fireByClass = async (cls, nth = 0) => {
  const hits = created.filter((n) => String(n.className || "").includes(cls));
  if (!hits[nth]) { failures.push("brak elementu o klasie " + cls); return false; }
  const fns = handlers[hits[nth].__key + "|click"] || [];
  if (!fns.length) { failures.push("brak handlera na " + cls); return false; }
  for (const fn of fns) await fn({ preventDefault() {} });
  return true;
};

/** Klika element dynamiczny, uruchamiając TYLKO najnowszy handler i NIE czekając na
 *  jego zakończenie. Atrapy węzłów są współdzielone (klucz zależy od pozycji w `created`,
 *  a scenariusze zerują tę listę), więc na jednym węźle leżą też domknięcia z poprzednich
 *  renderów — a handler, który czeka na odpowiedź użytkownika, zablokowałby `await`. */
const clickLatestByClass = (cls, nth = 0) => {
  const hits = created.filter((n) => String(n.className || "").includes(cls));
  if (!hits[nth]) { failures.push("brak elementu o klasie " + cls); return Promise.resolve(); }
  const fns = handlers[hits[nth].__key + "|click"] || [];
  if (!fns.length) { failures.push("brak handlera na " + cls); return Promise.resolve(); }
  return Promise.resolve(fns[fns.length - 1]({ preventDefault() {} }));
};

const setInput = (id, value) => {
  const node = nodes.get("#" + id);
  if (node) node.value = value;
  else failures.push("brak pola " + id);
};

(async () => {
  await settle(); // init()

  const scenarios = [
    ["generowanie zadania (Ćwicz)", async () => fire("#btn-generate")],
    ["walidacja: ocena bez odpowiedzi", async () => { radioChecked = {}; await fire("#btn-grade"); }],
    ["ocena zadania z wariantami", async () => {
      radioChecked = { "mcq-1": "A a", "mcq-2": "A c" };
      await fire("#btn-grade");
    }],
    ["pozycje z polem tekstowym (części 2–4)", async () => {
      routes["/api/exercise"] = OPEN_EX;
      await fire("#btn-generate"); await settle();
      setInput("practice-answer-1", "inconvenience");
      setInput("practice-answer-2", "professionally");
      await fire("#btn-grade");
    }],
    ["pozycje ze słowem-kluczem", async () => {
      routes["/api/exercise"] = KWT_EX;
      await fire("#btn-generate"); await settle();
      radioChecked = { "mcq-1": "A a", "mcq-2": "A c" };
      await fire("#btn-grade");
    }],
    ["ocena Writing (kryteria + pasmo)", async () => {
      routes["/api/exercise"] = { id: 3, type: "writing_essay", topic: "content",
                                  instructions: "i", question_text: "temat" };
      routes["/api/grade"] = WRITING_RESULT;
      await fire("#btn-generate"); await settle();
      setInput("practice-answer", "My essay text.");
      await fire("#btn-grade");
    }],
    ["sprawdzanie z zewnątrz", async () => fire("#btn-grade-external")],
    ["Moje błędy", async () => fire("#btn-refresh-errors")],
    ["Ćwicz błędy: fokus → zestaw ćwiczeń → ocena → cel", async () => {
      await fire(".tab:tips"); await settle();
      await fire("#tips-generate"); await settle();
      radioChecked = {};
      await fire("#tips-grade"); await settle();          // brak odpowiedzi → walidacja
      [1, 2, 3, 4, 5].forEach((n) => setInput(`tips-answer-${n}`, "have"));
      routes["/api/grade"] = {
        correct: false, score: "4/5", feedback: "ok", errors: [],
        items: [1, 2, 3, 4, 5].map((n) => ({ number: n, correct: n !== 5, student_option: "have",
          correct_option: "have", comment: "c", option_notes: null })),
      };
      await fire("#tips-grade"); await settle();
      await fire("#tips-new");
      await fire("#tips-goal-save");
    }],
    ["Ćwicz błędy: zaległy cel po przespanych dniach", async () => {
      const normal = routes["/api/tips/focus"];
      routes["/api/tips/focus"] = {
        error: normal.error,
        progress: { done: 4, goal: 5, streak: 11, required_today: 15, overdue_days: 2,
                    at_risk: true, drill: { correct: 1, target: 5 } },
      };
      await fire(".tab:tips"); await settle();
      if (!nodeText("#tips-goal").includes("15")) {
        failures.push("cel dnia nie uwzględnia zaległości: " + nodeText("#tips-goal"));
      }
      if (!nodeText("#tips-streak").includes("11")) {
        failures.push("licznik serii nie pokazuje dni: " + nodeText("#tips-streak"));
      }
      const debt = nodeText("#tips-debt");
      if (!debt.includes("15") || !debt.includes("2")) {
        failures.push("brak notki o zaległościach (dni i cel): " + debt);
      }
      routes["/api/tips/focus"] = normal;
      await fire(".tab:tips"); await settle();
      if (nodeText("#tips-debt") !== "") {
        failures.push("notka o zaległościach została po ich spłacie: " + nodeText("#tips-debt"));
      }
    }],
    ["zastrzeżenie do pozycji wyniku + zatwierdzenie korekty", async () => {
      created.length = 0;
      routes["/api/exercise"] = MCQ_EX; routes["/api/grade"] = MULTI_RESULT;
      await fire(".tab:practice");
      await fire("#btn-generate"); await settle();
      radioChecked = { "mcq-1": "A a", "mcq-2": "A c" };
      await fire("#btn-grade"); await settle();
      await fireByClass("dispute-btn");                    // otwórz panel
      await fireByClass("dispute-send"); await settle();   // wyślij zastrzeżenie
      await fireByClass("dispute-apply"); await settle();  // zatwierdź korektę danych
    }],
    ["zastrzeżenie do wpisu w dzienniku", async () => {
      created.length = 0;
      await fire("#btn-refresh-errors"); await settle();
      await fireByClass("dispute-btn");
      await fireByClass("dispute-send"); await settle();
    }],
    ["zatwierdzenie błędu z oceny (pojedynczo)", async () => {
      created.length = 0;
      routes["/api/exercise"] = MCQ_EX; routes["/api/grade"] = MULTI_RESULT;
      await fire(".tab:practice");
      await fire("#btn-generate"); await settle();
      radioChecked = { "mcq-1": "A a", "mcq-2": "A c" };
      await fire("#btn-grade"); await settle();
      const before = calls.filter((c) => c.startsWith("POST /api/errors")).length;
      await fireByClass("add-btn"); await settle();
      const after = calls.filter((c) => c.startsWith("POST /api/errors")).length;
      if (after !== before + 1) failures.push("zatwierdzenie błędu nie wysłało POST /api/errors");
    }],
    ["Dodaj wszystkie (dwie propozycje na raz)", async () => {
      created.length = 0;
      routes["/api/grade"] = TWO_CANDIDATES_RESULT;
      setInput("external-question", "I ______ done it.");
      setInput("external-answer", "has");
      await fire("#btn-grade-external"); await settle();
      const before = calls.filter((c) => c.startsWith("POST /api/errors")).length;
      await fireByClass("add-all"); await settle();
      const added = calls.filter((c) => c.startsWith("POST /api/errors")).length - before;
      if (added !== 2) failures.push("Dodaj wszystkie zapisało " + added + " z 2 propozycji");
      routes["/api/grade"] = MULTI_RESULT;
    }],
    ["cztery błędne luki z tą samą odpowiedzią → cztery osobne przyciski", async () => {
      created.length = 0;
      routes["/api/exercise"] = FIVE_GAPS_EX; routes["/api/grade"] = FIVE_GAPS_RESULT;
      await fire(".tab:practice");
      await fire("#btn-generate"); await settle();
      // Ta sama odpowiedź w każdej luce — właśnie to sklejało błędy w jedną pozycję.
      [1, 2, 3, 4, 5].forEach((n) => setInput(`practice-answer-${n}`, "-"));
      await fire("#btn-grade"); await settle();
      const buttons = created.filter((n) => String(n.className || "").includes("add-btn"));
      if (buttons.length !== 4) failures.push("przyciski dodawania: " + buttons.length + " z 4");
      // Zatwierdzamy drugi z nich — musi polecieć dokładnie jedno żądanie.
      const before = calls.filter((c) => c.startsWith("POST /api/errors")).length;
      await fireByClass("add-btn", 1); await settle();
      const added = calls.filter((c) => c.startsWith("POST /api/errors")).length - before;
      if (added !== 1) failures.push("zatwierdzenie jednej luki wysłało " + added + " żądań");
      routes["/api/exercise"] = MCQ_EX; routes["/api/grade"] = MULTI_RESULT;
    }],
    ["anulowanie usuwania błędu (nic nie leci do API)", async () => {
      created.length = 0;
      await fire("#btn-refresh-errors"); await settle();
      const before = calls.length;
      await fireByClass("delete-btn");     // rozwiń potwierdzenie
      await fireByClass("delete-no");      // wycofaj się
      if (calls.length !== before) failures.push("anulowanie wysłało żądanie do API");
    }],
    ["usunięcie błędu z dziennika", async () => {
      created.length = 0;
      await fire("#btn-refresh-errors"); await settle();
      await fireByClass("delete-btn");
      await fireByClass("delete-yes"); await settle();
      if (!calls.includes("DELETE /api/errors/1")) failures.push("brak wywołania usunięcia błędu");
    }],
    ["usunięcie ostatniego wpisu grupy → pytanie o osieroconą grupę", async () => {
      created.length = 0;
      routes["/api/errors/1"] = { deleted: 1, emptied_group_id: 1,
                                  emptied_group_rule: "depend + on" };
      await fire("#btn-refresh-errors"); await settle();
      await clickLatestByClass("delete-btn");
      // Handler „Tak, usuń" czeka na odpowiedź o osieroconej grupie, więc NIE czekamy
      // na jego zakończenie — dokładnie jak przeglądarka, która wraca do pętli zdarzeń.
      const pending = clickLatestByClass("delete-yes");
      await settle();

      if (!created.some((n) => String(n.className || "") === "orphan-ask")) {
        failures.push("brak pytania o osieroconą grupę po usunięciu ostatniego wpisu");
      }
      // Sedno regresji: pytanie musi paść PO wyjściu z `withBusy`. Nakładka ładowania
      // jest `position: fixed; inset: 0` — gdyby jeszcze wisiała, ani „Zostaw", ani
      // „Usuń grupę" nie dałyby się kliknąć myszą i aplikacja stałaby na „Usuwam…".
      if (!hasClass("#loader", "hidden")) {
        failures.push("nakładka ładowania wisi nad pytaniem o osieroconą grupę");
      }

      const before = calls.length;
      await clickLatestByClass("orphan-keep");   // „Zostaw” — pusta grupa ZOSTAJE
      await pending;
      await settle();
      if (calls.slice(before).some((c) => c.startsWith("DELETE /api/groups/"))) {
        failures.push("„Zostaw\" usunęło grupę");
      }
      if (!hasClass("#loader", "hidden")) {
        failures.push("nakładka ładowania została po odpowiedzi na pytanie o grupę");
      }
      routes["/api/errors/1"] = { deleted: 1 };
    }],
    ["usunięcie ćwiczonego błędu (Ćwicz błędy)", async () => {
      created.length = 0;
      await fire(".tab:tips"); await settle();   // setFocus() buduje panel od nowa
      await fireByClass("delete-btn");
      await fireByClass("delete-yes"); await settle();
    }],
    ["zastrzeżenie do ćwiczonego błędu (Ćwicz błędy)", async () => {
      created.length = 0;
      await fire(".tab:tips"); await settle();
      await fireByClass("dispute-btn");
      await fireByClass("dispute-send"); await settle();
    }],
    ["przełączniki trybu: grupy błędów (Moje błędy) i grupy ćwiczeń (Ćwicz błędy)", async () => {
      await fire("#errors-mode-groups"); await settle();
      await fire("#errors-mode-items"); await settle();

      await fire("#tips-mode-groups"); await settle();
      let before = calls.length;
      await fire("#tips-new"); await settle();   // „Inny błąd" w trybie grupowym
      const groupCall = calls.slice(before).find((c) => c.startsWith("GET /api/tips/focus"));
      if (!groupCall || !groupCall.includes("mode=group") || !groupCall.includes("exclude=1")) {
        failures.push("Inny błąd (tryb grupowy) nie pominął bieżącej grupy: " +
          (groupCall || "brak żądania"));
      }

      await fire("#tips-mode-errors"); await settle();
      before = calls.length;
      await fire("#tips-new"); await settle();   // „Inny błąd" w trybie pojedynczym
      const errCall = calls.slice(before).find((c) => c.startsWith("GET /api/tips/focus"));
      if (!errCall || !errCall.includes("mode=error") || !errCall.includes("exclude=7")) {
        failures.push("Inny błąd (tryb pojedynczy) nie pominął bieżącego błędu: " +
          (errCall || "brak żądania"));
      }
    }],
    ["ochrona zaliczenia: zmiana trybu w trakcie ćwiczenia nie gubi jednostki", async () => {
      routes["/api/grade"] = {
        correct: false, score: "4/5", feedback: "ok", errors: [],
        items: [1, 2, 3, 4, 5].map((n) => ({ number: n, correct: n !== 5, student_option: "have",
          correct_option: "have", comment: "c", option_notes: null })),
      };

      await fire("#tips-mode-groups"); await settle();     // fokus: grupa id 1
      await fire("#tips-generate"); await settle();        // zadanie wygenerowane DLA GRUPY 1
      [1, 2, 3, 4, 5].forEach((n) => setInput(`tips-answer-${n}`, "have"));

      // Wyścig: przełącznik zeruje tipsGroup/tipsError SYNCHRONICZNIE i odpala loadTips
      // (asynchronicznie), ale NIE czekamy na jego rozstrzygnięcie — dokładnie w tym oknie
      // stare ćwiczenie (i jednostka, dla której powstało) musi przetrwać do zaliczenia.
      await fire("#tips-mode-errors");
      const before = calls.length;
      await fire("#tips-grade"); await settle();

      const completeCall = calls.slice(before).find((c) => c.startsWith("POST /api/tips/complete"));
      if (!completeCall) {
        failures.push("zaliczenie w trakcie przełączania trybu nie wysłało /api/tips/complete");
      } else if (!completeCall.includes('"group_id":1')) {
        failures.push("zaliczenie w trakcie przełączania trybu zgubiło jednostkę (grupę): " + completeCall);
      }

      routes["/api/grade"] = MULTI_RESULT;
    }],
    ["Ćwicz tę grupę: skok z widoku grup do trybu grupowego", async () => {
      created.length = 0;
      await fire("#errors-mode-groups"); await settle();
      const before = calls.length;
      await clickLatestByClass("practice-btn");   // „Ćwicz tę grupę”
      await settle();
      if (!calls.slice(before).some((c) => c.startsWith("GET /api/tips/progress"))) {
        failures.push("„Ćwicz tę grupę” nie odświeżyło postępu");
      }
      if (nodeText("#tips-from") !== "depend + on") {
        failures.push("karta skupienia nie pokazuje reguły grupy: " + nodeText("#tips-from"));
      }
      if (hasClass("#tips-focus", "hidden")) failures.push("„Ćwicz tę grupę” nie pokazało karty");
      // Bez tej klasy reguła renderowałaby się na czerwono i przekreślona — jak błąd.
      if (!hasClass("#tips-focus", "is-group")) {
        failures.push("karta w trybie grupowym nie ma klasy is-group");
      }
      await fire("#errors-mode-items"); await settle();
    }],
    ["rozwinięcie grupy do kontekstów i odpięcie wpisu", async () => {
      created.length = 0;
      await fire("#errors-mode-groups"); await settle();

      const membersCalls = () => calls.filter((c) => c.includes("/api/groups/1/members")).length;
      await clickLatestByClass("group-expand"); await settle();
      if (membersCalls() !== 1) failures.push("rozwinięcie grupy nie pobrało kontekstów");

      // Zwinięcie i ponowne rozwinięcie korzysta z tego, co już pobrane.
      await clickLatestByClass("group-expand"); await settle();
      await clickLatestByClass("group-expand"); await settle();
      if (membersCalls() !== 1) {
        failures.push("ponowne rozwinięcie pobrało konteksty drugi raz: " + membersCalls());
      }

      const pending = clickLatestByClass("detach-btn");
      await settle();
      if (!calls.some((c) => c.startsWith("PATCH /api/errors/11/group"))) {
        failures.push("„Odepnij” nie wysłało PATCH /api/errors/{id}/group");
      }
      if (!created.some((n) => String(n.className || "") === "orphan-ask")) {
        failures.push("odpięcie ostatniego wpisu nie zapytało o osieroconą grupę");
      }
      if (!hasClass("#loader", "hidden")) {
        failures.push("nakładka ładowania wisi nad pytaniem po odpięciu wpisu");
      }
      const before = calls.length;
      await clickLatestByClass("orphan-keep");   // grupa ZOSTAJE
      await pending; await settle();
      if (calls.slice(before).some((c) => c.startsWith("DELETE /api/groups/"))) {
        failures.push("„Zostaw” po odpięciu usunęło grupę");
      }
      await fire("#errors-mode-items"); await settle();
    }],
    ["tryb grupowy bez grup: komunikat kieruje do „Scal nowe”", async () => {
      const normal = routes["/api/tips/focus"];
      routes["/api/tips/focus"] = { error: null, group: null, progress: normal.progress };
      await fire(".tab:tips"); await settle();
      await fire("#tips-mode-groups"); await settle();
      const msg = nodeText("#tips-empty-text");
      if (!msg.includes("Scal nowe")) {
        failures.push("brak wskazówki „Scal nowe” przy braku grup: " + msg);
      }
      if (msg.includes("Dziennik błędów jest pusty")) {
        failures.push("brak grup opisany jako pusty dziennik: " + msg);
      }
      // Powrót do trybu błędów przywraca właściwy komunikat pustki.
      await fire("#tips-mode-errors"); await settle();
      if (!nodeText("#tips-empty-text").includes("Dziennik błędów jest pusty")) {
        failures.push("komunikat pustki dziennika nie wrócił: " + nodeText("#tips-empty-text"));
      }
      routes["/api/tips/focus"] = normal;
      await fire("#tips-mode-errors"); await settle();
    }],
    ["zmiana języka w trakcie ćwiczenia grupy nie gubi zadania", async () => {
      await fire(".tab:tips"); await settle();
      await fire("#tips-mode-groups"); await settle();   // fokus: grupa id 1
      await fire("#tips-generate"); await settle();      // zadanie DLA GRUPY 1
      [1, 2, 3, 4, 5].forEach((n) => setInput(`tips-answer-${n}`, "have"));

      const before = calls.length;
      await fire(".lang:en"); await settle();
      const refetch = calls.slice(before).find((c) => c.startsWith("GET /api/tips/focus"));
      if (refetch) {
        failures.push("zmiana języka pobrała nową grupę i zgubiła ćwiczenie: " + refetch);
      }

      routes["/api/grade"] = {
        correct: false, score: "4/5", feedback: "ok", errors: [],
        items: [1, 2, 3, 4, 5].map((n) => ({ number: n, correct: n !== 5, student_option: "have",
          correct_option: "have", comment: "c", option_notes: null })),
      };
      await fire("#tips-grade"); await settle();
      const completeCall = calls.slice(before).find((c) => c.startsWith("POST /api/tips/complete"));
      if (!completeCall || !completeCall.includes('"group_id":1')) {
        failures.push("ćwiczenie grupy nie przetrwało zmiany języka: " +
          (completeCall || "brak zaliczenia"));
      }
      routes["/api/grade"] = MULTI_RESULT;
      await fire(".lang:pl"); await settle();
      await fire("#tips-mode-errors"); await settle();
    }],
    ["Fiszki: przygotowanie treści kart", async () => {
      await fire(".tab:cards"); await settle();
      const before = calls.length;
      await fire("#cards-prepare"); await settle();
      if (!calls.slice(before).some((c) => c.startsWith("POST /api/cards/prepare"))) {
        failures.push("przygotowanie kart nie wysłało żądania do API");
      }
      // Podsumowanie („Przygotowano: 2, nieudanych: 0, zostało: 0" z fikstury) musi
      // ZOSTAĆ widoczne po zakończeniu — inaczej uczeń nie wie, czy kosztowna operacja
      // (dziesiątki sekund, prawdziwe pieniądze) coś dała, i klika ponownie w niepewności.
      if (!nodeText("#cards-counter").includes("Przygotowano: 2")) {
        failures.push("podsumowanie przygotowania kart zniknęło z licznika: " +
          nodeText("#cards-counter"));
      }
    }],
    ["Fiszki: nieudane przygotowanie odświeża licznik", async () => {
      // Partie zapisują się po kolei, więc błąd którejkolwiek zostawia CZĘŚĆ kart już
      // przygotowanych. Licznik sprzed operacji kłamałby wtedy o stanie bazy.
      created.length = 0;
      const progressBefore = routes["/api/cards/progress"];
      routes["/api/cards/progress"] = { done_today: 0, overdue: 0, due_now: 1,
                                        new_limit: 20, total_sources: 9, unprepared: 7 };
      failing.set("POST /api/cards/prepare", "model padł w połowie");
      await fire(".tab:cards"); await settle();
      const before = calls.length;
      await fire("#cards-prepare"); await settle();
      if (!calls.slice(before).some((c) => c.startsWith("GET /api/cards/progress"))) {
        failures.push("nieudane przygotowanie nie odświeżyło licznika");
      }
      if (!nodeText("#cards-counter").includes("Nieprzygotowanych: 7")) {
        failures.push("licznik został z treścią sprzed nieudanego przygotowania: " +
          nodeText("#cards-counter"));
      }
      // Banner jest DOKLEJANYM węzłem, a atrapa nie sumuje treści dzieci w `textContent`
      // rodzica — szukamy go więc wśród elementów utworzonych dynamicznie.
      if (!created.some((n) => String(n.className || "").includes("error-banner") &&
                               String(n.textContent || "").includes("model padł w połowie"))) {
        failures.push("nieudane przygotowanie nie pokazało bannera z błędem");
      }
      failing.clear();
      routes["/api/cards/progress"] = progressBefore;
      await fire(".tab:cards"); await settle();
    }],
    ["Fiszki: sesja → odkrycie → ocena karty", async () => {
      await fire(".tab:cards"); await settle();
      await fire("#cards-start"); await settle();
      await fire("#cards-reveal"); await settle();
      if (hasClass("#cards-back", "hidden")) failures.push("rewers fiszki nie odkrył się");
      await fire("#cards-known"); await settle();
      if (!calls.some((c) => c.includes("/api/cards/1/grade"))) {
        failures.push("ocena fiszki nie poleciała na serwer");
      }
    }],
    ["Fiszki: karta-pijawka pokazuje podpowiedź z przyciskiem", async () => {
      created.length = 0;
      // Kontynuacja poprzedniego scenariusza: zaliczenie pierwszej karty przesunęło
      // kolejkę na drugą pozycję — kartę-pijawkę z fikstury sesji (leech: true).
      await fire("#cards-reveal"); await settle();
      if (hasClass("#cards-leech", "hidden")) {
        failures.push("podpowiedź o pijawce nie pokazała się przy karcie-pijawce");
      }
      const leechBtns = created.filter((n) => String(n.className || "").includes("btn-sm"));
      // Karta-pijawka z fikstury jest GRUPOWA, więc przycisk ma mówić o grupie.
      if (leechBtns.length !== 1 || leechBtns[0].textContent !== "Ćwicz tę grupę") {
        failures.push("brak przycisku „Ćwicz tę grupę” przy grupowej karcie-pijawce: " +
          leechBtns.map((n) => n.textContent).join(", "));
      }
      if (await fireByClass("btn-sm")) {
        await settle();
        if (!hasClass("#view-tips", "is-active")) {
          failures.push("„Ćwicz ten błąd” przy pijawce nie przeniosło do „Ćwicz błędy”");
        }
        if (nodeText("#tips-from") !== "depend + on") {
          failures.push("skok z pijawki nie pokazał reguły grupy: " + nodeText("#tips-from"));
        }
      }
      await fire(".tab:cards"); await settle();
    }],
    ["Fiszki: skróty klawiszowe (spacja/n) i blokada w polu tekstowym", async () => {
      routes["/api/cards/session"] = {
        cards: [
          { card_id: 2, source_kind: "error", source_id: 2, topic: "prepositions",
            topic_label: "Przyimki", front: "front1", back: "back1", shape: "translate",
            leech: false },
          { card_id: 3, source_kind: "error", source_id: 3, topic: "prepositions",
            topic_label: "Przyimki", front: "front2", back: "back2", shape: "translate",
            leech: false },
        ],
        progress: { done_today: 0, overdue: 0, due_now: 2, new_limit: 20, total_sources: 2,
                   unprepared: 0 },
      };
      routes["/api/cards/2/grade"] = { card_id: 2, interval_days: 1, due_on: "2026-09-18",
        leech: false, progress: { done_today: 1, overdue: 0, due_now: 1, new_limit: 20,
                                  total_sources: 2, unprepared: 0 } };
      routes["/api/cards/3/grade"] = { card_id: 3, interval_days: 1, due_on: "2026-09-18",
        leech: false, progress: { done_today: 2, overdue: 0, due_now: 0, new_limit: 20,
                                  total_sources: 2, unprepared: 0 } };
      await fire(".tab:cards"); await settle();
      await fire("#cards-start"); await settle();

      // W polu tekstowym spacja/„n" NIE mogą odkrywać ani oceniać fiszki.
      const before = calls.length;
      await fireKey(" ", "INPUT");
      if (!hasClass("#cards-back", "hidden")) {
        failures.push("spacja w polu tekstowym odkryła fiszkę");
      }
      await fireKey("n", "INPUT");
      if (calls.length !== before) {
        failures.push("skrót klawiszowy zadziałał mimo fokusu w polu tekstowym");
      }

      // Poza polem tekstowym: spacja odkrywa, potem zalicza jako „umiem".
      await fireKey(" ");
      if (hasClass("#cards-back", "hidden")) failures.push("spacja nie odkryła fiszki");
      await fireKey(" "); await settle();
      if (!calls.some((c) => c.includes("/api/cards/2/grade"))) {
        failures.push("spacja po odkryciu nie zaliczyła fiszki");
      }

      // Druga karta: odkrycie + „n" zalicza jako „nie umiem".
      await fireKey(" ");
      if (hasClass("#cards-back", "hidden")) failures.push("spacja nie odkryła drugiej fiszki");
      await fireKey("n"); await settle();
      const lastGrade = calls.filter((c) => c.includes("/api/cards/3/grade")).pop();
      if (!lastGrade || !lastGrade.includes('"grade":"unknown"')) {
        failures.push('klawisz „n" nie zaliczył fiszki jako „nie umiem": ' + lastGrade);
      }
      routes["/api/cards/session"] = {
        cards: [
          { card_id: 1, source_kind: "error", source_id: 1, topic: "prepositions",
            topic_label: "Przyimki", front: "To zależy od pogody.",
      back: "It depends on the weather.\n\nkalka z polskiego",
            shape: "translate", leech: false }],
        progress: { done_today: 0, overdue: 0, due_now: 1, new_limit: 20, total_sources: 1,
                   unprepared: 0 },
      };
    }],
    ["Fiszki: podpowiedź jest przy luce i znika przy karcie bez niej", async () => {
      routes["/api/cards/session"] = {
        cards: [
          { card_id: 7, source_kind: "error", source_id: 7, topic: "tenses",
            topic_label: "Czasy", front: "I ______ you tomorrow.", back: "will call",
            shape: "gap", hint: "zadzwonię do ciebie", leech: false },
          { card_id: 8, source_kind: "error", source_id: 8, topic: "prepositions",
            topic_label: "Przyimki", front: "W domu jest cicho.", back: "at home",
            shape: "translate", hint: "", leech: false },
        ],
        progress: { done_today: 0, overdue: 0, due_now: 2, new_limit: 20,
                   total_sources: 2, unprepared: 0 },
      };
      await fire(".tab:cards"); await settle();
      await fire("#cards-start"); await settle();
      // Bez podpowiedzi „I ______ you tomorrow" pasuje do call, text, see i meet —
      // to zgadywanka, nie sprawdzanie gramatyki.
      if (nodeText("#cards-hint") !== "zadzwonię do ciebie") {
        failures.push("brak podpowiedzi przy karcie z luką: " + nodeText("#cards-hint"));
      }
      if (nodes.get("#cards-hint").__classes.has("hidden")) {
        failures.push("podpowiedź przy karcie z luką została ukryta");
      }
      await fire("#cards-reveal"); await settle();
      await fire("#cards-known"); await settle();
      // Karta tłumaczeniowa podpowiedzi nie ma. Gdyby została po poprzedniej karcie,
      // uczeń czytałby wskazówkę do zdania, którego już nie widzi.
      if (nodeText("#cards-hint") !== "") {
        failures.push("podpowiedź została po poprzedniej karcie: " + nodeText("#cards-hint"));
      }
      if (!nodes.get("#cards-hint").__classes.has("hidden")) {
        failures.push("pusta podpowiedź nie została ukryta");
      }
    }],
    ["Fiszki: karta \u201enie umiem\u201d wraca w kolejnej rundzie", async () => {
      routes["/api/cards/session"] = {
        cards: [
          { card_id: 11, source_kind: "error", source_id: 11, topic: "prepositions",
            topic_label: "Przyimki", front: "pomylona", back: "b11",
            shape: "translate", hint: "", leech: false },
          { card_id: 12, source_kind: "error", source_id: 12, topic: "prepositions",
            topic_label: "Przyimki", front: "umiana", back: "b12",
            shape: "translate", hint: "", leech: false },
        ],
        mode: "both",
        progress: { done_today: 0, overdue: 0, due_now: 2, new_limit: 20,
                   total_sources: 2, unprepared: 0 },
      };
      await fire(".tab:cards"); await settle();
      const before = calls.length;
      await fire("#cards-start"); await settle();

      const szerokosc = () => parseInt(nodes.get("#cards-progress-bar").style.width) || 0;
      await fire("#cards-reveal"); await settle();
      await fire("#cards-unknown"); await settle();   // karta 11 do poprawki
      const poPomylce = szerokosc();
      await fire("#cards-reveal"); await settle();
      await fire("#cards-known"); await settle();     // karta 12 opanowana

      // Pasek liczy opanowane karty z całej sesji, nie postęp w bieżącej rundzie —
      // gdyby liczył rundę, druga runda cofnęłaby go na zero i wyglądałby na błąd.
      if (szerokosc() < poPomylce) {
        failures.push("pasek postępu cofnął się przy nowej rundzie: "
          + poPomylce + "% -> " + szerokosc() + "%");
      }

      // Runda pierwsza się skończyła, ale karta 11 czeka — sesja ma trwać dalej.
      if (nodeText("#cards-front") !== "pomylona") {
        failures.push("karta \u201enie umiem\u201d nie wróciła w drugiej rundzie: "
          + nodeText("#cards-front"));
      }
      if (nodes.get("#cards-round").__classes.has("hidden")) {
        failures.push("licznik rundy nie pokazał się w drugiej rundzie");
      }
      if (!nodeText("#cards-round").includes("Runda 2")) {
        failures.push("licznik rundy nie mówi, która to runda: " + nodeText("#cards-round"));
      }

      await fire("#cards-reveal"); await settle();
      await fire("#cards-known"); await settle();

      // Liczy się PIERWSZA odpowiedź: powtórka nie może wysłać drugiej oceny, bo
      // przeliczyłaby odstęp i zbliżyła kartę do oznaczenia \u201euparta\u201d.
      const oceny = calls.slice(before).filter((c) => c.includes("/grade"));
      if (oceny.length !== 2) {
        failures.push("oczekiwano 2 ocen (po jednej na kartę), było " + oceny.length
          + ": " + oceny.join(" | "));
      }
      // Po czystym przejściu sesja się kończy.
      if (nodes.get("#cards-empty").__classes.has("hidden")) {
        failures.push("sesja nie zakończyła się po poprawnym przejściu wszystkich kart");
      }
      if (!nodes.get("#cards-round").__classes.has("hidden")) {
        failures.push("licznik rundy został po zakończeniu sesji");
      }
    }],
    ["Fiszki: cztery przyciski startu wysyłają swój tryb", async () => {
      routes["/api/cards/session"] = {
        cards: [], mode: "due",
        progress: { done_today: 0, overdue: 0, due_now: 0, new_limit: 20,
                   total_sources: 2, unprepared: 0 },
      };
      await fire(".tab:cards"); await settle();
      for (const [sel, tryb] of [["#cards-start", "both"], ["#cards-start-due", "due"],
                                 ["#cards-start-new", "new"], ["#cards-start-all", "all"]]) {
        const before = calls.length;
        await fire(sel); await settle();
        if (!calls.slice(before).some((c) => c.includes("mode=" + tryb))) {
          failures.push(sel + " nie wysłał trybu " + tryb);
        }
      }
    }],
    ["Fiszki: dwa szybkie naciśnięcia spacji oceniają kartę raz", async () => {
      routes["/api/cards/session"] = {
        cards: [
          { card_id: 4, source_kind: "error", source_id: 4, topic: "prepositions",
            topic_label: "Przyimki", front: "front1", back: "back1",
            shape: "translate", leech: false },
          { card_id: 5, source_kind: "error", source_id: 5, topic: "prepositions",
            topic_label: "Przyimki", front: "front2", back: "back2",
            shape: "translate", leech: false },
        ],
        progress: { done_today: 0, overdue: 0, due_now: 2, new_limit: 20, total_sources: 2,
                   unprepared: 0 },
      };
      routes["/api/cards/4/grade"] = { card_id: 4, interval_days: 1, due_on: "2026-09-18",
        leech: false, progress: { done_today: 1, overdue: 0, due_now: 1, new_limit: 20,
                                  total_sources: 2, unprepared: 0 } };
      await fire(".tab:cards"); await settle();
      await fire("#cards-start"); await settle();

      await fireKey(" ");                 // odkrycie rewersu
      const before = calls.filter((c) => c.includes("/api/cards/4/grade")).length;
      fireKeyTwice(" ");                  // dwie oceny, zanim pierwsza zdąży wrócić
      await settle();

      const graded = calls.filter((c) => c.includes("/api/cards/4/grade")).length - before;
      if (graded !== 1) {
        failures.push("podwójna spacja wysłała ocen: " + graded + " (powinna jedną)");
      }
      if (nodeText("#cards-front") !== "front2") {
        failures.push("druga fiszka wypadła z kolejki, widać: " + nodeText("#cards-front"));
      }
      if (hasClass("#cards-area", "hidden")) {
        failures.push("kolejka skończyła się przedwcześnie po podwójnej spacji");
      }

      routes["/api/cards/session"] = {
        cards: [
          { card_id: 1, source_kind: "error", source_id: 1, topic: "prepositions",
            topic_label: "Przyimki", front: "To zależy od pogody.",
      back: "It depends on the weather.\n\nkalka z polskiego",
            shape: "translate", leech: false }],
        progress: { done_today: 0, overdue: 0, due_now: 1, new_limit: 20, total_sources: 1,
                   unprepared: 0 },
      };
    }],
    ["Fiszki: „Przegeneruj” pyta o uwagi, zanim zapłaci za model", async () => {
      await fire(".tab:cards"); await settle();
      await fire("#cards-start"); await settle();
      await fire("#cards-reveal"); await settle();
      const before = calls.length;
      await fire("#cards-regenerate"); await settle();
      // Samo kliknięcie ma TYLKO otworzyć pole. Gdyby strzelało od razu, uczeń płaciłby
      // za ślepe ułożenie od nowa, zanim zdąży powiedzieć, co poprawić.
      if (calls.slice(before).some((c) => c.includes("/regenerate"))) {
        failures.push("„Przegeneruj” wysłał żądanie, zanim spytał o uwagi");
      }
      if (nodes.get("#cards-regen-box").__classes.has("hidden")) {
        failures.push("pole na uwagi nie pokazało się po kliknięciu „Przegeneruj”");
      }
      setInput("cards-regen-notes", "za długie, daj krótsze zdanie");
      await fire("#cards-regen-go"); await settle();
      const żądanie = calls.slice(before)
        .find((c) => c.startsWith("POST /api/cards/1/regenerate"));
      if (!żądanie) {
        failures.push("potwierdzenie nie wysłało żądania do API");
      } else if (!żądanie.includes("za długie, daj krótsze zdanie")) {
        failures.push("uwagi nie doleciały do API: " + żądanie);
      }
      // Uwagi są jednorazowe — po użyciu pole ma być puste i schowane, żeby nie
      // doklejały się po cichu do następnej próby.
      if (nodes.get("#cards-regen-notes").value !== "") {
        failures.push("uwagi zostały w polu po użyciu");
      }
      if (!nodes.get("#cards-regen-box").__classes.has("hidden")) {
        failures.push("pole na uwagi nie schowało się po użyciu");
      }
      // Nowa treść ma wejść na obie strony karty OD RAZU — bez tego uczeń zapłacił za
      // wywołanie modelu i dalej patrzy na starą, odrzuconą kartę.
      if (nodeText("#cards-front") !== "Wszystko zależy od ciebie.") {
        failures.push("przód karty nie przyjął przegenerowanej treści: " +
          nodeText("#cards-front"));
      }
      if (!nodeText("#cards-back").startsWith("It all depends on you.")) {
        failures.push("rewers karty nie przyjął przegenerowanej treści: " +
          nodeText("#cards-back"));
      }
    }],
    ["Statystyki: rozliczenie kosztów tłumaczy rodzaj wywołania", async () => {
      created.length = 0;
      await fire(".tab:stats"); await settle();
      const labels = created.filter((n) => String(n.className || "").includes("sl-label"))
                            .map((n) => String(n.textContent || ""));
      if (!labels.includes("Przygotowanie fiszek (3×)")) {
        failures.push("rozliczenie kosztów nie przetłumaczyło rodzaju „cards”: " +
          labels.join(" | "));
      }
    }],
    ["zmiana języka EN → PL", async () => { await fire(".lang:en"); await fire(".lang:pl"); }],
  ];

  for (const [name, run] of scenarios) {
    try { await run(); await settle(); console.log("  ✓", name); }
    catch (e) { failures.push(`${name} → ${e.constructor.name}: ${e.message}`); console.log("  ✗", name); }
  }
  await settle();

  const paths = [...new Set(calls.map((c) => c.split("?")[0]))].sort();
  console.log("\nwywołane ścieżki API:\n  " + paths.join("\n  "));

  const unique = [...new Set(failures)];
  if (unique.length) {
    console.log("\nBŁĘDY:");
    unique.forEach((f) => console.log("  -", f));
    process.exit(1);
  }
  console.log("\nSMOKE TEST: OK — żadnych błędów wykonania");
})();
