<p align="center">
  <img src="web/logo.svg" alt="DariaTech Data Cleanup" width="380">
</p>

# DariaTech Data Cleanup

Ein lokales, kundenfähiges Tool zum **Finden, sicheren Bereinigen und sauberen Zusammenführen** von mehrfach
vorhandenen Dateien, Bildern und Videos. Läuft komplett lokal, lädt nichts in eine Cloud und arbeitet
standardmäßig mit Quarantäne als Sicherheitsnetz.

Ein Produkt von **DariaTech IT-Systemhaus** ([dariatech.de](https://www.dariatech.de)).

## Highlights

- **Mehrere Quellordner gleichzeitig** scannen (ordnerübergreifender Vergleich)
- **Sauber zusammenführen in einen neuen Zielordner** – jede Datei landet genau einmal, ohne Duplikate
- **Live-Fortschritt** mit Phasen-Anzeige und **Abbrechen** auch bei sehr großen Beständen
- Exakte Duplikate per **SHA-256**, ähnliche Bilder per **Bild-Fingerprint** (dHash)
- **Quarantäne mit Undo** – versehentlich verschobene Dateien per Klick wiederherstellen
- **Scan-Profile pro Kunde** speichern und laden
- Bild-Vorschau, JSON-/CSV-Berichte, Speicherplatz-Anzeige am Ziel
- Bereinigung per Quarantäne oder Windows-Papierkorb
- Hintergrund-Jobs mit SQLite-Verlauf, versionierte REST-API (`/api/v1`)
- Windows-EXE per GitHub Actions baubar

## Die Kernfunktion: Sauber zusammenführen

Genau dafür gedacht, mehrere gewachsene Ordner (Fotoarchive, alte Backups, Kundenordner) zu einem sauberen,
duplikatfreien Bestand zusammenzuführen:

1. Mehrere Quellordner hinzufügen.
2. Tab **„Sauber zusammenführen"** wählen.
3. Zielordner angeben (ein **neuer** Ordner, nicht innerhalb der Quellen).
4. Struktur wählen – der Anwender entscheidet:
   - **Pro Quelle getrennt** – Zielordner/`<Quellname>`/… (Standard, keine Konflikte)
   - **Struktur exakt spiegeln** – relative Pfade werden gespiegelt
   - **Alles flach** – alle Dateien direkt in den Zielordner
5. **Kopieren** (sicher, Originale bleiben) oder **Verschieben** wählen.
6. **Probelauf** starten – zeigt ohne Risiko, was passieren würde.
7. **Jetzt zusammenführen** – fertig ist der saubere Ordner.

Das Tool dedupliziert exakt (SHA-256) und optional auch ähnliche Bilder (es behält dann das beste Bild laut
Behalte-Regel, z. B. höchste Auflösung).

## Sicherheit

- Endgültiges Löschen ist in der API bewusst gesperrt – nur Quarantäne oder Papierkorb.
- Geschützte Systemordner (Laufwerkswurzeln, Windows, Programme, Home) sind gesperrt.
- Der Zielordner darf nicht innerhalb einer Quelle liegen (und umgekehrt).
- Beim Zusammenführen ist **Kopieren** der Standard – Originale bleiben unangetastet.
- Quarantäne-Verschiebungen werden protokolliert und sind über **Undo** wiederherstellbar.

Quarantäne-Ordner pro Scan-Root:

```text
.quarantine-duplicates
```

## Empfohlener Kunden-Workflow

1. Quellordner über **„+ Ordner auswählen"** hinzufügen (mehrfach klickbar).
2. Optional ein **Profil** speichern, um die Einstellungen wiederzuverwenden.
3. Kategorien, Behalte-Regel und Erkennung einstellen.
4. Entweder **bereinigen** (Duplikate in Quarantäne/Papierkorb) **oder zusammenführen** (sauberer Zielordner).
5. Bei Bereinigung: Bericht als CSV/JSON exportieren, Empfohlene auswählen, verschieben.
6. Bei Bedarf über **Quarantäne & Wiederherstellen** rückgängig machen.

## Start unter Windows ohne EXE-Build

1. Repository herunterladen oder klonen.
2. `start-windows.bat` doppelt anklicken.
3. Im Browser öffnen: `http://127.0.0.1:8787`

## Start unter Linux oder macOS

```bash
chmod +x start-linux-mac.sh
./start-linux-mac.sh
```

Danach `http://127.0.0.1:8787` öffnen.

## Windows: installieren oder portabel starten

Die Action `.github/workflows/build-windows.yml` läuft bei Push auf `main` und kann manuell gestartet werden
(**Actions → Build Windows App → Run workflow**). Sie baut die EXE, testet automatisch, dass sie startet, und
erzeugt zwei Artefakte:

- **`DariaTech-Data-Cleanup-Setup`** – ein richtiger Installer (`...-Setup.exe`). Doppelklick installiert die
  Software nach *Programme*, legt **Startmenü- und Desktop-Verknüpfung** an und richtet eine **Deinstallation** ein.
- **`DariaTech-Data-Cleanup-Windows`** – die portable EXE im ZIP (ohne Installation startbar).

Die App startet lokal einen kleinen Webserver auf `http://127.0.0.1:8787` und öffnet den Browser automatisch.
Das Programmfenster (Konsole) zeigt den Status und bleibt bei einem Fehler offen.

### Herausgeber / SmartScreen

Die EXE trägt bereits Hersteller-Metadaten (*DariaTech IT-Systemhaus*, sichtbar unter Eigenschaften → Details).
Damit Windows beim Start einen **verifizierten Herausgeber** statt „Unbekannt" anzeigt und die SmartScreen-Warnung
entfällt, ist eine **Code-Signatur mit einem Zertifikat** nötig. Der Build signiert automatisch, sobald diese
Repository-Secrets gesetzt sind:

- `WINDOWS_CERT_PFX_BASE64` – das Code-Signing-Zertifikat (`.pfx`) als Base64
- `WINDOWS_CERT_PASSWORD` – das Passwort des Zertifikats

Ohne Zertifikat ist die App voll funktionsfähig; Windows zeigt lediglich den Standard-Hinweis für unsignierte
Programme.

## Entwicklung & Tests

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
ruff check app tests
pytest
```

## REST-API (Kurzüberblick)

| Endpoint | Zweck |
| --- | --- |
| `POST /api/v1/scans` | Hintergrund-Scan starten |
| `POST /api/v1/consolidations` | Zusammenführung starten (mit `dry_run` für Probelauf) |
| `GET /api/v1/jobs/{id}` | Status + Live-Fortschritt |
| `GET /api/v1/jobs/{id}/result` | Ergebnis abrufen |
| `POST /api/v1/jobs/{id}/cancel` | Laufenden Job abbrechen |
| `GET /api/v1/jobs/{id}/report?format=csv` | Bericht herunterladen |
| `GET/POST/DELETE /api/v1/profiles` | Scan-Profile verwalten |
| `POST /api/quarantine/list` · `POST /api/quarantine/restore` | Quarantäne anzeigen / Undo |

## Hinweis zu ähnlichen Bildern

Die Ähnlichkeitssuche nutzt einen Difference-Hash und erkennt häufig verkleinerte, komprimierte oder leicht
geänderte Versionen eines Bildes. Sie ist als Vorschlag gedacht und sollte vor der Bereinigung kontrolliert werden.
