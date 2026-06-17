# Duplicat-Clearner

Ein lokales Tool zum Finden und sicheren Entfernen von mehrfach vorhandenen Dateien, Bildern und Videos.

## Was macht das Tool?

Duplicat-Clearner scannt einen Ordner und findet echte Duplikate. Die Erkennung basiert nicht nur auf Dateinamen, sondern auf einem SHA-256-Hash. Dadurch werden nur Dateien als Duplikat markiert, wenn der Inhalt wirklich identisch ist.

## Funktionen

- Dateien, Bilder und Videos scannen
- echte Duplikate per SHA-256 erkennen
- älteste Datei wird automatisch als Original vorgeschlagen
- Duplikate mit einem Klick auswählen
- ausgewählte Duplikate sicher in Quarantäne verschieben
- keine Cloud, läuft lokal auf deinem PC

## Sicherheit

Das Tool löscht Dateien nicht sofort endgültig. Ausgewählte Duplikate werden zuerst in den Ordner `.quarantine-duplicates` innerhalb des gescannten Ordners verschoben.

Beispiel:

```text
C:\Users\Name\Pictures\.quarantine-duplicates
```

So kannst du die Dateien kontrollieren und bei Bedarf wiederherstellen.

## Start unter Windows

1. Repository herunterladen oder klonen.
2. `start-windows.bat` doppelt anklicken.
3. Im Browser öffnen:

```text
http://127.0.0.1:8787
```

## Start unter Linux oder macOS

```bash
chmod +x start-linux-mac.sh
./start-linux-mac.sh
```

Danach öffnen:

```text
http://127.0.0.1:8787
```

## Ordner scannen

Im Feld `Ordnerpfad` den gewünschten Pfad eintragen, zum Beispiel:

```text
C:\Users\Ahmad\Pictures
```

oder:

```text
/home/ahmad/Bilder
```

Dann auf **Scannen** klicken.

## Hinweis

Bei sehr großen Video-Ordnern kann der Scan länger dauern, weil große Dateien vollständig gelesen werden müssen, damit der Hash sicher berechnet werden kann.
