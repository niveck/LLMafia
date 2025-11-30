from game_constants import *  # incl. argparse, time, Path (from pathlib), colored (from termcolor)
from game_status_checks import is_game_over, is_time_to_vote, all_players_joined, get_is_mafia, \
    is_nighttime


def introducing_mafia_members(game_dir, is_mafia, name):
    mafia_names = (game_dir / MAFIA_NAMES_FILE).read_text().splitlines()
    if len(mafia_names) > 1:
        start = HOW_MANY_MAFIA_MESSAGE_START
        bold = len(mafia_names)
        end = HOW_MANY_MAFIA_MESSAGE_END
        introduce_other_mafia = True
    else:
        start = ONLY_ONE_MAFIA_MESSAGE_START
        bold = ONLY_ONE_MAFIA_MESSAGE_BOLD
        end = ONLY_ONE_MAFIA_MESSAGE_END
        introduce_other_mafia = False
    print(colored(start, MANAGER_COLOR), colored(bold, MANAGER_COLOR, attrs=["bold", "underline"]),
          colored(end, MANAGER_COLOR))
    if introduce_other_mafia:
        if is_mafia:
            other_mafia_names = [other_name for other_name in mafia_names if other_name != name]
            print(colored(OTHER_MAFIA_NAMES_MESSAGE, MANAGER_COLOR),
                  colored(", ".join(other_mafia_names), NIGHTTIME_COLOR), "\n")
        else:
            print(colored(MAFIA_KNOW_EACH_OTHER_MESSAGE, MANAGER_COLOR), "\n")
    else:
        print()


def welcome_player(game_dir):
    print(colored(PARTICIPATION_CONSENT_MESSAGE + "\n", CONSENT_COLOR))
    print(colored(WELCOME_MESSAGE + "\n", MANAGER_COLOR))
    print(colored(RULES_OF_THE_GAME_TITLE, MANAGER_COLOR, attrs=["underline"]))
    print(colored(RULES_OF_THE_GAME + "\n", MANAGER_COLOR))
    name, real_name = get_player_name_and_real_name_from_user(game_dir)
    print(colored(CODE_NAME_REVELATION_MESSAGE_FORMAT.format(real_name), MANAGER_COLOR))
    print(colored(name, MANAGER_COLOR, attrs=["bold"]))
    is_mafia = get_is_mafia(name, game_dir)
    
    # Only show role for AI player
    if is_mafia:
        role = get_role_display_string(is_mafia)
        role_color = NIGHTTIME_COLOR
        print(colored(ROLE_REVELATION_MESSAGE, MANAGER_COLOR))
        print(colored(role + "\n", role_color))
    else:
        print()  # Just add spacing for human players
    
    (game_dir / PERSONAL_STATUS_FILE_FORMAT.format(name)).write_text(JOINED)
    introducing_mafia_members(game_dir, is_mafia, name)
    print(colored(WAITING_FOR_ALL_PLAYERS_TO_JOIN_MESSAGE, MANAGER_COLOR))
    while not all_players_joined(game_dir):
        continue
    # The game manager automatically posts a message that will be printed when the game starts
    return name, is_mafia  # name is used only in the joint read-and-write interface (with threads)


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


def ask_player_to_vote_only_once(already_asked, game_dir, is_mafia):
    if is_time_to_vote(game_dir):
        # leaving the is_nighttime check to the end because it's expensive and might not be needed
        if not already_asked and (is_mafia or not is_nighttime(game_dir)):
            ask_player_to_vote()
            already_asked = True
    else:
        already_asked = False
    return already_asked


def read_game_text_loop(is_mafia, game_dir):
    num_read_lines_manager = num_read_lines_daytime = num_read_lines_nighttime = 0
    already_asked = False
    while not is_game_over(game_dir):
        num_read_lines_manager += display_lines_from_file(
            game_dir, PUBLIC_MANAGER_CHAT_FILE, num_read_lines_manager, MANAGER_COLOR)
        # only current phase file will have new messages, so no need to run expensive is_nighttime()
        num_read_lines_daytime += display_lines_from_file(
            game_dir, PUBLIC_DAYTIME_CHAT_FILE, num_read_lines_daytime, DAYTIME_COLOR)
        if is_mafia:  # only mafia can see what happens during nighttime
            num_read_lines_nighttime += display_lines_from_file(
                game_dir, PUBLIC_NIGHTTIME_CHAT_FILE, num_read_lines_nighttime, NIGHTTIME_COLOR)
        already_asked = ask_player_to_vote_only_once(already_asked, game_dir, is_mafia)


def game_over_message(game_dir):
    who_wins = (game_dir / WHO_WINS_FILE).read_text().strip()
    print(colored(who_wins, MANAGER_COLOR))
    mafia_names = (game_dir / MAFIA_NAMES_FILE).read_text().splitlines()  # removes the "\n"
    print(colored(MAFIA_REVELATION_MESSAGE, MANAGER_COLOR),
          colored(", ".join(mafia_names), MANAGER_COLOR, attrs=["bold"]))


def main():
    game_dir = get_game_dir_from_argv()
    _, is_mafia = welcome_player(game_dir)
    read_game_text_loop(is_mafia, game_dir)
    game_over_message(game_dir)


if __name__ == '__main__':
    main()
