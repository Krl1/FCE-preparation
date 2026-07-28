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

# Liczba luk w zadaniu typu multiple-choice cloze (FCE Part 1).
MCQ_ITEM_COUNT = 5


def generate_exercise(exercise_type: str, topic: str, weak_points: list[str] | None = None,
                      lang: str = "pl") -> GeneratedExercise:
    """Generuje jedno zadanie danego typu, ukierunkowane na wskazany temat."""
    lang_name = _lang_name(lang)
    type_label = tax.EXERCISE_TYPES.get(exercise_type, {}).get("label", exercise_type)
    topic_label = tax.topic_label(topic)
    weak = ", ".join(tax.topic_label(t) for t in (weak_points or []) if t != topic)

    if tax.is_writing(exercise_type):
        shape = (
            '{"instructions": str, "question_text": str}'
            "  // question_text = pełne polecenie zadania Writing (temat + wymagania, ~140-190 słów)"
        )
        focus = f"Zadbaj, by temat naturalnie sprzyjał ćwiczeniu obszaru: {topic_label}."
    elif exercise_type == "uoe_part1_mcq_cloze":
        shape = (
            '{"instructions": str, "question_text": str, '
            '"items": [{"number": int, "options": [str, str, str, str], "answer": str, "answer_notes": str}]}'
        )
        focus = (
            f"Ułóż jeden spójny, ciekawy tekst po angielsku (~120–160 słów) z DOKŁADNIE "
            f"{MCQ_ITEM_COUNT} lukami, oznaczonymi w 'question_text' jako (1) ______ , (2) ______ itd. "
            f"Dla KAŻDEJ luki podaj w 'items' dokładnie 4 warianty (z prefiksami A/B/C/D) i jeden poprawny "
            f"w polu 'answer' — zapisany identycznie jak w 'options'. Luki mają testować przede wszystkim: "
            f"{topic_label}; pozostałe mogą sprawdzać inne słownictwo na poziomie B2. "
            f"Numery w 'items' muszą odpowiadać numerom luk w tekście."
        )
    elif exercise_type == "uoe_part4_key_word_transformation":
        shape = '{"instructions": str, "question_text": str, "key_word": str, "answer": str, "answer_notes": str}'
        focus = (
            f"Przekształcenie ma testować: {topic_label}. question_text zawiera zdanie wyjściowe i "
            "zdanie z luką do uzupełnienia (2–5 słów, ze słowem-kluczem)."
        )
    else:  # part2 open cloze, part3 word formation
        shape = '{"instructions": str, "question_text": str, "answer": str, "answer_notes": str}'
        focus = f"Zadanie ma testować: {topic_label}."

    weak_line = f"\nUczeń ma słabe punkty w: {weak}. Jeśli to naturalne, delikatnie je uwzględnij." if weak else ""

    prompt = (
        f"Wygeneruj JEDNO zadanie egzaminacyjne FCE typu: {type_label}.\n"
        f"{focus}{weak_line}\n"
        f"Zwróć TYLKO obiekt JSON o kształcie: {shape}\n"
        f"Pola z treścią zadania (question_text, options, key_word, answer) po angielsku; "
        f"pole 'instructions' napisz w języku: {lang_name}."
    )
    data = _call_json(prompt, kind="generate")
    return GeneratedExercise.model_validate(data)


_DRILL_TYPES = [
    "uoe_part1_mcq_cloze",
    "uoe_part2_open_cloze",
    "uoe_part3_word_formation",
    "uoe_part4_key_word_transformation",
]


def generate_drill(topic: str, student_text: str, correct_text: str, explanation: str,
                   lang: str = "pl") -> tuple[str, GeneratedExercise]:
    """Generuje krótkie ćwiczenie celowane w KONKRETNY błąd ucznia.
    Zwraca (exercise_type, GeneratedExercise) — typ wybiera model spośród części Use of English."""
    lang_name = _lang_name(lang)
    topic_lbl = tax.topic_label(topic, "en")
    types = ", ".join(_DRILL_TYPES)
    shape = (
        '{"exercise_type": str, "instructions": str, "question_text": str, '
        '"options": [str]|null, "key_word": str|null, "answer": str, "answer_notes": str}'
    )
    prompt = (
        "Uczeń przygotowujący się do FCE popełnił konkretny błąd. Ułóż JEDNO krótkie ćwiczenie, "
        "które ćwiczy DOKŁADNIE ten punkt gramatyczny/leksykalny w NOWYM kontekście "
        "(nie powielaj zdania z błędu). Wybierz najlepiej pasujący typ ćwiczenia.\n\n"
        f"Błąd — temat: {topic_lbl}\n"
        f"Wersja błędna: {student_text}\n"
        f"Wersja poprawna: {correct_text}\n"
        f"Wyjaśnienie: {explanation}\n\n"
        f"Pole 'exercise_type' MUSI być jednym z: {types}. "
        "Dla multiple-choice podaj dokładnie 4 'options'; dla key word transformation podaj 'key_word'; "
        "w pozostałych ustaw je na null.\n"
        f"Treść zadania po angielsku; pole 'instructions' w języku: {lang_name}.\n"
        f"Zwróć TYLKO obiekt JSON o kształcie: {shape}"
    )
    data = _call_json(prompt, kind="drill")
    ex_type = data.get("exercise_type")
    if ex_type not in _DRILL_TYPES:
        ex_type = "uoe_part2_open_cloze"
    return ex_type, GeneratedExercise.model_validate(data)


def grade_items(exercise_type: str, question_text: str, items: list[dict],
                student_answers: list[str], lang: str = "pl") -> GradingResult:
    """Ocenia zadanie wieloczęściowe (multiple-choice cloze) — wszystkie luki w jednym wywołaniu.

    Poprawność każdej luki jest ustalana deterministycznie po stronie serwera (porównanie
    z zapisaną odpowiedzią wzorcową); model dostarcza wyłącznie wyjaśnienia."""
    lang_name = _lang_name(lang)
    valid_topics = ", ".join(tax.topics_for_type(exercise_type)) or ", ".join(tax.TOPICS.keys())

    def norm(s: str) -> str:
        """Normalizuje wariant do porównania: ucina prefiks 'A' / 'A.' / 'A)',
        wielkość liter i kropkę na końcu ('B heat' i 'heat' są równoważne)."""
        s = (s or "").strip().rstrip(".").lower()
        head, _, rest = s.partition(" ")
        if rest and len(head.rstrip(").")) == 1 and head.rstrip(").").isalpha():
            return rest.strip()
        return s

    # Deterministyczna ocena + materiał dla modelu.
    verdicts, lines = [], []
    for idx, item in enumerate(items):
        given = student_answers[idx] if idx < len(student_answers) else ""
        answer = item.get("answer") or ""
        is_ok = bool(given) and norm(given) == norm(answer)
        verdicts.append({
            "number": item.get("number", idx + 1),
            "correct": is_ok,
            "student_option": given or None,
            "correct_option": answer,
        })
        lines.append(
            f"Luka {item.get('number', idx + 1)}: warianty={item.get('options')}; "
            f"poprawny='{answer}'; odpowiedź ucznia='{given or '(brak)'}' → "
            f"{'POPRAWNA' if is_ok else 'BŁĘDNA'}"
        )

    wrong_numbers = [v["number"] for v in verdicts if not v["correct"]]
    correct_count = sum(1 for v in verdicts if v["correct"])

    shape = (
        '{"feedback": str, '
        '"items": [{"number": int, "comment": str, '
        '"option_notes": [{"option": str, "is_correct": bool, "comment": str}]|null}], '
        '"errors": [{"topic": str, "student_text": str, "correct_text": str, "explanation": str, "severity": "minor"|"major"}]}'
    )
    prompt = (
        "Uczeń rozwiązał zadanie FCE typu multiple-choice cloze (tekst z lukami). "
        "Poprawność każdej luki została już ustalona — Twoim zadaniem jest tylko wyjaśnić.\n\n"
        f"Tekst zadania:\n{question_text}\n\n"
        "Wyniki poszczególnych luk:\n" + "\n".join(lines) + "\n\n"
        f"Dla KAŻDEJ luki podaj w 'items' krótki 'comment' (jedno zdanie) uzasadniający poprawny wariant.\n"
        f"Dla luk BŁĘDNIE rozwiązanych ({wrong_numbers or 'brak'}) wypełnij dodatkowo 'option_notes' — "
        "omówienie wszystkich 4 wariantów (is_correct + jedno zdanie, dlaczego pasuje/nie pasuje). "
        "Dla luk poprawnych ustaw 'option_notes' na null.\n"
        "W 'errors' umieść po jednej pozycji dla każdej BŁĘDNIE rozwiązanej luki "
        "(student_text = wariant wybrany przez ucznia, correct_text = wariant poprawny). "
        f"Pole 'topic' MUSI być jednym z: {valid_topics}.\n"
        f"'feedback' to maksymalnie 1–2 krótkie zdania podsumowania (wynik: {correct_count}/{len(items)}).\n"
        f"Pola 'feedback', 'comment', 'explanation' napisz w języku: {lang_name}; warianty i poprawki po angielsku.\n"
        f"Zwróć TYLKO obiekt JSON o kształcie: {shape}"
    )
    data = _call_json(prompt, kind="grade")

    # Scal wyjaśnienia modelu z deterministycznymi werdyktami serwera.
    notes_by_num = {}
    for entry in data.get("items") or []:
        try:
            notes_by_num[int(entry.get("number"))] = entry
        except (TypeError, ValueError):
            continue
    merged = []
    for verdict in verdicts:
        entry = notes_by_num.get(verdict["number"], {})
        merged.append({
            **verdict,
            "comment": str(entry.get("comment") or ""),
            "option_notes": entry.get("option_notes") if not verdict["correct"] else None,
        })

    return GradingResult.model_validate({
        "correct": correct_count == len(items),
        "score": f"{correct_count}/{len(items)}",
        "items": merged,
        "feedback": str(data.get("feedback") or ""),
        "errors": data.get("errors") or [],
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
