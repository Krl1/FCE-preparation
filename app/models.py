"""Modele Pydantic — kontrakt danych między LLM, backendem, bazą i frontendem."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, model_validator


# --- Generowanie zadań -------------------------------------------------------

class ExerciseItem(BaseModel):
    """Jedna pozycja zadania wieloczęściowego. `answer`/`answer_notes` zostają na serwerze.

    Dwa warianty użycia:
    - Part 1 (multiple-choice cloze): pozycje to luki we WSPÓLNYM tekście zadania,
      każda z `options`; `question_text` pozycji jest puste.
    - Part 2/3/4: każda pozycja to osobne mini-zadanie z własnym `question_text`
      (plus `stem` dla word formation, `key_word` dla przekształceń).
    """

    number: int = Field(description="Numer pozycji (1..n), zgodny z oznaczeniem w treści.")
    question_text: Optional[str] = Field(
        default=None, description="Własne zdanie/kontekst pozycji (części 2–4)."
    )
    options: Optional[list[str]] = Field(
        default=None, description="Warianty odpowiedzi — tylko multiple-choice (dokładnie 4)."
    )
    key_word: Optional[str] = Field(default=None, description="Słowo-klucz (part 4).")
    stem: Optional[str] = Field(
        default=None, description="Wyraz podstawowy do przekształcenia (part 3, np. CONVENIENT)."
    )
    answer: Optional[str] = Field(default=None, description="Poprawna odpowiedź.")
    answer_notes: Optional[str] = Field(default=None)


class ExerciseItemPublic(BaseModel):
    """Pozycja widziana przez klienta — bez poprawnej odpowiedzi."""

    number: int
    question_text: Optional[str] = None
    options: Optional[list[str]] = None
    key_word: Optional[str] = None
    stem: Optional[str] = None


class GeneratedExercise(BaseModel):
    """Zadanie zwrócone przez LLM. `answer`/`answer_notes` są trzymane po stronie
    serwera i NIE wysyłane do klienta przed sprawdzeniem odpowiedzi."""

    instructions: str = Field(description="Polecenie dla ucznia.")
    question_text: str = Field(
        default="",
        description="Wspólna treść zadania: tekst z lukami (part 1), temat wypracowania (Writing). "
                    "Dla części 2–4 pusty — treść jest w poszczególnych pozycjach `items`.",
    )
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
    question_text: str = ""
    options: Optional[list[str]] = None
    items: Optional[list[ExerciseItemPublic]] = None
    key_word: Optional[str] = None


# --- Ocena odpowiedzi --------------------------------------------------------

class ErrorItem(BaseModel):
    """Pojedynczy błąd wykryty w odpowiedzi ucznia."""

    # Uzupełniane po zapisie do dziennika — pozwala zakwestionować ten wpis
    # zarówno na ekranie wyniku, jak i później w zakładce „Moje błędy".
    id: Optional[int] = Field(default=None)
    # Numer pozycji zadania, z której wziął się ten błąd (zadania wieloczęściowe).
    # Pozwala przy zastrzeżeniu usunąć dokładnie ten wpis, bez zgadywania.
    item_number: Optional[int] = Field(default=None)
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
    """Ćwiczenie do jednostki: pojedynczego błędu ALBO grupy. Dokładnie jedno z pól."""
    error_id: Optional[int] = None
    group_id: Optional[int] = None
    lang: str = "pl"

    @model_validator(mode="after")
    def exactly_one_unit(self):
        if (self.error_id is None) == (self.group_id is None):
            raise ValueError("Podaj dokładnie jedno: error_id albo group_id.")
        return self


class CompleteRequest(BaseModel):
    """Wynik zestawu ćwiczeń do jednostki: pojedynczego błędu ALBO grupy."""
    error_id: Optional[int] = None
    group_id: Optional[int] = None
    # Ile ćwiczeń z zestawu uczeń rozwiązał poprawnie (i ile ich było).
    correct_items: int = 1
    total_items: int = 1

    @model_validator(mode="after")
    def exactly_one_unit(self):
        if (self.error_id is None) == (self.group_id is None):
            raise ValueError("Podaj dokładnie jedno: error_id albo group_id.")
        return self


class GoalRequest(BaseModel):
    goal: int


class ErrorCreate(BaseModel):
    """Błąd zgłoszony do dziennika po zatwierdzeniu przez ucznia.

    Ocena zwraca błędy jako *propozycje* — do dziennika trafiają dopiero stąd,
    więc pole `topic` przychodzi od klienta i musi zostać znormalizowane po stronie
    serwera (klientowi nie wolno wstawić tematu spoza taksonomii)."""

    topic: str
    student_text: str
    correct_text: str
    explanation: str = ""
    severity: str = "minor"
    # Skąd pochodzi błąd: gdy podane, typ i źródło bierzemy z zapisanego zadania.
    exercise_id: Optional[int] = None
    exercise_type: Optional[str] = None


class GroupUpdate(BaseModel):
    """Ręczna poprawka grupy — zmiana nazwy reguły lub jej wyjaśnienia."""
    rule: str
    explanation: str = ""


class ErrorGroupUpdate(BaseModel):
    """Przepięcie wpisu do innej grupy (`group_id`) albo odpięcie (`None`)."""
    group_id: Optional[int] = None


class DisputeRequest(BaseModel):
    """Zastrzeżenie do wyjaśnienia wystawionego przez model."""

    scope: str  # 'item' — wyjaśnienie pozycji zadania; 'error' — wpis w dzienniku błędów
    disputed_text: str = Field(description="Kwestionowane wyjaśnienie (to, co widzi uczeń).")
    comment: str = Field(default="", description="Opcjonalne uzasadnienie zastrzeżenia.")
    exercise_id: Optional[int] = None
    item_number: Optional[int] = None
    error_id: Optional[int] = None
    lang: str = "pl"


# --- Fiszki -------------------------------------------------------------------

# Sufit długości uwag do przegenerowania. Idą wprost do promptu, więc tekst wklejony
# przez przypadek rozdmuchałby żądanie i jego koszt. Kilka zdań wskazówek mieści się
# swobodnie.
CARD_NOTES_MAX = 500


class CardRegenerate(BaseModel):
    """Uwagi do ponownego ułożenia JEDNEJ karty.

    Jednorazowe: nigdzie się nie zapisują, więc kolejne przegenerowanie znowu zaczyna
    od czystej kartki. Puste uwagi oznaczają zachowanie sprzed tej funkcji — ułożenie
    karty od nowa bez żadnych wskazówek."""
    notes: str = ""

    @model_validator(mode="after")
    def _przytnij(self) -> "CardRegenerate":
        self.notes = (self.notes or "").strip()[:CARD_NOTES_MAX]
        return self


class CardGrade(BaseModel):
    """Ocena karty. Serwer nie ufa klientowi — cokolwiek innego niż 'known'
    reguła odstępu potraktuje jako pomyłkę."""
    grade: str


class CardSettings(BaseModel):
    new_per_day: int
