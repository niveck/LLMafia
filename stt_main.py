import json
import os
from game_constants import *  # incl. argparse, time, Path (from pathlib), colored (from termcolor)

# global variable for the game dir
game_dir = Path()  # will be updated only if __name__ == __main__ (prevents new ones in imports)

class Player:

    def __init__(self, name, is_ai, **kwargs):
        self.name = name
        self.is_ai = is_ai
        self.personal_chat_file = game_dir / PERSONAL_CHAT_FILE_FORMAT.format(self.name)
        self.personal_chat_file_lines_read = 0
        self.personal_vote_file = game_dir / PERSONAL_VOTE_FILE_FORMAT.format(self.name)
        self.personal_vote_file_lines_read = 0
        # status is whether the player has joined and then whether was voted out
        self.personal_status_file = game_dir / PERSONAL_STATUS_FILE_FORMAT.format(self.name)

    def get_new_messages(self):
        with open(self.personal_chat_file, "r", encoding="utf-8", errors="ignore") as f:
            # the readlines method includes the "\n"
            lines = f.readlines()[self.personal_chat_file_lines_read:]
        self.personal_chat_file_lines_read += len(lines)
        return lines

    def get_voted_player(self):
        all_votes = self.personal_vote_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        new_votes = all_votes[self.personal_vote_file_lines_read:]
        if new_votes:
            self.personal_vote_file_lines_read += len(new_votes)  # should be 1 if works correctly
            return new_votes[-1].strip()
        else:
            return None

    def eliminate(self):
        self.personal_status_file.write_text(VOTED_OUT)

def get_config():
    with open(game_dir / GAME_CONFIG_FILE, "r", encoding="utf-8", errors="ignore") as f:
        config = json.load(f)
    return config

def get_players(config):
    return [Player(**player_config) for player_config in config[PLAYERS_KEY_IN_CONFIG]]

def is_game_over(players):
    """
    Social Turing Test win conditions:
    - Humans win: AI is eliminated (0 mafia players remaining)
    - AI wins: Only 2 players remain (AI + 1 human)
    """
    ai_players = [player for player in players if player.is_ai]
    human_players = [player for player in players if not player.is_ai]
    
    # Humans win if AI is eliminated
    if len(ai_players) == 0:
        (game_dir / WHO_WINS_FILE).write_text(HUMANS_WIN_MESSAGE)
        return True
    
    # AI wins if only 2 players remain (AI + 1 human)
    if len(players) == 2 and len(ai_players) == 1:
        (game_dir / WHO_WINS_FILE).write_text(AI_WINS_MESSAGE)
        return True
    
    return False

def run_chat_round_between_players(players, chat_room):
    for player in players:
        lines = player.get_new_messages()
        with open(chat_room, "a", encoding="utf-8") as f:
            f.writelines(lines)  # lines already include "\n"

def notify_players_about_voting_time(phase_name, public_chat_file):
    phase_end_message = DAYTIME_VOTING_TIME_MESSAGE
    with open(public_chat_file, "a", encoding="utf-8") as f:  # only to the current phase's active players chat room
        f.write(format_message(GAME_MANAGER_NAME, phase_end_message))
    voting_phase_name = DAYTIME_VOTING_TIME
    (game_dir / PHASE_STATUS_FILE).write_text(voting_phase_name)

def get_voted_out_name(optional_votes_players, public_chat_file, voting_players, anonymous_voting=False):
    votes = {player.name: 0 for player in optional_votes_players}
    vote_details = []  # Collect who voted for whom
    
    while voting_players:
        voted_players = []
        for player in voting_players:
            voted_for = player.get_voted_player()
            if not voted_for:
                continue
            voted_players.append(player)
            if voted_for in votes:
                vote_details.append((player.name, voted_for))
                votes[voted_for] += 1
        for player in voted_players:
            voting_players.remove(player)
    
    # if there were invalid votes or if there was a tie, decision will be made "randomly"
    voted_out_name = max(votes, key=votes.get)
    
    # Write ONE unified voting results message
    with open(public_chat_file, "a", encoding="utf-8") as f:
        f.write(format_message(GAME_MANAGER_NAME, "Voting results:"))
        
        if not anonymous_voting:
            # Show who voted for whom
            for voter, voted_for in vote_details:
                f.write(format_message(GAME_MANAGER_NAME, f"  {voter} → {voted_for}"))
            f.write(format_message(GAME_MANAGER_NAME, ""))  # blank line separator
        
        # Show summary (sorted by vote count, descending)
        f.write(format_message(GAME_MANAGER_NAME, "Summary:"))
        sorted_votes = sorted(votes.items(), key=lambda x: x[1], reverse=True)
        for player_name, vote_count in sorted_votes:
            plural = "vote" if vote_count == 1 else "votes"
            f.write(format_message(GAME_MANAGER_NAME, f"  {player_name}: {vote_count} {plural}"))
    
    return voted_out_name

def voting_sub_phase(phase_name, voting_players, optional_votes_players, public_chat_file, players, anonymous_voting=False):
    notify_players_about_voting_time(phase_name, public_chat_file)
    voted_out_name = get_voted_out_name(optional_votes_players, public_chat_file, voting_players[:], anonymous_voting)
    # update info file of remaining players
    remaining_players = (game_dir / REMAINING_PLAYERS_FILE).read_text(encoding="utf-8", errors="ignore").splitlines()
    remaining_players.remove(voted_out_name)
    (game_dir / REMAINING_PLAYERS_FILE).write_text("\n".join(remaining_players))
    # update player object status
    voted_out_player = {player.name: player for player in optional_votes_players}[voted_out_name]
    voted_out_player.eliminate()
    players.remove(voted_out_player)
    announce_voted_out_player(voted_out_player)

def game_manager_announcement(message):
    with open(game_dir / PUBLIC_MANAGER_CHAT_FILE, "a", encoding="utf-8") as f:
        f.write(format_message(GAME_MANAGER_NAME, message))

def announce_voted_out_player(voted_out_player):
    role = get_role_display_string(voted_out_player.is_ai)
    voted_out_message = VOTED_OUT_MESSAGE_FORMAT.format(voted_out_player.name, role)
    game_manager_announcement(voted_out_message)

def run_phase(players, voting_players, optional_votes_players, public_chat_file,
              time_limit_seconds, phase_name, anonymous_voting=False):
    if len(voting_players) > 1:
        start_time = time.time()
        while time.time() - start_time < time_limit_seconds:
            run_chat_round_between_players(voting_players, public_chat_file)
    else:
        game_manager_announcement(CUTTING_TO_VOTE_MESSAGE)
    print("Now voting starts...")
    voting_sub_phase(phase_name, voting_players, optional_votes_players, public_chat_file, players, anonymous_voting)

def run_daytime(players, daytime_minutes, anonymous_voting=False):
    """Run discussion phase where all players can communicate and vote"""
    (game_dir / PHASE_STATUS_FILE).write_text(DAYTIME)
    print(colored(DAYTIME_START_MESSAGE_FORMAT.format(daytime_minutes), DAYTIME_COLOR))
    game_manager_announcement(DAYTIME_START_MESSAGE_FORMAT.format(daytime_minutes))
    run_phase(players, players, players, game_dir / PUBLIC_DAYTIME_CHAT_FILE,
              minutes_to_seconds(daytime_minutes), DAYTIME, anonymous_voting)

def wait_for_players(players):
    havent_joined_yet = [player for player in players]
    print("Waiting for all players to connect and start running their programs to join:")
    print(",  ".join([player.name for player in havent_joined_yet]))
    while havent_joined_yet:
        joined = []
        for player in havent_joined_yet:
            if bool(player.personal_status_file.read_text(encoding="utf-8", errors="ignore")):  # file isn't empty once joined
                joined.append(player)
                print(f"{player.name} has joined!")
        for player in joined:
            havent_joined_yet.remove(player)
    (game_dir / GAME_START_TIME_FILE).write_text(get_current_timestamp())
    print("Game is now running! Its content is displayed to players.")

def get_all_player_out_of_voting_time():
    current_phase = (game_dir / PHASE_STATUS_FILE).read_text(encoding="utf-8", errors="ignore")
    (game_dir / PHASE_STATUS_FILE).write_text(current_phase.replace(VOTING_TIME, ""))

def end_game():
    get_all_player_out_of_voting_time()
    print("Game has finished.")

def main():
    global game_dir
    game_dir = get_game_dir_from_argv()
    config = get_config()
    players = get_players(config)
    anonymous_voting = config.get(ANONYMOUS_VOTING_KEY, False)
    wait_for_players(players)
    # Social Turing Test: Only day phases (discussion + voting), no night phase
    while not is_game_over(players):
        run_daytime(players, config[DAYTIME_MINUTES_KEY], anonymous_voting)
    end_game()

if __name__ == '__main__':
    main()
