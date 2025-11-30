"""
Simple web interface for Social Turing Test game
Run this instead of player_merged_chat_and_input.py for a chat-like UI
"""
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import secrets
from pathlib import Path
from game_constants import *
from game_status_checks import (
    is_game_over,
    is_time_to_vote,
    all_players_joined,
    get_is_mafia,
)

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)
CORS(app)

# Global state for each player session
player_states = {}


class WebPlayer:
    def __init__(self, game_dir: Path, name: str, is_mafia: bool):
        self.game_dir = game_dir
        self.name = name
        self.is_mafia = is_mafia
        self.personal_chat_file = game_dir / PERSONAL_CHAT_FILE_FORMAT.format(name)
        self.personal_vote_file = game_dir / PERSONAL_VOTE_FILE_FORMAT.format(name)
        self.num_read_manager = 0
        self.num_read_daytime = 0

    def get_new_messages(self):
        """Get new messages from all relevant chat files"""
        messages = []
        
        try:
            # Manager messages
            manager_file = self.game_dir / PUBLIC_MANAGER_CHAT_FILE
            if manager_file.exists():
                with open(manager_file, 'r', encoding='utf-8') as f:
                    all_lines = f.readlines()
                    new_lines = all_lines[self.num_read_manager:]
                    # Filter blank lines before counting
                    filtered_lines = [l.strip() for l in new_lines if l.strip()]
                    self.num_read_manager += len(new_lines)  # Count all lines including blanks
                    
                    for line in filtered_lines:
                        messages.append({'text': line, 'type': 'manager'})
                    
                    if filtered_lines:
                        print(f"[WebPlayer] Read {len(filtered_lines)} new manager messages")
            
            # Daytime chat messages
            daytime_file = self.game_dir / PUBLIC_DAYTIME_CHAT_FILE
            if daytime_file.exists():
                with open(daytime_file, 'r', encoding='utf-8') as f:
                    all_lines = f.readlines()
                    new_lines = all_lines[self.num_read_daytime:]
                    # Filter blank lines before counting
                    filtered_lines = [l.strip() for l in new_lines if l.strip()]
                    self.num_read_daytime += len(new_lines)  # Count all lines including blanks
                    
                    for line in filtered_lines:
                        messages.append({'text': line, 'type': 'chat'})
                    
                    if filtered_lines:
                        print(f"[WebPlayer] Read {len(filtered_lines)} new chat messages")
        except Exception as e:
            print(f"[WebPlayer] Error reading messages: {e}")
        
        return messages

    def send_message(self, message: str):
        """Send a chat message (personal file, game manager merges)"""
        formatted = format_message(self.name, message)
        with open(self.personal_chat_file, "a", encoding="utf-8") as f:
            f.write(formatted)

    def send_vote(self, voted_name: str):
        """Send a vote"""
        with open(self.personal_vote_file, "a", encoding="utf-8") as f:
            f.write(voted_name + "\n")


@app.route("/")
def index():
    return render_template("game.html")


@app.route("/get_players", methods=["POST"])
def get_players():
    data = request.json or {}
    game_id = data.get("game_id")

    game_dir = Path(DIRS_PREFIX) / game_id
    if not game_dir.exists():
        return jsonify({"error": "Game not found"}), 404

    real_names_file = game_dir / REAL_NAMES_FILE
    if not real_names_file.exists():
        return jsonify({"error": "Game not ready"}), 404

    real_names_to_codenames_str = real_names_file.read_text(encoding="utf-8").splitlines()
    real_names = [
        line.split(REAL_NAME_CODENAME_DELIMITER)[0]
        for line in real_names_to_codenames_str
        if REAL_NAME_CODENAME_DELIMITER in line
    ]

    return jsonify({"players": real_names})


@app.route("/join", methods=["POST"])
def join_game():
    data = request.json or {}
    game_id = data.get("game_id")
    real_name = data.get("real_name")

    game_dir = Path(DIRS_PREFIX) / game_id
    if not game_dir.exists():
        return jsonify({"error": "Game not found"}), 404

    real_names_file = game_dir / REAL_NAMES_FILE
    real_names_to_codenames_str = real_names_file.read_text(encoding="utf-8").splitlines()
    real_names_to_codenames = dict(
        real_to_code.split(REAL_NAME_CODENAME_DELIMITER)
        for real_to_code in real_names_to_codenames_str
        if REAL_NAME_CODENAME_DELIMITER in real_to_code
    )

    if real_name not in real_names_to_codenames:
        return jsonify({"error": "Name not found in game"}), 404

    name = real_names_to_codenames[real_name]
    is_mafia = get_is_mafia(name, game_dir)

    session_id = secrets.token_hex(8)
    player = WebPlayer(game_dir, name, is_mafia)
    player_states[session_id] = player

    # Mark as joined (כמו ב-player_merged_chat_and_input)
    status_file = game_dir / PERSONAL_STATUS_FILE_FORMAT.format(name)
    status_file.write_text(JOINED, encoding="utf-8")

    role_display = get_role_display_string(is_mafia) if is_mafia else None

    return jsonify(
        {
            "session_id": session_id,
            "code_name": name,
            "is_ai": is_mafia,
            "role": role_display,
            "rules": RULES_OF_THE_GAME,
        }
    )


@app.route("/messages", methods=["POST"])
def get_messages():
    data = request.json or {}
    session_id = data.get("session_id")

    if session_id not in player_states:
        return jsonify({"error": "Invalid session"}), 401

    player = player_states[session_id]
    messages = player.get_new_messages()

    game_over = is_game_over(player.game_dir)
    can_vote = is_time_to_vote(player.game_dir)
    game_started = all_players_joined(player.game_dir)

    remaining = []
    if can_vote:
        remaining_file = player.game_dir / REMAINING_PLAYERS_FILE
        if remaining_file.exists():
            remaining = [
                line.strip()
                for line in remaining_file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

    can_chat = game_started and (not can_vote) and (not game_over)

    return jsonify(
        {
            "messages": messages,
            "game_over": game_over,
            "can_vote": can_vote,
            "can_chat": can_chat,
            "game_started": game_started,
            "remaining_players": remaining,
        }
    )


@app.route("/send", methods=["POST"])
def send_message():
    data = request.json or {}
    session_id = data.get("session_id")
    message = (data.get("message") or "").strip()

    if session_id not in player_states:
        return jsonify({"error": "Invalid session"}), 401

    if not message:
        return jsonify({"error": "Empty message"}), 400

    player = player_states[session_id]
    player.send_message(message)
    return jsonify({"success": True})


@app.route("/vote", methods=["POST"])
def vote():
    data = request.json or {}
    session_id = data.get("session_id")
    voted_name = data.get("voted_name")

    if session_id not in player_states:
        return jsonify({"error": "Invalid session"}), 401

    if not voted_name:
        return jsonify({"error": "No vote"}), 400

    player = player_states[session_id]
    player.send_vote(voted_name)

    return jsonify({"success": True})


if __name__ == "__main__":
    print("Starting Social Turing Test Web Interface...")
    print("Open your browser to: http://localhost:5000")
    app.run(debug=True, host="0.0.0.0", port=5000)
