# Ablage, Volltextsuche, Anmeldung, Logging

Store ≠ Logfile (#54/#59), Migrationen, Volltextsuche (#49), keine Aufzeichnung ohne Anmeldung (#72), die Identitäts-Naht (#53), was in `logs/` und was in `data/` liegt.

> Bis zum 2026-09-29 stand das wortgleich in `CLAUDE.md`. Dort steht jetzt nur
> noch die Regel als Kurzfassung mit Verweis hierher; die Begründung, die
> Messungen und die Geschichte dahinter stehen hier.

### Ablage der Gespräche (#54): Store ≠ Logfile
`src/storage/store.py` hält die Gespräche in einer SQLite-Datei
(`storage.path`, gitignored). **Das Gesprächs-Logfile war vorher die Persistenz**
— mit zwei unvereinbaren Formaten und ohne Gesprächsbegriff. Jetzt gilt:

| Artefakt | Rolle |
|---|---|
| `data/conversations.sqlite3` | **das Gespräch**, wie der Nutzer es sieht — Verlauf (#25), später Suche (#49) und Fakten (#24) |
| `logs/conversation_*.json` | roher Mitschnitt der *Versuche* zum Debuggen, **opt-in** über `logging.conversation_jsonl` |

**Die Rollenverteilung stimmt erst seit #59.** Vorher schrieb `stream()` beides,
und damit protokollierte die Ablage Generierungs*versuche* statt des Gesprächs:
„Nochmal 🔄" hängte Frage und verworfene Antwort erneut an (dreimal gedrückt →
drei Fragen und drei Antworten im Store, während die Oberfläche eine zeigte),
„Stop ⏹" ließ die Antwort ganz weg. Ask-All und Self-Talk zeichneten gar nichts
auf, weil dort nie eine Gesprächs-ID gesetzt wurde — das ist bis heute so und
**seit 2026-08-05 eine bewusste Entscheidung**, siehe unten.

Jetzt gilt: **die Oberfläche besitzt den Gesprächsstand, die Ablage spiegelt
ihn.** `stream()` schreibt nur noch den JSONL-Mitschnitt (der *soll* Versuche
festhalten); den Store bedient `record_conversation(messages)`, aufgerufen vom
Aufrufer, sobald der Turn steht. `ConversationStore.sync` ersetzt den ganzen
Nachrichtenverlauf statt anzuhängen — dadurch kann keine Buchführung mehr
auseinanderlaufen, und injizierter System-Kontext (Wiki, Briefing) bleibt
draußen, weil er zum Prompt gehört und nicht zum Gespräch.

Wer einen **neuen Antwortweg** baut, muss `record_conversation` aufrufen —
sonst bleibt er spurlos. Aufgezeichnet wird heute aus Einzelchat, Briefing,
„Nochmal", Terminal, API und Mail-Adapter.

> **⚠️ Datierter Hinweis (2026-09-05): die nächsten zwei Absätze widersprechen
> dem Code — nachgemessen, nicht strittig.** `iter_broadcast_events`/`_parallel`
> eröffnen seit #59 (Commit `6f5e16a`, 2026-08-01 — also *vor* der Entscheidung
> vom 2026-08-05) je Persona ein Gespräch (`app: ask-all`) und rufen
> `record_conversation`; `SelfTalkRunner` ebenso (`app: self-talk`). Tests
> nageln das als Absicht fest. Auf einer Default-Installation fällt der
> Widerspruch nicht auf, weil ohne Anmeldung ein `NullStore` läuft (#72) — mit
> Anmeldung wird aufgezeichnet, unter dem Eigentümer `local`, für niemanden im
> Verlauf sichtbar. Welche Seite gilt, entscheidet **#77** (backlog.md); bis
> dahin ist weder auf diese Absätze noch auf die Docstrings in
> `ask_all_moderator.py` Verlass.

**Zwei Wege zeichnen bewusst nicht auf: Ask-All und Self-Talk (#75, verworfen
am 2026-08-05).** Das ist keine Lücke, sondern eine Entscheidung — und sie steht
hier, weil der Satz davor sonst wie ein unerledigter Fehler aussieht:

- **Ask-All** sind vier parallele Antworten auf *eine* Frage. Das Datenmodell
  der Ablage ist „eine Persona, ein Faden"; Ask-All hineinzuzwingen hieße, eine
  Form zu erfinden, die niemand braucht. Die Ansicht ist ohnehin ein
  `gr.Markdown` ohne Daumen — es hängt also auch kein Feedback daran.
- **Self-Talk** erzeugt ein Artefakt, kein Nutzergespräch: zwei Personas reden
  miteinander, der Nutzer gibt nur den Startprompt.

**Die Fußnote zu Self-Talk, damit sie niemand neu entdecken muss:** anders als
Ask-All schreibt er in **dasselbe** `chatbot` wie der Einzelchat — an dem die
👍/👎 hängen. Ein Daumen dort wird also geschrieben, aber mit **leerer
`conversation_id`**, weil es kein Gespräch gibt. Derselbe Zustand wie ohne
Anmeldung (#72), nur auf einem zweiten Weg erreichbar. Der Preis ist bekannt und
klein: genau diese Vote-Zeilen lassen sich später nicht gegen Persona, Modell
und Verlauf joinen — wofür #65 gebaut wurde. Wer die Entscheidung umdreht, fängt
bei Self-Talk an, nicht bei Ask-All.

**Der Datei-Im-/Export bleibt, ist aber abschaltbar** (`storage.file_exchange`, Default an) — er ist etwas anderes als die Ablage. `conversation_io_terminal.py`
(JSON hoch-/runterladen im WebUI, `/save` und Laden im Terminal) ist der
*Austausch mit der Außenwelt*: sichern, auf einen anderen Rechner mitnehmen,
weitergeben. Die Ablage ist das *eigene Gedächtnis der App*. Drei Wege, drei
Zwecke:

| Weg | Format | wofür |
|---|---|---|
| Verlauf → Öffnen | — | eigenes Gespräch fortsetzen |
| Verlauf → Als Markdown | Markdown | lesbar weitergeben (Einbahnstraße) |
| „Konversation herunterladen" / Upload | JSON | Austausch, verlustfrei zurückladbar — abschaltbar über `storage.file_exchange`. Ein hochgeladenes Gespräch läuft als **eigener** Eintrag in der Ablage weiter (`app: web-import`); ohne das schriebe jeder Turn nach dem Laden ins Leere |

**Migrationen** über `PRAGMA user_version` plus die Liste `_MIGRATIONS`: neue
Schritte nur **anhängen**, nie einen ausgelieferten Schritt ändern. Schritt 2 ist
seit #49 die FTS5-Tabelle — SQLite bringt FTS5 mit, ein eigener Index ist
unnötig.

**Jeder Schritt läuft ganz oder gar nicht.** Vorher lief er über
`executescript`, das die pendente Transaktion vorher committet und das Skript
selbst nicht klammert: scheiterte Anweisung 2 von 3, blieb Anweisung 1 stehen,
`user_version` blieb zurück — und damit war der Schritt **nie wieder** anwendbar
(„table … already exists"). Der Store degradierte bei jedem weiteren Start zum
`NullStore`, und die App lief weiter, ohne noch etwas aufzuzeichnen. Jetzt steht
`BEGIN`/`COMMIT` im Skript, `user_version` wird darin gesetzt (in SQLite
transaktional), ein Fehlschlag rollt zurück und nennt die Schrittnummer.
Bewusst weiter `executescript` statt einer Zerlegung an `;`: ein FTS5-Trigger
bringt eigene Semikolons im `BEGIN…END`-Rumpf mit.

**Ein Schritt darf fehlschlagen dürfen — genau einer, und der steht in einer
Liste (#49).** Der FTS5-Schritt ist der erste, dessen Scheitern *kein* Defekt
der Datei ist: ein SQLite ohne FTS5-Modul kann ihn schlicht nicht. Ohne
Sonderbehandlung risse er aber die **ganze** Ablage mit — `_migrate` wirft,
`build_store` fängt jede `sqlite3.Error` mit einem `NullStore` ab, und die App
liefe weiter, ohne noch irgendetwas aufzuzeichnen. Der Nutzer verlöre seinen
Verlauf und bekäme dafür eine Logzeile: dieselbe stille Sorte, die #72 so teuer
gemacht hat, nur diesmal als Nebenwirkung eines Features, das er nicht bestellt
hat. `_OPTIONAL_MIGRATIONS` nennt deshalb die Schrittnummern, die übersprungen
werden dürfen; ein übersprungener Schritt **hält die Kette an** (kein
`continue`), weil Schritt 3 auf einer Datei ohne Schritt 2 ein Schema ergäbe,
das es in keiner Version je gab. `test_without_fts5_the_store_still_records_
and_search_stays_quiet` hält beides fest.

### Volltextsuche: die Eingabe ist Text, nicht Syntax (#49)

`SqliteStore.search()` gibt die Nutzereingabe **nie roh** an FTS5. Deren
Abfragesprache kennt `"`, `*`, `AND`, `NEAR()` und `^` — ein Suchfeld, das sie
durchreicht, antwortet auf `"` mit einem `OperationalError` statt mit „nichts
gefunden". `_fts_query` quotet deshalb jedes Wort einzeln (inneres `"`
verdoppelt) und stellt sie nebeneinander, was in FTS5 UND bedeutet. Das ist,
was ein Suchfeld tut — und es ist die einzige Stelle, an der sich das
entscheiden lässt.

Drei weitere Punkte, die man beim Anfassen leicht umdreht:

1. **Der Backfill gehört in den Migrationsschritt**, nicht in einen späteren
   Wartungslauf: ohne ihn sind alle *bestehenden* Gespräche unsichtbar, und das
   fällt erst dem auf, der lange sucht und nichts findet.
2. **Der Index hängt an Triggern, nicht an Aufrufern.** `sync()` ersetzt den
   ganzen Verlauf pro Turn (DELETE + INSERT) — mit einem Trigger stimmt der
   Index dadurch von selbst. Nachgemessen und als Test festgenagelt: SQLite
   feuert die DELETE-Trigger der Kindtabelle auch bei `ON DELETE CASCADE`, ein
   gelöschtes Gespräch verschwindet also mit.
3. **Die Suche liefert dieselbe Form wie die Liste** (`[(Beschriftung, ID)]`,
   `ConversationHistory.search_choices`). Dadurch bleiben Vorschau, Öffnen,
   Export und Löschen unverändert — sie hängen weiter am selben Dropdown, und
   die Suche schränkt nur ein, was darin steht. Eine leere Eingabe ist deshalb
   kein Sonderfall, sondern die ganze Liste. `user` wird gesetzt wie überall an
   der Ablage; im Terminal bewusst nicht, dort gibt es keine Anmeldung.

**Fundstellen als Kontext ins Gespräch zu injizieren steht bewusst noch aus
(#49b).** Das Backlog empfahl dafür `injected_message` — seit #75 wäre das eine
Regelverletzung, und `tests/test_context_channels.py` fängt es per AST.
Sachlich wäre es ohnehin **kein** Fremdtext-Kanal: in der Ablage stehen nur
eigene Nutzerturns und eigene Modellausgabe, injizierter System-Kontext bleibt
draußen — dieselbe Einordnung wie bei Karl und beim Ask-All-Fazit. Das gehört
entschieden, nicht nebenbei gebaut.

**Ohne Anmeldung wird nichts aufgezeichnet (#72).** `DisabledAuth` — der
Default — gibt *jedem* Besucher die Identität `local`. Alle Gespräche tragen
damit denselben Eigentümer, und die Eigentümerprüfung unten läuft ins Leere:
wer die Seite erreicht, sieht im Verlauf die Gespräche aller anderen, kann sie
fortsetzen und löschen. Deshalb liefert `AppFactory.get_store()` einen
`NullStore`, wenn `ui.type: web` ohne Anmeldung läuft — mit einer Meldung, die
beide Auswege nennt. Der ausdrückliche Weg in den gemeinsamen Topf ist
`storage.shared_without_login: true` (Default aus); dann warnt der Start einmal
laut, was geteilt wird. **Terminal und API sind nicht betroffen** — dort gibt es
keine Anmeldung, die fehlen könnte.

Die Web-UI fragt die Ablage, ob sie überhaupt schreibt (`store.records`), und
lässt die Verlauf-Karte sonst weg. Eine Karte über einem `NullStore` verspricht
etwas, das sich nie füllen kann — das galt auch schon bei
`storage.enabled: false`. Wer an der Karte etwas bindet, prüft deshalb auf
`None` (wie bei Ask-All); `test_the_app_still_starts_without_a_store` hält fest,
dass die App ohne sie startet.

**Nutzergebundenes Lesen und Löschen:** `load()` und `delete()` nehmen ein
optionales, keyword-only `user`. Mit gesetztem Wert verhält sich ein fremdes
Gespräch wie ein nicht existierendes — die Antwort soll nicht verraten, dass es
die ID gibt. Terminal und API rufen weiter ohne `user`. **Die WebUI muss ihn
immer setzen:** die Gesprächs-ID kommt aus einem `gr.Dropdown`, und dessen
`preprocess` reichte in Gradio 4.44 den Wert des Clients ungeprüft durch (die
Lücke hinter dem Verlauf-IDOR, GHSA-26jh-r8g2-6fpr, seit #61 gehoben) — die
Auswahl im Browser ist keine Schranke.

**Die Gesprächs-ID gehört der Oberfläche, nicht dem Streamer:** sie liegt im
`gr.State` `conversation_state` und wird nach einem Streamer-Neubau erneut
gesetzt (`set_conversation`). Sonst begänne jede Fortsetzung ein neues Gespräch.

Aufzeichnen darf **nie** den Stream abbrechen (wie beim Logfile davor), und eine
unbrauchbare Datei degradiert zum `NullStore`, statt den Start zu verhindern.
Tests laufen per autouse-Fixture gegen `storage.enabled: false` — sonst schriebe
jede Test-Session in die echte Datenbank. **Dieser Satz stimmte lange nicht ganz
(#64f):** die Fixture hängt an `Config._load_config`, und zwei Tests bauen sich
ein eigenes Config-Objekt, das dort nie vorbeikommt und kein `storage`-Feld
hatte. `build_store` nahm seinen Default, ein voller Lauf legte
`data/conversations.sqlite3` an (leer, aber da). Deshalb gibt es jetzt einen
zweiten Riegel: die Fixture biegt zusätzlich `storage.store.DEFAULT_STORE_PATH`
nach `tmp_path`. Wer künftig am ersten vorbeikommt, schreibt trotzdem nicht ins
Repo — und wer ein Config-Objekt von Hand baut, sollte es ohnehin nicht tun
(siehe `tests/doubles.py`).

### Anmeldung (#53): eine Naht, kein Sicherheitsprodukt
`src/auth/provider.py` beantwortet „wer bedient die UI". Drei Provider über
`ui.web.auth.provider`:

| Provider | Verhalten |
|---|---|
| `disabled` (**Default**) | kein Login, alle sind `local` — und deshalb zeichnet die WebUI nichts auf (#72) |
| `local` | Nutzer aus `ui.web.auth.users`, Passwörter über die `env:`-Konvention |
| `header` | Identität aus dem Header eines vorgeschalteten Proxys |

**Der Wert liegt in der Naht:** `user` hängt an jedem Gespräch in der Ablage
(#54) und steht in jeder Feedback-Vote. Genau das
brauchen #25 (Verlauf), #49 (Suche), #40b und #24 (Fakten über den Nutzer).
Die Identität wird **einmal pro Browser-Sitzung** über `demo.load` + `gr.Request`
in ein `gr.State` geholt — nicht `gr.Request` an jeden Handler hängen, die
Persona-Buttons laufen über `functools.partial`.

**Ehrlich einordnen:** Gradios Basic-Auth geht über HTTP im Klartext. Ohne TLS
ist das eine *Trennung* von Nutzern, kein Schutz gegen Mitlesen. `header`
vertraut dem Header bedingungslos und darf nur hinter einem Proxy laufen, der
ihn von außen entfernt.

**Zwei Richtungen, zwei Reaktionen — der Unterschied ist Absicht:**

| Lage | Reaktion |
|---|---|
| `provider: local`, aber **kein Nutzer auflösbar** (meist ein nicht durchgereichtes `env:`) | **Abbruch** (`AuthConfigError`, Exit 4) |
| App horcht auf nicht-Loopback **ohne** konfigurierte Anmeldung | laute Warnung, Start läuft weiter |
| WebUI **ohne** Anmeldung, `storage.enabled: true` | Ablage bleibt aus, Verlauf-Karte weg (#72); `storage.shared_without_login: true` schaltet sie mit lauter Warnung wieder ein |

Der erste Fall bricht ab, weil dort jemand ausdrücklich Schutz konfiguriert hat
und ihn sonst stillschweigend verlöre; die frühere Begründung („lieber offen und
laut") unterstellt einen Tippfehler, der häufigere Auslöser ist aber eine
systemd-Unit ohne `EnvironmentFile` oder ein Container ohne `--env`. Der zweite
Fall warnt nur — „im Heimnetz ohne Login" ist ein legitimer Betriebsmodus.

`ui.web.host` steht seit dieser Runde auf **`127.0.0.1`**. Vorher war `0.0.0.0`
der Default, ohne dass es irgendwo stand.

**Kein OIDC direkt:** Gradios `auth=`-Callable bekommt nur Name und Passwort —
kein Redirect-Flow, keine Token-Validierung. Keycloak & Co. laufen über
oauth2-proxy/Authelia davor, die die Identität als Header durchreichen; genau
dafür gibt es `HeaderAuth`.

Die Anmeldung gilt **unabhängig von `share`**. Das alte `ui.web.share_auth`
greift nur noch als Fallback (mit Deprecation-Warnung) — es wirkte früher
ausschließlich beim Share-Link, obwohl der Server per Default auf `0.0.0.0`
horcht.

## Logging

**Gespräche liegen nicht hier**, sondern seit #54 in `data/conversations.sqlite3`
(siehe „Ablage der Gespräche"). In `logs/` steht nur noch Betriebs-Diagnostik
(Eval-Reports in `logs/evals/`):
- `yulyen_ai_YYYY-MM-DD_HH-MM.log` — Systemlog
- `conversation_[TIMESTAMP].json` — roher Turn-Mitschnitt als JSONL, **opt-in**
  über `logging.conversation_jsonl` (Default aus). Debug-Artefakt, keine Ablage
- `wiki_proxy_[TIMESTAMP].log` — Wiki-Proxy-Log

**Die Vote-Datei ist hier weg** und liegt seit dieser Runde in `data/`, neben
der Ablage: `data/feedback_votes.jsonl` — 👍/👎-Bewertungen (#40), append-only,
eine Zeile pro Vote, seit #65 mit `conversation_id`/`message_index` als
Schlüssel in die Ablage.

Der Grund ist derselbe Schnitt wie bei #54, nur eine Datei später. Alles in
`logs/` ist **wegwerfbar**: Systemlogs erzählen von einem Lauf, Eval-Reports
lassen sich neu fahren, der JSONL-Mitschnitt ist Debug-Material. Die Votes
nicht — sie sind gesammeltes menschliches Urteil, nicht reproduzierbar und
nicht nachträglich erzeugbar, und sie sind der Trainingsdaten-Kanal für #7. In
einem Verzeichnis, das man beim Aufräumen leert, war das eine Frage der Zeit.

Zwei Entwurfspunkte dazu: das Verzeichnis wird **aus `storage.path` abgeleitet**
statt zweit-konfiguriert (die Votes zeigen auf genau diese Datenbank, also
folgen sie ihr), und eine vorhandene Datei **zieht beim ersten Zugriff um**
(`adopt_legacy_votes`). Ein Pfadwechsel ohne Umzug verliert still: die alten
Zeilen blieben liegen, neue kämen woanders dazu, und auffallen würde es erst
beim Zusammenstellen der Trainingsdaten. Liegen beide Dateien, wird **nichts**
angefasst und laut gewarnt — welche die richtige ist, kann der Code nicht
wissen, und Zusammenführen wäre geraten.
