"""Walidacja i normalizacja odpowiedzi modelu przy grupowaniu błędów.

Moduł jest czysty: żadnej bazy, żadnego LLM. Wejściem jest surowy słownik zwrócony
przez model, wyjściem — plan przypisań, który warstwa bazy wykonuje bez podejmowania
dalszych decyzji. Dzięki temu najbardziej podatna na przekłamania część testuje się
tabelką wejście-wyjście, tak jak reguła serii w `app/streak.py`.

Model potrafi wymyślić id grupy, pominąć wpis, zaproponować dwa razy tę samą grupę
albo zwrócić temat spoza taksonomii. Każdy z tych przypadków kończy się tutaj, a nie
wyjątkiem w trakcie żądania.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import fce_taxonomy as tax

_WS = re.compile(r"\s+")
# Klucz jest wyłącznie wewnętrzny (deduplikacja), nigdy nie jest pokazywany — wyświetlamy
# oryginalne `rule`. Dlatego zrzucamy też '+': model zapisze tę samą regułę raz jako
# "depend + on", raz jako "depend on", a to ma trafić do jednej grupy.
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


def normalize_rule(rule: str | None) -> str:
    """Klucz deduplikacji nowych grup: bez wielkości liter, interpunkcji i nadmiarowych spacji."""
    lowered = (rule or "").strip().lower()
    return _WS.sub(" ", _PUNCT.sub(" ", lowered)).strip()


def chunks(items: list, size: int) -> list[list]:
    """Dzieli listę na porcje o zadanym rozmiarze (ostatnia bywa krótsza)."""
    if size <= 0:
        raise ValueError("size musi być dodatnie")
    return [items[i:i + size] for i in range(0, len(items), size)]


@dataclass(frozen=True)
class NewGroup:
    """Grupa do utworzenia wraz z wpisami, które mają do niej trafić."""
    key: str
    rule: str
    explanation: str
    topic: str
    error_ids: tuple[int, ...]


@dataclass(frozen=True)
class AssignmentPlan:
    """Komplet decyzji dla jednej porcji: co dopiąć, co utworzyć, co zostawić luzem."""
    to_existing: dict[int, int]
    new_groups: tuple[NewGroup, ...]
    unassigned: tuple[int, ...]


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def plan_assignments(model_output: dict | None, sent_error_ids: list[int],
                     existing_group_ids: set[int]) -> AssignmentPlan:
    """Zamienia surową odpowiedź modelu w plan przypisań.

    Każdy wpis, którego model nie obsłużył wiarygodnie, ląduje w `unassigned` —
    żądanie ma się nie wywalić tylko dlatego, że model coś zmyślił.
    """
    sent = list(dict.fromkeys(int(e) for e in sent_error_ids))
    pending = set(sent)
    to_existing: dict[int, int] = {}
    buckets: dict[str, dict] = {}

    for row in (model_output or {}).get("assignments") or []:
        if not isinstance(row, dict):
            continue
        error_id = _as_int(row.get("error_id"))
        if error_id is None or error_id not in pending:
            continue  # wymyślony wpis albo powtórzenie już rozstrzygniętego

        if row.get("group_id") is not None:
            group_id = _as_int(row.get("group_id"))
            if group_id is not None and group_id in existing_group_ids:
                to_existing[error_id] = group_id
                pending.discard(error_id)
            continue  # wymyślone id → wpis zostaje nieprzypisany

        new = row.get("new_group")
        if not isinstance(new, dict):
            continue
        rule = str(new.get("rule") or "").strip()
        key = normalize_rule(rule)
        if not key:
            continue  # grupa bez reguły jest bezużyteczna
        bucket = buckets.get(key)
        if bucket is None:
            # normalize_topic jest wrażliwe na wielkość liter i nie przycina spacji.
            raw_topic = str(new.get("topic") or "").strip().lower()
            bucket = {
                "rule": rule,
                "explanation": str(new.get("explanation") or "").strip(),
                "topic": tax.normalize_topic(raw_topic),
                "error_ids": [],
            }
            buckets[key] = bucket
        bucket["error_ids"].append(error_id)
        pending.discard(error_id)

    new_groups = tuple(
        NewGroup(key=key, rule=b["rule"], explanation=b["explanation"],
                 topic=b["topic"], error_ids=tuple(b["error_ids"]))
        for key, b in buckets.items()
    )
    return AssignmentPlan(
        to_existing=to_existing,
        new_groups=new_groups,
        unassigned=tuple(eid for eid in sent if eid in pending),
    )
