import random
from dataclasses import dataclass, field
from typing import Optional, List


# ── Datenklassen ─────────────────────────────────────────────────

class Player:
    def __init__(self, user_id: str, username: str, color: str):
        self.user_id = user_id
        self.username = username
        self.color = color
        self.money = 1500
        self.position = 0
        self.properties: List["Field"] = []
        self.in_jail = False
        self.jail_turns = 0
        self.get_out_of_jail_cards = 0
        self.is_bankrupt = False

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "color": self.color,
            "money": self.money,
            "position": self.position,
            "properties": [p.name for p in self.properties],
            "in_jail": self.in_jail,
            "is_bankrupt": self.is_bankrupt,
            "get_out_of_jail_cards": self.get_out_of_jail_cards,
        }


class Field:
    def __init__(self, name: str, field_type: str, price: int = 0,
                 rent: list = None, color_group: str = "special",
                 mortgage_value: int = 0):
        self.name = name
        self.field_type = field_type   # property, station, utility, tax, special, chance, community
        self.price = price
        self.rent = rent or [0]        # [base, 1h, 2h, 3h, 4h, hotel]
        self.color_group = color_group
        self.mortgage_value = mortgage_value
        self.owner: Optional[Player] = None
        self.houses = 0                # 0-4 Häuser, 5 = Hotel
        self.is_mortgaged = False

    def get_rent(self, board: list, owner: "Player") -> int:
        if self.is_mortgaged or self.owner is None:
            return 0
        if self.field_type == "station":
            owned = sum(1 for f in board if f.field_type == "station" and f.owner == owner)
            return 25 * (2 ** (owned - 1))
        if self.field_type == "utility":
            owned = sum(1 for f in board if f.field_type == "utility" and f.owner == owner)
            return None  # Miete wird mit Würfelwurf berechnet
        if self.houses == 0:
            # Wenn Spieler alle der Farbe besitzt: doppelte Grundmiete
            group_fields = [f for f in board if f.color_group == self.color_group and f.field_type == "property"]
            if all(f.owner == owner for f in group_fields):
                return self.rent[0] * 2
            return self.rent[0]
        return self.rent[min(self.houses, len(self.rent) - 1)]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "field_type": self.field_type,
            "price": self.price,
            "color_group": self.color_group,
            "owner": self.owner.username if self.owner else None,
            "owner_color": self.owner.color if self.owner else None,
            "houses": self.houses,
            "is_mortgaged": self.is_mortgaged,
            "mortgage_value": self.mortgage_value,
            "current_rent": self.rent[self.houses] if self.field_type == "property" and self.rent else 0,
        }


# ── Chance / Gemeinschaftsfeld-Karten ───────────────────────────

CHANCE_CARDS = [
    {"text": "Gehe zu Los. Erhalte 200 €.", "action": "goto", "value": 0},
    {"text": "Du erhältst ein Bankfehler zu deinen Gunsten. Erhalte 200 €.", "action": "money", "value": 200},
    {"text": "Du hast eine Strafe erhalten. Zahle 100 €.", "action": "money", "value": -100},
    {"text": "Gehe ins Gefängnis.", "action": "jail", "value": 10},
    {"text": "Gehe zur nächsten Station.", "action": "next_station", "value": 0},
    {"text": "Du gewinnst zweiten Preis in einem Schönheitswettbewerb. Erhalte 10 €.", "action": "money", "value": 10},
    {"text": "Fälligkeit der Schulden. Zahle 50 €.", "action": "money", "value": -50},
    {"text": "Kurreise nach Bad Homburg. Zahle 100 €.", "action": "money", "value": -100},
    {"text": "Du wirst freigelassen! Freie Karte aus dem Gefängnis.", "action": "jail_card", "value": 0},
    {"text": "Rücke 3 Felder zurück.", "action": "move", "value": -3},
]

COMMUNITY_CARDS = [
    {"text": "Du erbst 100 €.", "action": "money", "value": 100},
    {"text": "Arztkosten. Zahle 50 €.", "action": "money", "value": -50},
    {"text": "Steuerrückerstattung: 20 €.", "action": "money", "value": 20},
    {"text": "Gehe zu Los. Erhalte 200 €.", "action": "goto", "value": 0},
    {"text": "Versicherungsfälligkeit. Zahle 50 €.", "action": "money", "value": -50},
    {"text": "Du hast gewonnen! Erhalte 10 €.", "action": "money", "value": 10},
    {"text": "Bankirrtum zu deinen Gunsten. Erhalte 200 €.", "action": "money", "value": 200},
    {"text": "Gehe ins Gefängnis.", "action": "jail", "value": 10},
]


def _create_board() -> List[Field]:
    """Erstellt ein Monopoly-Brett mit 40 Feldern (deutsche Version)."""
    board = [
        Field("Los", "special"),                                               # 0
        Field("Badstraße", "property", 60, [2, 10, 30, 90, 160, 250], "brown", 30),    # 1
        Field("Gemeinschaft", "community"),                                    # 2
        Field("Turmstraße", "property", 60, [4, 20, 60, 180, 320, 450], "brown", 30),  # 3
        Field("Einkommensteuer", "tax", 0, [200]),                             # 4
        Field("Südbahnhof", "station", 200, [25, 50, 100, 200], "station", 100),        # 5
        Field("Chausseestraße", "property", 100, [6, 30, 90, 270, 400, 550], "lightblue", 50),   # 6
        Field("Chance", "chance"),                                             # 7
        Field("Elisenstraße", "property", 100, [6, 30, 90, 270, 400, 550], "lightblue", 50),     # 8
        Field("Poststraße", "property", 120, [8, 40, 100, 300, 450, 600], "lightblue", 60),      # 9
        Field("Gefängnis / Besuch", "special"),                                # 10
        Field("Seestraße", "property", 140, [10, 50, 150, 450, 625, 750], "pink", 70),           # 11
        Field("Elektrizitätswerk", "utility", 150, [0], "utility", 75),       # 12
        Field("Christian Straße", "property", 140, [10, 50, 150, 450, 625, 750], "pink", 70),         # 13
        Field("Neuestraße", "property", 160, [12, 60, 180, 500, 700, 900], "pink", 80),          # 14
        Field("Westbahnhof", "station", 200, [25, 50, 100, 200], "station", 100),                # 15
        Field("Münchnerstraße", "property", 180, [14, 70, 200, 550, 750, 950], "orange", 90),    # 16
        Field("Gemeinschaft", "community"),                                    # 17
        Field("Wienerstraße", "property", 180, [14, 70, 200, 550, 750, 950], "orange", 90),      # 18
        Field("Berlinerstraße", "property", 200, [16, 80, 220, 600, 800, 1000], "orange", 100),  # 19
        Field("Frei Parken", "special"),                                       # 20
        Field("Theaterstraße", "property", 220, [18, 90, 250, 700, 875, 1050], "red", 110),      # 21
        Field("Chance", "chance"),                                             # 22
        Field("Museumsstraße", "property", 220, [18, 90, 250, 700, 875, 1050], "red", 110),      # 23
        Field("Opernplatz", "property", 240, [20, 100, 300, 750, 925, 1100], "red", 120),        # 24
        Field("Nordbahnhof", "station", 200, [25, 50, 100, 200], "station", 100),                # 25
        Field("Lessingstraße", "property", 260, [22, 110, 330, 800, 975, 1150], "yellow", 130),  # 26
        Field("Schillerstraße", "property", 260, [22, 110, 330, 800, 975, 1150], "yellow", 130), # 27
        Field("Wasserwerk", "utility", 150, [0], "utility", 75),               # 28
        Field("Goethestraße", "property", 280, [24, 120, 360, 850, 1025, 1200], "yellow", 140),  # 29
        Field("Gehe ins Gefängnis", "special"),                                # 30
        Field("Rathausplatz", "property", 300, [26, 130, 390, 900, 1100, 1275], "green", 150),   # 31
        Field("Havelstraße", "property", 300, [26, 130, 390, 900, 1100, 1275], "green", 150),    # 32
        Field("Gemeinschaft", "community"),                                    # 33
        Field("Potsdamer Platz", "property", 320, [28, 150, 450, 1000, 1200, 1400], "green", 160), # 34
        Field("Hauptbahnhof", "station", 200, [25, 50, 100, 200], "station", 100),                # 35
        Field("Chance", "chance"),                                             # 36
        Field("Parkstraße", "property", 350, [35, 175, 500, 1100, 1300, 1500], "darkblue", 175), # 37
        Field("Zusatzsteuer", "tax", 0, [100]),                                # 38
        Field("Schlossallee", "property", 400, [50, 200, 600, 1400, 1700, 2000], "darkblue", 200), # 39
    ]
    return board


# ── Spielklasse ──────────────────────────────────────────────────

class Game:
    def __init__(self):
        self.players: List[Player] = []
        self.current_player_index = 0
        self.board = _create_board()
        self.dice_result: Optional[tuple] = None
        self.status_message = "Warte auf Spieler..."
        self.can_buy = False
        self.double_roll_count = 0
        self.chance_deck = CHANCE_CARDS.copy()
        self.community_deck = COMMUNITY_CARDS.copy()
        random.shuffle(self.chance_deck)
        random.shuffle(self.community_deck)
        self.turn_phase = "roll"  # "roll" | "action" | "end"
        self.last_event = None    # Für UI-Animationen

    # ── Spieler ──

    def add_player(self, user_id: str, username: str, color: str) -> bool:
        if len(self.players) >= 6:
            return False
        if any(p.user_id == user_id for p in self.players):
            return False
        self.players.append(Player(user_id, username, color))
        self.status_message = f"{username} ist dem Spiel beigetreten!"
        return True

    # ── Würfeln ──

    def roll_dice(self) -> dict:
        if self.turn_phase != "roll":
            return {"error": "Noch nicht dran"}

        d1, d2 = random.randint(1, 6), random.randint(1, 6)
        self.dice_result = (d1, d2)
        player = self.players[self.current_player_index]
        is_double = d1 == d2

        # Gefängnis-Logik
        if player.in_jail:
            return self._handle_jail_roll(player, d1, d2, is_double)

        # Drei Mal Pasch = Gefängnis
        if is_double:
            self.double_roll_count += 1
            if self.double_roll_count >= 3:
                self._send_to_jail(player)
                self.double_roll_count = 0
                self.turn_phase = "end"
                return {}
        else:
            self.double_roll_count = 0

        self._move_player(player, d1 + d2)
        self.turn_phase = "action" if not is_double else "roll"
        return {}

    def _handle_jail_roll(self, player: Player, d1: int, d2: int, is_double: bool) -> dict:
        if is_double:
            player.in_jail = False
            player.jail_turns = 0
            self.status_message = f"{player.username} würfelt Pasch und kommt frei!"
            self._move_player(player, d1 + d2)
            self.turn_phase = "action"
        else:
            player.jail_turns += 1
            if player.jail_turns >= 3:
                player.money -= 50
                player.in_jail = False
                player.jail_turns = 0
                self.status_message = f"{player.username} zahlt 50 € Kaution und kommt frei."
                self._move_player(player, d1 + d2)
                self.turn_phase = "action"
            else:
                self.status_message = f"{player.username} bleibt im Gefängnis (Runde {player.jail_turns}/3)"
                self.turn_phase = "end"
        return {}

    def _move_player(self, player: Player, steps: int):
        old_pos = player.position
        player.position = (player.position + steps) % 40

        # Über Los
        if player.position < old_pos:
            player.money += 200
            self.status_message = f"{player.username} überquert Los und erhält 200 €!"

        self._handle_field(player)

    def _handle_field(self, player: Player):
        field = self.board[player.position]
        d1, d2 = self.dice_result or (0, 0)
        self.can_buy = False
        self.last_event = None

        # Gehe ins Gefängnis (Feld 30)
        if player.position == 30:
            self._send_to_jail(player)
            return

        # Einkommensteuer (4) / Zusatzsteuer (38)
        if field.field_type == "tax":
            amount = field.rent[0]
            player.money -= amount
            self.status_message = f"{player.username} zahlt {amount} € Steuer."
            self.last_event = {"type": "tax", "amount": amount}
            return

        # Chance-Karte
        if field.field_type == "chance":
            card = self.chance_deck.pop(0)
            self.chance_deck.append(card)
            self._apply_card(player, card)
            return

        # Gemeinschaftskarte
        if field.field_type == "community":
            card = self.community_deck.pop(0)
            self.community_deck.append(card)
            self._apply_card(player, card)
            return

        # Kaufbare Felder
        if field.field_type in ("property", "station", "utility"):
            if field.owner is None and field.price > 0:
                self.status_message = (
                    f"{player.username} landet auf {field.name}. "
                    f"Kaufpreis: {field.price} €."
                )
                self.can_buy = player.money >= field.price
                self.last_event = {"type": "land_empty", "field": field.name, "price": field.price}

            elif field.owner and field.owner != player and not field.is_mortgaged:
                if field.field_type == "utility":
                    rent = (d1 + d2) * (10 if sum(1 for f in self.board if f.field_type == "utility" and f.owner == field.owner) == 2 else 4)
                else:
                    rent = field.get_rent(self.board, field.owner)

                rent = min(rent, player.money)  # Nicht mehr als vorhanden
                player.money -= rent
                field.owner.money += rent
                self.status_message = (
                    f"{player.username} zahlt {rent} € Miete an {field.owner.username}."
                )
                self.last_event = {"type": "rent", "amount": rent, "to": field.owner.username}
                self._check_bankruptcy(player)

            else:
                self.status_message = (
                    f"{player.username} landet auf {field.name}."
                    + (f" (Eigenes Grundstück)" if field.owner == player else "")
                )
        else:
            self.status_message = f"{player.username} landet auf {field.name}."

    def _apply_card(self, player: Player, card: dict):
        action = card["action"]
        value = card["value"]
        self.last_event = {"type": "card", "text": card["text"]}

        if action == "money":
            player.money += value
            self.status_message = f"Karte: {card['text']}"
            if value < 0:
                self._check_bankruptcy(player)

        elif action == "goto":
            old_pos = player.position
            player.position = value
            if old_pos > value:
                player.money += 200
            self.status_message = f"Karte: {card['text']}"
            self._handle_field(player)

        elif action == "jail":
            self._send_to_jail(player)
            self.status_message = f"Karte: {card['text']}"

        elif action == "jail_card":
            player.get_out_of_jail_cards += 1
            self.status_message = f"Karte: {card['text']}"

        elif action == "move":
            player.position = max(0, player.position + value)
            self.status_message = f"Karte: {card['text']}"
            self._handle_field(player)

        elif action == "next_station":
            pos = player.position
            stations = [5, 15, 25, 35]
            next_st = next((s for s in stations if s > pos), stations[0])
            if next_st < pos:
                player.money += 200
            player.position = next_st
            self.status_message = f"Karte: {card['text']}"
            self._handle_field(player)

    def _send_to_jail(self, player: Player):
        player.position = 10
        player.in_jail = True
        player.jail_turns = 0
        self.double_roll_count = 0
        self.status_message = f"{player.username} geht ins Gefängnis!"
        self.last_event = {"type": "jail"}

    def _check_bankruptcy(self, player: Player):
        if player.money < 0:
            player.is_bankrupt = True
            for prop in player.properties:
                prop.owner = None
                prop.houses = 0
            player.properties = []
            self.status_message += f" {player.username} ist bankrott!"
            self.last_event = {"type": "bankrupt", "player": player.username}

    # ── Kaufen ──

    def buy_property(self) -> bool:
        player = self.players[self.current_player_index]
        field = self.board[player.position]

        if (field.field_type not in ("property", "station", "utility")
                or field.owner is not None
                or player.money < field.price
                or field.price == 0):
            return False

        player.money -= field.price
        field.owner = player
        player.properties.append(field)
        self.can_buy = False
        self.status_message = f"{player.username} kauft {field.name} für {field.price} €."
        return True

    # ── Rundenende ──

    def _next_player(self):
        active = [p for p in self.players if not p.is_bankrupt]
        if not active:
            self.status_message = "Kein Spieler mehr übrig."
            return
        idx = (self.current_player_index + 1) % len(self.players)
        while self.players[idx].is_bankrupt:
            idx = (idx + 1) % len(self.players)
        self.current_player_index = idx

    # ── Serialisierung ──

    def to_dict(self) -> dict:
        current = self.players[self.current_player_index] if self.players else None
        return {
            "players": [p.to_dict() for p in self.players],
            "board": [f.to_dict() for f in self.board],
            "current_player": current.username if current else None,
            "current_player_color": current.color if current else None,
            "dice": self.dice_result,
            "status": self.status_message,
            "can_buy": self.can_buy,
            "turn_phase": self.turn_phase,
            "last_event": self.last_event,
        }


# Globale Spielverwaltung (mehrere Spielräume möglich)
active_games: dict[str, Game] = {}