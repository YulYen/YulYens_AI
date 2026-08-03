<!--
Vier Abschnitte, mehr nicht. Eine Vorlage, die zu viel verlangt, wird
ausgefüllt wie ein Formular und gelesen wie keins.

Bewusst *keine* Häkchenliste für Tests, black, ruff und mypy: das prüft die CI,
und ein Häkchen daneben behauptet nur dasselbe noch einmal — schlimmer, es
lässt sich setzen, ohne dass es stimmt.

Abschnitte, die auf diesen PR nicht passen, ersatzlos löschen. Ein leerer
Abschnitt ist schlechter als keiner.
-->

## Worum es geht

<!--
Der Defekt oder die Entscheidung — nicht die Liste der geänderten Dateien.
Die steht im Diff. Was hier steht, steht sonst nirgends: warum das nötig war
und was es kostet, wenn es nicht passiert.
-->

## Nachgewiesen

<!--
Was tatsächlich gelaufen ist, mit Zahlen. Nicht "getestet", sondern was und
womit. Bei Verhaltensänderungen: die Mutationsprobe — Fix zurückgenommen, wie
viele Fälle fallen? Ein Test, der auch ohne die Änderung besteht, hat nichts
gezeigt.
-->

## Nicht geprüft

<!--
Der wichtigste Abschnitt, und der einzige, der ohne Vorlage regelmäßig fehlt.

Diese Umgebung kann manches nicht: Ollama, Piper, faster-whisper, Kiwix/ZIM,
Windows, echte Mailserver. Was davon berührt ist und ungeprüft blieb, gehört
hierher — vor den Merge, nicht danach.

"Nichts" ist eine gültige Antwort, wenn sie stimmt.
-->

## Was man leicht umdreht

<!--
Optional, aber die Stelle, an der dieses Projekt sein Geld verdient: welche
Entscheidung sieht aus wie ein Detail und ist keins? Was fällt still um, wenn
jemand sie zurücknimmt?

Beispiele aus dem Archiv: erst markieren, dann senden (#14). Der Guard filtert
pro Meldung, bevor zusammengefügt wird (#73). Ein nicht deutbarer Vote-Index
wird verworfen, nicht geraten (#61a).

Wenn es so eine Stelle gibt, gehört sie außerdem nach CLAUDE.md — hier steht
sie für den Review, dort für den nächsten Umbau.
-->

## Backlog

<!-- Ticketnummer(n). Erledigtes wandert im selben PR ins Archiv. -->
