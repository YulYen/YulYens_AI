# Offline Wikipedia with Kiwix: Install & Update

In offline mode (`wiki.mode: "offline"`) the Orchestra answers knowledge questions
with excerpts from a **local Wikipedia copy** — no internet access needed at runtime.
Two pieces are required:

1. **kiwix-serve** — a small local web server that serves ZIM archives
2. a **ZIM archive** — the actual Wikipedia packed into a single file

This guide covers first-time setup and updates. The reference setup is Windows with
the folder `C:\wikipedia-de-offline\`; Linux/macOS works the same way with adjusted
paths.

---

## Prerequisites & disk space

| What | Size (approx.) |
|---|---|
| kiwix-tools (kiwix-serve etc.) | < 20 MB |
| `wikipedia_de_all_nopic` (German Wikipedia without images) | **14–16 GB** |
| During an update, old + new ZIM exist side by side | **plan for ~30 GB free** |

> 💡 The `nopic` variant is all the Orchestra needs: only text snippets are injected
> into the prompt — images would just waste space.

---

## First-time installation

### 1. Download kiwix-tools

From the official download page: <https://download.kiwix.org/release/kiwix-tools/>
(for Windows take the `..._win-i686.zip` or current x64 package). Extract to:

```
C:\wikipedia-de-offline\
├── kiwix-serve.exe
├── kiwix-manage.exe
└── kiwix-search.exe
```

### 2. Download the ZIM archive

All Wikipedia dumps live at: <https://download.kiwix.org/zim/wikipedia/>

Look for the **newest** file matching `wikipedia_de_all_nopic_YYYY-MM.zim`
(or the equivalent for your language). Download via browser or:

```powershell
curl.exe -L -o "C:\wikipedia-de-offline\wikipedia_de_all_nopic_2026-01.zim" `
  "https://download.kiwix.org/zim/wikipedia/wikipedia_de_all_nopic_2026-01.zim"
```

⏳ At 14 GB this takes 30 minutes to several hours depending on your connection.

### 3. Adjust `config.yaml`

```yaml
wiki:
  mode: offline
  offline:
    host: "127.0.0.1"
    kiwix_port: 8080
    zim_prefix: "wikipedia_de_all_nopic_2026-01"   # file name without .zim
    autostart: true                                 # start kiwix-serve automatically
    kiwix_exe: "C:/wikipedia-de-offline/kiwix-serve.exe"
    zim_path: "C:\\wikipedia-de-offline\\wikipedia_de_all_nopic_2026-01.zim"
```

Important: `zim_prefix` must match the file name (without `.zim`) exactly — the
Orchestra also derives the **data snapshot date** for the three-timestamp block in
the system prompt from it (so the personas know how fresh their Wikipedia knowledge is).

### 4. Verify

```bash
python src/launch.py --doctor
```

The setup doctor checks (among other things) that kiwix-serve is reachable.
Alternatively open `http://127.0.0.1:8080/` in a browser: the Kiwix UI should show
the loaded archive.

Then ask a knowledge question in the Orchestra (e.g. via Ask-All): the 🕵️ hint
indicates that a Wikipedia snippet was injected into the prompt.

---

## Updating to a newer dump

Dumps are rebuilt several times a year — an outdated dump means outdated knowledge
(and the personas are told so via the timestamp block).

1. **Find the latest version:** browse <https://download.kiwix.org/zim/wikipedia/>
   for `wikipedia_de_all_nopic_...`.
2. **Check disk space** (old + new archive briefly exist side by side).
3. **Download** (as above; ideally into a `.part` file, rename after the download
   completed successfully).
4. **Adjust `config.yaml`:** point `zim_prefix` and `zim_path` at the new file name.
5. **Stop a running kiwix-serve** (it keeps the old ZIM open) and restart the
   Orchestra — with `autostart: true`, kiwix-serve comes back up with the new archive.
6. **Verify:** `python src/launch.py --doctor` → Kiwix check green.
7. **Delete the old ZIM** once everything works.

---

## Troubleshooting

- **`--doctor` reports "kiwix unreachable"**: Is kiwix-serve running? Is
  `autostart: true` set? Is port 8080 free (`netstat -ano | findstr 8080`)?
- **kiwix-serve does not start**: Check the paths in `kiwix_exe`/`zim_path` — a typo
  in the file name is the most common mistake after an update.
- **No wiki hints in chat**: Is `wiki.mode: offline` set? Is the spaCy model
  installed (`python -m spacy download de_core_news_lg`)? Without the keyword
  finder there are no lookups.
