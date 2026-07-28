"""Jedyny moduł wywołujący Claude.

Aplikacja korzysta z Claude Code w trybie headless (`claude -p ... --output-format json`),
używając logowania z subskrypcji (~/.claude/.credentials.json) — bez klucza API.
Cała zależność od sposobu uwierzytelnienia jest odizolowana tutaj: aby przełączyć się
na klucz API/SDK, wystarczy podmienić funkcję `_invoke`.
"""

from __future__ import annotations

import json
import os
import subprocess

from . import fce_taxonomy as tax
from .models import ErrorItem, GeneratedExercise, GradingResult

CLAUDE_BIN = os.environ.get("FCE_CLAUDE_BIN", "claude")
TIMEOUT_S = int(os.environ.get("FCE_LLM_TIMEOUT", "180"))
_DISALLOWED_TOOLS = ["Bash", "Read", "Write", "Edit", "Glob", "Grep", "WebSearch", "WebFetch"]

_EXAMINER_SYSTEM = (
    "You are an experienced Cambridge B2 First (FCE) examiner and English teacher. "
    "You reply with ONLY the requested JSON object — no prose, no explanations outside "
    "the JSON, no markdown code fences. Write feedback, explanations and instructions in the "
    "language requested in the user message; keep exercise content and corrected sentences in English."
)

_LANG_NAME = {"pl": "Polish", "en": "English"}


def _lang_name(lang: str) -> str:
    return _LANG_NAME.get(lang, "Polish")


class LLMError(RuntimeError):
    """Błąd wywołania lub parsowania odpowiedzi Claude."""


# Hook do rejestrowania zużycia (tokeny/koszt). main.py ustawia go na zapis do bazy;
# domyślnie no-op, dzięki czemu llm_client pozostaje niezależny od warstwy trwałości.
_usage_recorder = None


def set_usage_recorder(fn) -> None:
    global _usage_recorder
    _usage_recorder = fn


def _record_usage(kind: str, envelope: dict, est_input_tokens: int = 0) -> None:
    if _usage_recorder is None:
        return
    usage = envelope.get("usage") or {}
    model = ""
    for meta in (envelope.get("modelUsage") or {}).values():
        model = meta.get("canonicalModel") or ""
        break
    try:
        _usage_recorder({
            "kind": kind,
            "model": model,
            "input_tokens": int(usage.get("input_tokens", 0) or 0),
            "output_tokens": int(usage.get("output_tokens", 0) or 0),
            "cache_creation_input_tokens": int(usage.get("cache_creation_input_tokens", 0) or 0),
            "cache_read_input_tokens": int(usage.get("cache_read_input_tokens", 0) or 0),
            "est_input_tokens": int(est_input_tokens),
            "cost_usd": float(envelope.get("total_cost_usd", 0.0) or 0.0),
            "duration_ms": int(envelope.get("duration_ms", 0) or 0),
        })
    except Exception:
        pass  # logowanie użycia nigdy nie może przerwać właściwego działania


def _invoke(prompt: str, kind: str = "other") -> str:
    """Wywołuje Claude headless i zwraca surową treść odpowiedzi modelu (pole `result`).

    Seam do testów i do ewentualnej podmiany na inny backend (klucz API / SDK).
    """
    args = [
        CLAUDE_BIN,
        "-p",
        prompt,
        "--system-prompt",
        _EXAMINER_SYSTEM,
        "--disallowedTools",
        *_DISALLOWED_TOOLS,
        "--output-format",
        "json",
    ]
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=TIMEOUT_S)
    except FileNotFoundError as exc:
        raise LLMError(
            f"Nie znaleziono polecenia '{CLAUDE_BIN}'. Zainstaluj Claude Code lub ustaw FCE_CLAUDE_BIN."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise LLMError(f"Przekroczono limit czasu ({TIMEOUT_S}s) oczekiwania na Claude.") from exc

    if proc.returncode != 0:
        raise LLMError(f"Claude zakończył się kodem {proc.returncode}: {proc.stderr.strip()[:500]}")

    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise LLMError(f"Nie udało się sparsować koperty JSON z Claude: {proc.stdout[:300]}") from exc

    # Szacunek tokenów wejściowych "lekkiej" wersji na API (system egzaminatora + prompt),
    # z pominięciem narzutu Claude Code. Przybliżenie ~4 znaki/token.
    est_input = (len(_EXAMINER_SYSTEM) + len(prompt)) // 4
    _record_usage(kind, envelope, est_input)  # rejestruj także przy błędzie (koszt mógł powstać)

    if envelope.get("is_error"):
        raise LLMError(f"Claude zwrócił błąd: {envelope.get('result', '')[:500]}")

    return envelope.get("result", "")


def _extract_json(text: str) -> dict:
    """Wyciąga obiekt JSON z odpowiedzi modelu (usuwa ewentualne ```json fences```)."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # usuń pierwszą linię z fence i zamykający fence
        cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[: -3]
        cleaned = cleaned.strip()
    # dodatkowe zabezpieczenie: wytnij od pierwszego '{' do ostatniego '}'
    if not cleaned.startswith("{"):
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


def _call_json(prompt: str, kind: str = "other") -> dict:
    """Wywołuje model i zwraca sparsowany JSON. Jedna ponowna próba przy błędzie parsowania."""
    raw = _invoke(prompt, kind)
    try:
        return _extract_json(raw)
    except (json.JSONDecodeError, ValueError):
        retry_prompt = (
            prompt
            + "\n\nWAŻNE: Poprzednia odpowiedź nie była poprawnym JSON. "
            "Zwróć TYLKO poprawny obiekt JSON, bez żadnego dodatkowego tekstu ani znaczników."
        )
        raw2 = _invoke(retry_prompt, kind)
        try:
            return _extract_json(raw2)
        except (json.JSONDecodeError, ValueError) as exc:
            raise LLMError(f"Model nie zwrócił poprawnego JSON po ponownej próbie: {raw2[:300]}") from exc


# --- Funkcje domenowe --------------------------------------------------------

# Liczba pozycji w jednym zadaniu Use of English (luki / mini-zadania).
ITEMS_PER_EXERCISE = 5


# Ile zadań generować w JEDNYM wywołaniu. Koszt wywołania jest zdominowany przez stały
# narzut Claude Code (~23 tys. tokenów niezależnie od treści), więc generowanie wsadowe
# jest niemal darmowe na sztukę i dodatkowo eliminuje czekanie na kolejne zadania.
# Ograniczeniem jest długość odpowiedzi: przy zbyt dużym JSON zostaje on ucięty i trzeba
# powtarzać wywołanie, co niweczy oszczędność. Każde zadanie Use of English ma teraz
# 5 pozycji, więc wsad jest mniejszy niż dla krótkich poleceń Writing.
_UOE_BATCH = 2
_WRITING_BATCH = 3


def batch_size(exercise_type: str) -> int:
    return _WRITING_BATCH if tax.is_writing(exercise_type) else _UOE_BATCH


def _expected_item_count(exercise_type: str) -> int:
    """Ile pozycji powinno mieć zadanie danego typu (0 = zadanie jednoczęściowe, np. Writing)."""
    return 0 if tax.is_writing(exercise_type) else ITEMS_PER_EXERCISE


def _has_enough_items(exercise: GeneratedExercise, expected: int) -> bool:
    return expected == 0 or len(exercise.items or []) >= expected


# Dopisek do promptu, gdy model zignorował wymaganą liczbę pozycji.
_STRICT_ITEMS = (
    "\n\nUWAGA: poprzednia odpowiedź miała ZA MAŁO pozycji. Tablica 'items' MUSI zawierać "
    "dokładnie {n} elementów o numerach 1–{n}. Nie skracaj jej."
)


def generate_exercises(exercise_type: str, topic: str, weak_points: list[str] | None = None,
                       lang: str = "pl", count: int = 1) -> list[GeneratedExercise]:
    """Generuje `count` różnych zadań danego typu w JEDNYM wywołaniu modelu.

    Pierwsze zadanie jest pokazywane od razu, pozostałe trafiają do kolejki w bazie."""
    if count <= 1:
        return [generate_exercise(exercise_type, topic, weak_points, lang)]

    single = _exercise_shape(exercise_type, topic, lang)
    weak = ", ".join(tax.topic_label(t) for t in (weak_points or []) if t != topic)
    weak_line = f"\nUczeń ma słabe punkty w: {weak}. Jeśli to naturalne, delikatnie je uwzględnij." if weak else ""
    type_label = tax.EXERCISE_TYPES.get(exercise_type, {}).get("label", exercise_type)

    prompt = (
        f"Wygeneruj {count} RÓŻNYCH zadań egzaminacyjnych FCE typu: {type_label}.\n"
        f"{single['focus']}{weak_line}\n"
        f"Zadania muszą różnić się tematyką i słownictwem — nie powielaj tego samego kontekstu.\n"
        f"Zwróć TYLKO obiekt JSON postaci {{\"exercises\": [element, element, ...]}} "
        f"z dokładnie {count} elementami, gdzie element = {single['shape']}\n"
        f"Uwaga na dwie różne liczby: {count} to liczba ZADAŃ w tablicy 'exercises', "
        f"a każde z nich ma mieć pełną liczbę pozycji w swojej tablicy 'items'.\n"
        f"Pisz zwięźle — pola tekstowe bez zbędnych komentarzy, żeby odpowiedź nie została ucięta.\n"
        f"Pola z treścią zadania po angielsku; pole 'instructions' w języku: {_lang_name(lang)}."
    )
    expected = _expected_item_count(exercise_type)

    def parse(payload: dict) -> list[GeneratedExercise]:
        raw = payload.get("exercises") or []
        return [GeneratedExercise.model_validate(item) for item in raw[:count]]

    out = parse(_call_json(prompt, kind="generate"))
    good = [e for e in out if _has_enough_items(e, expected)]
    if not good and expected:
        # Model zignorował wymaganą liczbę pozycji — jedna ponowna próba z dosłownym
        # przypomnieniem. Gdy znów nie posłucha, wydajemy to, co jest (lepsze krótsze
        # zadanie niż błąd), ale kolejki już nie zasilamy skróconymi zadaniami.
        retry = parse(_call_json(prompt + _STRICT_ITEMS.format(n=expected), kind="generate"))
        good = [e for e in retry if _has_enough_items(e, expected)] or retry or out
    if not good:
        raise LLMError("Model nie zwrócił żadnego zadania w odpowiedzi wsadowej.")
    return good


def _exercise_shape(exercise_type: str, topic: str, lang: str) -> dict:
    """Kształt JSON i wytyczne merytoryczne dla danego typu zadania (wspólne dla
    generowania pojedynczego i wsadowego).

    Wszystkie części Use of English są wieloczęściowe — jedno zadanie zawiera
    `ITEMS_PER_EXERCISE` pozycji. Part 1 dzieli jeden wspólny tekst, części 2–4
    mają osobne zdanie w każdej pozycji.
    """
    topic_label = tax.topic_label(topic)
    n = ITEMS_PER_EXERCISE

    if tax.is_writing(exercise_type):
        return {
            "shape": '{"instructions": str, "question_text": str}',
            "focus": (
                "question_text ma być pełnym poleceniem zadania Writing (temat + wymagania, "
                f"~140-190 słów). Zadbaj, by temat naturalnie sprzyjał ćwiczeniu obszaru: {topic_label}."
            ),
        }

    if exercise_type == "uoe_part1_mcq_cloze":
        return {
            "shape": ('{"instructions": str, "question_text": str, '
                      '"items": [{"number": int, "options": [str, str, str, str], '
                      '"answer": str, "answer_notes": str}]}'),
            "focus": (
                f"Ułóż spójny, ciekawy tekst po angielsku (~120–160 słów) z DOKŁADNIE {n} lukami, "
                f"oznaczonymi w 'question_text' jako (1) ______ , (2) ______ itd. "
                f"Dla KAŻDEJ luki podaj w 'items' dokładnie 4 warianty (z prefiksami A/B/C/D) i jeden "
                f"poprawny w polu 'answer' — zapisany identycznie jak w 'options'. Luki mają testować "
                f"przede wszystkim: {topic_label}; pozostałe mogą sprawdzać inne słownictwo na poziomie B2. "
                f"Numery w 'items' muszą odpowiadać numerom luk w tekście. "
                f"'answer_notes' to najwyżej jedno krótkie zdanie."
            ),
        }

    if exercise_type == "uoe_part4_key_word_transformation":
        return {
            "shape": ('{"instructions": str, '
                      '"items": [{"number": int, "question_text": str, "key_word": str, '
                      '"answer": str, "answer_notes": str}]}'),
            "focus": (
                f"Przygotuj DOKŁADNIE {n} niezależnych przekształceń zdań, testujących: {topic_label}. "
                "W każdej pozycji 'question_text' zawiera zdanie wyjściowe ORAZ zdanie z luką "
                "(______) do uzupełnienia, 'key_word' to słowo-klucz (WIELKIMI literami), a 'answer' "
                "to same brakujące słowa (2–5 wyrazów, ze słowem-kluczem) — bez powtarzania reszty "
                "zdania. Pozostaw 'question_text' zadania puste. "
                "'answer_notes' to najwyżej jedno krótkie zdanie z dopuszczalnymi wariantami."
            ),
        }

    if exercise_type == "uoe_part3_word_formation":
        return {
            "shape": ('{"instructions": str, '
                      '"items": [{"number": int, "question_text": str, "stem": str, '
                      '"answer": str, "answer_notes": str}]}'),
            "focus": (
                f"Przygotuj DOKŁADNIE {n} niezależnych zadań na słowotwórstwo, testujących: {topic_label}. "
                "W każdej pozycji 'question_text' to jedno zdanie po angielsku z jedną luką (______), "
                "'stem' to wyraz podstawowy WIELKIMI literami (np. CONVENIENT), a 'answer' to poprawnie "
                "utworzona forma wypełniająca lukę (np. inconvenience). Różnicuj typy afiksów "
                "(przedrostki, przyrostki, formy przeczące, rzeczowniki/przymiotniki/przysłówki). "
                "Pozostaw 'question_text' zadania puste. 'answer_notes' — najwyżej jedno krótkie zdanie."
            ),
        }

    # uoe_part2_open_cloze
    return {
        "shape": ('{"instructions": str, '
                  '"items": [{"number": int, "question_text": str, '
                  '"answer": str, "answer_notes": str}]}'),
        "focus": (
            f"Przygotuj DOKŁADNIE {n} niezależnych zadań (tablica 'items' musi mieć {n} elementów "
            f"o numerach 1–{n}), testujących: {topic_label}. W każdej pozycji 'question_text' to "
            "jedno zdanie po angielsku z JEDNĄ luką (______), a 'answer' to JEDNO słowo wypełniające "
            "tę lukę (bez wariantów w nawiasach). Każde zdanie w innym kontekście. "
            "Pozostaw 'question_text' zadania puste. 'answer_notes' — najwyżej jedno krótkie zdanie."
        ),
    }


def generate_exercise(exercise_type: str, topic: str, weak_points: list[str] | None = None,
                      lang: str = "pl") -> GeneratedExercise:
    """Generuje jedno zadanie danego typu, ukierunkowane na wskazany temat."""
    spec = _exercise_shape(exercise_type, topic, lang)
    type_label = tax.EXERCISE_TYPES.get(exercise_type, {}).get("label", exercise_type)
    weak = ", ".join(tax.topic_label(t) for t in (weak_points or []) if t != topic)
    weak_line = f"\nUczeń ma słabe punkty w: {weak}. Jeśli to naturalne, delikatnie je uwzględnij." if weak else ""

    prompt = (
        f"Wygeneruj JEDNO zadanie egzaminacyjne FCE typu: {type_label}.\n"
        f"{spec['focus']}{weak_line}\n"
        f"Zwróć TYLKO obiekt JSON o kształcie: {spec['shape']}\n"
        f"Pola z treścią zadania (question_text, options, items, key_word, answer) po angielsku; "
        f"pole 'instructions' napisz w języku: {_lang_name(lang)}."
    )
    exercise = GeneratedExercise.model_validate(_call_json(prompt, kind="generate"))
    expected = _expected_item_count(exercise_type)
    if not _has_enough_items(exercise, expected):
        exercise = GeneratedExercise.model_validate(
            _call_json(prompt + _STRICT_ITEMS.format(n=expected), kind="generate")
        )
    return exercise


_DRILL_TYPES = [
    "uoe_part1_mcq_cloze",
    "uoe_part2_open_cloze",
    "uoe_part3_word_formation",
    "uoe_part4_key_word_transformation",
]


def generate_drill(topic: str, student_text: str, correct_text: str, explanation: str,
                   lang: str = "pl") -> tuple[str, GeneratedExercise]:
    """Generuje zestaw ćwiczeń celowanych w KONKRETNY błąd ucznia (jedno wywołanie modelu).

    Zwraca `(exercise_type, GeneratedExercise)` — typ wybiera model spośród części
    Use of English, a zadanie zawiera `ITEMS_PER_EXERCISE` niezależnych pozycji,
    każda w innym kontekście.
    """
    lang_name = _lang_name(lang)
    topic_lbl = tax.topic_label(topic, "en")
    types = ", ".join(_DRILL_TYPES)
    n = ITEMS_PER_EXERCISE
    shape = (
        '{"exercise_type": str, "instructions": str, '
        '"items": [{"number": int, "question_text": str, "options": [str, str, str, str]|null, '
        '"key_word": str|null, "stem": str|null, "answer": str, "answer_notes": str}]}'
    )
    prompt = (
        f"Uczeń przygotowujący się do FCE popełnił konkretny błąd. Ułóż {n} KRÓTKICH ćwiczeń, "
        "które ćwiczą DOKŁADNIE ten punkt gramatyczny/leksykalny, każde w INNYM, nowym kontekście "
        "(nie powielaj zdania z błędu ani kontekstów między pozycjami).\n\n"
        f"Błąd — temat: {topic_lbl}\n"
        f"Wersja błędna: {student_text}\n"
        f"Wersja poprawna: {correct_text}\n"
        f"Wyjaśnienie: {explanation}\n\n"
        f"Pole 'exercise_type' MUSI być jednym z: {types} — wybierz jeden typ dla całego zestawu.\n"
        "Każda pozycja w 'items' ma własne 'question_text' (jedno zdanie po angielsku z luką ______) "
        "oraz 'answer'. Dla multiple-choice podaj w pozycji dokładnie 4 'options' (z prefiksami "
        "A/B/C/D, 'answer' zapisane identycznie jak wybrany wariant); dla key word transformation "
        "podaj 'key_word'; dla word formation podaj 'stem'. Nieużywane pola ustaw na null.\n"
        f"Trudność stopniuj rosnąco. 'answer_notes' to najwyżej jedno krótkie zdanie.\n"
        f"Treść ćwiczeń po angielsku; pole 'instructions' w języku: {lang_name}.\n"
        f"Zwróć TYLKO obiekt JSON o kształcie: {shape}"
    )
    data = _call_json(prompt, kind="drill")
    ex_type = data.get("exercise_type")
    if ex_type not in _DRILL_TYPES:
        ex_type = "uoe_part2_open_cloze"
    exercise = GeneratedExercise.model_validate(data)
    if not exercise.items:
        raise LLMError("Model nie zwrócił żadnego ćwiczenia do tego błędu.")
    return ex_type, exercise


def _norm_answer(s: str) -> str:
    """Normalizuje odpowiedź do porównania: ucina prefiks wariantu ('A' / 'A.' / 'A)'),
    wielkość liter i kropkę na końcu — 'B heat' i 'heat' są równoważne."""
    s = (s or "").strip().rstrip(".").lower()
    head, _, rest = s.partition(" ")
    if rest and len(head.rstrip(").")) == 1 and head.rstrip(").").isalpha():
        return rest.strip()
    return s


def grade_items(exercise_type: str, question_text: str, items: list[dict],
                student_answers: list[str], lang: str = "pl") -> GradingResult:
    """Ocenia zadanie wieloczęściowe — wszystkie pozycje w JEDNYM wywołaniu modelu.

    Dwa tryby oceny, zależnie od pozycji:
    - pozycja z wariantami (multiple choice) — poprawność ustalana DETERMINISTYCZNIE
      po stronie serwera; model tylko wyjaśnia,
    - pozycja z odpowiedzią otwartą (części 2–4) — o poprawności rozstrzyga model,
      bo równoważne odpowiedzi ('have'/'has', inny szyk) są normalne; ale dokładne
      trafienie w zapisaną odpowiedź ZAWSZE nadpisuje wynik na poprawny, żeby dobra
      odpowiedź nigdy nie trafiła do dziennika jako błąd.
    """
    lang_name = _lang_name(lang)
    valid_topics = ", ".join(tax.topics_for_type(exercise_type)) or ", ".join(tax.TOPICS.keys())

    verdicts, lines, open_numbers = [], [], []
    for idx, item in enumerate(items):
        number = item.get("number", idx + 1)
        given = student_answers[idx] if idx < len(student_answers) else ""
        answer = item.get("answer") or ""
        options = item.get("options") or None
        exact = bool(given) and _norm_answer(given) == _norm_answer(answer)
        if not options:
            open_numbers.append(number)
        verdicts.append({
            "number": number,
            "closed": bool(options),
            "exact": exact,
            "correct": exact,  # dla pozycji otwartych może jeszcze zmienić to model
            "student_option": given or None,
            "correct_option": answer,
        })
        context = item.get("question_text") or ""
        extra = ""
        if item.get("stem"):
            extra += f" [wyraz podstawowy: {item['stem']}]"
        if item.get("key_word"):
            extra += f" [słowo-klucz: {item['key_word']}]"
        lines.append(
            f"Pozycja {number}: " + (f"{context}{extra}; " if context or extra else "")
            + (f"warianty={options}; " if options else "")
            + f"poprawna='{answer}'; odpowiedź ucznia='{given or '(brak)'}'"
            + (f" → {'POPRAWNA' if exact else 'BŁĘDNA'}" if options
               else (" → POPRAWNA (dokładne trafienie)" if exact else " → OCEŃ SAM"))
        )

    closed_wrong = [v["number"] for v in verdicts if v["closed"] and not v["correct"]]
    to_judge = [n for n in open_numbers
                if not next(v for v in verdicts if v["number"] == n)["exact"]]

    judge_line = ""
    if to_judge:
        judge_line = (
            f"\nPozycje {to_judge} mają odpowiedź OTWARTĄ i nie trafiają dokładnie we wzorzec — "
            "dla nich ustaw 'correct' na podstawie własnej oceny: true, jeśli odpowiedź ucznia jest "
            "poprawna gramatycznie i znaczeniowo równoważna wzorcowej (dopuszczaj sensowne warianty), "
            "false w przeciwnym razie. Dla pozostałych pozycji pole 'correct' jest ignorowane.\n"
        )

    notes_line = ""
    if closed_wrong:
        notes_line = (
            f"Dla błędnych pozycji z wariantami ({closed_wrong}) wypełnij 'option_notes' — "
            "omówienie wszystkich 4 wariantów (is_correct + jedno zdanie). "
            "W pozostałych ustaw 'option_notes' na null.\n"
        )

    shape = (
        '{"feedback": str, '
        '"items": [{"number": int, "correct": bool, "comment": str, '
        '"option_notes": [{"option": str, "is_correct": bool, "comment": str}]|null}], '
        '"errors": [{"topic": str, "student_text": str, "correct_text": str, "explanation": str, "severity": "minor"|"major"}]}'
    )
    prompt = (
        f"Uczeń rozwiązał zadanie FCE (typ: {exercise_type}) składające się z {len(items)} pozycji.\n"
        + (f"\nWspólna treść zadania:\n{question_text}\n" if question_text else "")
        + "\nPozycje i odpowiedzi ucznia:\n" + "\n".join(lines) + "\n\n"
        + judge_line
        + "Dla KAŻDEJ pozycji podaj krótki 'comment' (jedno zdanie) uzasadniający poprawną odpowiedź.\n"
        + notes_line
        + "W 'errors' umieść po jednej pozycji dla każdej pozycji, którą uznajesz za BŁĘDNĄ "
        "(student_text = odpowiedź ucznia, correct_text = poprawna). "
        f"Pole 'topic' MUSI być jednym z: {valid_topics}.\n"
        "'feedback' to maksymalnie 1–2 krótkie zdania podsumowania.\n"
        f"Pola 'feedback', 'comment', 'explanation' napisz w języku: {lang_name}; "
        "treści angielskie i poprawki po angielsku.\n"
        f"Zwróć TYLKO obiekt JSON o kształcie: {shape}"
    )
    data = _call_json(prompt, kind="grade")

    # Scal ocenę modelu z werdyktami serwera.
    by_num = {}
    for entry in data.get("items") or []:
        try:
            by_num[int(entry.get("number"))] = entry
        except (TypeError, ValueError):
            continue

    merged = []
    for verdict in verdicts:
        entry = by_num.get(verdict["number"], {})
        if verdict["closed"]:
            correct = verdict["exact"]           # warianty zamknięte: tylko serwer
        else:
            correct = verdict["exact"] or bool(entry.get("correct"))
        merged.append({
            "number": verdict["number"],
            "correct": correct,
            "student_option": verdict["student_option"],
            "correct_option": verdict["correct_option"],
            "comment": str(entry.get("comment") or ""),
            "option_notes": entry.get("option_notes") if not correct else None,
        })

    # Odfiltruj błędy dotyczące pozycji uznanych ostatecznie za poprawne — inaczej
    # model mógłby zanieczyścić dziennik błędem przy odpowiedzi, którą sami zaliczyliśmy.
    ok_answers = {_norm_answer(m["student_option"] or "") for m in merged if m["correct"]}
    errors = [e for e in (data.get("errors") or [])
              if _norm_answer(str(e.get("student_text", ""))) not in ok_answers]

    correct_count = sum(1 for m in merged if m["correct"])
    return GradingResult.model_validate({
        "correct": correct_count == len(items),
        "score": f"{correct_count}/{len(items)}",
        "items": merged,
        "feedback": str(data.get("feedback") or ""),
        "errors": errors,
    })


def grade_answer(exercise_type: str, question_text: str, student_answer: str,
                 model_answer: str | None = None, key_word: str | None = None,
                 options: list[str] | None = None, lang: str = "pl") -> GradingResult:
    """Ocenia odpowiedź ucznia; klasyfikuje błędy wg taksonomii FCE.

    Feedback jest zwięzły. Dla zadań wielokrotnego wyboru dołącza omówienie,
    dlaczego pozostałe warianty są błędne (`option_notes`)."""
    lang_name = _lang_name(lang)
    valid_topics = ", ".join(tax.topics_for_type(exercise_type)) or ", ".join(tax.TOPICS.keys())
    kw_line = f"\nSłowo-klucz (key word): {key_word}" if key_word else ""
    ref_line = f"\nWzorcowa odpowiedź: {model_answer}" if model_answer else ""
    is_mcq = bool(options) and not tax.is_writing(exercise_type)
    opts_line = f"\nWarianty: {options}" if is_mcq else ""

    if tax.is_writing(exercise_type):
        shape = (
            '{"feedback": str, '
            '"scores": [{"criterion": str, "score": int(0-5), "comment": str}], '
            '"band": str, '
            '"errors": [{"topic": str, "student_text": str, "correct_text": str, "explanation": str, "severity": "minor"|"major"}]}'
        )
        task = (
            "Oceń poniższe wypracowanie FCE wg czterech kryteriów Cambridge: "
            "content, communicative_achievement, organisation, language (każde 0–5). "
            "Wypisz konkretne błędy językowe z poprawkami."
        )
    else:
        option_notes_field = (
            ', "option_notes": [{"option": str, "is_correct": bool, "comment": str}]' if is_mcq else ""
        )
        shape = (
            '{"correct": bool, "corrected": str, "feedback": str, '
            '"errors": [{"topic": str, "student_text": str, "correct_text": str, "explanation": str, "severity": "minor"|"major"}]'
            + option_notes_field + "}"
        )
        task = (
            "Oceń, czy odpowiedź ucznia jest poprawna dla tego zadania FCE. "
            "Jeśli są błędy, podaj poprawioną wersję i wypisz każdy błąd osobno. "
            "Jeśli odpowiedź jest w pełni poprawna, errors ma być pustą listą."
        )

    mcq_line = (
        "\nW polu 'option_notes' omów KAŻDY podany wariant: 'is_correct' true dla poprawnego, "
        "a w 'comment' napisz zwięźle (jedno zdanie), dlaczego wariant jest błędny lub dlaczego pasuje."
        if is_mcq else ""
    )

    prompt = (
        f"{task}\n\n"
        f"Typ zadania: {exercise_type}\n"
        f"Treść zadania:\n{question_text}{opts_line}{kw_line}{ref_line}\n\n"
        f"Odpowiedź ucznia:\n{student_answer}\n\n"
        f"Pole 'topic' każdego błędu MUSI być jednym z: {valid_topics}.\n"
        "Pisz ZWIĘŹLE: 'feedback' to maksymalnie 1–2 krótkie zdania, każde 'explanation' i 'comment' "
        "to jedno zdanie. Bez powtórzeń i wstępów.\n"
        f"Pola tekstowe 'feedback', 'explanation' i 'comment' napisz w języku: {lang_name}; "
        f"poprawki (corrected, correct_text) po angielsku.{mcq_line}\n"
        f"Zwróć TYLKO obiekt JSON o kształcie: {shape}"
    )
    data = _call_json(prompt, kind="grade")
    return GradingResult.model_validate(data)


def extract_errors_from_text(text: str) -> list[ErrorItem]:
    """Wyciąga ustrukturyzowane błędy z nieuporządkowanej informacji zwrotnej
    (np. z oceny prac pisemnych). Zwraca listę ErrorItem sklasyfikowanych wg taksonomii."""
    valid_topics = ", ".join(tax.TOPICS.keys())
    prompt = (
        "Poniżej znajduje się nieuporządkowana informacja zwrotna z oceny prac pisemnych ucznia FCE. "
        "Wyodrębnij z niej WSZYSTKIE konkretne błędy językowe w formie par 'wersja błędna → wersja poprawna'. "
        "Pomiń ogólne komentarze bez konkretnej poprawki. Dla każdego błędu przypisz temat z taksonomii "
        "i dopisz zwięzłe wyjaśnienie po polsku.\n\n"
        f"Pole 'topic' MUSI być jednym z: {valid_topics}.\n"
        "'severity' to 'major' (błąd rażący/gramatyczny) lub 'minor' (drobny/literówka).\n\n"
        f"TEKST:\n{text}\n\n"
        'Zwróć TYLKO obiekt JSON: {"errors": [{"topic": str, "student_text": str, '
        '"correct_text": str, "explanation": str, "severity": "minor"|"major"}]}'
    )
    data = _call_json(prompt, kind="extract")
    return [ErrorItem.model_validate(e) for e in data.get("errors", [])]


def explain_error(topic: str, student_text: str, correct_text: str, lang: str = "pl") -> str:
    """Rozszerzone wyjaśnienie pojedynczego błędu na żądanie (zwraca zwykły tekst)."""
    lang_name = _lang_name(lang)
    prompt = (
        f"Wyjaśnij szczegółowo (w języku: {lang_name}) poniższy błąd językowy ucznia "
        "przygotowującego się do FCE. Podaj regułę, 1–2 przykłady poprawnego użycia po angielsku "
        "i wskazówkę, jak go unikać.\n"
        f"Temat: {tax.topic_label(topic, lang)}\n"
        f"Wersja ucznia: {student_text}\n"
        f"Wersja poprawna: {correct_text}\n"
        'Zwróć TYLKO obiekt JSON: {"explanation": str}'
    )
    data = _call_json(prompt, kind="explain")
    return str(data.get("explanation", "")).strip()
