# Treść fiszki — przeprojektowanie

Data: 2026-09-18
Status: zatwierdzony do planowania
Zastępuje: decyzję D1 ze specu `2026-09-17-fiszki-design.md` (czym jest treść karty)

## Problem

Fiszki działają, ale uczą źle. Karta pokazuje na pierwszej stronie **formę błędną**:

```
in home            →  at home        (stały zwrot — zawsze 'at home')
a free time        →  free time      ('time' jest niepoliczalne — bez 'a')
prefer X than Y    →  prefer X rather than Y
```

Zgłoszenie użytkownika po pierwszym realnym przejrzeniu talii: *„na dzień dobry pokazują
błąd… zamiast mnie uczyć, pokazują błędy na początek"*.

To nie jest usterka implementacji, tylko defekt projektu. Zaprojektowano kartę jako parę
„błędnie → poprawnie", ponieważ **taką parę ma już dziennik** — `student_text`,
`correct_text`, `explanation`. Wyszło tanio i natychmiastowo, ale kosztem sensu:

- ekspozycja na formę błędną ją utrwala, zamiast osłabiać,
- uczeń niczego sobie nie przypomina — rozpoznaje pomyłkę, a to inna, łatwiejsza czynność,
- karta nie mówi, **co chcemy powiedzieć**, więc nie ćwiczy produkcji języka.

### Sprostowanie do poprzedniego specu

Poprzedni spec zapisał ograniczenie jako „karty powstają z danych, zero wywołań". To było
złe odczytanie. Użytkownik przez „szybkość" rozumiał **tempo sesji**: dwadzieścia kart jedna
za drugą przypomina dwadzieścia zasad szybciej, niż przerobienie trzech błędów w trybie
„Ćwicz błędy".

Prawdziwe ograniczenie brzmi: **przewracanie karty nie może czekać na model.** Jednorazowe,
wsadowe wygenerowanie treści jest dopuszczalne i kosztowo akceptowalne.

## Cel

Karta ma uczyć produkcji poprawnej formy, nigdy nie pokazując formy błędnej jako pierwszej
rzeczy, którą uczeń widzi — przy zachowaniu tempa sesji.

## Decyzje i ich uzasadnienie

### D1. Dwa kształty karty, dobierane do materiału

Dziennik nie jest jednorodny. Zmierzone na 219 wpisach:

| Rodzaj | Tematy | Wpisów |
|---|---|---|
| leksykalny | collocations, prepositions, false_friends, phrasal_verbs, word_formation, compound_nouns | ~113 |
| gramatyczny | gerund_infinitive, articles, tenses, quantifiers, word_order, conditionals, relative_clauses, modals, passive_voice, comparatives, adverb_adjective, linkers | ~95 |
| pozostałe | spelling, language, register | ~11 |

Dla `Healthy cuisine` polski sens jest oczywisty („zdrowa kuchnia"). Dla `is worth seeing`
nie ma znaczenia słownikowego — jest konstrukcja. Jeden kształt karty nie obsłuży obu.

- **`translate`** — przód: polskie zdanie do powiedzenia po angielsku. Tył: angielska wersja
  plus jedno zdanie, dlaczego tak.
- **`gap`** — przód: angielskie zdanie z luką `______`. Tył: forma wpisywana w lukę plus
  jedno zdanie, dlaczego tak.

W obu kształtach forma błędna **nie pojawia się nigdzie** — ani na przodzie, ani na tyle.

### D2. Kształt wybiera mapa tematów; model może odstąpić, ale musi to uzasadnić

Mapa `temat → kształt` mieszka w czystym `app/flashcards.py` i jest testowalna tabelką.
Model dostaje ją jako sugestię i może odstąpić, wypełniając `shape_reason`.

Powód dopuszczenia odstępstwa: przyimki to drugi co do wielkości zbiór (36 wpisów) i dzielą
się wewnętrznie — `It depends on the weather` to naturalna karta tłumaczeniowa, a `on Friday`
raczej zdanie z luką. Sztywna mapa pomyliłaby się na części z nich.

Powód wymagania uzasadnienia: odstępstwo bez powodu jest nieodróżnialne od kaprysu, a projekt
nie ma jak go zweryfikować — wszystkie testy podstawiają model. Zapisany powód zamienia
niewidoczną decyzję w policzalną.

### D3. Treść powstaje wsadowo, na wyraźne kliknięcie

Przycisk „Przygotuj karty" w zakładce Fiszki, obok „Zacznij sesję", z licznikiem
nieprzygotowanych — ten sam wzorzec, co „Scal nowe" w grupach, więc nie wprowadza nowego gestu.

Odrzucono generowanie przy starcie sesji (czekanie w najgorszym momencie) oraz przy zapisie
błędu do dziennika (płacenie za karty, których uczeń może nigdy nie powtarzać, i tak
wymagające jednorazowego nadrobienia 219 istniejących wpisów).

### D4. „Ulepsz tę kartę" znika; zastępuje je „Przegeneruj"

Ulepszanie istniało wyłącznie po to, żeby zamienić surową parę w kartę wymuszającą
przypomnienie — czyli robiło ręcznie i za dopłatą to, co teraz robi generowanie dla
wszystkich. Utrzymywanie obu byłoby dwiema koncepcjami na jedną potrzebę.

Endpoint wraca jako „przegeneruj tę kartę": ten sam kod generowania, dla jednej sztuki,
na wypadek słabej karty.

### D5. Karta bez treści nie wchodzi do kolejki

`prepared_at IS NULL` oznacza kartę nieprzygotowaną. To zastępuje dotychczasowe kryterium
„karta jeszcze nie istnieje" i przesuwa moment powstania wiersza: karta powstaje przy
**przygotowaniu**, nie przy pierwszej ocenie.

W konsekwencji limit nowych kart dziennie przestaje rządzić powstawaniem wierszy i zaczyna
rządzić wyłącznie kolejką — co jest jego właściwym miejscem. Nowa karta to taka bez ani
jednej oceny w `card_reviews`; zaległa to taka z oceną i terminem na dziś lub wcześniej.

### D6. Harmonogramy przeżywają przeprojektowanie

Istniejące karty mają terminy i historię ocen. Generowanie treści ich nie dotyka. Zmienia
się to, co uczeń widzi na karcie, nie to, kiedy ją widzi.

## Model danych

Migracja **addytywna**: pięć nowych kolumn, zero przepisywania danych.

```sql
ALTER TABLE cards ADD COLUMN front         TEXT;
ALTER TABLE cards ADD COLUMN back          TEXT;
ALTER TABLE cards ADD COLUMN shape         TEXT;   -- 'translate' | 'gap'
ALTER TABLE cards ADD COLUMN shape_reason  TEXT;   -- tylko przy odstąpieniu od mapy
ALTER TABLE cards ADD COLUMN prepared_at   TEXT;   -- NULL = nieprzygotowana

CREATE INDEX IF NOT EXISTS idx_cards_prepared ON cards(prepared_at);
```

Te pięć kolumn wymaga ścieżki `_migrate` w `app/db.py`, **inaczej niż nowe tabele**:
`_SCHEMA` idzie przez `executescript` przy każdym połączeniu, więc `CREATE TABLE IF NOT EXISTS`
obsługuje istniejące bazy samo z siebie, ale `ALTER TABLE … ADD COLUMN` nie jest idempotentne
i musi być osłonięte sprawdzeniem `PRAGMA table_info(cards)` — dokładnie tak, jak zrobiono to
dla `errors.group_id` przy grupowaniu.

`front_override` i `back_override` zostają w tabeli **nieużywane**. SQLite nie upuszcza
kolumn bez przebudowy tabeli, a przebudowa żywej bazy z historią ocen to ryzyko bez pokrycia
wobec dwóch martwych kolumn.

## Mapa kształtów

W `app/flashcards.py`, obok drabinki odstępów:

```
translate: collocations, prepositions, false_friends, phrasal_verbs,
           compound_nouns, word_formation
gap:       tenses, articles, gerund_infinitive, quantifiers, conditionals,
           relative_clauses, modals, passive_voice, comparatives,
           adverb_adjective, word_order, linkers
translate: spelling, register, language   (domyślnie, jako reszta)
```

`default_shape(topic)` zwraca `translate` dla tematu spoza mapy — nieznany temat ma dostać
kartę tłumaczeniową, bo ta nie wymaga poprawnie postawionej luki.

## Generowanie

### Wejście i wyjście modelu

Model dostaje dla każdego wpisu: `source_kind`, `source_id`, temat, etykietę tematu,
`student_text`, `correct_text`, `explanation` oraz `suggested_shape`.

Zwraca: `source_id`, `shape`, `front`, `back`, `shape_reason`.

Prompt musi powiedzieć wprost, że **forma błędna nie może wystąpić ani na przodzie, ani
na tyle** — to jest cała racja bytu tej zmiany, a model ma tę formę w danych wejściowych.

### Serwer odrzuca pozycje w całości

Odmiennie niż przy grupowaniu, gdzie wpis bez przypisania po prostu zostawał nieprzypisany:
tutaj niespójna odpowiedź musi wypaść **cała**, bo załatanie jej znaczyłoby podanie treści
ułożonej dla jednego kształtu pod etykietą drugiego.

| Sytuacja | Zachowanie |
|---|---|
| `source_id` spoza wysłanych | pozycja ignorowana |
| wpis pominięty przez model | zostaje nieprzygotowany |
| `shape` spoza `translate`/`gap` | pozycja odrzucona |
| odstąpienie od mapy bez `shape_reason` | pozycja odrzucona |
| `shape: gap`, a we froncie brak `______` | pozycja odrzucona |
| pusty `front` albo `back` | pozycja odrzucona |

Odrzucone pozycje zostają nieprzygotowane i wracają przy kolejnym kliknięciu — funkcja leczy
się sama, bez osobnej ścieżki naprawczej.

Walidacja w czystym `app/flashcards.py` jako `plan_cards(...)`, tabelka wejście-wyjście,
bez bazy i bez modelu — jak `grouping.plan_assignments`.

Przygotowanie obejmuje **dwa rodzaje kandydatów**: źródła, które nie mają jeszcze karty,
oraz karty istniejące bez treści — czyli te powstałe pod poprzednim projektem. Dla pierwszych
tworzy wiersz wraz z treścią; dla drugich dopisuje treść, nie dotykając harmonogramu (D6).

Porcja: 40 wpisów na wywołanie. 285 źródeł to około ośmiu wywołań, jednorazowo.

## API

| Endpoint | Zmiana |
|---|---|
| `POST /api/cards/prepare` | nowy — przygotowuje wsadowo nieprzygotowane karty |
| `POST /api/cards/{id}/regenerate` | zastępuje `…/improve` |
| `GET /api/cards/session` | serwuje wyłącznie karty z `prepared_at`; nadal **nie woła modelu** |
| `GET /api/cards/progress` | dochodzi `unprepared` do liczników |
| `POST /api/cards/{id}/improve` | usunięty |
| `POST /api/cards/grade-new` | **usunięty** |

`grade-new` istniał, bo sesja mogła podać kartę, której jeszcze nie ma w bazie (`card_id: null`).
Po D5 sesja serwuje wyłącznie karty przygotowane, więc każda ma identyfikator i jedyną ścieżką
oceny zostaje `POST /api/cards/{id}/grade`. Gałąź `card_id === null` we frontendzie znika razem
z endpointem — dziś jest jej jedynym konsumentem.

## UI

Zakładka Fiszki: przycisk **„Przygotuj karty"** obok „Zacznij sesję", z licznikiem
nieprzygotowanych. Przy karcie, w miejscu dawnego „Ulepsz tę kartę", przycisk **„Przegeneruj"**.

Przód i tył biorą się teraz z kolumn karty, nie z renderowania ze źródła. Klucze i18n
dawnego ulepszania znikają z obu bloków; nowe dochodzą do obu.

## Testy

- `app/flashcards.py` — tabelka dla `default_shape(topic)` (temat leksykalny, gramatyczny,
  nieznany) oraz sześciowierszowa dla `plan_cards`, po jednym wierszu na każdy powód odrzucenia.
- warstwa bazy — kolejka po `prepared_at` i po obecności ocen; regresja na tym, że
  przygotowanie **nie rusza** `due_on` ani `interval_days` istniejącej karty.
- endpointy — z podstawionym `llm_client`; regresja, że `GET /api/cards/session` nadal nie
  woła modelu, oraz że `POST /api/cards/prepare` nie woła go, gdy nie ma czego przygotować.
- regresja treści: na **wyrazistym fixture** (wpis o `student_text = "in home"`, sprawdzany
  bez względu na wielkość liter) ani `front`, ani `back` nie zawiera formy błędnej. To jedyny
  test pilnujący powodu, dla którego ta zmiana powstała.

  Test **nie może** być ogólnym sprawdzeniem podciągu po wszystkich wpisach: 35 z 219 ma
  `student_text` krótszy niż pięć znaków — w tym `in`, `at`, `do` i `-` — więc naiwna wersja
  padałaby na niemal każdym poprawnym angielskim zdaniu. Test, który psuje się bez powodu,
  jest gorszy niż jego brak, bo uczy zespół ignorowania czerwonego wyniku.
- smoke frontendu — przycisk przygotowania i przejście sesji.
- README w obu językach: opis obu kształtów karty i tego, że forma błędna nie jest pokazywana.

## Poza zakresem

- Ręczna edycja treści karty przez ucznia.
- Karty odwrotne (angielski → polski).
- Wybór kształtu przez ucznia dla konkretnej karty.
- Usunięcie martwych kolumn `front_override` / `back_override`.

## Ryzyka

| Ryzyko | Ograniczenie |
|---|---|
| Model mimo zakazu wstawi formę błędną na kartę | test regresji porównujący `front`/`back` z `student_text`; przycisk „Przegeneruj" |
| Mapa źle przypisuje przyimki | dopuszczone odstępstwo z uzasadnieniem; mapa poprawialna jedną linią |
| Odstępstwa okażą się częste i bezzasadne | `shape_reason` jest zapisane, więc da się je policzyć i przejrzeć |
| Jednorazowy koszt przygotowania 285 kart | ~8 wywołań, na wyraźne kliknięcie, z widocznym licznikiem |
| Uczeń nie kliknie „Przygotuj" i zobaczy pustą sesję | pusty ekran mówi wprost, ile kart czeka na przygotowanie |
