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
- **Frontend:** statyczna strona (HTML/JS/CSS, bez frameworków) z pięcioma widokami: *Ćwicz*, *Tipy*,
  *Sprawdź z zewnątrz*, *Moje błędy*, *Statystyki*.
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
  **Każda część Use of English daje 5 zadań na jedno kliknięcie**, sprawdzanych jednym przyciskiem —
  dostajesz wynik punktowy (np. 3/5) i omówienie każdej pozycji:
  - *Part 1 (multiple-choice cloze)* — jeden spójny tekst z 5 lukami, każda z 4 wariantami;
    przy błędnych lukach omówienie wszystkich wariantów,
  - *Part 2 (open cloze)* — 5 zdań, w każdym jedna luka na jedno słowo,
  - *Part 3 (word formation)* — 5 zdań z wyrazem podstawowym do przekształcenia,
  - *Part 4 (key word transformation)* — 5 przekształceń ze słowem-kluczem.

  Liczbę pozycji zmienia stała `ITEMS_PER_EXERCISE` w `app/llm_client.py`. Odpowiedzi zamknięte
  (warianty) są oceniane **deterministycznie** przez serwer; przy odpowiedziach otwartych ocenia
  model, ale dokładne trafienie we wzorzec zawsze liczy się jako poprawne — dobra odpowiedź nie
  trafi do dziennika jako błąd.
  Zadania powstają **wsadowo**: jedno wywołanie modelu tworzy kilka zadań, pierwsze dostajesz od razu,
  a pozostałe czekają w kolejce w bazie i pojawiają się **natychmiast** przy kolejnych kliknięciach.
  Ponieważ koszt wywołania jest zdominowany przez stały narzut trybu headless (~23 tys. tokenów
  niezależnie od treści), to kilkukrotnie tańsze i szybsze. Wielkość wsadu: `_UOE_BATCH`
  / `_WRITING_BATCH` w `app/llm_client.py`.
- **Tipy** — tryb skupienia: aplikacja pokazuje jeden Twój błąd (dobierany losowo, ważony częstością
  Twoich słabych tematów) wraz z wyjaśnieniem i generuje do niego **zestaw 5 ćwiczeń**. Przyciski:
  *Ćwiczenie* (kolejny zestaw do tego samego błędu), *Inny błąd* (zmiana na nowy).
  U góry **dzienny cel** — ustalasz, ile błędów chcesz dziennie przerobić. Błąd zalicza się (+1)
  dopiero po **5 poprawnie rozwiązanych ćwiczeniach** do niego, liczonych **narastająco w obrębie
  dnia** — 3/5 w jednym podejściu i 2/5 w kolejnym też wystarczy. Postęp widać pod celem
  („Poprawne ćwiczenia do zaliczenia tego błędu: 3/5"). Próg zmienia `DRILL_CORRECT_TARGET`
  w `app/main.py`. Obok celu widać **serię** (🔥) — liczbę kolejnych dni z osiągniętym celem.

  Uwaga na skalę: przy celu 5 błędów dziennie oznacza to 25 poprawnych ćwiczeń — jeśli to za dużo,
  obniż cel w polu *Dzienny cel*.
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
  decyzji o migracji na API. Cennik jest w `app/pricing.py`; jeśli użyty model nie ma
  **potwierdzonej** stawki, szacunek jest wyraźnie oznaczony jako założony (zamiast podawać
  liczbę jako pewnik).

## Testy

```bash
python3 -m pytest -q
```

Pokrycie: warstwa bazy (w tym regresja współbieżności i migracji kolejki), logika doboru
zadań (`srs`), parsowanie odpowiedzi modelu i deterministyczna ocena luk, endpointy HTTP
(FastAPI TestClient, bez wywoływania modelu) oraz import wcześniejszych błędów.

## Konfiguracja (zmienne środowiskowe)

- `FCE_CLAUDE_BIN` — ścieżka do binarki `claude` (domyślnie `claude`).
- `FCE_LLM_TIMEOUT` — limit czasu wywołania modelu w sekundach (domyślnie 180).
- `FCE_DB_PATH` — ścieżka pliku bazy SQLite (domyślnie `data/fce.db`).

## Uwagi

- Wywołania modelu **liczą się do limitów Twojej subskrypcji** (Pro/Max). Dla nauki osobistej to zwykle bez znaczenia.
- Uporządkowany JSON jest wymuszany promptem i parsowany z jedną ponowną próbą (nie gwarantowany schematem).
- Latencja pojedynczego sprawdzenia to zwykle ~2–5 s (widać wskaźnik ładowania).
- Aby w przyszłości przejść na **klucz API**, wystarczy podmienić funkcję `_invoke` w `app/llm_client.py`.
