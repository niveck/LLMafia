import os
import json
import argparse
from pathlib import Path
from game_constants import DIRS_PREFIX, DEFAULT_GAME_CONFIG, GAME_ID_NUM_DIGITS, GAME_CONFIG_FILE, \
    PLAYER_NAMES_FILE, REMAINING_PLAYERS_FILE, AI_PLAYER_FILE, PHASE_STATUS_FILE, DAYTIME, \
    PUBLIC_MANAGER_CHAT_FILE, PUBLIC_DAYTIME_CHAT_FILE, WHO_WINS_FILE, \
    GAME_START_TIME_FILE, NOTES_FILE, REAL_NAME_CODENAME_DELIMITER, REAL_NAMES_FILE, \
    PLAYERS_KEY_IN_CONFIG, PERSONAL_STATUS_FILE_FORMAT, PERSONAL_CHAT_FILE_FORMAT, \
    PERSONAL_VOTE_FILE_FORMAT, LLM_LOG_FILE_FORMAT, PERSONAL_SURVEY_FILE_FORMAT
from prepare_config import PlayerConfig


def get_next_free_game_id():
    all_game_dirs = Path(DIRS_PREFIX).glob("*")
    number_game_dirs = [int(game.name) for game in all_game_dirs if game.name.isdigit()]
    number_game_dirs.append(0)  # for robustness and for first time
    next_id = max(number_game_dirs) + 1
    return f"{next_id}".zfill(GAME_ID_NUM_DIGITS)


def get_id_and_config():
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--id", default=None, help="explicit new game id")
    parser.add_argument("-c", "--config", default=None, help="non-default configuration path")
    args = parser.parse_args()
    parent_games_dir = Path(DIRS_PREFIX)
    # handle game_id
    game_id = args.id
    if game_id is None:
        game_id = get_next_free_game_id()
        print(f"Generated a new game id: {game_id}")
    if (parent_games_dir / game_id).exists():
        raise ValueError(f"Can't create game dir with the following id"
                         f" because it already exists: {game_id}")
    # handle config_path
    config_path = args.config
    if config_path is None:
        print(f"(!) Using default config path: {DEFAULT_GAME_CONFIG}")
        config_path = DEFAULT_GAME_CONFIG
    if not Path(config_path).exists():
        raise ValueError(f"Can't use this config because its path doesn't exist: {config_path}")
    return game_id, config_path


def init_game(game_id, config_path):
    game_dir = Path(DIRS_PREFIX) / game_id
    game_dir.mkdir(mode=0o777)
    with open(config_path, "r") as original_file:
        config = json.load(original_file)
    config["config_original_path_when_game_created"] = config_path
    with open(game_dir / GAME_CONFIG_FILE, "w") as output_file:
        json.dump(config, output_file, indent=4)
    players = [PlayerConfig(**player_config) for player_config in config[PLAYERS_KEY_IN_CONFIG]]
    all_names_str = "\n".join([player.name for player in players])
    (game_dir / PLAYER_NAMES_FILE).write_text(all_names_str)
    (game_dir / REMAINING_PLAYERS_FILE).write_text(all_names_str)
    all_ai_names_str = [player.name for player in players if player.is_ai]
    (game_dir / AI_PLAYER_FILE).write_text("\n".join(all_ai_names_str))
    real_name_to_codename_str = [f"{player.real_name}{REAL_NAME_CODENAME_DELIMITER}{player.name}"
                                 for player in players if not player.is_llm]
    (game_dir / REAL_NAMES_FILE).write_text("\n".join(real_name_to_codename_str))
    (game_dir / PHASE_STATUS_FILE).write_text(DAYTIME)
    (game_dir / PUBLIC_MANAGER_CHAT_FILE).touch()
    (game_dir / PUBLIC_DAYTIME_CHAT_FILE).touch()
    (game_dir / WHO_WINS_FILE).touch()
    (game_dir / GAME_START_TIME_FILE).touch()
    (game_dir / NOTES_FILE).touch()
    for player in players:
        (game_dir / PERSONAL_CHAT_FILE_FORMAT.format(player.name)).touch()
        (game_dir / PERSONAL_VOTE_FILE_FORMAT.format(player.name)).touch()
        (game_dir / PERSONAL_STATUS_FILE_FORMAT.format(player.name)).touch()
        if player.is_llm:
            (game_dir / LLM_LOG_FILE_FORMAT.format(player.name)).touch()
        else:
            (game_dir / PERSONAL_SURVEY_FILE_FORMAT.format(player.name)).touch()
    # since for some reason the `mode` arg in mkdir doesn't work properly:
    os.system(f"chmod -R 777 {game_dir}")
    print(f"Successfully created a new game dir in: {game_dir.absolute()}")


def main():
    game_id, config_path = get_id_and_config()
    init_game(game_id, config_path)


if __name__ == '__main__':
    main()
