import re
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

TOKEN = os.environ.get("BOT_TOKEN", "8932137146:AAErqWryYEPzU7Nz3_Llxu3yv__x3vumvlI")
CANAL_ID = int(os.environ.get("CANAL_ID", "-1003839030429"))
PORT = int(os.environ.get("PORT", "10000"))


class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Jeu21 bot is running")

    def log_message(self, format, *args):
        pass  # silence les logs HTTP


def start_web_server():
    server = HTTPServer(("0.0.0.0", PORT), PingHandler)
    server.serve_forever()


VALEURS_CARTES = {
    'A': 11, 'J': 2, 'Q': 3, 'K': 4,
    '2': 2, '3': 3, '4': 4, '5': 5,
    '6': 6, '7': 7, '8': 8, '9': 9, '10': 10
}

# Format strict et complet attendu : #N15. 19(K♣️J♥️8♥️Q♥️J♠️) - 27(A♣️7♦️9♠️) #T46
FORMAT_COMPLET = re.compile(
    r'#N\d+\.\s*\d+\([^)]+\)\s*-\s*\d+\([^)]+\)\s*#T\d+'
)


def parse_cartes(texte):
    """Extrait les valeurs numériques des cartes depuis une chaîne comme K♣️J♥️8♥️"""
    texte = texte.replace('10', 'X')  # protège '10' avant de splitter
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
    """Parse le format : #N15. 19(K♣️J♥️8♥️Q♥️J♠️) - 27(A♣️7♦️9♠️) #T46"""
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
    """Nouvel algorithme d'analyse (remplace entièrement l'ancien)."""
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

    # RÈGLE F — Abandon si J1 ou J2 a 5 cartes
    if len(cartes_j1) == 5 or len(cartes_j2) == 5:
        lignes.append("🚫 *Abandon — règle F : 5 cartes détectées*")
        if len(cartes_j1) == 5:
            lignes.append(f"  J1 a 5 cartes ({data['cartes_j1']})")
        if len(cartes_j2) == 5:
            lignes.append(f"  J2 a 5 cartes ({data['cartes_j2']})")
        return "\n".join(lignes)

    # ÉTAPE 1 — Éligibilité
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

    # ÉTAPE 2 — &
    amper = 20 - J1
    lignes.append(f"& = 20 − {J1} = *{amper}*")

    # ÉTAPE 3 — Plus grande carte de J2
    max_carte = max(cartes_j2)
    lignes.append(f"Cartes J2 : {cartes_j2} → max = {max_carte}")

    # ÉTAPE 4 — J2_an (somme des cartes de J2 sauf sa plus grande, un seul exemplaire retiré)
    j2_an = sum(cartes_j2) - max_carte
    lignes.append(f"J2_an = somme(J2) − max = {sum(cartes_j2)} − {max_carte} = *{j2_an}*")

    # ÉTAPE 5 — Écart
    ecart = J2 - J1
    lignes.append(f"Écart = {J2} − {J1} = *{ecart}*")

    # ÉTAPE 6 — alpha
    alpha = J1 - ecart + j2_an + amper
    lignes.append(f"alpha = J1 − Écart + J2_an + & = {J1} − {ecart} + {j2_an} + {amper} = *{alpha}*")

    # ÉTAPE 7 — Vérification alpha > J1
    lignes.append(f"alpha > J1 : {alpha} > {J1} {'✅' if alpha > J1 else '❌'}")
    if not (alpha > J1):
        lignes.append("❌ *Échec de validation (alpha ≤ J1) — arrêt*")
        return "\n".join(lignes)

    # ÉTAPE 8 — delta
    delta = alpha - J1
    lignes.append(f"delta = alpha − J1 = {alpha} − {J1} = *{delta}*")

    if not cartes_j1:
        lignes.append("⚠️ Cartes J1 non lisibles")
        return "\n".join(lignes)

    # ÉTAPE 9 — Vérifications (om = delta + plus petite carte de J2)
    petite_carte_j2 = min(cartes_j2)
    petite_carte_j1 = min(cartes_j1)
    om = delta + petite_carte_j2
    lignes.append(f"Plus petite carte J2 = {petite_carte_j2} → om = delta + petite_carte_j2 = {delta} + {petite_carte_j2} = *{om}*")

    cond1 = om >= J1
    lignes.append(f"Condition 1 — om ≥ J1 : {om} ≥ {J1} {'✅' if cond1 else '❌'}")
    if cond1:
        lignes.append("❌ *Échec de validation (condition 1 : om ≥ J1) — arrêt*")
        return "\n".join(lignes)

    cond_delta_j2 = petite_carte_j2 == delta
    cond_delta_j1 = petite_carte_j1 == delta
    lignes.append(
        f"Plus petite carte J1 = {petite_carte_j1} → Vérification : "
        f"petite_carte_j2 ≠ delta ({petite_carte_j2} ≠ {delta}) "
        f"{'✅' if not cond_delta_j2 else '❌'} | "
        f"petite_carte_j1 ≠ delta ({petite_carte_j1} ≠ {delta}) "
        f"{'✅' if not cond_delta_j1 else '❌'}"
    )
    if cond_delta_j2 or cond_delta_j1:
        lignes.append("❌ *Échec de validation (petite carte = delta) — arrêt*")
        return "\n".join(lignes)

    # ÉTAPE 11 — Partie future
    n_future = N + delta
    lignes.append(f"N_future = N + delta = {N} + {delta} = *N{n_future}*")

    total = J1 + J2
    comparateur = J1 - petite_carte_j1

    # ÉTAPE 10 — Prédiction selon (J1 − petite_carte_j1) vs om
    lignes.append("─────────────────")
    lignes.append(f"(J1 − petite_carte_j1) = {J1} − {petite_carte_j1} = *{comparateur}*")
    if comparateur < om:
        lignes.append(f"⚠️ *Burst prévu à la partie N{n_future}*")
        lignes.append("J1 ou J2 dépassera strictement 21")
    elif comparateur > om:
        lignes.append(f"📡 *Signal : Total + 37,5 = {total} + 37,5 = {total + 37.5}*")
        lignes.append(f"🎯 *À la partie N{n_future}*")
    else:
        lignes.append("➖ *Cas neutre ((J1 − petite_carte_j1) = om) — aucune prédiction émise*")

    return "\n".join(lignes)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.channel_post
    if not msg:
        return

    texte = msg.text or msg.caption or ""
    if not texte:
        return

    # Condition stricte : le message doit contenir le format COMPLET
    # #Nxxxx. xx(...) - yy(...) #Txx avant toute tentative d'analyse.
    # findall() (et non un simple "#N123" isolé) évite les faux
    # déclenchements sur des messages partiels ou mal formés.
    if not FORMAT_COMPLET.search(texte):
        return

    # Une seule analyse envoyée par message, même si le format complet
    # apparaît plusieurs fois dans le même texte : on ne traite que la
    # première occurrence trouvée par parse_message.
    data = parse_message(texte)
    if not data:
        return

    resultat = analyser(data)

    await context.bot.send_message(
        chat_id=CANAL_ID,
        text=resultat,
        parse_mode="Markdown"
    )


def main():
    threading.Thread(target=start_web_server, daemon=True).start()

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL, handle_message))
    print("✅ Bot Jeu21 démarré...")
    app.run_polling()


if __name__ == "__main__":
    main()
