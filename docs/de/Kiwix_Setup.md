# Offline-Wikipedia mit Kiwix: Installieren & Aktualisieren

Im Offline-Modus (`wiki.mode: "offline"`) beantwortet das Orchestra Wissensfragen mit
Ausschnitten aus einer **lokalen Wikipedia-Kopie** — ganz ohne Internetzugriff zur
Laufzeit. Dafür braucht es zwei Dinge:

1. **kiwix-serve** — ein kleiner lokaler Webserver, der ZIM-Archive ausliefert
2. ein **ZIM-Archiv** — die eigentliche Wikipedia als eine einzige Datei

Diese Anleitung beschreibt Erstinstallation und Update. Referenz-Setup ist Windows
mit dem Ordner `C:\wikipedia-de-offline\`; unter Linux/macOS funktioniert alles
analog mit angepassten Pfaden.

---

## Voraussetzungen & Plattenplatz

| Was | Größe (ca.) |
|---|---|
| kiwix-tools (kiwix-serve u. a.) | < 20 MB |
| `wikipedia_de_all_nopic` (deutsche Wikipedia ohne Bilder) | **14–16 GB** |
| Während eines Updates liegen alte + neue ZIM parallel | **~30 GB frei einplanen** |

> 💡 Die `nopic`-Variante reicht für das Orchestra völlig: Es werden nur Text-Snippets
> in den Prompt injiziert, Bilder würden nur Platz kosten.

---

## Erstinstallation

### 1. kiwix-tools herunterladen

Von der offiziellen Download-Seite: <https://download.kiwix.org/release/kiwix-tools/>
(für Windows das `..._win-i686.zip` bzw. aktuelle x64-Paket). Entpacken nach:

```
C:\wikipedia-de-offline\
├── kiwix-serve.exe
├── kiwix-manage.exe
└── kiwix-search.exe
```

### 2. ZIM-Archiv herunterladen

Alle Wikipedia-Dumps liegen unter: <https://download.kiwix.org/zim/wikipedia/>

Gesucht ist die jeweils **neueste** Datei nach dem Muster
`wikipedia_de_all_nopic_JJJJ-MM.zim`. Download z. B. per Browser oder:

```powershell
curl.exe -L -o "C:\wikipedia-de-offline\wikipedia_de_all_nopic_2026-01.zim" `
  "https://download.kiwix.org/zim/wikipedia/wikipedia_de_all_nopic_2026-01.zim"
```

⏳ Bei 14 GB je nach Anbindung 30 Minuten bis einige Stunden.

### 3. `config.yaml` anpassen

```yaml
wiki:
  mode: offline
  offline:
    host: "127.0.0.1"
    kiwix_port: 8080
    zim_prefix: "wikipedia_de_all_nopic_2026-01"   # Dateiname ohne .zim
    autostart: true                                 # kiwix-serve automatisch starten
    kiwix_exe: "C:/wikipedia-de-offline/kiwix-serve.exe"
    zim_path: "C:\\wikipedia-de-offline\\wikipedia_de_all_nopic_2026-01.zim"
```

Wichtig: `zim_prefix` muss exakt zum Dateinamen (ohne `.zim`) passen — daraus liest
das Orchestra auch den **Datenstand** für den Drei-Zeitstempel-Block im System-Prompt
(die Personas wissen dann, wie aktuell ihr Wikipedia-Wissen ist).

### 4. Verifizieren

```bash
python src/launch.py --doctor
```

Der Setup-Doktor prüft u. a., ob kiwix-serve erreichbar ist. Alternativ im Browser:
`http://127.0.0.1:8080/` zeigt die Kiwix-Oberfläche mit dem geladenen Archiv.

Danach im Orchestra eine Wissensfrage stellen (z. B. via Ask-All): Der 🕵️-Hinweis
zeigt an, wenn ein Wikipedia-Snippet in den Prompt injiziert wurde.

---

## Update auf einen neueren Dump

Die Dumps werden mehrmals pro Jahr neu erzeugt — ein veralteter Dump bedeutet
veraltetes Wissen (und wird den Personas über den Zeitstempel-Block auch so mitgeteilt).

1. **Neueste Version ermitteln:** <https://download.kiwix.org/zim/wikipedia/> nach
   `wikipedia_de_all_nopic_...` durchsuchen.
2. **Plattenplatz prüfen** (altes + neues Archiv liegen kurzzeitig parallel).
3. **Herunterladen** (wie oben; am besten erst in eine `.part`-Datei und nach
   erfolgreichem Download umbenennen).
4. **`config.yaml` anpassen:** `zim_prefix` und `zim_path` auf den neuen Dateinamen.
5. **Laufenden kiwix-serve beenden** (er hält das alte ZIM offen) und das Orchestra
   neu starten — bei `autostart: true` startet kiwix-serve automatisch mit dem neuen
   Archiv.
6. **Verifizieren:** `python src/launch.py --doctor` → Kiwix-Check grün.
7. **Altes ZIM löschen**, sobald alles läuft.

---

## Troubleshooting

- **`--doctor` meldet „kiwix unreachable"**: Läuft kiwix-serve? `autostart: true`
  gesetzt? Port 8080 frei (`netstat -ano | findstr 8080`)?
- **kiwix-serve startet nicht**: Pfade in `kiwix_exe`/`zim_path` prüfen — Tippfehler
  im Dateinamen sind der häufigste Fehler nach einem Update.
- **Keine Wiki-Hinweise im Chat**: `wiki.mode: offline` gesetzt? spaCy-Modell
  installiert (`python -m spacy download de_core_news_lg`)? Ohne Keyword-Finder
  gibt es keine Lookups.
