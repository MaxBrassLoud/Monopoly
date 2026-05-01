import os
import hashlib
import random
import string
import requests
from functools import wraps
from flask import Flask, request, jsonify, render_template, redirect, session
from database import create_database, create_user, get_user_by_username
from ID_Creator import create_user_id
from game_logic import Game, active_games
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", os.urandom(32))

DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")

create_database()


# ── Helpers ──────────────────────────────────────────────────

def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated


def generate_room_code() -> str:
    chars = string.ascii_uppercase + string.digits
    while True:
        code = ''.join(random.choices(chars, k=6))
        if code not in active_games:
            return code


def get_room_code():
    return session.get("room_code")


def get_current_game():
    code = get_room_code()
    if not code or code not in active_games:
        return None, None
    return active_games[code], code


# ── Pages ─────────────────────────────────────────────────────

@app.route('/')
@login_required
def home():
    return render_template("dashboard.html", username=session["username"])


@app.route('/login')
def login_page():
    if "user_id" in session:
        return redirect("/")
    return render_template("login.html")


@app.route('/logout')
def logout():
    session.clear()
    return redirect("/login")


@app.route('/monopoly')
@login_required
def monopoly():
    return render_template("monopoly.html", room_code=get_room_code() or "")


# ── Auth ──────────────────────────────────────────────────────

@app.route('/api/v1/register', methods=['POST'])
def register():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    email = data.get("email", "").strip()
    if not username or not password or not email:
        return jsonify({"error": "Alle Felder sind erforderlich"}), 400
    if len(username) < 3 or len(username) > 20:
        return jsonify({"error": "Benutzername muss 3–20 Zeichen lang sein"}), 400
    if len(password) < 6:
        return jsonify({"error": "Passwort muss mindestens 6 Zeichen lang sein"}), 400
    user_id = create_user_id()
    success = create_user(user_id, username, hash_password(password), email)
    if not success:
        return jsonify({"error": "Benutzername oder E-Mail bereits vergeben"}), 409
    return jsonify({"message": "Registrierung erfolgreich"}), 201


@app.route('/api/v1/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        return jsonify({"error": "Benutzername und Passwort erforderlich"}), 400
    user = get_user_by_username(username)
    if not user or user[2] != hash_password(password):
        return jsonify({"error": "Ungültige Anmeldedaten"}), 401
    session["user_id"] = user[0]
    session["username"] = user[1]
    return jsonify({"message": "Login erfolgreich"}), 200


# ── Discord OAuth ─────────────────────────────────────────────

@app.route('/login/discord')
def discord_login():
    url = (
        "https://discord.com/api/oauth2/authorize"
        f"?client_id={DISCORD_CLIENT_ID}"
        "&response_type=code"
        f"&redirect_uri={DISCORD_REDIRECT_URI}"
        "&scope=identify email"
    )
    return redirect(url)


@app.route('/api/v1/discord/callback')
def discord_callback():
    code = request.args.get("code")
    if not code:
        return redirect("/login?error=oauth_failed")
    token_res = requests.post(
        "https://discord.com/api/oauth2/token",
        data={"client_id": DISCORD_CLIENT_ID, "client_secret": DISCORD_CLIENT_SECRET,
              "grant_type": "authorization_code", "code": code, "redirect_uri": DISCORD_REDIRECT_URI},
        headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=10)
    access_token = token_res.json().get("access_token")
    if not access_token:
        return redirect("/login?error=oauth_failed")
    user_res = requests.get("https://discord.com/api/users/@me",
                            headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
    user_data = user_res.json()
    discord_id = user_data.get("id")
    username = user_data.get("username")
    email = user_data.get("email")
    user = get_user_by_username(username)
    if not user:
        user_id = create_user_id()
        create_user(user_id, username, "DISCORD_LOGIN", email, third_party=1, provider=1, ext_user_id=discord_id)
    else:
        user_id = user[0]
    session["user_id"] = user_id
    session["username"] = username
    return redirect("/")


# ── Room API ──────────────────────────────────────────────────

@app.route('/api/room/create', methods=['POST'])
@login_required
def create_room():
    code = generate_room_code()
    game = Game()
    game.host_id = session["user_id"]
    game.host_username = session["username"]
    active_games[code] = game
    session["room_code"] = code
    return jsonify({"code": code, "is_host": True}), 201


@app.route('/api/room/join', methods=['POST'])
@login_required
def join_room():
    data = request.get_json(silent=True) or {}
    code = data.get("code", "").strip().upper()
    if not code or len(code) != 6:
        return jsonify({"error": "Ungültiger Code"}), 400
    if code not in active_games:
        return jsonify({"error": "Raum nicht gefunden"}), 404
    session["room_code"] = code
    return jsonify({"code": code}), 200


@app.route('/api/room/leave', methods=['POST'])
@login_required
def leave_room():
    game, _ = get_current_game()
    if game:
        game.disconnect_player(session["username"])
    session.pop("room_code", None)
    return jsonify({"message": "Raum verlassen"}), 200


@app.route('/api/room/info')
@login_required
def room_info():
    code = get_room_code()
    if not code or code not in active_games:
        return jsonify({"in_room": False}), 200
    game = active_games[code]
    is_host = game.host_id == session.get("user_id","")
    return jsonify({"in_room": True, "code": code, "player_count": len(game.players), "is_host": is_host}), 200


# ── Game State ────────────────────────────────────────────────

@app.route('/api/game/state')
@login_required
def game_state():
    game, _ = get_current_game()
    if not game:
        return jsonify({"error": "Kein Raum beigetreten"}), 400
    # Auto-add player if viewing
    return jsonify(game.to_dict())


# ── Game Actions ──────────────────────────────────────────────

def _require_my_turn(game):
    if not game.players:
        return jsonify({"error": "Kein aktives Spiel"}), 400
    current = game.players[game.current_player_index]
    if current.user_id != session["user_id"]:
        return jsonify({"error": "Du bist nicht dran"}), 403
    return None


@app.route('/api/game/roll', methods=['POST'])
@login_required
def roll_dice():
    game, _ = get_current_game()
    if not game:
        return jsonify({"error": "Kein Raum"}), 400
    err = _require_my_turn(game)
    if err:
        return err
    game.roll_dice()
    return jsonify(game.to_dict())


@app.route('/api/game/buy', methods=['POST'])
@login_required
def buy_property():
    game, _ = get_current_game()
    if not game:
        return jsonify({"error": "Kein Raum"}), 400
    err = _require_my_turn(game)
    if err:
        return err
    success = game.buy_property()
    return jsonify({"success": success, **game.to_dict()})


@app.route('/api/game/build', methods=['POST'])
@login_required
def build_property():
    game, _ = get_current_game()
    if not game:
        return jsonify({"error": "Kein Raum"}), 400
    err = _require_my_turn(game)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    prop = data.get("property", "").strip()
    btype = data.get("type", "house")
    if not prop:
        return jsonify({"error": "Grundstücksname fehlt"}), 400
    result = game.build(prop, btype)
    if not result.get("success"):
        return jsonify({"error": result.get("error", "Bauen fehlgeschlagen")}), 400
    return jsonify(game.to_dict())


@app.route('/api/game/join', methods=['POST'])
@login_required
def join_game():
    game, _ = get_current_game()
    if not game:
        return jsonify({"error": "Kein Raum"}), 400
    data = request.get_json(silent=True) or {}
    color = data.get("color", "blue")
    valid = ["red","green","yellow","blue","purple","orange","pink","teal","lime","white","brown","cyan"]
    if color not in valid:
        return jsonify({"error": f"Ungültige Farbe."}), 400
    if any(p.color == color for p in game.players):
        return jsonify({"error": f"Die Farbe '{color}' ist bereits vergeben. Wähle eine andere."}), 409
    if any(p.user_id == session["user_id"] for p in game.players):
        return jsonify({"error": "Du bist bereits im Spiel"}), 409
    success = game.add_player(session["user_id"], session["username"], color)
    return jsonify({"success": success, **game.to_dict()})


@app.route('/api/game/mortgage', methods=['POST'])
@login_required
def mortgage():
    game, _ = get_current_game()
    if not game:
        return jsonify({"error": "Kein Raum"}), 400
    data = request.get_json(silent=True) or {}
    prop = data.get("property", "").strip()
    action = data.get("action", "take")  # "take" or "lift"
    if not prop:
        return jsonify({"error": "Grundstücksname fehlt"}), 400
    if action == "take":
        result = game.take_mortgage(prop, session["username"])
    else:
        result = game.lift_mortgage(prop, session["username"])
    if not result.get("success"):
        return jsonify({"error": result.get("error", "Fehler")}), 400
    return jsonify(game.to_dict())


@app.route('/api/room/kick', methods=['POST'])
@login_required
def kick_player():
    game, _ = get_current_game()
    if not game:
        return jsonify({"error": "Kein Raum"}), 400
    data = request.get_json(silent=True) or {}
    target = data.get("username", "").strip()
    if not target:
        return jsonify({"error": "Kein Benutzername angegeben"}), 400
    result = game.kick_player(session["user_id"], target)
    if not result.get("success"):
        return jsonify({"error": result.get("error", "Fehler")}), 400
    return jsonify(game.to_dict())


@app.route('/api/game/confirm_card', methods=['POST'])
@login_required
def confirm_card():
    game, _ = get_current_game()
    if not game:
        return jsonify({"error": "Kein Raum"}), 400
    result = game.confirm_card(session["username"])
    if not result.get("success"):
        return jsonify({"error": result.get("error", "Fehler")}), 400
    return jsonify(game.to_dict())


@app.route('/api/game/use_jail_card', methods=['POST'])
@login_required
def use_jail_card():
    game, _ = get_current_game()
    if not game:
        return jsonify({"error": "Kein Raum"}), 400
    result = game.use_jail_card(session["username"])
    if not result.get("success"):
        return jsonify({"error": result.get("error", "Fehler")}), 400
    return jsonify(game.to_dict())


@app.route('/api/game/buy_out_of_jail', methods=['POST'])
@login_required
def buy_out_of_jail():
    game, _ = get_current_game()
    if not game:
        return jsonify({"error": "Kein Raum"}), 400
    result = game.buy_out_of_jail(session["username"])
    if not result.get("success"):
        return jsonify({"error": result.get("error", "Fehler")}), 400
    return jsonify(game.to_dict())


@app.route('/api/game/sell_building', methods=['POST'])
@login_required
def sell_building():
    game, _ = get_current_game()
    if not game:
        return jsonify({"error": "Kein Raum"}), 400
    data = request.get_json(silent=True) or {}
    prop = data.get("property", "").strip()
    sell_type = data.get("type", "house")
    if not prop:
        return jsonify({"error": "Grundstücksname fehlt"}), 400
    result = game.sell_building(prop, sell_type, session["username"])
    if not result.get("success"):
        return jsonify({"error": result.get("error", "Fehler")}), 400
    return jsonify(game.to_dict())


@app.route('/api/game/end_turn', methods=['POST'])
@login_required
def end_turn():
    game, _ = get_current_game()
    if not game:
        return jsonify({"error": "Kein Raum"}), 400
    err = _require_my_turn(game)
    if err:
        return err
    game._next_player()
    game.dice_result = None
    game.can_buy = False
    game.turn_phase = "roll"
    game.status_message = f"{game.players[game.current_player_index].username} ist dran."
    return jsonify(game.to_dict())


# ── Rent Confirmation ─────────────────────────────────────────

@app.route('/api/game/pay_rent', methods=['POST'])
@login_required
def pay_rent():
    game, _ = get_current_game()
    if not game:
        return jsonify({"error": "Kein Raum"}), 400
    result = game.confirm_rent_payment(session["username"])
    if not result.get("success"):
        return jsonify({"error": result.get("error", "Fehler")}), 400
    return jsonify(game.to_dict())


@app.route('/api/game/offer_prop_for_rent', methods=['POST'])
@login_required
def offer_prop_for_rent():
    game, _ = get_current_game()
    if not game:
        return jsonify({"error": "Kein Raum"}), 400
    data = request.get_json(silent=True) or {}
    prop = data.get("property", "").strip()
    result = game.offer_property_for_rent(session["username"], prop)
    if not result.get("success"):
        return jsonify({"error": result.get("error", "Fehler")}), 400
    return jsonify(game.to_dict())


@app.route('/api/game/respond_rent_offer', methods=['POST'])
@login_required
def respond_rent_offer():
    game, _ = get_current_game()
    if not game:
        return jsonify({"error": "Kein Raum"}), 400
    data = request.get_json(silent=True) or {}
    accept = data.get("accept", False)
    result = game.respond_rent_offer(session["username"], accept)
    if not result.get("success"):
        return jsonify({"error": result.get("error", "Fehler")}), 400
    return jsonify(game.to_dict())


# ── Trade API ─────────────────────────────────────────────────

@app.route('/api/trade/send', methods=['POST'])
@login_required
def trade_send():
    game, _ = get_current_game()
    if not game:
        return jsonify({"error": "Kein Raum"}), 400
    data = request.get_json(silent=True) or {}
    to = data.get("to", "").strip()
    my_props = data.get("my_props", [])
    my_money = int(data.get("my_money", 0))
    their_props = data.get("their_props", [])
    their_money = int(data.get("their_money", 0))
    result = game.send_trade(session["username"], to, my_props, my_money, their_props, their_money)
    if not result.get("success"):
        return jsonify({"error": result.get("error", "Fehler")}), 400
    return jsonify(game.to_dict())


@app.route('/api/trade/respond', methods=['POST'])
@login_required
def trade_respond():
    game, _ = get_current_game()
    if not game:
        return jsonify({"error": "Kein Raum"}), 400
    data = request.get_json(silent=True) or {}
    action = data.get("action", "")
    if action not in ("accept", "reject", "counter"):
        return jsonify({"error": "Ungültige Aktion"}), 400
    counter = None
    if action == "counter":
        counter = {
            "my_props": data.get("my_props", []),
            "my_money": int(data.get("my_money", 0)),
            "their_props": data.get("their_props", []),
            "their_money": int(data.get("their_money", 0))
        }
    result = game.respond_trade(session["username"], action, counter)
    if not result.get("success"):
        return jsonify({"error": result.get("error", "Fehler")}), 400
    return jsonify(game.to_dict())


# ── Chat API ──────────────────────────────────────────────────

@app.route('/api/game/chat', methods=['POST'])
@login_required
def chat():
    game, _ = get_current_game()
    if not game:
        return jsonify({"error": "Kein Raum"}), 400
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()[:200]
    if not text:
        return jsonify({"error": "Leere Nachricht"}), 400
    me = next((p for p in game.players if p.username == session["username"]), None)
    color = me.color if me else "blue"
    game.chat_messages.append({
        "type": "chat",
        "from": session["username"],
        "from_color": color,
        "text": text
    })
    return jsonify(game.to_dict())


@app.errorhandler(404)
def not_found(error):
    return render_template("404.html"), 404


if __name__ == '__main__':
    app.run(debug=False, host="0.0.0.0", port=5000)