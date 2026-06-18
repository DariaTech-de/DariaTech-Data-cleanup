# Enterprise Plan

Stand der Härtung und Funktionsreife für größere Kunden-Workloads.

## Umgesetzt

- **Sauberes Zusammenführen** mehrerer Quellordner in einen neuen Zielordner (Kopieren/Verschieben,
  Struktur wählbar, Konfliktstrategie, Probelauf)
- Hintergrund-Jobs für Scan **und** Zusammenführung mit Live-Fortschritt und Abbrechen
- SQLite-Verlauf für Jobs und gespeicherte Profile
- Versionierte REST-API (`/api/v1`) inkl. Job-Steuerung und Report-Download
- Quarantäne mit Protokoll und **Undo/Restore**
- Thread-sicherer Preview-Wächter (sichere Bildvorschau ohne offenen Dateizugriff)
- Robuste Validierung (geschützte Ordner, Ziel-/Quell-Überschneidung, Größen-/Typfilter)
- Test- und Lint-Grundlage (pytest, ruff) mit CI

## Design-Prinzipien

- Local-first: keine Cloud-Pflicht, alle Daten bleiben auf dem Gerät
- Review vor Veränderung: Probelauf, Quarantäne, Undo
- Nicht-destruktive Voreinstellungen (Kopieren, Quarantäne)
- Vorhersagbares Verhalten auf großen Ordnerbäumen (gedrosselte Fortschritts-Updates, Größen-Buckets)
- Nachvollziehbarkeit für Kundenarbeit (Berichte, Manifest, Job-Verlauf)

## Nächste sinnvolle Schritte

- Echter Windows-Installer mit Startmenü-Eintrag und EXE-Signatur (SmartScreen)
- Video-Fingerprint über einzelne Frames
- Musik-Duplikate über Audio-Fingerprinting und Tags
- Mehrsprachige Oberfläche (DE/EN)
