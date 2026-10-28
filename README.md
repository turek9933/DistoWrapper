# distocad

Konwersja plików DISTO Plan (`.cmi`, `.xml`) do DXF. W repozytorium są trzy części:

- `distocad` — rdzeń konwersji,
- CLI `distocad` — praca wsadowa w terminalu,
- `web` — minimalna aplikacja Django do wysyłania plików przez przeglądarkę.

DXF jest zapisywany w wersji **R2010**. Domyślnie wszystkie obiekty są na warstwie `0` z kolorem `BYLAYER`; opcja warstw jest wyłączona.

## Co trafia na rysunek

### Wersja prostopadła

- Rysowane są wyłącznie obrysy pomieszczeń (zamknięte wielokąty w szkicu).
- Ściany dostają kierunki poziome/pionowe i zmierzone długości.
- Pomiary są czytane jako `Decimal`, normalizowane do 0,1 mm i zaokrąglane do pełnego milimetra metodą **half-up** (np. `6.0885 m` → `6089 mm`).
- **Polilinia nigdy nie jest domykana automatycznie.** Zawsze pozostaje otwarta, nawet gdy szczelina wynosi 0 mm.
- Szczelina jest zawsze przy wierzchołku o największej sumie dwóch sąsiednich boków.
- Szczelina większa niż próg (domyślnie 15 mm) dostaje tekst `UWAGA, szczelina 24.23 mm`. Mniejsza szczelina nie dostaje tekstu, ale obrys nadal jest otwarty.
- Pole powierzchni jest liczone z obrysu i zapisywane jako `CHECK37.38 m2` (dwa miejsca po przecinku, spacja przed `m2`).
- Domyślnie rysowane są dwa okręgi przy szczelinie: środek w połowie sąsiednich ścian, promień równy połowie ich długości. Można je wyłączyć.
- Etykiety długości ścian są domyślnie wyłączone; włącza je opcja `--labels` w CLI lub checkbox w webie.
- Tytuł jest umieszczany w lewym górnym narożniku obszaru rysunku, 500 mm powyżej, o wysokości 100 mm.
- Wysokość wszystkich tekstów wynosi **100 mm**.

### Wersja oryginalna

- Rysowane są wszystkie linie ze szkicu: pomieszczenia, miedzymiary, grubości i inne linie otwarte.
- Kierunki i kąty pochodzą ze szkicu, a długości są przeliczone na milimetry.
- Współrzędne X/Y są brane wprost ze szkicu; oś Y nie jest lustrzana.
- Etykiety długości są zawsze przy zmierzonych odcinkach. Nie ma etykiet pól powierzchni ani tytułu.
- Polilinia pomieszczenia jest otwarta w tym samym wierzchołku co w wersji prostopadłej.

### Pomieszczenia bez pełnych pomiarów

Nie ma zgadywania ani uzupełniania brakujących ścian w wersji prostopadłej. Pomieszczenie z brakującym pomiarem ma status `partial`:

- rysowane są tylko ciągłe, zmierzone odcinki, jako osobne otwarte polilinie,
- brakujące ściany są pomijane,
- nie ma pola powierzchni, ostrzeżenia o szczelinie ani okręgów.

Jeśli brakuje wszystkich ścian, pomieszczenie ma status `skipped` i nie trafia do wersji prostopadłej. Wersja oryginalna nadal pokazuje wszystkie linie.

### Nazwy i wiele plików

- Dla jednego pliku można podać nazwę ręczną (`--name` w CLI, pole w web).
- Bez nazwy ręcznej używana jest nazwa pliku.
- Gdy plik wejściowy nazywa się `DistoFile.xml`, używana jest nazwa z `<Documents><Document><Name>`.
- Przy `--version both` pliki nazywają się `<nazwa>_prostopadle.dxf` i `<nazwa>_oryginal.dxf`.
- Przy jednej wersji plik nazywa się `<nazwa>.dxf`.
- Kolizje nazw przy wielu plikach dostają sufiks `_2`, `_3`, itd.

## Instalacja

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## Konfiguracja

Skopiuj przykładową konfigurację:

```bash
cp .env.example .env
```

Plik `.env` jest ignorowany przez git. Zmienne bez wartości domyślnej trzeba ustawić w produkcji.

| Zmienna | Domyślnie | Opis |
|---|---|---|
| `DJANGO_DEBUG` | `0` | `1` włącza tryb developerski |
| `DJANGO_SECRET_KEY` | brak | wymagane poza `DEBUG` |
| `DJANGO_ALLOWED_HOSTS` | puste | wymagane w produkcji; lista po przecinku |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | puste | wymagane w produkcji; lista po przecinku |
| `DJANGO_HSTS_SECONDS` | `0` | HSTS w produkcji |
| `DATA_UPLOAD_MAX_NUMBER_FILES` | `1000` | limit plików na żądanie |
| `FILE_UPLOAD_MAX_MEMORY_SIZE_MB` | `5` | limit bufora uploadu |
| `DISTO_PASSWORD` | puste | hasło aplikacji; puste wyłącza |
| `DISTO_MAX_FILES` | `40` | limit plików; `0` wyłącza |
| `DISTO_MAX_FILE_MB` | `25` | limit pojedynczego pliku; `0` wyłącza |
| `DISTO_MAX_TOTAL_MB` | `150` | limit łączny; `0` wyłącza |
| `DISTO_EPHEMERAL_DIR` | temp `distoweb`; Docker `/data` | katalog wyników |
| `DISTO_EPHEMERAL_TTL` | `900` | czas życia wyniku w sekundach |
| `DISTO_RATE_LIMIT` | `30` | limit żądań; `0` wyłącza |
| `DISTO_RATE_WINDOW` | `600` | okno limitu w sekundach |
| `DISTO_CLIENT_IP_HEADER` | `REMOTE_ADDR`; compose `HTTP_CF_CONNECTING_IP` | nagłówek IP klienta |
| `CLOUDFLARE_TUNNEL_TOKEN` | brak | wymagane dla profilu `tunnel` |
| `UID` / `GID` | `1000` | użytkownik dla profilu `cli` |

## GitHub

Instrukcja publikacji: [`GITHUB.md`](GITHUB.md). Polecenia wykonuj w katalogu `distocad-project`.

## CLI

```bash
# jeden plik, obie wersje, domyślny układ jak w szkicu
python -m distocad mieszkanie.cmi -o wyniki

# katalog z plikami, własna nazwa tylko dla jednego pliku
python -m distocad "Plan 2026-10-15 092826.cmi" -o wyniki --name A.2.2.01

# wiele plików, ZIP z rysunkami i raportem
python -m distocad dane/ -o wyniki --version both --zip

# wersja prostopadła, warstwy, etykiety ścian, układ w rzędzie (okręgi są domyślnie)
python -m distocad dane/ -o wyniki --version orthogonal --layers --labels --layout row
```

Wyniki trafiają do `--outdir` (domyślnie `wyniki`). Oprócz DXF zapisywany jest `report.json` z polami powierzchni, szczelinami, brakującymi ścianami, ostrzeżeniami i listą wyjść.

Najważniejsze opcje:

- `--version orthogonal|original|both` (domyślnie `both`),
- `--layout sketch|row` (domyślnie `sketch`),
- `--gap-threshold 15` — próg szczeliny i ostrzeżenia,
- `--gap-circles` / `--no-gap-circles` — okręgi przy szczelinach w wersji prostopadłej (domyślnie włączone),
- `--labels` — etykiety długości ścian w wersji prostopadłej (domyślnie wyłączone; wersja oryginalna zawsze ma etykiety),
- `--layers` — warstwy i kolory zamiast warstwy `0`,
- `--free-limit 25` — odchyłka, od której ściana jest uznawana za nieortogonalną,
- `--spacing 1000` — odstęp w układzie `row`,
- `--no-title`, `--name`, `--zip`.

## Aplikacja Django

```bash
export DJANGO_DEBUG=1
python web/manage.py runserver
```

Aplikacja działa pod `/`. Wynik jest dostępny domyślnie przez 15 minut (`DISTO_EPHEMERAL_TTL`) i tylko w sesji, która go utworzyła.

- Jeden plik: na stronie wyniku są bezpośrednie linki do każdego DXF. Przy `both` jest też przycisk `Pobierz oba`, który pobiera ZIP z wersją prostopadłą i oryginalną.
- Wiele plików: jeden ZIP z rysunkami i `report.json`.
- Zawsze dostępny jest link do `report.json`.
- Obsługiwany jest drag & drop plików `.cmi` i `.xml`.
- Opcjonalne hasło ustawia `DISTO_PASSWORD`. Puste oznacza brak hasła.

Limity można wyłączyć, ustawiając `0`:

- `DISTO_MAX_FILES` (domyślnie 40),
- `DISTO_MAX_FILE_MB` (domyślnie 25),
- `DISTO_MAX_TOTAL_MB` (domyślnie 150),
- `DISTO_RATE_LIMIT` (domyślnie 30; `0` wyłącza limit).

Dodatkowo: `DISTO_RATE_WINDOW` (sekundy), `DISTO_EPHEMERAL_TTL` (sekundy), `DISTO_CLIENT_IP_HEADER`, `DATA_UPLOAD_MAX_NUMBER_FILES`, `FILE_UPLOAD_MAX_MEMORY_SIZE_MB`.

Testy:

```bash
python -m unittest discover -s tests -t .
cd web && DJANGO_DEBUG=1 python manage.py test converter
```

## Docker i Cloudflare Tunnel

Produkcja:

```bash
cp .env.example .env
# uzupełnij DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS, DJANGO_CSRF_TRUSTED_ORIGINS
# oraz CLOUDFLARE_TUNNEL_TOKEN; pozostałe zmienne mają domyślne wartości
docker compose --profile tunnel up -d --build
```

Sekret można wygenerować poleceniem:

```bash
python -c 'import secrets; print(secrets.token_urlsafe(50))'
```

Docker Compose wczytuje `.env` automatycznie. Plik `.env` jest ignorowany przez git.

Tunel Cloudflare ma kierować na `http://distoweb:8000` (ta sama sieć Dockera). Aplikacja nie wystawia portu na hosta; dostęp jest przez tunel. Endpoint `/healthz/` służy do sprawdzania stanu i jest używany przez `HEALTHCHECK`.

Praca CLI w Dockerze:

```bash
mkdir -p dane wyniki
# wrzuć pliki .cmi/.xml do dane/
docker compose --profile cli run --rm cli
```

Usługa `cli` montuje `./dane` tylko do odczytu i `./wyniki` do zapisu. Domyślnie uruchamia `--version both`; własne argumenty można podać po nazwie usługi, np.:

```bash
docker compose --profile cli run --rm cli /dane -o /wyniki --version orthogonal --layers
```

Nic nie jest zapisywane trwale w aplikacji web: wyniki i raport trafiają do `/data` (tmpfs) i są usuwane po `DISTO_EPHEMERAL_TTL`. Dostęp do wyniku ma tylko sesja, która go utworzyła (podpisane ciasteczko, bez bazy danych).

## Ograniczenia

- Wejściem jest DISTO Plan `.cmi` lub `.xml`; wyjściem jest DXF. Konwersja do DWG nie jest częścią projektu.
- Nie ma OCR nazw ze zdjęć, podglądu rysunku, trwałej historii ani porównywania pięter.
- Pomieszczeniem jest zamknięty wielokąt w szkicu. Linie otwarte trafiają wyłącznie do wersji oryginalnej.
- Wersja prostopadła nie domyka szczelin i nie uzupełnia brakujących ścian.
- Wysokość tekstu jest stała (100 mm), a domyślnie wszystkie obiekty są na warstwie `0`.
