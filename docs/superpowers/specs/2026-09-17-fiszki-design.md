# Fiszki — projekt

Data: 2026-09-17
Status: zatwierdzony do planowania

## Problem

Tryb „Ćwicz błędy" jest dokładny, ale wolny i kosztowny. Zmierzone na żywej bazie
(`usage_events`, 2026-09-17):

| Wywołanie | Liczba | Średni czas | Średni koszt |
|---|---|---|---|
| `drill` (5 ćwiczeń do jednego błędu) | 137 | 12,4 s | 0,11 $ |
| `grade` (sprawdzenie zestawu) | 139 | 14,9 s | 0,14 $ |

Jeden przerobiony błąd to zatem **~27 s czekania i ~0,26 $**. Przy dziennym celu 5 błędów
wychodzi ponad dwie minuty samego spinnera i ~1,30 $ dziennie. Ta wolność nie bierze się
z interfejsu, tylko z dwóch wywołań modelu na każdy błąd.

Jednocześnie duża część nauki nie wymaga generowania ćwiczeń. Przypomnienie sobie, że
`depend` łączy się z `on`, to zadanie na sekundę — pod warunkiem, że pytanie jest gotowe.

Materiał już jest: 211 wpisów w dzienniku, każdy z kompletem `student_text`,
`correct_text` i `explanation`. Wyjaśnienia mają dobrą długość na rewers — 116 mieści się
w 40–100 znakach, 75 w 100–200.

## Cel

Dać drugi tryb nauki, w którym przelot przez kilkadziesiąt reguł trwa tyle, co dziś
przerobienie jednego błędu — bez rezygnacji z dokładności tam, gdzie jest potrzebna.

## Decyzje i ich uzasadnienie

### D1. Karty powstają z danych, model tylko na żądanie

Fiszka składa się z tego, co już jest w bazie: pary „błędnie → poprawnie" z wyjaśnieniem,
albo reguły grupy wraz z jej kontekstami. Zero wywołań, zero kosztu, działa bez sieci.

Osobno, na wyraźne kliknięcie, model może **ulepszyć konkretną kartę** — zamienić parę
w zdanie z luką. To jedyne miejsce w tej funkcji, które kosztuje, i nigdy nie uruchamia
się samo.

### D2. Karta ma własny harmonogram; dziennik zostaje nietknięty

To świadome odejście od zasady obowiązującej w „Ćwicz błędy" (README: *„błąd opanowany
dziesięć razy może wracać tak samo często jak nowy"*). Bez malejącej częstotliwości fiszki
nie są fiszkami, tylko karuzelą — przelot nigdy by się nie skracał.

Odejście dotyczy **wyłącznie kart**. Dziennik błędów, jego dobór i licznik pozostają bez zmian.

### D3. Fiszki mają własny licznik; seria 🔥 ich nie widzi

Seria mierzy głęboką pracę: pięć poprawnych ćwiczeń na błąd lub grupę, ~27 s modelu.
Karta to kliknięcie „umiem" — zero sekund, zero kosztu. Gdyby liczyła się tak samo,
dzienny cel 5 zamykałoby się w pół minuty i seria przestałaby odróżniać dzień pracy
od dnia przewijania kart.

Fiszki dostają osobny, widoczny licznik („28 kart dziś, 12 zaległych”).

### D4. Jedna kolejka „na dziś", temat jako filtr

Domyślnie wszystkie karty zaplanowane na dziś, wymieszane — tak działa odstęp i tak
uczy się najlepiej. Selektor tematu pozwala zawęzić sesję („dziś tylko przyimki”), ale
jest opcją nałożoną na jeden mechanizm, a nie osobnym podziałem na talie. Talie per temat
odrzucono: karty z pomijanych tematów cicho by się piętrzyły.

### D5. Karta jest widokiem na źródło, nie bytem obok niego

Treść renderuje się ze źródła w momencie pokazania, więc poprawione w dzienniku wyjaśnienie
natychmiast widać na karcie. Usunięcie błędu lub grupy usuwa jej kartę wraz z harmonogramem.

To jedyne miejsce w aplikacji, gdzie coś znika samo — i wynika wprost z tego, czym karta
jest. Alternatywa (materializacja treści przy tworzeniu) prowadziłaby do kart z martwą
treścią po usunięciu źródła, co kłóci się z zasadą „dziennik jest zapisem prawdy".

## Model danych

```sql
CREATE TABLE IF NOT EXISTS cards (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    source_kind    TEXT NOT NULL,     -- 'error' | 'group'
    source_id      INTEGER NOT NULL,
    due_on         TEXT NOT NULL,     -- 'YYYY-MM-DD'
    interval_days  INTEGER NOT NULL,
    front_override TEXT,              -- treść ulepszona modelem (NULL = renderuj ze źródła)
    back_override  TEXT,
    UNIQUE (source_kind, source_id)
);

CREATE INDEX IF NOT EXISTS idx_cards_due ON cards(due_on);

CREATE TABLE IF NOT EXISTS card_reviews (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id    INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    grade      TEXT NOT NULL          -- 'known' | 'unknown'
);

CREATE INDEX IF NOT EXISTS idx_card_reviews_card ON card_reviews(card_id, created_at);
CREATE INDEX IF NOT EXISTS idx_card_reviews_created ON card_reviews(created_at);
```

Świadomie **nie ma** kolumn `ease`, `reps` ani `lapses`. Przy stałej drabince odstępów
`ease` nie miałoby czytelnika, a liczba powtórek i pomyłek wylicza się z `card_reviews`,
więc trzymanie ich osobno tylko groziłoby rozjazdem.

Migracja jest addytywna: dwie nowe tabele, zero zmian w istniejących.

### Kasowanie karty wraz ze źródłem musi być RĘCZNE

W schemacie celowo nie ma `FOREIGN KEY … ON DELETE CASCADE`. Powód jest praktyczny,
nie estetyczny: `PRAGMA foreign_keys` jest w tej aplikacji **wyłączone** (sprawdzone —
`get_connection` ustawia tylko `journal_mode=WAL`), a w całym `app/db.py` nie ma ani
jednej klauzuli `ON DELETE`. Deklaratywna kaskada wyglądałaby więc poprawnie i po cichu
nie robiłaby nic: karta przeżyłaby usunięcie źródła i wróciłaby w sesji z martwą treścią.

Usunięcie karty należy zatem dopisać wprost do `db.delete_error` i `db.delete_group`,
wraz z jej wierszami w `card_reviews`, i pokryć testem regresji. Włączanie `foreign_keys`
globalnie jest poza zakresem tej funkcji — zmieniłoby zachowanie całej istniejącej bazy.

## Kolejka na dany dzień

```
kolejka = karty z due_on <= dziś
        + nowe źródła bez karty, do dziennego limitu (domyślnie 20)
```

Wiersz w `cards` powstaje **dopiero przy pierwszym pokazaniu**. Bez limitu nowych kart
pierwsza sesja miałaby 211 pozycji i zostałaby porzucona; z limitem kolejka narasta
łagodnie, a po kilku tygodniach sama siada, bo opanowane karty odsuwają się w przyszłość.

Limit jest ustawieniem w `settings`, tak jak dzienny cel.

Filtr tematu zawęża obie części kolejki — temat karty to temat jej źródła.

### Pusta kolejka

Gdy na dziś nie ma nic, ekran mówi to wprost i podaje datę najbliższej karty
(„Na dziś nic — następne 3 karty jutro”). Gdy kart nie ma w ogóle, bo dziennik jest pusty,
kieruje do zakładek, które je tworzą. Milczący pusty ekran jest tu najgorszą opcją, bo
nie da się odróżnić „wszystko zrobione" od „coś się zepsuło".

### Licznik dzienny

Liczba przerobionych dziś kart to `COUNT(DISTINCT card_id)` z `card_reviews` za dzisiaj —
liczona tak samo jak zaliczenia błędów, ale w osobnej tabeli i **bez udziału w serii 🔥**
(D3). Liczba zaległych to karty z `due_on < dziś`.

## Algorytm odstępu

Drabinka: `1 → 3 → 7 → 14 → 30 → 90` dni.

- **Umiem** → następny szczebel (z 90 zostaje 90).
- **Nie umiem** → powrót na 1 dzień.

Bez współczynnika łatwości: przy dwóch przyciskach nie ma z czego go liczyć, a wyliczanie
go mimo to dałoby liczbę, która wygląda mądrze i nic nie znaczy.

Dwa przyciski, nie cztery. Anki rozróżnia *Again / Hard / Good / Easy* i planuje
dokładniej, ale każda karta kosztuje wtedy decyzję — a celem tej funkcji jest tempo.
Obsługa z klawiatury: spacja odkrywa rewers i zalicza, `n` oznacza „nie umiem".

## Karty uparte — most do trybu ćwiczeń

Cztery oceny `unknown` na jednej karcie (liczone z `card_reviews`) oznaczają ją jako trudną.
Rewers pokazuje wtedy zdanie „ta reguła wraca uparcie — przerób ją w Ćwicz błędy" wraz
z przyciskiem skaczącym do tamtego trybu z tym właśnie błędem lub grupą.

Fiszki rozpoznają w ten sposób własną granicę: jeśli samo przypominanie nie działa,
potrzebne są ćwiczenia, a aplikacja już je ma.

## API

| Endpoint | Rola |
|---|---|
| `GET /api/cards/session` | kolejka na dziś (`topic`, `lang`) z wyrenderowanymi frontami i rewersami |
| `POST /api/cards/{id}/grade` | ocena (`known`/`unknown`), aktualizacja harmonogramu, zwrot postępu |
| `POST /api/cards/{id}/improve` | jednorazowe ulepszenie karty modelem |
| `GET /api/cards/progress` | licznik dzienny i liczba zaległych |
| `POST /api/cards/settings` | limit nowych kart dziennie |

Kolejka pobiera się **raz na sesję**, więc przewracanie kart jest czysto lokalne. Oceny
lecą osobnymi, małymi żądaniami od razu po kliknięciu — nie zbiorczo na koniec — żeby
zamknięta zakładka nie kasowała postępu.

## UI

Szósta zakładka, **Fiszki**. Tym razem osobna zakładka jest uzasadniona: to inna
aktywność z własnym stanem i własnym licznikiem, a nie druga soczewka na te same dane
(grupy słusznie zostały przełącznikiem wewnątrz istniejących zakładek).

Układ: u góry licznik („Dziś: 12 do powtórki + 8 nowych"), selektor tematu i ustawienie
limitu nowych. Na środku karta — front, przycisk *Pokaż odpowiedź*, po odkryciu rewers
i dwa przyciski oceny. Pasek postępu przez sesję. Na koniec podsumowanie z liczbą kart
zaplanowanych na jutro.

Klucze i18n w obu blokach (`pl` i `en`), jak wszędzie.

## Testy

- `app/flashcards.py` — czysty moduł: drabinka odstępów i składanie kolejki (due + nowe
  do limitu, filtr tematu). Tabelka wejście-wyjście, bez bazy i bez modelu, na wzór
  `app/streak.py` i `app/grouping.py`.
- warstwa bazy — powstanie karty przy pierwszym pokazaniu, `UNIQUE (source_kind, source_id)`,
  wyliczanie kart upartych z logu, oraz **regresja na ręcznej kaskadzie**: po `delete_error`
  i po `delete_group` nie zostaje ani karta, ani jej wiersze w `card_reviews` (test musi
  padać, jeśli ktoś usunie sprzątanie, licząc na klucze obce).
- endpointy — z podstawionym `llm_client`, w tym regresja na tym, że `GET /api/cards/session`
  **nie woła modelu**.
- smoke frontendu — przejście zakładki: kolejka, odkrycie, obie oceny, filtr tematu.

## Poza zakresem

- Import i eksport talii (Anki, CSV).
- Ręczne tworzenie kart spoza dziennika.
- Warianty kart odwrotnych (rozpoznawanie zamiast przypominania).
- Współczynnik łatwości i pełne SM-2 — drabinka wystarcza, dopóki nie okaże się, że nie.

## Ryzyka

| Ryzyko | Ograniczenie |
|---|---|
| Pierwsza sesja przytłacza liczbą kart | limit nowych dziennie, domyślnie 20, zmienialny |
| Karty z surowej pary są za słabe na przypomnienie | ulepszanie modelem na żądanie, karta po ulepszeniu jest darmowa na zawsze |
| Drabinka za sztywna dla części materiału | oznaczanie kart upartych i most do „Ćwicz błędy"; pełne SP dopiero, gdy okaże się potrzebne |
| Odejście od „nic nie wygasa" myli użytkownika | zasada obowiązuje dalej w dzienniku; README musi wyraźnie rozgraniczyć oba tryby |
