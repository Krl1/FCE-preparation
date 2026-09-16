# FCE Trener

**Polski** · [English](README.md)

Lokalna aplikacja w przeglądarce do przygotowania do egzaminu **Cambridge B2 First (FCE)**.
Generuje zadania (**Use of English** + **Writing**), sprawdza odpowiedzi — także te **wklejone
z zewnątrz** (z książki / od korepetytora) — i prowadzi **dziennik Twoich błędów**, który steruje
doborem kolejnych zadań, żebyś oduczał się powtarzanych pomyłek.

> ### ⚠️ Zanim uruchomisz — przeczytaj
>
> To narzędzie **osobiste, uruchamiane lokalnie**, nie usługa dla wielu osób. Wynika z tego kilka
> rzeczy, o których trzeba wiedzieć **przed** pierwszym startem:
>
> - **Aplikacja nie ma żadnego logowania.** Kto dosięgnie portu, ten ma pełny dostęp do dziennika
>   błędów i może zużywać Twoją subskrypcję Claude. Dlatego `compose.yaml` wystawia port
>   **tylko na `127.0.0.1`** — nie zmieniaj tego na `0.0.0.0` bez postawienia czegoś przed aplikacją.
> - **Wariant dockerowy montuje `~/.claude` z prawem zapisu**, czyli oddaje kontenerowi Twoje
>   **poświadczenia subskrypcji Claude** (musi, bo Claude Code odświeża wygasający token). Uruchamiaj
>   ten obraz tylko z kodu, któremu ufasz, i nie publikuj zbudowanego obrazu — powstaje z Twojego
>   katalogu domowego.
> - **Wywołania modelu liczą się do limitów Twojej subskrypcji** (Pro/Max), a nie do osobnego klucza API.
> - **Baza `data/fce.db` to Twoje dane osobiste** — dziennik błędów, prace, statystyki. Jest
>   w `.gitignore` i nigdy nie powinna trafić do repozytorium. To samo dotyczy materiałów do importu
>   (patrz *Import wcześniejszych błędów*).

## Jak to działa

- **Backend:** FastAPI (Python) + SQLite.
- **Model:** aplikacja wywołuje **Claude Code w trybie headless** (`claude -p … --output-format json`)
  i korzysta z Twojego **logowania z subskrypcji** (`~/.claude/.credentials.json`) — **bez klucza API**.
  Cała ta zależność jest w jednym pliku: `app/llm_client.py`.
- **Frontend:** statyczna strona (HTML/JS/CSS, bez frameworków) z pięcioma widokami: *Ćwicz zadania*, *Ćwicz błędy*,
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

## Import wcześniejszych błędów (opcjonalnie)

Jeśli masz już listę swoich pomyłek — z korepetycji, ocenionych prac albo własnych notatek —
możesz wgrać ją do dziennika na starcie, żeby aplikacja od pierwszego zadania celowała w Twoje
słabe punkty. Skrypt czyta trzy pliki z katalogu głównego:

| Plik | Format | Jak jest przetwarzany |
|---|---|---|
| `english_mistakes.tsv` | TSV: `date`, `wrong`, `correct`, `category`, `note`, `source` | deterministycznie, z mapowaniem `category` na taksonomię FCE (`CATEGORY_MAP` w `app/import_mistakes.py`) |
| `writing_mistakes.txt` | dowolny tekst | model wyławia pary „błędnie → poprawnie"; błędy dostają typ `writing` |
| `other_mistakes.txt` | dowolny tekst | jak wyżej, typ `imported` |

**Tych plików nie ma w repozytorium — i nie powinno być.** To materiał osobisty, więc są wpisane
do `.gitignore`. Wzorce formatu do skopiowania leżą w `examples/`:

```bash
cp examples/english_mistakes.tsv examples/writing_mistakes.txt examples/other_mistakes.txt .
# podmień zawartość na własną, potem:
python3 -m app.import_mistakes
```

Brakujący plik jest po prostu pomijany — możesz użyć jednego, dwóch albo żadnego. Import jest
**idempotentny**: każde źródło zapisuje błędy z etykietą `import:<nazwa_pliku>`, a ponowne
uruchomienie kasuje poprzednie wpisy z tego pliku i wstawia świeże. Powtórny import nie mnoży
duplikatów, mimo że ekstrakcja przez model nie jest deterministyczna.

Uwaga: pliki tekstowe idą przez model, więc ich import **kosztuje wywołania subskrypcji**
(TSV nie — jest czytany lokalnie).

## Użycie

- **Ćwicz zadania** — wybierz typ zadania (np. *open cloze*, *key word transformation*, *essay*), opcjonalnie
  temat (albo zostaw dobór automatyczny wg Twoich błędów), wygeneruj i rozwiąż. Aplikacja oceni odpowiedź
  i **zaproponuje** błędy do dziennika — zapisuje je dopiero po Twoim zatwierdzeniu (patrz *Cykl życia błędu*).
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
- **Ćwicz błędy** — tryb skupienia: aplikacja pokazuje jeden Twój błąd (dobierany losowo, ważony częstością
  Twoich słabych tematów) wraz z wyjaśnieniem i generuje do niego **zestaw 5 ćwiczeń**. Przyciski:
  *Ćwiczenie* (kolejny zestaw do tego samego błędu), *Inny błąd* (zmiana na nowy). Pod wyjaśnieniem
  masz też **Nie zgadzam się** (zastrzeżenie do wyjaśnienia) i **Usuń błąd** — obsługujesz błąd tam,
  gdzie go widzisz, bez szukania wpisu w dzienniku.
  U góry **dzienny cel** — ustalasz, ile błędów chcesz dziennie przerobić. Błąd zalicza się (+1)
  dopiero po **5 poprawnie rozwiązanych ćwiczeniach** do niego, liczonych **narastająco w obrębie
  dnia** — 3/5 w jednym podejściu i 2/5 w kolejnym też wystarczy. Postęp widać pod celem
  („Poprawne ćwiczenia do zaliczenia tego błędu: 3/5"). Próg zmienia `DRILL_CORRECT_TARGET`
  w `app/main.py`. Obok celu widać **serię** (🔥) — liczbę kolejnych dni z osiągniętym celem.

  **Opuszczony dzień można odrobić.** Przespanie dnia nie zrywa serii od razu: następny dzień musi
  pokryć cel za siebie i za każdy zaległy dzień — po jednym opuszczonym dniu to `2 × cel` różnych
  błędów, po dwóch `3 × cel`. Licznik nad paskiem pokazuje wtedy ten podniesiony cel, a pod serią
  pojawia się ostrzeżenie („⚠️ Zaległość z 2 dni — zalicz dziś 15 różnych błędów, inaczej seria
  przepada"). Zasady:
  - **trzy dni pod rząd bez ćwiczeń = seria pęka** nieodwracalnie (limit `GRACE_DAYS` w `app/streak.py`);
  - rozliczenie jest **wszystko albo nic** w obrębie dnia — 10 z wymaganych 15 nie zmniejsza długu
    na jutro, taki dzień liczy się po prostu jako zwykły zaliczony i zaczyna nową serię;
  - **odrobione dni nie wchodzą do licznika** — po dwóch przespanych dniach i spłacie seria rośnie
    o 1, bo 🔥 pokazuje dni, w których naprawdę ćwiczyłeś;
  - dzisiejszy dzień ma jak dotąd czas do końca doby — dopóki trwa, seria stoi (choć oznaczona
    jako zagrożona), a nie zeruje się o północy.

  Uwaga na skalę: przy celu 5 błędów dziennie oznacza to 25 poprawnych ćwiczeń — a przy dwudniowej
  zaległości 15 błędów, czyli 75 ćwiczeń w jednym dniu. Jeśli to za dużo, obniż cel w polu
  *Dzienny cel* (reguła serii liczy się zawsze od aktualnej wartości celu).

  Przełącznik **Pojedyncze błędy / Grupy** decyduje, co dostajesz do przerobienia. Tryb
  grupowy pozwala szybciej przejść przez wiele powiązanych pomyłek: zamiast jednego zdania
  model widzi regułę i kilka kontekstów, w których ją złamałeś. Do dziennego celu grupa
  liczy się **jak jeden błąd**, więc seria 🔥 pozostaje porównywalna między trybami.
- **Sprawdź z zewnątrz** — wklej zadanie z książki i swoją odpowiedź; aplikacja sprawdzi je i zaproponuje
  błędy do zatwierdzenia.
- **Moje błędy** — przegląd słabych punktów i pełny dziennik błędów. Przy każdym błędzie przycisk
  **Ćwicz ten błąd** przenosi do zakładki *Ćwicz błędy* z tym błędem i od razu generuje do niego ćwiczenie,
  a **Usuń błąd** (z potwierdzeniem w miejscu) wyrzuca go z dziennika.

  Przełącznik **Wpisy / Grupy** pokazuje ten sam dziennik w dwóch ujęciach. Grupa to jedna
  reguła wraz z kontekstami, w których ją złamałeś — **Scal nowe** przypisuje wpisy, które
  jeszcze nie mają grupy, a **Przegrupuj wszystko** liczy podział od zera (kasuje ręczne
  poprawki, więc pyta o potwierdzenie). Grupy mogą łączyć wpisy z różnych tematów, jeśli
  łamią tę samą regułę. **Pusta grupa zostaje** — gdy usuniesz z niej ostatni wpis,
  aplikacja zapyta, czy usunąć też samą grupę; reguła bez wpisów nadal daje się ćwiczyć.
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

### Cykl życia błędu: nic nie wchodzi i nic nie wychodzi samo

**Ocena nie zapisuje błędów do dziennika.** Zwraca je jako **propozycje** — przy każdej jest
przycisk **+ Dodaj do dziennika**, a nad listą pasek z przypomnieniem i (gdy propozycji jest
więcej) **+ Dodaj wszystkie**. Przy zadaniach wieloczęściowych przycisk stoi przy tej luce,
z której błąd pochodzi; propozycje niepowiązane z żadną luką lądują w osobnej sekcji, żeby nic
nie przepadło po cichu. Zapisywane jest natomiast **podejście** (do statystyk skuteczności) —
niezależnie od tego, co zatwierdzisz.

Dlaczego tak: łatwiej zatwierdzić trzy trafne wpisy, niż potem szukać w dzienniku dziesięciu
śmieci do usunięcia. Skutki uboczne, o których warto wiedzieć: *słabe punkty*, dobór tematów
i licznik „Błędy w dzienniku" widzą **tylko zatwierdzone** błędy, a temat propozycji jest
sprowadzany do taksonomii już przy ocenie — zatwierdzasz dokładnie to, co zostanie zapisane
(serwer normalizuje go ponownie przy zapisie, bo dane z przeglądarki nie są wiarygodne).

Zastrzeżenie (**Nie zgadzam się**) dotyczy wpisów, które **są** w dzienniku — propozycji nie
trzeba podważać, wystarczy jej nie zatwierdzać.

Błąd raz zapisany **zostaje w dzienniku na zawsze** — nie ma automatycznego wygaszania po
n-krotnym przerobieniu. Tabela `reviews` notuje tylko, że danego dnia zaliczyłeś błąd do celu,
i **nie wpływa na dobór**: `_choose_focus_error` waży wyłącznie liczbą i świeżością wpisów
w temacie. Praktyczny skutek: błąd opanowany dziesięć razy może w „Ćwicz błędy" wracać tak samo
często jak nowy.

Dlatego dziennik porządkujesz sam, **ręcznie**:

- w zakładce *Moje błędy* — przycisk **Usuń błąd** przy każdym wpisie,
- w zakładce *Ćwicz błędy* — ten sam przycisk **przy błędzie, który właśnie ćwiczysz**, żeby nie szukać
  go potem w setkach innych wpisów.

Oba wymagają potwierdzenia (**Na pewno? / Anuluj**), świadomie bez okienka przeglądarki.
Usunięcie **nie cofa dziś zdobytego celu ani serii** — powtórki zostają w `reviews`, bo praca,
którą naprawdę wykonałeś, powinna zostać policzona. Zmienia się natomiast lista *słabych punktów*,
bo liczona jest z dziennika na bieżąco.

### Zastrzeżenie do wyjaśnienia („Nie zgadzam się")

Model czasem myli się w samym wyjaśnieniu — np. powołuje się na słowo, którego w zadaniu nie było.
Dlatego przy każdym wyjaśnieniu (komentarz do luki, omówienie wariantu, wpis w dzienniku błędów)
jest link **Nie zgadzam się**. Rozwija pole na komentarz — napisz, co się nie zgadza —
i wysyła zastrzeżenie do ponownej weryfikacji wraz z **dokładną treścią zadania i Twoimi
odpowiedziami**, żeby model mógł sprawdzić, czy nie zmyślił cytatu.

Weryfikacja rozstrzyga **dwie niezależne rzeczy**, bo mieszanie ich było źródłem błędnych
werdyktów:

1. **Czy wyjaśnienie było błędne** (`verdict`: `upheld` / `rejected`) — zmyślony cytat wystarcza,
   żeby uznać zastrzeżenie, nawet jeśli sama reguła gramatyczna była prawdziwa.
2. **Czy Twoja odpowiedź była jednak dopuszczalna** (`student_was_right`) — to osobna sprawa.
   Najczęstszy przypadek: wyjaśnienie było wadliwe, ale odpowiedź nadal błędna.

Co się dzieje dalej:

- **Zastrzeżenie uznane** → dostajesz **poprawione wyjaśnienie** (od razu, bez zmian w danych).
- **Dodatkowo model przyzna, że Twoja odpowiedź była dopuszczalna** → pojawia się przycisk
  **Popraw ocenę**. Dopiero jego kliknięcie usuwa błędny wpis z dziennika i przelicza wynik
  podejścia. Nic nie zmienia się bez Twojego potwierdzenia, a każde zastrzeżenie jest zapisane
  w tabeli `disputes` (jednorazowe zastosowanie).
- **Zastrzeżenie odrzucone** → wyjaśnienie zostaje, z uzasadnieniem dlaczego. Prompt jawnie
  zakazuje ustępowania z uprzejmości — inaczej dałoby się wygadać z każdego prawdziwego błędu
  i dziennik przestałby być wiarygodny.

## Uruchomienie w Dockerze (z autostartem po włączeniu laptopa)

Jednorazowo:

```bash
docker compose up -d --build
```

Aplikacja jest dostępna pod **http://localhost:8008**.

### Jak działa autostart

Kontener ma politykę `restart: unless-stopped`, a demon Dockera jest włączony w systemd
(`systemctl is-enabled docker` → `enabled`). Po włączeniu laptopa demon startuje i wznawia
kontener, jeśli działał w momencie wyłączania komputera. Dwa zachowania warte zapamiętania:

- `docker compose stop` (albo `docker kill`) to **zatrzymanie na Twoje życzenie** — po takim
  zatrzymaniu kontener nie wróci sam, także po restarcie systemu. Wznawiasz go przez
  `docker compose start`.
- Jeśli wolisz, żeby wracał *zawsze*, nawet po ręcznym zatrzymaniu, zmień politykę
  w `compose.yaml` na `restart: always`.

### Co jest montowane i dlaczego

Obraz **nie zawiera** Claude Code — binarka i konfiguracja są montowane z hosta, więc
kontener korzysta z Twojego logowania z subskrypcji i nie potrzebuje klucza API:

| Montowanie | Tryb | Po co |
|---|---|---|
| `./data` | zapis | baza SQLite (dziennik błędów, postępy, statystyki) zostaje na hoście |
| `~/.local/bin/claude` + `~/.local/share/claude` | odczyt | natywna binarka Claude Code (aktualizacja na hoście działa po restarcie kontenera) |
| `~/.claude` | **zapis** | poświadczenia; Claude Code odświeża wygasający token, więc montowanie tylko do odczytu zepsułoby autoryzację po jego wygaśnięciu |

#### Dlaczego ścieżki w kontenerze są takie same jak na hoście

`~/.local/bin/claude` to **absolutny** symlink (→ `/home/<user>/.local/share/claude/versions/X.Y.Z`).
Gdyby kontener montował te katalogi pod inną ścieżką, symlink wskazywałby w pustkę i `claude` nie
uruchomiłby się. Dlatego katalog domowy w obrazie jest równy `${HOME}` hosta — `compose.yaml`
podstawia go jako argument budowania `APP_HOME`. W kodzie nie ma żadnej zaszytej nazwy użytkownika.

Z tego samego powodu kontener działa jako UID/GID **1000**: musi odczytać
`~/.claude/.credentials.json` (prawa 0600) i zapisać bazę w `./data`. Jeśli Twój użytkownik ma
inny UID (sprawdź: `id -u`), zbuduj obraz tak:

```bash
export APP_UID=$(id -u) APP_GID=$(id -g)
docker compose up -d --build
```

### Codzienne polecenia

```bash
docker compose logs -f          # podgląd logów
docker compose ps               # stan i zdrowie kontenera
docker compose up -d --build    # po zmianie kodu: przebuduj i wznów
docker compose stop             # zatrzymaj (nie wróci sam)
docker compose start            # wznów
docker compose down             # usuń kontener (dane w ./data zostają)
```

### O czym warto wiedzieć

- **Nie uruchamiaj jednocześnie kontenera i `uvicorn` na hoście** — oba pisałyby do tej samej
  bazy SQLite z dwóch procesów, co grozi błędami „database is locked".
- Port jest wystawiony **tylko na `127.0.0.1`**. Aplikacja nie ma logowania i korzysta z Twojej
  subskrypcji, więc nie powinna być widoczna dla innych urządzeń w sieci.
- Kontener zapisuje też do `~/.claude` (odświeżony token, historia wywołań) — dzieli ten katalog
  z Twoim interaktywnym Claude Code. Wywołania z aplikacji liczą się do limitów tej samej subskrypcji.
- Sprawdzenie po najbliższym restarcie laptopa: `docker compose ps` powinno pokazać
  `Up ... (healthy)`.

## Testy

```bash
python3 -m pytest -q
```

Pokrycie: warstwa bazy (w tym regresja współbieżności i migracji kolejki), logika doboru
zadań (`srs`), reguła serii wraz z odrabianiem zaległości (`streak` — moduł jest czysty, więc
testy budują historię dni bez bazy), parsowanie odpowiedzi modelu i deterministyczna ocena luk,
endpointy HTTP (FastAPI TestClient, bez wywoływania modelu) oraz import wcześniejszych błędów.

Dodatkowo test przejścia frontendu bez przeglądarki (atrapa DOM + `fetch`), który przechodzi
wszystkie zakładki i sprawdza, że żadna ścieżka nie wywala się na wyjątku:

```bash
node tests/smoke_frontend.js
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

## Licencja

[MIT](LICENSE) — rób z tym, co chcesz, zachowaj tylko notę o prawach autorskich. Bez gwarancji.

Aplikacja jest narzędziem do nauki, nie oficjalnym produktem Cambridge Assessment English.
„B2 First" i „FCE" to znaki towarowe ich właścicieli i użyto ich tu wyłącznie opisowo.
