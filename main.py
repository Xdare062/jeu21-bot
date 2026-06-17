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

def est_paire_as(cartes):
    """Vrai si la main est composée exactement de deux As (A+A = 21)."""
    return len(cartes) == 2 and all(c == 11 for c in cartes)


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

    # RÈGLE A — Anomalie paire d'As (J1 ou J2)
    if est_paire_as(cartes_j1) or est_paire_as(cartes_j2):
        lignes.append("🚫 *Anomalie — paire d'As détectée*")
        if est_paire_as(cartes_j1):
            lignes.append(f"  J1 = A+A = 22 ({data['cartes_j1']})")
        if est_paire_as(cartes_j2):
            lignes.append(f"  J2 = A+A = 22 ({data['cartes_j2']})")
        lignes.append("Partie ignorée — pas d'analyse.")
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

    # ÉTAPE 2 — &
    amper = 20 - J1
    lignes.append(f"& = 20 − {J1} = *{amper}*")

    # ÉTAPE 3+4 — Diff
    if not cartes_j2:
        lignes.append("⚠️ Cartes J2 non lisibles")
        return "\n".join(lignes)

    max_carte = max(cartes_j2)
    sum_autres = sum(cartes_j2) - max_carte
    diff = sum_autres - max_carte
    lignes.append(f"Cartes J2 : {cartes_j2} → max = {max_carte}")
    lignes.append(f"Diff = {sum_autres} − {max_carte} = *{diff}*")

    # ÉTAPE 5 — Écart
    ecart = J2 - J1
    lignes.append(f"Écart = {J2} − {J1} = *{ecart}*")

    # ÉTAPE 6 — Vérif Diff ≤ Écart
    check_diff = diff <= ecart
    lignes.append(f"Diff ≤ Écart : {diff} ≤ {ecart} {'✅' if check_diff else '❌'}")

    if not check_diff:
        lignes.append("❌ *Condition non remplie — arrêt*")
        return "\n".join(lignes)

    # ÉTAPE 7 — @
    at = diff + amper
    lignes.append(f"@ = {diff} + {amper} = *{at}*")

    # NOUVELLE RÈGLE — Abandon si (Écart + sum_autres − J1) > &
    resultat_regle = ecart + sum_autres - J1
    lignes.append(
        f"Vérif. abandon (règle 1) : Écart + sum_autres − J1 = {ecart} + {sum_autres} − {J1} = {resultat_regle} "
        f"(comparé à & = {amper})"
    )
    if resultat_regle > amper:
        lignes.append(f"🚫 *Condition d'abandon remplie ({resultat_regle} > {amper}) — partie abandonnée*")
        return "\n".join(lignes)

    # RÈGLE B — Abandon si (Écart + &) + une carte de J2 = J1
    somme_b = ecart + amper
    cartes_en_cause = [c for c in cartes_j2 if somme_b + c == J1]
    if cartes_en_cause:
        lignes.append(
            f"Vérif. abandon (règle B) : (Écart + &) = {ecart} + {amper} = {somme_b} ; "
            f"+ carte({cartes_en_cause[0]}) = {somme_b + cartes_en_cause[0]} = J1"
        )
        lignes.append("🚫 *Condition d'abandon remplie (règle B) — partie abandonnée*")
        return "\n".join(lignes)

    # ÉTAPE 8 — Vérif @ ≤ Écart
    check_at = at <= ecart
    lignes.append(f"@ ≤ Écart : {at} ≤ {ecart} {'✅' if check_at else '❌'}")

    if not check_at:
        lignes.append("❌ *Condition non remplie — arrêt*")
        return "\n".join(lignes)

    # ÉTAPE 9 — Partie future
    n_future = N + at
    lignes.append(f"N_future = {N} + {at} = *N{n_future}*")

    # SIGNAL
    lignes.append("─────────────────")
    lignes.append(f"📡 *Signal : J1 + 19,5*")
    lignes.append(f"🎯 *À la partie N{n_future}*")

    # CAS PARTICULIER
    if at == ecart:
        lignes.append("─────────────────")
        lignes.append(f"⚠️ *Cas particulier — @ = Écart ({at} = {ecart})*")
        lignes.append(f"À N{n_future} : J1 ou Croupier dépassera 21")

    return "\n".join(lignes)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.channel_post
    if not msg:
        return

    texte = msg.text or msg.caption or ""
    if not texte:
        return

    # Vérifier que c'est bien un message de partie
    if not re.search(r'#N\d+', texte):
        return

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
    # Démarre le serveur web factice en arrière-plan (pour satisfaire Render)
    threading.Thread(target=start_web_server, daemon=True).start()

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL, handle_message))
    print("✅ Bot Jeu21 démarré...")
    app.run_polling()


if __name__ == "__main__":
    main()
