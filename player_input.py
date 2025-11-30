from game_constants import *  # incl. random, Path (from pathlib), colored (from termcolor)
from game_status_checks import is_game_over, is_voted_out, is_time_to_vote, \
    all_players_joined, get_is_ai
from player_survey import run_survey_about_llm_player

def get_name_and_role(game_dir):
    print(colored(WELCOME_INPUT_INTERFACE_MESSAGE + "\n", MANAGER_COLOR))
    player_names = (game_dir / PLAYER_NAMES_FILE).read_text().splitlines()
    random.shuffle(player_names)
    name = get_player_name_from_user(player_names, GET_CODE_NAME_FROM_USER_MESSAGE)
    is_ai = get_is_ai(name, game_dir)
    print(colored(WAITING_FOR_ALL_PLAYERS_TO_JOIN_MESSAGE, MANAGER_COLOR))
    while not all_players_joined(game_dir):
        continue
    print(colored(YOU_CAN_START_WRITING_MESSAGE, MANAGER_COLOR))
    return name, is_ai

def notify_only_once_about_finish_writing(already_notified):
    if not already_notified:
        print(colored(YOU_CANT_WRITE_MESSAGE, MANAGER_COLOR))
        already_notified = True
    return already_notified

def collect_vote(name, game_dir):
    remaining_player_names = (game_dir / REMAINING_PLAYERS_FILE).read_text().splitlines()
    remaining_player_names.remove(name)  # players shouldn't vote for themselves
    voted_name = get_player_name_from_user(remaining_player_names,
                                           GET_VOTED_NAME_MESSAGE_FORMAT.format(name))
    with open(game_dir / PERSONAL_VOTE_FILE_FORMAT.format(name), "a") as f:
        f.write(voted_name + "\n")

def write_text_to_game_loop(name, is_ai, game_dir):
    already_notified = False
    while not is_game_over(game_dir):
        if is_voted_out(name, game_dir):
            already_notified = notify_only_once_about_finish_writing(already_notified)
            continue  # can't write or vote anymore, waiting for final survey
        # No nighttime restrictions in Social Turing Test - all players can always communicate
        user_input = input(colored(GET_CHAT_INPUT_MESSAGE, MANAGER_COLOR)).strip()
        if not user_input:
            continue
        elif user_input == VOTE_FLAG:
            if not is_time_to_vote(game_dir):
                print(colored(NOT_TIME_TO_VOTE_MESSAGE, MANAGER_COLOR))
                continue
            collect_vote(name, game_dir)
            while is_time_to_vote(game_dir):
                continue  # wait for voting time to end when all players have voted
        elif not is_time_to_vote(game_dir):  # if it's time to vote then players can't chat
            with open(game_dir / PERSONAL_CHAT_FILE_FORMAT.format(name), "a") as f:
                f.write(format_message(name, user_input))

def main():
    game_dir = get_game_dir_from_argv()
    name, is_ai = get_name_and_role(game_dir)
    write_text_to_game_loop(name, is_ai, game_dir)
    run_survey_about_llm_player(game_dir, name)

if __name__ == '__main__':
    main()
