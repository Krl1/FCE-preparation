# Grupowanie błędów — projekt

Data: 2026-09-16
Status: zatwierdzony do planowania

## Problem

Dziennik błędów rośnie liniowo i nie ma wewnętrznej struktury. Stan na dziś: **196 wpisów**,
z czego `in_app` 63, `import:other_mistakes.txt` 63, `import:english_mistakes.tsv` 33,
`import:writing_mistakes.txt` 28, `external` 9.

Wpisy `in_app` są głównym źródłem narastania: każde potknięcie na regule, która jest już
w dzienniku, dokłada nowy wpis, bo pochodzi z innego zdania. Taksonomia FCE daje tylko gruby
podział (12 tematów, `prepositions` 34 i `collocations` 33 na czele) i nie mówi nic o tym,
co wewnątrz tematu jest tą samą regułą.

Duplikaty są **semantyczne, nie tekstowe**. Zapytanie o powtórzenia po `student_text` zwraca
głównie `-`, `at`, `in` — czyli odpowiedzi do luk, nie powtórzone pojęcia. Dopasowanie po
stringach nie rozwiązuje problemu; grupowanie musi rozumieć, że `Depends from` i `it depends
from the weather` to ta sama reguła.

Jednocześnie przegląd 12 pierwszych wpisów z `prepositions` pokazuje, że **nie są to głównie
duplikaty** — `depend on`, `discuss` bez przyimka, `on Friday`, `take care of`, `scared of` to
różne reguły. Grupa nie będzie więc zlepkiem identycznych wpisów, tylko **jedną regułą wraz
z kontekstami, w których została złamana**.

## Cel

Umożliwić okresowe scalanie wpisów w grupy odpowiadające regułom, tak żeby dało się ćwiczyć
regułami zamiast pojedynczymi potknięciami — bez naruszania dziennika jako pełnego zapisu.

## Decyzje i ich uzasadnienie

### D1. Grupa jest dodatkowym widokiem, nie zamiennikiem wpisu

Dziennik nadal pokazuje wszystkie wpisy; grupy są drugą soczewką. W trybach ćwiczeń dochodzi
wybór: trenować pojedyncze błędy czy grupy.

Świadomie przyjęty koszt: licznik „Błędy w dzienniku" nadal rośnie liniowo, bo grupowanie
niczego z dziennika nie zdejmuje. Zysk jest w strukturze (widać, że na jednej regule potknąłeś
się sześć razy) i w tym, że grupa jest naturalną jednostką do szybszego przerobienia wielu
błędów naraz.

### D2. Nic nie jest kasowane

Grupowanie ustawia przypisania, nie usuwa wpisów. Usunięcie grupy zwraca jej wpisy do puli
nieprzypisanych. Wynika to wprost z zasady, na której stoi cała aplikacja: nic nie wchodzi
do dziennika i nic z niego nie wychodzi samo.

### D3. Bez zatwierdzania każdej grupy

Skoro grupa to widok i nic nie ginie, zła grupa nie psuje danych — poprawia się ją albo
uruchamia scalanie ponownie. Przeklikanie 60–80 propozycji po każdym przebiegu byłoby kosztem
bez pokrycia. To jedyne miejsce, w którym odchodzimy od zatwierdzania — i wolno nam, bo
operacja jest odwracalna, w przeciwieństwie do zapisu błędu do dziennika.

### D4. Przerobiona grupa liczy się do celu jak jeden błąd

Grupa daje +1 do dziennego celu, tak samo jak pojedynczy wpis, i tak samo po uzbieraniu
`DRILL_CORRECT_TARGET` poprawnych ćwiczeń w danym dniu (stała jest pochodną
`llm_client.ITEMS_PER_EXERCISE`, dziś 5 — nie literałem). Alternatywa „grupa zalicza wszystkie
swoje wpisy" psułaby porównywalność serii 🔥 z dotychczasową historią — cel 5 dałoby się zamknąć
jedną grupą.

### D5. Jedno wywołanie modelu, grupy mogą przecinać tematy

Koszt wywołania jest zdominowany przez stały narzut trybu headless (~23 tys. tokenów niezależnie
od treści). Wywołanie na każdy temat taksonomii to **12 × 23 tys. ≈ 276 tys. tokenów narzutu**
zamiast 23 tys. — dwunastokrotnie drożej za gorszy wynik, bo grupa nie mogłaby połączyć
`Depends from` (`prepositions`) z `by some reason` (`collocations`), choć to ta sama klasa kalki
z polskiego.

Odrzucono też klastrowanie po podobieństwie bez modelu: wymaga embeddingów, czyli nowej
zależności i modelu lokalnego. Projekt trzyma całą zależność od LLM w jednym pliku
(`app/llm_client.py`) i ta decyzja jest warta utrzymania.

### D6. Przyrostowo domyślnie, pełne przeliczenie osobno

Nowe błędy trafiają do istniejących grup albo zakładają własne. Pełne przegrupowanie jest osobną,
rzadszą akcją — po kilkuset wpisach pierwotny podział zwykle wymaga korekty.

Pełne przegrupowanie **kasuje ręczne poprawki** i dlatego wymaga potwierdzenia. Świadomie nie
budujemy przypinania grup: to złożoność bez pokrycia, dopóki nie wiadomo, czy ręczne poprawki
w ogóle będą używane.

## Model danych

Migracja jest **addytywna**: dwie nowe tabele i jedna kolumna, zero przepisywania istniejących
danych.

```sql
CREATE TABLE IF NOT EXISTS error_groups (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    rule        TEXT NOT NULL,   -- krótka nazwa reguły, np. "depend + on"
    explanation TEXT NOT NULL,   -- scalone wyjaśnienie
    topic       TEXT NOT NULL    -- temat dominujący wśród wpisów
);
-- `updated_at` ma konkretnego konsumenta: sortowanie listy grup (ostatnio ruszane na górze)
-- i zmiana znacznika przy zmianie nazwy reguły. Kolumny `origin` świadomie nie ma — ręczne
-- tworzenie grup jest poza zakresem, więc nie miałaby czytelnika.

-- errors.group_id: NULL = wpis nieprzypisany (przyszedł po ostatnim przebiegu)
ALTER TABLE errors ADD COLUMN group_id INTEGER;
CREATE INDEX IF NOT EXISTS idx_errors_group ON errors(group_id);
```

Jeden błąd należy do **co najwyżej jednej** grupy.

### Cykl życia grupy

Grupa jest definiowana przez swoje wpisy, więc **grupa bez wpisów jest usuwana automatycznie**.
Dzieje się to w trzech miejscach: przy odpięciu ostatniego wpisu, przy przepięciu go do innej
grupy i przy usunięciu błędu istniejącym `DELETE /api/errors/{id}` — ta ścieżka musi więc
sprzątać po sobie, inaczej w widoku zostałyby puste reguły.

Zaliczenia w `group_reviews` **zostają** po usunięciu grupy. To ta sama zasada, która już
obowiązuje przy usuwaniu błędu: praca, którą naprawdę wykonałeś, ma zostać policzona, więc
usunięcie nie cofa dziś zdobytego celu ani serii.

### Zaliczenia grup

`reviews` i `drill_scores` pozostają **nietknięte**. Dochodzą `group_reviews` i
`group_drill_scores` o tym samym kształcie, z `group_id` zamiast `error_id`.

Powód jest praktyczny: `reviews.error_id` jest `NOT NULL`, a zdjęcie tego ograniczenia w SQLite
wymaga przebudowy tabeli. Na żywej bazie, w której siedzi realna historia serii, to niepotrzebne
ryzyko wobec zysku z uniknięcia dwóch małych tabel.

`streak.py` jest czysty i przyjmuje gotową mapę `'YYYY-MM-DD' -> liczba`, więc wystarczy, że
`db.reviews_per_day()` zsumuje oba źródła. Reguła serii nie wymaga żadnej zmiany.

Zaliczenie pozostaje idempotentne w obrębie dnia, osobno dla wpisów i osobno dla grup.

## Przepływ grupowania

### Wejście i wyjście modelu

Model dostaje:
- listę wpisów do przypisania: `id`, `topic`, `student_text`, `correct_text`, skrócone `explanation`,
- listę istniejących grup: `id`, `rule`, `topic`.

Zwraca dla każdego wpisu albo `group_id` istniejącej grupy, albo propozycję nowej
(`rule`, `explanation`, `topic`).

### Serwer nie ufa odpowiedzi modelu

Ten sam wzorzec obronny, który już działa w `_errors_per_wrong_item` (luka pominięta przez model
dostaje propozycję zbudowaną z danych serwera):

| Sytuacja | Zachowanie |
|---|---|
| `group_id`, którego nie ma w bazie | wpis zostaje nieprzypisany; żądanie nie wybucha |
| wpis pominięty przez model | zostaje nieprzypisany |
| dwie identyczne „nowe" grupy w jednym przebiegu | scalane po znormalizowanej treści reguły |
| `topic` spoza taksonomii | normalizowany przez `tax.normalize_topic` |

### Porcjowanie

Pierwsze uruchomienie obejmuje 196 wpisów. Samo wyjście to wtedy kilka tysięcy tokenów, a przy
`FCE_LLM_TIMEOUT` = 180 s to realne ryzyko obcięcia odpowiedzi. Przebieg idzie więc porcjami po
około 60 wpisów; każda porcja widzi grupy utworzone przez poprzednie. Kolejność jest
deterministyczna (po `id`), więc wynik jest powtarzalny co do struktury przebiegu.

### Czysty moduł

Walidacja i normalizacja odpowiedzi modelu trafia do `app/grouping.py` — bez bazy i bez LLM,
na wzór `app/streak.py`. Najbardziej podatna na błędy część testuje się wtedy tabelką
wejście-wyjście.

## Ćwiczenie grup

`generate_drill` dostaje opcjonalną listę kontekstów. Przy grupie model widzi regułę plus kilka
przykładów, na których uczeń się potknął, zamiast jednego zdania. Nie powstaje drugi, bliźniaczy
prompt.

Dobór grupy do ćwiczenia idzie przez istniejące `srs`: waga z liczby wpisów w grupie i świeżości
najnowszego z nich.

## API

| Endpoint | Rola |
|---|---|
| `GET /api/groups` | lista grup z licznikami + liczba nieprzypisanych |
| `POST /api/groups/assign` | przyrostowe scalenie nieprzypisanych wpisów |
| `POST /api/groups/regroup` | pełne przeliczenie (kasuje ręczne poprawki) |
| `PATCH /api/groups/{id}` | zmiana reguły / wyjaśnienia |
| `DELETE /api/groups/{id}` | usunięcie grupy; wpisy wracają do nieprzypisanych |
| `PATCH /api/errors/{id}/group` | przepięcie wpisu do innej grupy lub odpięcie |

Endpointy `tips` dostają tryb `error` (domyślny, zachowanie bez zmian) albo `group`:
`GET /api/tips/focus?mode=…`, `POST /api/tips/exercise`, `POST /api/tips/complete`.

## UI

Bez szóstej zakładki.

**Moje błędy** — przełącznik `Wpisy | Grupy`. Grupa pokazuje regułę, temat i licznik wpisów,
rozwija się do kontekstów. Tam też oba przyciski scalania i poprawki: zmiana nazwy reguły,
odpięcie wpisu, usunięcie grupy.

**Ćwicz błędy** — przełącznik `Pojedyncze błędy | Grupy`. Reszta ekranu bez zmian: ten sam pasek
celu, ta sama seria, ten sam próg poprawnych ćwiczeń.

Nowe klucze i18n lecą do **obu** bloków w `static/app.js`. README opisuje teraz interfejs po
angielsku, więc rozjazd byłby od razu widoczny.

## Testy

- `app/grouping.py` — tabelka wejście-wyjście: wymyślone `group_id`, duplikaty nowych grup,
  wpisy pominięte przez model, temat spoza taksonomii.
- warstwa bazy — tworzenie grup, przypisanie, odpięcie, usunięcie grupy, liczniki.
- `db.reviews_per_day()` — sumowanie zaliczeń z obu źródeł; regresja na tym, że grupa nie
  podbija licznika dwa razy tego samego dnia.
- endpointy — z podstawionym `llm_client`, tak jak w istniejącym `tests/test_api.py`.
- `tests/smoke_frontend.js` — przejście obu nowych przełączników.

## Poza zakresem

- **Fiszki** — osobna funkcjonalność, zaprojektowana po tej i oparta na grupach.
- Przypinanie grup odpornych na pełne przegrupowanie (patrz D6).
- Ręczne tworzenie grupy od zera; grupy powstają z przebiegu, a potem można je poprawiać.

## Ryzyka

| Ryzyko | Ograniczenie |
|---|---|
| Model grupuje słabo (za grubo lub za drobno) | grupowanie jest odwracalne; „Przegrupuj wszystko" i poprawki ręczne |
| Pełne przegrupowanie kasuje ręczne poprawki | potwierdzenie przed uruchomieniem |
| Pierwszy przebieg drogi (196 wpisów) | porcjowanie; jednorazowy koszt, potem tryb przyrostowy |
| Grupy przecinające tematy mylą dobór w `srs` | grupa ma temat dominujący, więc `srs` działa jak dotąd |
