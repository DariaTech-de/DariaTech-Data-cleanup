# Tests

Automatisierte Tests decken Scanner-Logik, Zusammenführung, Quarantäne/Undo, Hintergrund-Jobs und die API ab.

## Ausführen

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
ruff check app tests
pytest
```

## Testdateien

- `tests/test_scanner.py` – exakte Duplikate, Größenfilter
- `tests/test_consolidate.py` – Zusammenführung: ordnerübergreifende Deduplizierung, Struktur-Modi,
  Probelauf, Verschieben, Ziel-Validierung, ähnliche Bilder
- `tests/test_quarantine.py` – Quarantäne + Wiederherstellung, Fortschritts-Callbacks, Abbruch
- `tests/test_job_runner.py` – Hintergrund-Scan und -Zusammenführung inkl. Fehlerfall
- `tests/test_api.py` / `tests/test_api_v1.py` – HTTP-Endpunkte, Profile, Sicherheits-Sperren
