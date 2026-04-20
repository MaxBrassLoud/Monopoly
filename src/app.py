import os
import hashlib
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


# ── Hilfsfunktionen ──────────────────────────────────────────────

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def login_required(f):
    """Decorator: Leitet nicht eingeloggte Nutzer zur Login-Seite um."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated


def get_or_create_game(game_id: str = "default") -> Game:
    """Gibt das aktive Spiel zurück oder erstellt eines."""
    if game_id not in active_games:
        active_games[game_id] = Game()
    return active_games[game_id]


# ── Seiten ───────────────────────────────────────────────────────

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
    return render_template("monopoly.html")


# ── Auth API ─────────────────────────────────────────────────────

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


# ── Discord OAuth ────────────────────────────────────────────────

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
        data={
            "client_id": DISCORD_CLIENT_ID,
            "client_secret": DISCORD_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": DISCORD_REDIRECT_URI,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )
    access_token = token_res.json().get("access_token")
    if not access_token:
        return redirect("/login?error=oauth_failed")

    user_res = requests.get(
        "https://discord.com/api/users/@me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    user_data = user_res.json()
    discord_id = user_data.get("id")
    username = user_data.get("username")
    email = user_data.get("email")

    user = get_user_by_username(username)
    if not user:
        user_id = create_user_id()
        create_user(user_id, username, "DISCORD_LOGIN", email,
                    third_party=1, provider=1, ext_user_id=discord_id)
    else:
        user_id = user[0]

    session["user_id"] = user_id
    session["username"] = username
    return redirect("/")


# ── Game API ─────────────────────────────────────────────────────

@app.route('/api/game/state')
@login_required
def game_state():
    game = get_or_create_game()
    if not any(p.user_id == session["user_id"] for p in game.players):
        game.add_player(session["user_id"], session["username"], "blue")
    return jsonify(game.to_dict())


@app.route('/api/game/roll', methods=['POST'])
@login_required
def roll_dice():
    game = get_or_create_game()
    if not game.players:
        return jsonify({"error": "Kein aktives Spiel"}), 400

    current = game.players[game.current_player_index]
    if current.user_id != session["user_id"]:
        return jsonify({"error": "Du bist nicht dran"}), 403

    result = game.roll_dice()
    return jsonify(game.to_dict())


@app.route('/api/game/buy', methods=['POST'])
@login_required
def buy_property():
    game = get_or_create_game()
    if not game.players:
        return jsonify({"error": "Kein aktives Spiel"}), 400

    current = game.players[game.current_player_index]
    if current.user_id != session["user_id"]:
        return jsonify({"error": "Du bist nicht dran"}), 403

    success = game.buy_property()
    return jsonify({"success": success, "game": game.to_dict()})


@app.route('/api/game/join', methods=['POST'])
@login_required
def join_game():
    game = get_or_create_game()
    data = request.get_json(silent=True) or {}
    color = data.get("color", "red")

    valid_colors = ["red", "green", "yellow", "blue", "purple", "orange"]
    if color not in valid_colors:
        return jsonify({"error": f"Ungültige Farbe. Wähle aus: {', '.join(valid_colors)}"}), 400

    if any(p.user_id == session["user_id"] for p in game.players):
        return jsonify({"error": "Du bist bereits im Spiel"}), 409

    success = game.add_player(session["user_id"], session["username"], color)
    return jsonify({"success": success, "game": game.to_dict()})


@app.route('/api/game/end_turn', methods=['POST'])
@login_required
def end_turn():
    game = get_or_create_game()
    if not game.players:
        return jsonify({"error": "Kein aktives Spiel"}), 400

    current = game.players[game.current_player_index]
    if current.user_id != session["user_id"]:
        return jsonify({"error": "Du bist nicht dran"}), 403

    game._next_player()
    game.dice_result = None
    game.can_buy = False
    game.status_message = f"{game.players[game.current_player_index].username} ist dran."
    return jsonify(game.to_dict())


@app.route('/api/game/reset', methods=['POST'])
@login_required
def reset_game():
    active_games["default"] = Game()
    return jsonify({"message": "Spiel zurückgesetzt"})


if __name__ == '__main__':
    app.run(debug=False)