/**
 * Smoke test frontendu bez przeglądarki: szkieletowy DOM + podstawiony fetch.
 *
 * Uruchomienie (z katalogu projektu):
 *   node tests/smoke_frontend.js
 *
 * Wykonuje realne przepływy aplikacji (generowanie, ocena, Tipy, zastrzeżenia,
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

const handlers = {};        // "klucz|zdarzenie" -> [fn]
const nodes = new Map();    // klucz -> atrapa elementu
const created = [];         // elementy tworzone dynamicznie (przyciski zastrzeżeń itp.)
let radioChecked = {};      // name -> wartość zaznaczonego radio
const failures = [];

function makeNode(key) {
  if (nodes.has(key)) return nodes.get(key);
  const children = [];
  const node = {
    __key: key,
    dataset: {}, style: {}, children,
    className: "", textContent: "", value: key.includes("type") ? "uoe_part1_mcq_cloze" : "",
    selectedIndex: 0, disabled: false, rows: 0, placeholder: "", type: "",
    classList: {
      add() {}, remove() {}, toggle() {},
      contains: () => key.includes("view-practice"),
    },
    set innerHTML(_v) {}, get innerHTML() { return ""; },
    appendChild(c) { children.push(c); return c; },
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
      return ["practice", "tips", "external", "errors", "stats"].map((v) => {
        const n = makeNode(".tab:" + v); n.dataset.view = v; return n;
      });
    }
    if (sel === ".lang") {
      return ["pl", "en"].map((l) => {
        const n = makeNode(".lang:" + l); n.dataset.lang = l; return n;
      });
    }
    return [];
  },
};
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
  errors: [{ id: 11, item_number: 2, topic: "collocations", student_text: "A c",
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

const routes = {
  "/api/taxonomy": TAXONOMY,
  "/api/exercise": MCQ_EX,
  "/api/grade": MULTI_RESULT,
  "/api/tips/focus": {
    error: { id: 7, topic: "collocations", topic_label: "Kolokacje", student_text: "x",
             correct_text: "y", explanation: "z" },
    progress: { done: 1, goal: 5, streak: 2, drill: { correct: 0, target: 5 } },
  },
  "/api/tips/progress": { done: 1, goal: 5, streak: 2, drill: { correct: 1, target: 5 } },
  "/api/tips/exercise": {
    id: 2, type: "uoe_part3_word_formation", topic: "collocations", instructions: "i",
    items: [1, 2, 3, 4, 5].map((n) => ({ number: n, question_text: `zdanie ${n} ______` })),
  },
  "/api/tips/complete": { done: 2, goal: 5, streak: 2, drill: { correct: 3, target: 5 } },
  "/api/tips/goal": { done: 1, goal: 3, streak: 2, drill: { correct: 0, target: 5 } },
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
    by_kind: [{ kind: "generate", calls: 1, cost_usd: 0.3 }], by_model: [], by_day: [],
    lean: { used_model: 0.03, sonnet: 0.02, assumed_models: ["claude-opus-5"] },
  },
  "/api/dispute": {
    dispute_id: 5, verdict: "upheld", revised_explanation: "Poprawione wyjaśnienie.",
    reasoning: "Cytowane słowo nie występowało w zadaniu.", student_was_right: true,
    proposed_changes: ["usunięcie tego wpisu z dziennika błędów"],
  },
  "/api/dispute/5/apply": { applied: ["usunięto wpis z dziennika błędów"] },
};

const calls = [];
global.fetch = async (url) => {
  calls.push(url);
  const p = url.split("?")[0];
  if (!(p in routes)) failures.push("nieznana ścieżka API: " + p);
  return { ok: true, json: async () => routes[p] ?? {} };
};

// --- uruchomienie -----------------------------------------------------------

process.on("unhandledRejection", (e) => failures.push("unhandledRejection: " + e.message));
eval(fs.readFileSync(APP, "utf8"));

const settle = () => new Promise((r) => setTimeout(r, 15));

const fire = async (key, ev = "click") => {
  const fns = handlers[key + "|" + ev] || [];
  if (!fns.length) { failures.push("brak handlera dla " + key); return; }
  for (const fn of fns) await fn({ preventDefault() {} });
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
    ["Tipy: fokus → zestaw ćwiczeń → ocena → cel", async () => {
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
    ["Statystyki", async () => fire(".tab:stats")],
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
