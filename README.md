# FCE Trener

Lokalna aplikacja w przeglądarce do przygotowania do egzaminu **Cambridge B2 First (FCE)**.
Generuje zadania (**Use of English** + **Writing**), sprawdza odpowiedzi — także te **wklejone
z zewnątrz** (z książki / od korepetytora) — i prowadzi **dziennik Twoich błędów**, który steruje
doborem kolejnych zadań, żebyś oduczał się powtarzanych pomyłek.

## Jak to działa

- **Backend:** FastAPI (Python) + SQLite.
- **Model:** aplikacja wywołuje **Claude Code w trybie headless** (`claude -p … --output-format json`)
  i korzysta z Twojego **logowania z subskrypcji** (`~/.claude/.credentials.json`) — **bez klucza API**.
  Cała ta zależność jest w jednym pliku: `app/llm_client.py`.
- **Frontend:** statyczna strona (HTML/JS/CSS) z trzema widokami: *Ćwicz*, *Sprawdź z zewnątrz*, *Moje błędy*.
- **Język:** przełącznik **PL / EN** w prawym górnym rogu zmienia zarówno interfejs, jak i język
  treści generowanych przez model (polecenia, wyjaśnienia, feedback) — przydatne, gdy pokazujesz
  aplikację osobie anglojęzycznej. Wybór jest zapamiętywany (localStorage), domyślnie polski.
  Uwaga: wcześniej zapisane błędy zachowują język, w jakim powstały.

## Wymagania

- Python 3.12
- Zainstalowany i **zalogowany** Claude Code (`claude` w `PATH`). Sprawdź: `claude --version`.

## Instalacja zależności

```bash
pip3 install --user --break-system-packages -r requirements.txt
```

(Alternatywnie, jeśli masz `python3-venv`: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
i uruchamiaj przez `.venv/bin/python -m uvicorn …`.)

## Uruchomienie

```bash
python3 -m uvicorn app.main:app --reload
```

Następnie otwórz **http://localhost:8000**.

## Użycie

- **Ćwicz** — wybierz typ zadania (np. *open cloze*, *key word transformation*, *essay*), opcjonalnie
  temat (albo zostaw dobór automatyczny wg Twoich błędów), wygeneruj i rozwiąż. Aplikacja oceni i zapisze błędy.
- **Tipy** — tryb skupienia: aplikacja pokazuje jeden Twój błąd (dobierany losowo, ważony częstością
  Twoich słabych tematów) wraz z wyjaśnieniem i generuje do niego ćwiczenia. Przyciski: *Ćwiczenie*
  (kolejne ćwiczenie do tego samego błędu), *Inny błąd* (zmiana na nowy). U góry **dzienny cel** —
  ustalasz, ile błędów chcesz dziennie przerobić; błąd liczy się po sprawdzeniu przynajmniej jednego
  ćwiczenia do niego. Obok celu widać **serię** (🔥) — liczbę kolejnych dni z osiągniętym celem.
- **Sprawdź z zewnątrz** — wklej zadanie z książki i swoją odpowiedź; aplikacja sprawdzi je i zaloguje błędy.
- **Moje błędy** — przegląd słabych punktów i pełny dziennik błędów. Przy każdym błędzie przycisk
  **Ćwicz ten błąd** przenosi do zakładki *Tipy* z tym błędem i od razu generuje do niego ćwiczenie.
- **Statystyki** — dwie sekcje: *Nauka* (wygenerowane ćwiczenia, sprawdzone odpowiedzi, skuteczność,
  powtórki, liczba błędów, podział wg typu zadania) oraz *Zużycie Claude* (liczba wywołań, tokeny
  wejściowe/wyjściowe/cache, **szacowany koszt wg stawek API** i podział wg rodzaju wywołania).
  Statystyki użycia zbierane są **od teraz** (z koperty JSON każdego wywołania `claude`); nie obejmują
  wcześniejszych wywołań (import, testy). **Uwaga:** tryb headless niesie narzut systemowego promptu
  Claude Code (~kilkadziesiąt tys. tokenów cache na wywołanie), więc oszacowany koszt to **górna
  granica** — aplikacja na kluczu API z lekkim promptem zużyłaby wyraźnie mniej. Dlatego obok
  pokazywany jest też **szacunek kosztu na API bez narzutu** (tylko realny prompt + odpowiedź,
  wyceniony po cenniku modelu — Opus oraz taniej: Sonnet 5), który daje realniejszą liczbę do
  decyzji o migracji na API.

## Testy

```bash
python3 -m pytest -q
```

## Konfiguracja (zmienne środowiskowe)

- `FCE_CLAUDE_BIN` — ścieżka do binarki `claude` (domyślnie `claude`).
- `FCE_LLM_TIMEOUT` — limit czasu wywołania modelu w sekundach (domyślnie 180).
- `FCE_DB_PATH` — ścieżka pliku bazy SQLite (domyślnie `data/fce.db`).

## Uwagi

- Wywołania modelu **liczą się do limitów Twojej subskrypcji** (Pro/Max). Dla nauki osobistej to zwykle bez znaczenia.
- Uporządkowany JSON jest wymuszany promptem i parsowany z jedną ponowną próbą (nie gwarantowany schematem).
- Latencja pojedynczego sprawdzenia to zwykle ~2–5 s (widać wskaźnik ładowania).
- Aby w przyszłości przejść na **klucz API**, wystarczy podmienić funkcję `_invoke` w `app/llm_client.py`.
