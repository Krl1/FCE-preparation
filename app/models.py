"""Modele Pydantic — kontrakt danych między LLM, backendem, bazą i frontendem."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# --- Generowanie zadań -------------------------------------------------------

class ExerciseItem(BaseModel):
    """Pojedyncza luka w zadaniu wieloczęściowym (multiple-choice cloze).
    `answer`/`answer_notes` zostają po stronie serwera."""

    number: int = Field(description="Numer luki (1..n), zgodny z oznaczeniem w question_text.")
    options: list[str] = Field(description="Warianty odpowiedzi (dokładnie 4).")
    answer: Optional[str] = Field(default=None, description="Poprawny wariant.")
    answer_notes: Optional[str] = Field(default=None)


class ExerciseItemPublic(BaseModel):
    """Luka widziana przez klienta — bez poprawnej odpowiedzi."""

    number: int
    options: list[str]


class GeneratedExercise(BaseModel):
    """Zadanie zwrócone przez LLM. `answer`/`answer_notes` są trzymane po stronie
    serwera i NIE wysyłane do klienta przed sprawdzeniem odpowiedzi."""

    instructions: str = Field(description="Polecenie dla ucznia.")
    question_text: str = Field(description="Treść zadania (tekst z luką, zdanie do przekształcenia, temat wypracowania).")
    options: Optional[list[str]] = Field(
        default=None, description="Warianty odpowiedzi dla zadań typu multiple-choice (jedna luka)."
    )
    items: Optional[list[ExerciseItem]] = Field(
        default=None,
        description="Wiele luk w jednym zadaniu (multiple-choice cloze); wtedy `options` jest puste.",
    )
    key_word: Optional[str] = Field(
        default=None, description="Słowo-klucz w zadaniach key word transformation."
    )
    answer: Optional[str] = Field(
        default=None, description="Wzorcowa odpowiedź (tylko po stronie serwera)."
    )
    answer_notes: Optional[str] = Field(
        default=None, description="Dopuszczalne warianty / uwagi dla korektora."
    )


class ExercisePublic(BaseModel):
    """Zadanie widziane przez klienta — bez wzorcowej odpowiedzi."""

    id: int
    type: str
    topic: str
    instructions: str
    question_text: str
    options: Optional[list[str]] = None
    items: Optional[list[ExerciseItemPublic]] = None
    key_word: Optional[str] = None


# --- Ocena odpowiedzi --------------------------------------------------------

class ErrorItem(BaseModel):
    """Pojedynczy błąd wykryty w odpowiedzi ucznia."""

    topic: str = Field(description="Identyfikator tematu z taksonomii FCE.")
    student_text: str = Field(description="Fragment odpowiedzi ucznia z błędem.")
    correct_text: str = Field(description="Poprawna wersja.")
    explanation: str = Field(description="Zwięzłe wyjaśnienie błędu po polsku.")
    severity: str = Field(default="minor", description="'minor' lub 'major'.")


class CriterionScore(BaseModel):
    """Ocena wg jednego kryterium FCE (dla części Writing), skala 0–5."""

    criterion: str
    score: int
    comment: str


class OptionNote(BaseModel):
    """Omówienie pojedynczego wariantu w zadaniu wielokrotnego wyboru."""

    option: str
    is_correct: bool
    comment: str = Field(description="Krótko, dlaczego wariant jest poprawny/błędny.")


class ItemResult(BaseModel):
    """Wynik oceny jednej luki w zadaniu wieloczęściowym."""

    number: int
    correct: bool
    student_option: Optional[str] = None
    correct_option: str
    comment: str = Field(description="Jedno zdanie: dlaczego poprawna odpowiedź jest właściwa.")
    option_notes: Optional[list[OptionNote]] = Field(
        default=None, description="Omówienie wariantów — wypełniane dla luk błędnie rozwiązanych."
    )


class GradingResult(BaseModel):
    """Wynik oceny zadania (Use of English lub Writing)."""

    correct: Optional[bool] = Field(
        default=None, description="Czy odpowiedź jest w pełni poprawna (Use of English)."
    )
    # Zadania wieloczęściowe (multiple-choice cloze): wynik per luka.
    items: Optional[list[ItemResult]] = Field(default=None)
    score: Optional[str] = Field(default=None, description="Np. '3/5' dla zadań wieloczęściowych.")
    corrected: Optional[str] = Field(
        default=None, description="Poprawiona wersja odpowiedzi ucznia."
    )
    feedback: str = Field(description="Ogólny komentarz / informacja zwrotna po polsku.")
    errors: list[ErrorItem] = Field(default_factory=list)
    # Tylko dla zadań wielokrotnego wyboru — dlaczego pozostałe warianty są błędne:
    option_notes: Optional[list[OptionNote]] = Field(default=None)
    # Tylko dla Writing:
    scores: Optional[list[CriterionScore]] = Field(default=None)
    band: Optional[str] = Field(default=None, description="Orientacyjne pasmo/ocena wypracowania.")


# --- Żądania API -------------------------------------------------------------

class GenerateRequest(BaseModel):
    type: str
    topic: Optional[str] = None  # jeśli None → dobór ważony przez srs.py
    lang: str = "pl"  # język poleceń/treści generowanych ('pl' | 'en')


class GradeRequest(BaseModel):
    type: str
    student_answer: str = ""
    # Zadania wieloczęściowe: odpowiedź na każdą lukę ("" = brak odpowiedzi).
    student_answers: Optional[list[str]] = None
    exercise_id: Optional[int] = None  # None → zadanie wklejone z zewnątrz
    # Dla zadań z zewnątrz klient podaje treść bezpośrednio:
    question_text: Optional[str] = None
    key_word: Optional[str] = None
    lang: str = "pl"  # język wyjaśnień/feedbacku ('pl' | 'en')


class TipExerciseRequest(BaseModel):
    error_id: int
    lang: str = "pl"


class CompleteRequest(BaseModel):
    error_id: int


class GoalRequest(BaseModel):
    goal: int
