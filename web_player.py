"""
Simple web interface for Social Turing Test game
Run this instead of player_merged_chat_and_input.py for a chat-like UI
"""

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import secrets
from pathlib import Path

from game_constants import (
    DIRS_PREFIX,
    PERSONAL_CHAT_FILE_FORMAT,
    PERSONAL_VOTE_FILE_FORMAT,
    PERSONAL_STATUS_FILE_FORMAT,
    PUBLIC_MANAGER_CHAT_FILE,
    PUBLIC_DAYTIME_CHAT_FILE,
    REAL_NAMES_FILE,
    REAL_NAME_CODENAME_DELIMITER,
    REMAINING_PLAYERS_FILE,
    JOINED,
    RULES_OF_THE_GAME,
    format_message,
)
from game_status_checks import (
    is_game_over,
    is_time_to_vote,
    all_players_joined,
    get_is_mafia,
    get_role_display_string,
)

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)
CORS(app)

# Global state for each player session (in-memory, per-server-process)
player_states = {}


class WebPlayer:
    """
    Represents one player connected through the web UI.
    Tracks how many lines were already read from each chat file in this session,
    so we only send *new* messages to the browser.
    """

    def __init__(self, game_dir: Path, name: str, is_mafia: bool):
        self.game_dir = game_dir
        self.name = name
        self.is_mafia = is_mafia

        self.personal_chat_file = game_dir / PERSONAL_CHAT_FILE_FORMAT.format(name)
        self.personal_vote_file = game_dir / PERSONAL_VOTE_FILE_FORMAT.format(name)

        # how many lines we have already read from each public chat file
        self.num_read_manager = 0
        self.num_read_daytime = 0

    def get_new_messages(self):
        """
        Read only *new* lines from manager & daytime chat files
        and return them as a list of {text, type} dicts.
        type: "manager" | "chat"
        """
        messages = []

        try:
            # Manager messages (rules, phase announcements, results...)
            manager_file = self.game_dir / PUBLIC_MANAGER_CHAT_FILE
            if manager_file.exists():
                with manager_file.open("r", encoding="utf-8") as f:
                    all_lines = f.readlines()
                    new_lines = all_lines[self.num_read_manager :]
                    # advance cursor by ALL new lines (including blank)
                    self.num_read_manager += len(new_lines)

                    for raw in new_lines:
                        line = raw.strip()
                        if line:
                            messages.append({"text": line, "type": "manager"})

            # Daytime chat (merged messages from all personal files)
            daytime_file = self.game_dir / PUBLIC_DAYTIME_CHAT_FILE
            if daytime_file.exists():
                with daytime_file.open("r", encoding="utf-8") as f:
                    all_lines = f.readlines()
                    new_lines = all_lines[self.num_read_daytime :]
                    self.num_read_daytime += len(new_lines)

                    for raw in new_lines:
                        line = raw.strip()
                        if line:
                            # Detect Game Manager messages by text pattern
                            if "] Game Manager:" in line:
                                messages.append({"text": line, "type": "manager"})
                            else:
                                messages.append({"text": line, "type": "chat"})
        except Exception as e:
            print(f"[WebPlayer] Error reading messages for {self.name}: {e}")

        return messages

    def send_message(self, message: str):
        """Append a personal chat message that the game manager process will merge."""
        formatted = format_message(self.name, message)
        with self.personal_chat_file.open("a", encoding="utf-8") as f:
            f.write(formatted)

    def send_vote(self, voted_name: str):
        """Append a vote for the current voting phase."""
        with self.personal_vote_file.open("a", encoding="utf-8") as f:
            f.write(voted_name + "\n")


@app.route("/")
def index():
    # main HTML template
    return render_template("game.html")


@app.route("/get_players", methods=["POST"])
def get_players():
    """
    Given a game_id, return the list of *real names* that appear in REAL_NAMES_FILE,
    so players can choose themselves from a dropdown.
    """
    data = request.json or {}
    game_id = data.get("game_id")

    game_dir = Path(DIRS_PREFIX) / game_id
    if not game_dir.exists():
        return jsonify({"error": "Game not found"}), 404

    real_names_file = game_dir / REAL_NAMES_FILE
    if not real_names_file.exists():
        return jsonify({"error": "Game not ready"}), 404

    real_names_to_codenames_str = real_names_file.read_text(encoding="utf-8").splitlines()

    real_names = []
    for line in real_names_to_codenames_str:
        if REAL_NAME_CODENAME_DELIMITER in line:
            real_name, _code = line.split(REAL_NAME_CODENAME_DELIMITER, 1)
            real_names.append(real_name)

    return jsonify({"players": real_names})


@app.route("/join", methods=["POST"])
def join_game():
    """
    Map real_name → code name, create a WebPlayer, mark player as JOINED,
    and return session_id + metadata to the browser.
    """
    data = request.json or {}
    game_id = data.get("game_id")
    real_name = data.get("real_name")

    game_dir = Path(DIRS_PREFIX) / game_id
    if not game_dir.exists():
        return jsonify({"error": "Game not found"}), 404

    real_names_file = game_dir / REAL_NAMES_FILE
    real_names_to_codenames_str = real_names_file.read_text(encoding="utf-8").splitlines()

    real_to_code = {}
    for line in real_names_to_codenames_str:
        if REAL_NAME_CODENAME_DELIMITER in line:
            real, code = line.split(REAL_NAME_CODENAME_DELIMITER, 1)
            real_to_code[real] = code

    if real_name not in real_to_code:
        return jsonify({"error": "Name not found in game"}), 404

    code_name = real_to_code[real_name]
    is_mafia = get_is_mafia(code_name, game_dir)

    # Create WebPlayer session
    session_id = secrets.token_hex(8)
    player_states[session_id] = WebPlayer(game_dir, code_name, is_mafia)

    # Mark as joined (same semantics as original CLI client)
    status_file = game_dir / PERSONAL_STATUS_FILE_FORMAT.format(code_name)
    status_file.write_text(JOINED, encoding="utf-8")

    role_display = get_role_display_string(is_mafia) if is_mafia else None

    return jsonify(
        {
            "session_id": session_id,
            "code_name": code_name,
            "is_ai": is_mafia,
            "role": role_display,
            # RULES_OF_THE_GAME is still available if you ever want a static area,
            # but we no longer inject it as a separate chat bubble to avoid duplicates.
            "rules": RULES_OF_THE_GAME,
        }
    )


@app.route("/messages", methods=["POST"])
def get_messages():
    """
    Polling endpoint: the browser calls this every second with a session_id.
    We return:
      - new messages since last poll
      - flags: game_over, can_vote, can_chat, game_started
      - remaining players (for voting)
    """
    data = request.json or {}
    session_id = data.get("session_id")

    if session_id not in player_states:
        return jsonify({"error": "Invalid session"}), 401

    player = player_states[session_id]
    messages = player.get_new_messages()

    game_over = is_game_over(player.game_dir)
    can_vote = is_time_to_vote(player.game_dir)
    game_started = all_players_joined(player.game_dir)

    remaining_players = []
    if can_vote:
        remaining_file = player.game_dir / REMAINING_PLAYERS_FILE
        if remaining_file.exists():
            remaining_players = [
                line.strip()
                for line in remaining_file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

    # chat is only allowed when:
    #   - all players joined
    #   - not voting time
    #   - game not over
    can_chat = game_started and (not can_vote) and (not game_over)

    return jsonify(
        {
            "messages": messages,
            "game_over": game_over,
            "can_vote": can_vote,
            "can_chat": can_chat,
            "game_started": game_started,
            "remaining_players": remaining_players,
        }
    )


@app.route("/send", methods=["POST"])
def send_message():
    """
    Append a chat message to this player's personal chat file.
    We assume the front-end already enforces "only during discussion",
    so here אנחנו רק בודקים תקינות בסיסית.
    """
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
    """
    Append a vote for the current player.
    """
    data = request.json or {}
    session_id = data.get("session_id")
    voted_name = (data.get("voted_name") or "").strip()

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
