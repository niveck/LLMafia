from game_constants import *  # incl. argparse, time, Path (from pathlib), colored (from termcolor)
from game_status_checks import is_game_over, is_time_to_vote, all_players_joined, get_is_ai

def welcome_player(game_dir):
    print(colored(PARTICIPATION_CONSENT_MESSAGE + "\n", CONSENT_COLOR))
    print(colored(WELCOME_MESSAGE + "\n", MANAGER_COLOR))
    print(colored(RULES_OF_THE_GAME_TITLE, MANAGER_COLOR, attrs=["underline"]))
    print(colored(RULES_OF_THE_GAME + "\n", MANAGER_COLOR))
    name, real_name = get_player_name_and_real_name_from_user(game_dir)
    print(colored(CODE_NAME_REVELATION_MESSAGE_FORMAT.format(real_name), MANAGER_COLOR))
    print(colored(name, MANAGER_COLOR, attrs=["bold"]))
    is_ai = get_is_ai(name, game_dir)
    
    # Show role information
    if is_ai:
        # AI player sees their role
        role = get_role_display_string(is_ai)
        print(colored(ROLE_REVELATION_MESSAGE, MANAGER_COLOR))
        print(colored(role, MANAGER_COLOR, attrs=["bold"]))
        print(colored(OTHER_MAFIA_NAMES_MESSAGE, MANAGER_COLOR))
    else:
        # Human players just see spacing
        print()
    
    # Inform about number of AI players (always 1 in Social Turing Test)
    print(colored(ONLY_ONE_MAFIA_MESSAGE_START, MANAGER_COLOR),
          colored(ONLY_ONE_MAFIA_MESSAGE_BOLD, MANAGER_COLOR, attrs=["bold", "underline"]),
          colored(ONLY_ONE_MAFIA_MESSAGE_END, MANAGER_COLOR))
    print()
    
    (game_dir / PERSONAL_STATUS_FILE_FORMAT.format(name)).write_text(JOINED)
    print(colored(WAITING_FOR_ALL_PLAYERS_TO_JOIN_MESSAGE, MANAGER_COLOR))
    while not all_players_joined(game_dir):
        continue
    # The game manager automatically posts a message that will be printed when the game starts
    return name, is_ai  # name is used only in the joint read-and-write interface (with threads)

def display_lines_from_file(game_dir, file_name, num_read_lines, display_color):
    with open(game_dir / file_name, "r") as f:
        lines = f.readlines()[num_read_lines:]
    if len(lines) > 0:  # this `if` in needed because of `print()` that is used for multithreading
        print()  # prevents the messages from being printed in the same line as the middle of input
        for line in lines:
            print(colored(line.strip(), display_color))
    return len(lines)

def ask_player_to_vote():
    print(colored(VOTE_INSTRUCTION_MESSAGE, MANAGER_COLOR))

def ask_player_to_vote_only_once(already_asked, game_dir):
    """Ask player to vote when it's voting time (no nighttime restrictions in STT)"""
    if is_time_to_vote(game_dir):
        if not already_asked:
            ask_player_to_vote()
            already_asked = True
    else:
        already_asked = False
    return already_asked

def read_game_text_loop(is_ai, game_dir):
    """Main loop to display game messages (no nighttime chat in Social Turing Test)"""
    num_read_lines_manager = num_read_lines_daytime = 0
    already_asked = False
    while not is_game_over(game_dir):
        num_read_lines_manager += display_lines_from_file(
            game_dir, PUBLIC_MANAGER_CHAT_FILE, num_read_lines_manager, MANAGER_COLOR)
        # In Social Turing Test, everyone sees all daytime messages
        num_read_lines_daytime += display_lines_from_file(
            game_dir, PUBLIC_DAYTIME_CHAT_FILE, num_read_lines_daytime, DAYTIME_COLOR)
        already_asked = ask_player_to_vote_only_once(already_asked, game_dir)

def game_over_message(game_dir):
    who_wins = (game_dir / WHO_WINS_FILE).read_text().strip()
    print(colored(who_wins, MANAGER_COLOR))
    ai_player_names = (game_dir / AI_PLAYER_FILE).read_text().splitlines()  # removes the "\n"
    print(colored(MAFIA_REVELATION_MESSAGE, MANAGER_COLOR),
          colored(", ".join(ai_player_names), MANAGER_COLOR, attrs=["bold"]))

def main():
    game_dir = get_game_dir_from_argv()
    _, is_ai = welcome_player(game_dir)
    read_game_text_loop(is_ai, game_dir)
    game_over_message(game_dir)

if __name__ == '__main__':
    main()
