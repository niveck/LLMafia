from threading import Thread
from termcolor import colored
from game_constants import get_game_dir_from_argv
from player_chat import read_game_text_loop, welcome_player, game_over_message
from player_input import write_text_to_game_loop
from player_survey import run_survey_about_llm_player

THREADING_WARNING_MESSAGE = "Pay attention! This interface allows you to read and write in the " \
                            "same terminal, but it is not recommended!\n" \
                            "It is better to use different terminals for viewing the chat and " \
                            "for entering input:\n" \
                            "\t`player_chat.py` and `player_input.py`, respectively.\n"
WARNING_COLOR = "light_red"

def game_read_and_write_loop(name, is_ai, game_dir):
    write_thread = Thread(target=write_text_to_game_loop, args=(name, is_ai, game_dir))
    # daemon: writing in the background, so it can stop when eliminated and still allow reading
    write_thread.daemon = True
    write_thread.start()
    read_game_text_loop(is_ai, game_dir)

def main():
    game_dir = get_game_dir_from_argv()
    print(colored(THREADING_WARNING_MESSAGE, WARNING_COLOR))
    name, is_ai = welcome_player(game_dir)
    game_read_and_write_loop(name, is_ai, game_dir)
    game_over_message(game_dir)
    run_survey_about_llm_player(game_dir, name)

if __name__ == '__main__':
    main()
