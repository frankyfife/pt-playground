# -*- coding: utf-8 -*-
"""Uebersetzungen der Erklaerabsaetze.

Englisch ist die Quellsprache: die Texte stehen im Quelltext von `ptqt.py`,
dieses Woerterbuch bildet sie auf Deutsch ab. Kein Qt-Linguist -- alle
Beschriftungen sind statisch, ein Durchlauf genuegt.

Kurze Beschriftungen (Knoepfe, Spalten, Felder) stehen in `ptqt.DE`; hier nur
die Absaetze. Unuebersetzt bleiben Namen aus dem Spiel, Dateinamen und die
Schluessel der shadPS4-Konfiguration -- die heissen dort genauso.

ERZEUGT. Die englischen Schluessel sind aus dem Quelltext gelesen, nicht
abgetippt: sie muessen zeichengenau stimmen, sonst greift die Uebersetzung
nicht.
"""

LANGS = (('en', 'English'), ('de', 'Deutsch'))

DE = {
    'Keeps the distance and direction the camera has right now, measured'
    ' in the game camera' + chr(39) + 's own axes, and holds it while the'
    ' player walks. Fly to where you want to watch from, then tick this -'
    ' a shoulder view swings around with him.':
        'Merkt sich Abstand und Richtung, die die Kamera gerade hat -'
        ' gemessen in den Achsen der Spielkamera - und hält beides,'
        ' während der Spieler läuft. Flieg dorthin, von wo du zusehen'
        ' willst, dann anhaken: eine Schulterkamera schwenkt mit ihm.',
    'Borrow a camera nothing has ever used, put it where the game'
    ' camera is, and fly it yourself. This is the one that survives'
    ' cutscenes.':
        'Leiht eine Kamera, die noch nie jemand benutzt hat, setzt sie an'
        ' die Stelle der Spielkamera und überlässt sie dir. Das ist die'
        ' Betriebsart, die Sequenzen übersteht.',
    'Borrow a camera the game drives and keep its own position. You'
    ' see through it and ride along; the game keeps moving it, so the'
    ' movement keys will not get you anywhere.':
        'Leiht eine Kamera, die das Spiel führt, und behält deren eigene'
        ' Lage. Du siehst durch sie hindurch und fährst mit; das Spiel'
        ' bewegt sie weiter, die Bewegungstasten bringen dich also nicht'
        ' von der Stelle.',
    'Which camera to borrow. "unused" means nothing has ever written'
    ' its position - those are the safe ones. The game drives some of'
    ' the others: during the opening it writes the one at the front of'
    ' the list every single frame, which is why the view used to snap'
    ' back. Picking one that is in use puts you at its own position;'
    ' an unused one starts where you are standing.':
        'Welche Kamera geliehen wird. "unused" heißt, dass ihre Lage'
        ' noch nie jemand beschrieben hat - das sind die sicheren. Einige'
        ' der anderen führt das Spiel: in der Anfangssequenz beschreibt'
        ' es die vorderste der Liste in jedem Bild, und genau deshalb'
        ' sprang der Blick bisher zurück. Wählt man eine benutzte,'
        ' springt der Blick an deren eigene Stelle; eine unbenutzte'
        ' beginnt dort, wo du gerade stehst.',
    'Throws away everything the tool remembers and looks it up again:'
    ' the object list behind the door and object pages, the pointer'
    ' chain to the player, and the module base. Use it after a loop'
    ' change or a restart of the game. Hovering survives.':
        'Verwirft alles, was sich das Werkzeug gemerkt hat, und sucht es'
        ' neu: die Objektliste hinter der Tür- und der Objektseite, die'
        ' Zeigerkette zum Spieler und die Modulbasis. Nach einem'
        ' Schleifenwechsel oder einem Neustart des Spiels. Das Schweben'
        ' bleibt erhalten.',
    'Starts the tool again and closes this window. The game keeps'
    ' running. Needed after changing the paths, and whenever the door'
    ' and object lists stop matching the level: that list is scanned'
    ' once and is not rebuilt when the loop changes.':
        'Startet das Werkzeug neu und schließt dieses Fenster. Das Spiel'
        ' läuft weiter. Nötig nach einer Pfadänderung, und immer dann,'
        ' wenn Tür- und Objektliste nicht mehr zur Kulisse passen: diese'
        ' Liste wird einmal gesucht und bei einem Schleifenwechsel nicht'
        ' neu aufgebaut.',
    'Range alone is not enough: the 100 lumen the game ships are tuned for five metres and are too dim to see anything at forty. Raise brightness on the Light page as well, or the longer range looks like nothing happened.':
        'Reichweite allein genügt nicht: die 100 Lumen des Spiels sind auf fünf Meter abgestimmt und auf vierzig zu dunkel, um etwas zu erkennen. Dreh die Helligkeit auf der Lichtseite mit hoch, sonst sieht die größere Reichweite aus, als wäre nichts passiert.',
    'Spawn a gimmick':
        'Ein Gimmick setzen',
    'put it in the start room':
        'in den Startraum stellen',
    'Only Baby has been tried in game. The other six come from the same parts files, but whether they show up at all is untested - the spawn behaviour is not understood.':
        'Nur Baby ist im Spiel ausprobiert. Die anderen sechs stammen aus denselben parts-Dateien, ob sie überhaupt erscheinen, ist ungetestet — das Spawnverhalten ist nicht verstanden.',
    'Flashlight reach':
        'Reichweite der Taschenlampe',
    'Range and cone of the torch. These cannot be changed while the game runs: the cone body is built once when the light is created, which is why a hundredfold brightness still stops at the same distance. Only the archive reaches them.':
        'Reichweite und Kegel der Taschenlampe. Beides lässt sich im laufenden Spiel NICHT ändern: der Kegelkörper entsteht einmal beim Erzeugen des Lichts, weshalb hundertfache Helligkeit immer noch an derselben Stelle endet. Nur das Archiv erreicht diese Werte.',
    'The game ships 5 metres with a 78 degree cone and a 30 degree core. Forty metres lights a whole corridor and has been confirmed in game. Widening the angles changes the shape noticeably, so change them one at a time.':
        'Das Spiel liefert 5 Meter mit 78 Grad Kegel und 30 Grad Kern. Vierzig Meter leuchten einen ganzen Gang aus und sind im Spiel bestätigt. Weitere Winkel ändern die Form deutlich — also einzeln ändern.',
    'Compensation shifts the exposure directly. Ceiling raises the limit the automatic exposure may open up to - the game caps it at 1, and without lifting that cap the compensation runs against the cap.':
        'Ausgleich verschiebt die Belichtung unmittelbar. Deckel hebt die Grenze, bis zu der die Belichtungsautomatik aufmachen darf -- das Spiel begrenzt sie auf 1, und ohne Anheben läuft der Ausgleich gegen diese Grenze.',
    'Colour and brightness of the torch the player carries. Both take effect at once.':
        'Farbe und Helligkeit der Taschenlampe, die der Spieler trägt. Beides wirkt sofort.',
    'Brightens or darkens the WHOLE image instead of a five metre cone, so distant surfaces with no light of their own become visible. The torch cannot do that: its range is baked in when the light is created, which is why a hundredfold brightness still stops at the same distance.':
        'Ausgleich verschiebt die Belichtung unmittelbar. Deckel hebt die Grenze, bis zu der die Belichtungsautomatik aufmachen darf -- das Spiel begrenzt sie auf 1, und ohne Anheben läuft der Ausgleich gegen diese Grenze.',
    'A second emulator build that repaints the empty space out of bounds, which is otherwise black - useful for seeing silhouettes and where anything is drawn at all. Confirmed: the void really is a buffer clear, so this reaches it. Only RGB is replaced; the alpha the game set stays, otherwise a transparent overlay buffer turns opaque and covers the whole scene. It still touches every colour clear, so treat it as an analysis aid, not a display setting.':
        'Ein zweiter Emulator-Build, der die Leere out of bounds einfärbt, die sonst schwarz ist – gut, um Silhouetten zu sehen und wo überhaupt gezeichnet wird. Bestätigt: die Leere ist wirklich eine Pufferlöschung, der Schalter erreicht sie also. Ersetzt wird nur RGB; das Alpha des Spiels bleibt stehen, sonst wird ein durchsichtiger Überlagerungspuffer deckend und legt sich über die ganze Szene. Es trifft weiter jede Farblöschung – also ein Analysewerkzeug, keine Bildeinstellung.',
    'Turn Hover on first. Warping out of bounds without it means falling, and falling gets you killed by Lisa.':
        'Vorher Schweben einschalten. Wer ohne es out of bounds warpt, fällt – und wer fällt, wird von Lisa getötet.',
    'Start room, measured from its 69 object positions:  x -2.28..2.09,  y -0.2..2.99,  z -12.95..0.  y 0 is the floor, y 3 the ceiling, y 0.8 the table top.  The player starts at (0, 0, -9.531), the door is at z 0.':
        'Startraum, aus seinen 69 Objektpositionen gemessen:  x -2.28..2.09,  y -0.2..2.99,  z -12.95..0.  y 0 ist der Boden, y 3 die Decke, y 0.8 die Tischplatte.  Der Spieler startet bei (0, 0, -9.531), die Tür liegt bei z 0.',
    'Remembers places you have stood and jumps back to them. Pad: L1 saves where you are, R1 cycles through the saved ones.':
        'Merkt Stellen, an denen du gestanden hast, und springt dorthin zurück. Pad: L1 merkt die aktuelle Stelle, R1 geht reihum durch die gemerkten.',
    'Holds the player at a fixed height while x and z stay free, so'
        ' you can still walk. Pad: L3 toggles it, D-pad up and down change'
        ' the height.':
        'Hält den Spieler auf einer festen Höhe, x und z bleiben frei –'
        ' du kannst also weiterlaufen. Pad: L3 schaltet um, Steuerkreuz'
        ' oben/unten ändert die Höhe.',
    'How often the height gets rewritten. It affects hovering only.':
        'Wie oft die Höhe neu geschrieben wird. Wirkt nur auf das'
        ' Schweben.',
    'Moves you one step in the direction you are looking - through'
        ' doors and walls. Pad: hold X, then D-pad up and down for forward'
        ' and back, left and right to strafe.':
        'Versetzt dich einen Schritt in Blickrichtung – durch Türen und'
        ' Wände hindurch. Pad: X halten, dann Steuerkreuz oben/unten für'
        ' vor und zurück, links/rechts seitwärts.',
    'Drag and it acts at once. Pad: L2 slower, R2 faster.':
        'Ziehen wirkt sofort. Pad: L2 langsamer, R2 schneller.',
    'Connecting scans the process memory and runs in the background,'
        ' so the window stays usable.':
        'Das Verbinden durchsucht den Prozessspeicher und läuft im'
        ' Hintergrund, das Fenster bleibt also bedienbar.',
    'Shows which loop you are in and which one lies behind the next'
        ' door.':
        'Zeigt, in welcher Schleife du bist und welche hinter der'
        ' nächsten Tür liegt.',
    'Sets the loop you land in. Takes effect when you walk through'
        ' the start room door.':
        'Setzt die Schleife, in der du landest. Wirkt, wenn du durch die'
        ' Startraumtür gehst.',
    'Can crash the emulator - that has happened. Save your progress'
        ' first.':
        'Kann den Emulator abstürzen lassen – das ist vorgekommen. Vorher'
        ' speichern.',
    'Switches the 62 objects P.T. ships hidden. Acts at once, no'
        ' rebuild needed.':
        'Schaltet die 62 Objekte, die P.T. versteckt ausliefert. Wirkt'
        ' sofort, ohne Neubau.',
    'Switches a door between its closed and its open model, and'
        ' clears the lock the game checks before it rattles the handle.':
        'Schaltet eine Tür zwischen geschlossenem und offenem Modell um'
        ' und löst das Schloss, das das Spiel prüft, bevor es die Klinke'
        ' klappern lässt.',
    'The rattle stops and the door shows open, but you still cannot'
        ' walk through: collision is a separate asset and no visibility'
        ' switch reaches it. Use Warp to get past a door.':
        'Das Klappern verstummt und die Tür zeigt sich offen, durchgehen'
        ' kannst du trotzdem nicht: die Kollision ist ein eigenes Asset,'
        ' und kein Sichtbarkeitsschalter erreicht sie. Um an einer Tür'
        ' vorbeizukommen, nimm Warp.',
    'What chunk1.psarc currently holds, read from the file itself.':
        'Was chunk1.psarc gerade enthält, aus der Datei selbst gelesen.',
    'Restore copies the shipped archive back, byte for byte. That is'
        ' not the same as building "vanilla".':
        'Zurückholen kopiert das ausgelieferte Archiv Byte für Byte'
        ' zurück. Das ist nicht dasselbe wie „vanilla“ zu bauen.',
    'Rewrites chunk1.psarc and takes effect on the next start. Close'
        ' the game first - it holds the archive open.':
        'Schreibt chunk1.psarc neu und wirkt beim nächsten Start. Das'
        ' Spiel vorher schließen – es hält das Archiv offen.',
    'This part is dependable.':
        'Dieser Teil ist verlässlich.',
    'EXPERIMENTAL: changing the loop relocates gimmicks. It has left'
        ' the start room door stuck shut, and it can crash the emulator.':
        'EXPERIMENTELL: der Schleifenwechsel versetzt Gimmicks. Er hat'
        ' die Startraumtür schon verklemmt, und er kann den Emulator'
        ' abstürzen lassen.',
    'Only meaningful with the hallway behind the door: the mazes'
        ' carry f110 alone, and the start room and the ending carry no'
        ' loops at all.':
        'Nur mit dem Flur hinter der Tür sinnvoll: die Labyrinthe tragen'
        ' allein f110, Startraum und Ending gar keine Schleifen.',
    'Arms the ending trap on every floor. Walk into the box in the'
        ' hallway and the real ending plays. Needs the hallway behind the'
        ' door.':
        'Stellt die Ending-Falle auf jeder Etage scharf. Lauf im Flur in'
        ' die Box, und das echte Ende spielt. Braucht den Flur hinter der'
        ' Tür.',
    'Of eight gimmick types only one shows up - P.T. picks it by'
        ' progress, not by this setting.':
        'Von acht Gimmick-Typen erscheint nur einer – P.T. wählt ihn nach'
        ' Fortschritt, nicht nach dieser Einstellung.',
    'Reference only: what each hallway loop arms. Nothing here is a'
        ' switch.':
        'Nur zum Nachschlagen: was jede Flurschleife freischaltet. Hier'
        ' ist kein Schalter.',
    'These are hallway loops. The mazes carry f110 alone.':
        'Das sind Flurschleifen. Die Labyrinthe tragen allein f110.',
    'The full per-loop switch list comes from the GeoModuleConditions in'
        ' the archive: "python ptfloors.py --all" writes it out.':
        'Die vollständige Liste der Umschaltungen je Schleife stammt aus den'
        ' GeoModuleConditions im Archiv: "python ptfloors.py --all" gibt sie'
        ' aus.',
    'Patches eboot.bin. Reversible, takes effect on the next start,'
        ' and the game must be closed.':
        'Patcht eboot.bin. Umkehrbar, wirkt beim nächsten Start, und das'
        ' Spiel muss geschlossen sein.',
    'Mostly obsolete. The gravity and ground-ray patches were the old'
        ' way to get the player off the floor - Hover does that live,'
        ' reversibly and without touching the executable. Kept for'
        ' reference, not because you need it.':
        'Größtenteils überholt. Die Gravitations- und'
        ' Bodenstrahl-Eingriffe waren der alte Weg, den Spieler vom Boden'
        ' zu lösen – das macht Schweben live, umkehrbar und ohne die'
        ' ausführbare Datei anzufassen. Bleibt als Nachschlagewerk drin,'
        ' nicht weil du es brauchst.',
    'Deletes the savegame, always after writing a backup. The'
        ' confirmation names every place it found one.':
        'Löscht den Spielstand, immer nach einer Sicherung. Die Rückfrage'
        ' nennt jeden Ort, an dem einer gefunden wurde.',
    'Toggle this on the loading or title screen - the streamer only'
        ' picks it up when it next builds its list.':
        'Im Lade- oder Titelbildschirm umschalten – der Streamer'
        ' übernimmt es erst, wenn er seine Liste neu aufbaut.',
    'Holds most of the textures in the game. Moving it out is never a'
        ' delete: the file goes to bak\\ and comes back from there.':
        'Enthält die meisten Texturen des Spiels. Es wegzuschieben ist'
        ' nie ein Löschen: die Datei geht nach bak\\ und kommt von dort'
        ' zurück.',
    'Path changes need a restart of this tool.':
        'Geänderte Pfade wirken erst nach einem Neustart dieses'
        ' Werkzeugs.',
    'HIGHLY EXPERIMENTAL: unpredictable, often nothing visible'
        ' happens, and firing throws the player across the world.':
        'HOCH EXPERIMENTELL: unberechenbar, sichtbar passiert oft nichts,'
        ' und das Auslösen wirft den Spieler durch die Welt.',
    'The dependable version of this is the switch list read from the'
        ' archive: "python ptfloors.py --all".':
        'Die verlässliche Fassung davon ist die Liste der Umschaltungen aus'
        ' dem Archiv: "python ptfloors.py --all".',
    'Double-click a row to arm it and jump into its box.':
        'Doppelklick auf eine Zeile stellt sie scharf und springt in ihre'
        ' Box.',
    'Live tools and archive patcher for P.T. (CUSA01127) under'
        ' shadPS4.':
        'Werkzeuge fürs laufende Spiel und ein Archiv-Patcher für P.T.'
        ' (CUSA01127) unter shadPS4.',
    'MIT License with an attribution requirement. Copy, change and'
        ' redistribute it freely, including commercially. The one'
        ' condition: the copyright notice, the licence text and the'
        ' credits above must stay intact. Add your own name for what you'
        ' changed - do not remove the existing entries.':
        'MIT-Lizenz mit Namensnennungspflicht. Frei kopieren, ändern und'
        ' weitergeben, auch kommerziell. Die einzige Bedingung: der'
        ' Copyright-Hinweis, der Lizenztext und die Credits oben müssen'
        ' unverändert mitgehen. Trag deinen eigenen Namen für deine'
        ' Änderungen ein – entferne die vorhandenen Einträge nicht.',
    'Deliberately not in the list above. That list is for people whose work this tool builds on, and the people who made P.T. did not contribute to it. They made the thing it is for. P.T. was released in August 2014 under the studio name "7780s Studio", which was Kojima Productions, published by Konami Digital Entertainment, and directed by Hideo Kojima together with Guillermo del Toro.':
        'Bewusst nicht in der Liste oben. Dort stehen Leute, auf deren Arbeit dieses Werkzeug aufsetzt, und wer P.T. gemacht hat, hat dazu nichts beigetragen. Er hat das Werk geschaffen, um das es geht. P.T. erschien im August 2014 unter dem Studionamen „7780s Studio“, dahinter stand Kojima Productions, herausgegeben von Konami Digital Entertainment, unter der Regie von Hideo Kojima gemeinsam mit Guillermo del Toro.',
    'Thank you, Hideo Kojima. P.T. gets more out of a single corridor than most games get out of an entire world, and it is the reason this tool exists at all. Taking it apart only made the respect for it bigger.\n\nIt was delisted in April 2015 and has never been rereleased. It cannot be bought any more, only kept by those who already have a copy. I think that is a real shame. A work like this should not depend on whether you happened to reach for it in time, and not wanting to watch it quietly disappear is a good part of why this tool exists.\n\nNamed here out of respect, not as an endorsement of any kind.':
        'Danke, Hideo Kojima. P.T. holt aus einem einzigen Flur mehr heraus als die meisten Spiele aus einer ganzen Welt, und es ist der Grund, warum es dieses Werkzeug ueberhaupt gibt. Es auseinanderzunehmen hat den Respekt davor nur groesser gemacht.\n\nIm April 2015 wurde es aus dem Store genommen und nie wieder aufgelegt. Kaufen kann man es nicht mehr, nur behalten, wenn man es schon hat. Ich finde das sehr schade. Ein Werk wie dieses sollte nicht davon abhaengen, ob man zufaellig rechtzeitig zugegriffen hat, und dass ich nicht zusehen wollte, wie es still verschwindet, ist ein guter Teil des Grundes fuer dieses Werkzeug.\n\nHier aus Respekt genannt, nicht als Billigung irgendeiner Art.',
    'Unofficial fan tool. P.T. and Silent Hills are property of'
        ' Konami Digital Entertainment. Not affiliated with or endorsed by'
        ' Konami, Kojima Productions or the shadPS4 project. No game'
        ' assets are shipped - everything it touches must already be on'
        ' your own machine, from your own copy of the game.':
        'Unoffizielles Fan-Werkzeug. P.T. und Silent Hills sind Eigentum'
        ' von Konami Digital Entertainment. Keine Verbindung zu und keine'
        ' Billigung durch Konami, Kojima Productions oder das'
        ' shadPS4-Projekt. Es werden keine Spieldaten mitgeliefert –'
        ' alles, was das Werkzeug anfasst, muss bereits auf deinem Rechner'
        ' liegen, aus deiner eigenen Kopie des Spiels.',
    'Co-author, concept and direction. Every feature in this tool'
        ' exists because he asked for it, and every finding was confirmed'
        ' by him testing it in the running game.':
        'Mitautor, Konzept und Richtung. Jede Funktion in diesem Werkzeug'
        ' gibt es, weil er sie verlangt hat, und jeder Befund wurde von'
        ' ihm im laufenden Spiel bestätigt.',
    'Reverse engineering, memory analysis and implementation. Found'
        ' the movement parameter block, the player pointer chain and the'
        ' gimmick and floor structures in the Fox Engine archives.':
        'Reverse Engineering, Speicheranalyse und Umsetzung. Fand den'
        ' Bewegungsparameterblock, die Zeigerkette zum Spieler und die'
        ' Gimmick- und Etagenstrukturen in den Fox-Engine-Archiven.',
    'For the original idea of floating the player above the floor to'
        ' reach places P.T. does not let you walk to. Credited as its'
        ' originator, not as a contributor to this software.':
        'Für die ursprüngliche Idee, den Spieler über dem Boden schweben'
        ' zu lassen, um an Stellen zu kommen, die P.T. nicht vorsieht.'
        ' Genannt als Urheber dieser Idee, nicht als Beitragender zu'
        ' dieser Software.',
    'eboot.bin matches the reference (P.T. 1.00)':
        'eboot.bin stimmt mit der Referenz überein (P.T. 1.00)',
    'Immediate = no vsync, Mailbox = vsync without stutter, Fifo ='
        ' vsync':
        'Immediate = kein VSync, Mailbox = VSync ohne Ruckeln, Fifo ='
        ' VSync',
}


def tr(text, lang):
    """Uebersetzen, wenn es dafuer einen Eintrag gibt."""
    if lang != 'de' or not text:
        return text
    return DE.get(text, text)
