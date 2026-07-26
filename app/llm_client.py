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


def _invoke(prompt: str) -> str:
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


def _call_json(prompt: str) -> dict:
    """Wywołuje model i zwraca sparsowany JSON. Jedna ponowna próba przy błędzie parsowania."""
    raw = _invoke(prompt)
    try:
        return _extract_json(raw)
    except (json.JSONDecodeError, ValueError):
        retry_prompt = (
            prompt
            + "\n\nWAŻNE: Poprzednia odpowiedź nie była poprawnym JSON. "
            "Zwróć TYLKO poprawny obiekt JSON, bez żadnego dodatkowego tekstu ani znaczników."
        )
        raw2 = _invoke(retry_prompt)
        try:
            return _extract_json(raw2)
        except (json.JSONDecodeError, ValueError) as exc:
            raise LLMError(f"Model nie zwrócił poprawnego JSON po ponownej próbie: {raw2[:300]}") from exc


# --- Funkcje domenowe --------------------------------------------------------

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
        shape = '{"instructions": str, "question_text": str, "options": [str, str, str, str], "answer": str, "answer_notes": str}'
        focus = f"Luka ma testować: {topic_label}. Podaj DOKŁADNIE 4 warianty, jeden poprawny."
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
    data = _call_json(prompt)
    return GeneratedExercise.model_validate(data)


def grade_answer(exercise_type: str, question_text: str, student_answer: str,
                 model_answer: str | None = None, key_word: str | None = None,
                 lang: str = "pl") -> GradingResult:
    """Ocenia odpowiedź ucznia; klasyfikuje błędy wg taksonomii FCE."""
    lang_name = _lang_name(lang)
    valid_topics = ", ".join(tax.topics_for_type(exercise_type)) or ", ".join(tax.TOPICS.keys())
    kw_line = f"\nSłowo-klucz (key word): {key_word}" if key_word else ""
    ref_line = f"\nWzorcowa odpowiedź: {model_answer}" if model_answer else ""

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
        shape = (
            '{"correct": bool, "corrected": str, "feedback": str, '
            '"errors": [{"topic": str, "student_text": str, "correct_text": str, "explanation": str, "severity": "minor"|"major"}]}'
        )
        task = (
            "Oceń, czy odpowiedź ucznia jest poprawna dla tego zadania FCE. "
            "Jeśli są błędy, podaj poprawioną wersję i wypisz każdy błąd osobno. "
            "Jeśli odpowiedź jest w pełni poprawna, errors ma być pustą listą."
        )

    prompt = (
        f"{task}\n\n"
        f"Typ zadania: {exercise_type}\n"
        f"Treść zadania:\n{question_text}{kw_line}{ref_line}\n\n"
        f"Odpowiedź ucznia:\n{student_answer}\n\n"
        f"Pole 'topic' każdego błędu MUSI być jednym z: {valid_topics}.\n"
        f"Pola tekstowe 'feedback', 'explanation' i 'comment' napisz w języku: {lang_name}; "
        "poprawki (corrected, correct_text) po angielsku.\n"
        f"Zwróć TYLKO obiekt JSON o kształcie: {shape}"
    )
    data = _call_json(prompt)
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
    data = _call_json(prompt)
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
    data = _call_json(prompt)
    return str(data.get("explanation", "")).strip()
