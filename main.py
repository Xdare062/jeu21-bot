import re
import os
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telegram import Bot

# ---------- Configuration ----------
BOT_TOKEN = os.environ["BOT_TOKEN"]            # token du bot qui POSTE les résultats
CANAL_ID = int(os.environ["CANAL_ID"])         # canal de destination (où le bot poste)

API_ID = int(os.environ["API_ID"])             # depuis my.telegram.org
API_HASH = os.environ["API_HASH"]              # depuis my.telegram.org
SESSION_STRING = os.environ["SESSION_STRING"]  # généré une fois en local (generate_session.py)

SOURCE_CHANNEL = os.environ["SOURCE_CHANNEL"]  # @username ou ID numérique du canal source

PORT = int(os.environ.get("PORT", "10000"))

try:
    SOURCE_CHANNEL_ENTITY = int(SOURCE_CHANNEL)
except ValueError:
    SOURCE_CHANNEL_ENTITY = SOURCE_CHANNEL


# ---------- Petit serveur HTTP pour Render ----------
class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Jeu21 bot is running")

    def log_message(self, format, *args):
        pass


def start_web_server():
    server = HTTPServer(("0.0.0.0", PORT), PingHandler)
    server.serve_forever()


# ---------- Algorithme (strictement identique à la version précédente) ----------
VALEURS_CARTES = {
    'A': 11, 'J': 2, 'Q': 3, 'K': 4,
    '2': 2, '3': 3, '4': 4, '5': 5,
    '6': 6, '7': 7, '8': 8, '9': 9, '10': 10
}


def parse_cartes(texte):
    texte = texte.replace('10', 'X')
    symboles = re.sub(r'[♠♦♥♣️🂠\s]', '', texte)
    cartes = []
    i = 0
    while i < len(symboles):
        c = symboles[i]
        if c == 'X':
            cartes.append(10)
        elif c in VALEURS_CARTES:
            cartes.append(VALEURS_CARTES[c])
        i += 1
    return cartes


def parse_message(texte):
    pattern = r'#N(\d+)\.\s*(\d+)\(([^)]+)\)\s*-\s*(\d+)\(([^)]+)\)\s*#T(\d+)'
    m = re.search(pattern, texte)
    if not m:
        return None
    return {
        'N': int(m.group(1)),
        'J1': int(m.group(2)),
        'cartes_j1': m.group(3),
        'J2': int(m.group(4)),
        'cartes_j2': m.group(5),
        'tour': m.group(6)
    }


def analyser(data):
    N = data['N']
    J1 = data['J1']
    J2 = data['J2']
    tour = data['tour']
    cartes_j1 = parse_cartes(data['cartes_j1'])
    cartes_j2 = parse_cartes(data['cartes_j2'])

    lignes = []
    lignes.append(f"📊 *Analyse #N{N} — T{tour}*")
    lignes.append(f"J1 = {J1} | J2 = {J2}")
    lignes.append("─────────────────")

    if len(cartes_j1) == 5 or len(cartes_j2) == 5:
        lignes.append("🚫 *Abandon — règle F : 5 cartes détectées*")
        if len(cartes_j1) == 5:
            lignes.append(f"  J1 a 5 cartes ({data['cartes_j1']})")
        if len(cartes_j2) == 5:
            lignes.append(f"  J2 a 5 cartes ({data['cartes_j2']})")
        return "\n".join(lignes)

    elig_j1 = J1 < 20
    elig_j2 = 21 < J2 < 30
    if not elig_j1 or not elig_j2:
        lignes.append("❌ *Non éligible*")
        if not elig_j1:
            lignes.append(f"  J1 < 20 : ✗ (J1 = {J1})")
        if not elig_j2:
            lignes.append(f"  21 < J2 < 30 : ✗ (J2 = {J2})")
        return "\n".join(lignes)

    lignes.append("✅ Éligible")

    if not cartes_j2:
        lignes.append("⚠️ Cartes J2 non lisibles")
        return "\n".join(lignes)

    amper = 20 - J1
    lignes.append(f"& = 20 − {J1} = *{amper}*")

    max_carte = max(cartes_j2)
    lignes.append(f"Cartes J2 : {cartes_j2} → max = {max_carte}")

    j2_an = sum(cartes_j2) - max_carte
    lignes.append(f"J2_an = somme(J2) − max = {sum(cartes_j2)} − {max_carte} = *{j2_an}*")

    ecart = J2 - J1
    lignes.append(f"Écart = {J2} − {J1} = *{ecart}*")

    alpha = J1 - ecart + j2_an + amper
    lignes.append(f"alpha = J1 − Écart + J2_an + & = {J1} − {ecart} + {j2_an} + {amper} = *{alpha}*")

    lignes.append(f"alpha > J1 : {alpha} > {J1} {'✅' if alpha > J1 else '❌'}")
    if not (alpha > J1):
        lignes.append("❌ *Échec de validation (alpha ≤ J1) — arrêt*")
        return "\n".join(lignes)

    delta = alpha - J1
    lignes.append(f"delta = alpha − J1 = {alpha} − {J1} = *{delta}*")

    petite_carte_j2 = min(cartes_j2)
    om = delta + petite_carte_j2
    lignes.append(f"Plus petite carte J2 = {petite_carte_j2} → om = delta + petite_carte_j2 = {delta} + {petite_carte_j2} = *{om}*")

    cond1 = om < J1
    lignes.append(f"Condition 1 — om < J1 : {om} < {J1} {'✅' if cond1 else '❌'}")
    if not cond1:
        lignes.append("❌ *Échec de validation (condition 1 : om ≥ J1) — arrêt*")
        return "\n".join(lignes)

    if not cartes_j1:
        lignes.append("⚠️ Cartes J1 non lisibles")
        return "\n".join(lignes)

    petite_carte_j1 = min(cartes_j1)
    cond2 = (J1 - petite_carte_j1) < om
    lignes.append(
        f"Plus petite carte J1 = {petite_carte_j1} → Condition 2 — (J1 − petite_carte_j1) < om : "
        f"{J1 - petite_carte_j1} < {om} {'✅' if cond2 else '❌'}"
    )
    if not cond2:
        lignes.append("❌ *Échec de validation (condition 2) — arrêt*")
        return "\n".join(lignes)

    n_future = N + delta
    lignes.append(f"N_future = N + delta = {N} + {delta} = *N{n_future}*")

    total = J1 + J2

    lignes.append("─────────────────")
    if delta < max_carte:
        lignes.append(f"📡 *Signal : Total + 37,5 = {total} + 37,5 = {total + 37.5}*")
        lignes.append(f"🎯 *À la partie N{n_future}*")
    elif delta > max_carte:
        lignes.append(f"⚠️ *Burst prévu à la partie N{n_future}*")
        lignes.append("J1 ou J2 dépassera strictement 21")
    else:
        lignes.append("➖ *Cas neutre (delta = max_carte) — aucune prédiction émise*")

    return "\n".join(lignes)


# ---------- Lecture auto du canal source + envoi du résultat via le bot ----------
bot = Bot(token=BOT_TOKEN)
client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)


@client.on(events.NewMessage(chats=SOURCE_CHANNEL_ENTITY))
async def on_new_message(event):
    texte = event.message.message or ""
    if not texte or not re.search(r'#N\d+', texte):
        return

    data = parse_message(texte)
    if not data:
        return

    resultat = analyser(data)

    try:
        await bot.send_message(chat_id=CANAL_ID, text=resultat, parse_mode="Markdown")
    except Exception as e:
        print(f"Erreur d'envoi: {e}")


async def run_bot():
    await client.start()
    print("✅ Connecté au canal source, écoute automatique en cours...")
    await client.run_until_disconnected()


def main():
    threading.Thread(target=start_web_server, daemon=True).start()
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
