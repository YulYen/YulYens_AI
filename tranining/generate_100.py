import json, time, os, requests, random
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

API_URL = os.environ.get("LEAH_API_URL", "http://127.0.0.1:8013")
OUT_PATH = os.path.join("data", "doris_1_sft_v1.jsonl")

PROMPTS_5 = [
    "Sag mir was Nettes!",
    "Wer bist du?",
    "Kannst du mich heute mal ehrlich loben – ohne dass es peinlich wird?",
    "Ich hatte einen miesen Tag. Krieg ich einen Mini-Motivationsschub?",
    "Tu so, als wärst du charmant. Los."
]

PROMPTS_100_1 = [
    "Sag mir was Nettes!",
    "Kannst du mich heute mal ehrlich loben – ohne dass es peinlich wird?",
    "Ich hatte einen miesen Tag. Krieg ich einen Mini-Motivationsschub?",
    "Tu so, als wärst du charmant. Los.",
    "Was magst du an meiner Art zu schreiben?",
    "Bitte ein Kompliment – maximal 10 Wörter.",
    "Flüster mir digital etwas Nettes zu.",
    "Schenk mir einen Satz, der gut in meinen Morgen passt.",
    "Stell dir vor, wir kennen uns lange. Was würdest du mir Nettes sagen?",
    "Eine freundliche Bemerkung, aber ohne Kitsch, okay?",
    "Mach mir Mut vor einem schwierigen Gespräch.",
    "Gib mir ein ehrliches, kleines Schulterklopfen.",
    "Sag was Nettes, aber mit trockenem Humor.",
    "Was würdest du mir nach einem Lauftag sagen?",
    "Ein Satz, der mich grinsen lässt – kurz und frech.",
    "Mach mir ein Kompliment ohne Emojis.",
    "Gib mir eine nette Fußnote zu meinem Tag.",
    "Formuliere ein Lob, das so klingt, als wär’s dir fast peinlich.",
    "Sag was Positives, aber nicht offensichtlich.",
    "Kannst du nett sein, ohne dabei süßlich zu klingen?",
    "Wie hoch ist der Eiffelturm?",
    "Wer war Bundeskanzler in Deutschland im Jahr 1995?",
    "Wie alt ist das Universum ungefähr?",
    "Wann wurde der Euro als Bargeld eingeführt?",
    "Wer hat die Relativitätstheorie formuliert?",
    "Wie viele Knochen hat ein erwachsener Mensch?",
    "Was ist die Hauptstadt von Kanada?",
    "Wer malte die Mona Lisa?",
    "Wie tief ist der Marianengraben?",
    "Wie groß ist der Mount Everest in Metern?",
    "Wer war der erste Mensch auf dem Mond?",
    "Wann begann der Zweite Weltkrieg?",
    "Wie viele Planeten hat unser Sonnensystem?",
    "Wer erfand den Buchdruck in Europa?",
    "In welchem Jahr fiel die Berliner Mauer?",
    "Wie schnell ist Licht im Vakuum?",
    "Wer schrieb „Faust“?",
    "Wie lautet die Hauptstadt von Australien?"]
    
PROMPTS_100_2 = [
    "Wie viele Kontinente gibt es?",
    "Wer war die erste Frau im All?",
    "Erzähl mir was Nettes über Hamburger Wetter (ja, ich weiß…).",
    "Gib mir ein Kompliment, das ich nicht erwarte.",
    "Sag etwas Kurzes, das mutig klingt.",
    "Ein nett-frecher Satz über meinen Kaffeekonsum, bitte.",
    "Ich brauche ein Kompliment im Doris-Tempo: schnell, knapp, trocken.",
    "Schenk mir einen freundlichen Gedanken in 12 Wörtern.",
    "Wie viele Einwohner hat Deutschland ungefähr?",
    "Wer komponierte die 9. Sinfonie (Ode an die Freude)?",
    "Was ist die chemische Formel von Wasser?",
    "Wie heißt das längste Fließgewässer der Welt?",
    "Welche Sprache hat weltweit die meisten Muttersprachler?",
    "Wer entdeckte Penicillin?",
    "Wann wurde die UNO gegründet?",
    "Wie viele Bundesländer hat Deutschland?",
    "Wer war der erste Bundespräsident der BRD?",
    "Wie viele Zähne hat ein Erwachsener normalerweise?",
    "Fass meinen Tag lieb zusammen: „zu wenig Schlaf, viel geschafft“.",
    "Ein Kompliment, das nach Understatement klingt.",
    "Mach mir Mut für ein langweiliges Meeting.",
    "Gib mir einen trockenen, aber wohlwollenden Satz zum Durchhalten.",
    "Formuliere ein stilles Lob – maximal 15 Wörter.",
    "Wie viele Wochen hat ein Jahr?",
    "Wer erfand das Telefon?",
    "In welchem Jahr wurde die Dampfmaschine populär?",
    "Wie viele Spieler stehen bei Fußball pro Team auf dem Platz?",
    "Wer schrieb die „Brüder Grimm“-Märchen?",
    "Wie lautet die Hauptstadt der Schweiz?",
    "Wie viele Bundeskanzlerinnen gab es bisher in Deutschland?",
    "Wer entwickelte den ersten Computer (konzeptuell)?",
    "Was ist die SI-Einheit für elektrische Stromstärke?",
    "Ich bin müde. Sag was Nettes, das nicht nach Kalender klingt.",
    "Kannst du mich nüchtern loben – ohne Zuckerwatte?",
    "Eine charmant-freche Bemerkung, die nicht anbiedernd ist.",
    "Gib mir ein kleines „Weiter so“, aber glaubwürdig.",
    "Lob mich vorsichtig, als würdest du’s später abstreiten.",
    "Was ist die Hauptstadt von Neuseeland?",
    "Wie viele Tasten hat ein Standard-Klavier?",
    "Wann war die Mondlandung von Apollo 11?",
    "Wie heißt das größte Säugetier der Welt?",
    "Wer malte „Die Sternennacht“?",
    "Wie viele Karten hat ein Skatspiel?",
    "Was ist das chemische Symbol für Gold?",
    "Wie nennt man gefrorenen Regen wissenschaftlich?",
    "Wer war die erste Bundeskanzlerin Deutschlands?",
    "Ein Lob, das ich in meine Notizen kopieren kann – schlicht, präzise.",
    "Schnippisches Mini-Kompliment, das trotzdem gut tut.",
    "Sag mir was Nettes über meine Geduld (die keine ist).",
    "Gib mir ein trockenes, aber freundliches „Gut gemacht“.",
    "Ich brauche einen Satz, der nach „Weitergehen“ klingt.",
    "Wie heißt die Hauptstadt von Norwegen?",
    "Wer war der erste Bundeskanzler der BRD?",
    "Wie viele Sekunden hat ein Tag?",
    "Welches Element hat die Ordnungszahl 1?",
    "Wer schrieb „Der kleine Prinz“?",
    "Wie viele Spieler hat ein Volleyball-Team auf dem Feld?",
    "Wie lang ist ein Marathon in Kilometern?",
    "Wer erfand die Glühbirne (berühmt zugeschrieben)?",
    "Welche Farbe hat Chlorophyll?",
    "Eine freundliche Bemerkung, die sich wie ein Augenzwinkern anfühlt.",
    "Lobe mich so, dass ich es dir fast nicht glaube – aber mag.",
    "Formuliere einen Satz, der schlau klingt und nett ist.",
    "Ein Kompliment, das man auch im Büro lesen kann.",
    "Gib mir einen Satz, der nach gelassener Kompetenz riecht."
]



CONNECT_TIMEOUT = 10
READ_TIMEOUT = 120
MAX_RETRIES = 3
BACKOFF_FACTOR = 0.5
POOL_SIZE = 4           # klein halten; wir feuern sequentiell
SESSION_ROTATE_N = 25   # nach N Calls Session neu

def make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=MAX_RETRIES,
        backoff_factor=BACKOFF_FACTOR,
        status_forcelist=(502, 503, 504),
        allowed_methods=frozenset(["POST"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(pool_connections=POOL_SIZE, pool_maxsize=POOL_SIZE, max_retries=retry)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    s.headers.update({"Connection": "keep-alive", "Accept": "application/json"})
    return s

def ask(session: requests.Session, question: str) -> str:
    with session.post(
        f"{API_URL}/ask",
        json={"question": question},
        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
    ) as r:
        r.raise_for_status()
        data = r.json()  # liest den Body vollständig -> Verbindung wird sauber freigegeben
        return (data.get("answer") or "").strip()

def append_pair(user_text: str, assistant_text: str):
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({"user": user_text.strip(), "assistant": assistant_text}, ensure_ascii=False) + "\n")


PROMPTS= PROMPTS_100_2

def main():
    s = make_session()
    try:
        for i, q in enumerate(PROMPTS, 1):
            try:
                a = ask(s, q)
                if a:
                    append_pair(q, a)
                    print(f"[{i:03}] ok")
                else:
                    print(f"[{i:03}] leer übersprungen")
            except requests.exceptions.Timeout as e:
                print(f"[{i:03}] TIMEOUT: {e}")
                time.sleep(2.5)
            except requests.exceptions.RequestException as e:
                print(f"[{i:03}] REQUEST-FEHLER: {e}")
                time.sleep(2.0)
            except ValueError as e:
                print(f"[{i:03}] JSON-FEHLER: {e}")
                time.sleep(1.0)

            # Jitter 150–400 ms, entkoppelt Idle-Pattern vom Server
            time.sleep(0.15 + random.random() * 0.25)

            # Session alle N Calls „frisch“ aufsetzen
            if i % SESSION_ROTATE_N == 0:
                s.close()
                time.sleep(0.5)
                s = make_session()
    finally:
        s.close()

if __name__ == "__main__":
    main()