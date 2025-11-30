"""
usage: prepare_config.py [-h] [-o OUTPUT] [-p PLAYERS] [-m MAFIA] [-l {0,1}]
                         [-b] [-n NAMES_FILE] [-c] [-j LLM_CONFIG_JSON_PATH]
                         [-dt DAYTIME_MINUTES] [-nt NIGHTTIME_MINUTES]

options:
  -h, --help            show this help message and exit
  -o OUTPUT, --output OUTPUT
                        output config file name
  -p PLAYERS, --players PLAYERS
                        total number of players in game
  -m MAFIA, --mafia MAFIA
                        number of mafia players in game
  -l {0,1}, --llm {0,1}
                        number of LLM players in game, currently supports maximum 1
  -b, --bystander       whether the LLM player can only be bystander (not mafia)
  -n NAMES_FILE, --names_file NAMES_FILE
                        path to file with the participating players' real
                        names (before code names assignment), separated by new
                        line breaks ('\\n')
  -c, --change_llm_config
                        whether to edit the default LLM configuration
  -j LLM_CONFIG_JSON_PATH, --llm_config_json_path LLM_CONFIG_JSON_PATH
                        optional path to LLM configuration as json (has to be complete)
  -dt DAYTIME_MINUTES, --daytime_minutes DAYTIME_MINUTES
                        number of minutes for Daytime phase
  -nt NIGHTTIME_MINUTES, --nighttime_minutes NIGHTTIME_MINUTES
                        number of minutes for Nighttime phase

Process finished with exit code 0

"""
import json
import argparse
import random
import sys
import time
from pathlib import Path
from termcolor import colored
from dataclasses import dataclass, asdict, field
from game_constants import DEFAULT_CONFIG_DIR, DEFAULT_NUM_PLAYERS, DEFAULT_NUM_MAFIA, \
    MINIMUM_NUM_PLAYERS_FOR_ONE_MAFIA, MINIMUM_NUM_PLAYERS_FOR_MULT_MAFIA, OPTIONAL_CODE_NAMES, \
    WARNING_LIMIT_NUM_MAFIA, PLAYERS_KEY_IN_CONFIG, DEFAULT_DAYTIME_MINUTES, \
    DEFAULT_NIGHTTIME_MINUTES, DAYTIME_MINUTES_KEY, NIGHTTIME_MINUTES_KEY, ANONYMOUS_VOTING_KEY
from llm_players.llm_constants import INT_CONFIG_KEYS, FLOAT_CONFIG_KEYS, DEFAULT_LLM_CONFIG, \
    LLM_CONFIG_KEYS_OPTIONS, BOOL_CONFIG_KEYS

LLM_CONFIG_KEYS_INDEXED_OPTIONS = {
    key: {f"{i}": option for (i, option) in enumerate(options)}
    for key, options in LLM_CONFIG_KEYS_OPTIONS.items()
}


@dataclass
class PlayerConfig:
    name: str  # player's code name from the game's pool (in constants file)
    is_mafia: bool = False
    is_llm: bool = False
    real_name: str = ""
    llm_config: dict = field(default_factory=dict)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--output", default=None, help="output config file name")
    parser.add_argument("-p", "--players", type=int, default=None,
                        help="total number of players in game")
    parser.add_argument("-m", "--mafia", type=int, default=None,
                        help="number of mafia players in game")
    parser.add_argument("-l", "--llm", type=int, default=1, choices=[0, 1],
                        # since participants will rank the (single) LLM player performance
                        help="number of LLM players in game, currently supports maximum 1")
    parser.add_argument("-b", "--bystander", action="store_true",
                        help="whether the LLM player can only be bystander (not mafia)")
    parser.add_argument("-n", "--names_file", default=None,
                        help="path to file with the participating players' real names "
                             "(before code names assignment), separated by new line breaks ('\\n')")
    parser.add_argument("-c", "--change_llm_config", action="store_true",
                        help="whether to edit the default LLM configuration")
    parser.add_argument("-j", "--llm_config_json_path", default=None,
                        help="optional path to LLM configuration as json (has to be complete)")
    parser.add_argument("-dt", "--daytime_minutes", type=float, default=DEFAULT_DAYTIME_MINUTES,
                        help="number of minutes for Daytime phase")
    parser.add_argument("-nt", "--nighttime_minutes", type=float, default=DEFAULT_NIGHTTIME_MINUTES,
                        help="number of minutes for Nighttime phase")
    parser.add_argument("-a", "--anonymous_voting", action="store_true",
                        help="whether to use anonymous voting (show vote counts instead of individual votes)")
    args = parser.parse_args()
    return args


def handle_output_file(args):
    output_file = args.output
    if output_file is None:
        output_file = "config" + time.strftime("%d%m%y_%H%M")
    if not output_file.startswith(DEFAULT_CONFIG_DIR):
        output_file = DEFAULT_CONFIG_DIR + "/" + output_file
    if not output_file.endswith(".json"):
        output_file += ".json"
    output_file = Path(output_file)
    if output_file.exists():
        input("Warning: the destination output path already exists... "
              "[enter to continue and override, Ctrl+C to cancel]")
    else:
        output_file.touch()  # to raise an error immediately if the new path is invalid
    return output_file


def validate_names_file(args):
    if args.names_file is not None and not Path(args.names_file).exists():
        raise ValueError("Provided names file (with -n/--names_file) does not exist:",
                         args.names_file)


def handle_num_players(args):
    num_players = args.players
    if num_players is None:
        num_players = DEFAULT_NUM_PLAYERS
        print(f"Using default number of total players: {DEFAULT_NUM_PLAYERS}")
    elif num_players < 3:
        raise ValueError(f"{num_players} is not enough players for Social Turing Test! "
                         f"Minimum is 3 players (1 AI + 2 humans).")
    else:
        print(f"Using number of total players: {num_players}")
    
    # Social Turing Test: Always exactly 1 imposter (will be the AI)
    num_mafia = 1
    print(f"Social Turing Test mode: Exactly 1 Imposter (AI) among {num_players} total players")
    
    code_names = random.sample(OPTIONAL_CODE_NAMES, num_players)
    player_configs = [PlayerConfig(code_name) for code_name in code_names]
    
    # Select one player to be the imposter (will be assigned to AI)
    mafia_player = random.choice(player_configs)
    mafia_player.is_mafia = True
    
    return player_configs


def get_llm_config(llm_numbered_symbol, args):
    if args.llm_config_json_path is not None:
        print("Using the LLM configuration in provided path:", args.llm_config_json_path)
        with open(args.llm_config_json_path, "r") as f:
            llm_config = json.load(f)
    else:
        llm_config = DEFAULT_LLM_CONFIG.copy()  # pay attention it is shallow copy of primitives
    if args.change_llm_config:
        config_approved = False
        index2key = {f"{i}": key for i, key in enumerate(llm_config.keys())}
        while not config_approved:
            print(f"Here is the current config for {llm_numbered_symbol}:")
            for i, key in index2key.keys():
                print(f"{i}.\t{key}: {llm_config[key]}")
            index = input("Enter and key index to change its value, "
                          "or anything else to approve the config: ")
            if index in index2key:
                key = index2key[index]
                if key in INT_CONFIG_KEYS:
                    llm_config[key] = int(input(f"Enter a new number for {key}: "))
                elif key in FLOAT_CONFIG_KEYS:
                    llm_config[key] = float(input(f"Enter a new value for {key}: "))
                elif key in BOOL_CONFIG_KEYS:
                    llm_config[key] = eval(input(f"Enter True/False for {key}: ").capitalize())
                else:
                    choice = None
                    while choice not in LLM_CONFIG_KEYS_INDEXED_OPTIONS[key]:
                        all_options = "\n".join([f"\t{i}: {option}" for (i, option)
                                                 in LLM_CONFIG_KEYS_INDEXED_OPTIONS[key].items()])
                        choice = input(f"Choose the wanted option for {key}:\n"
                                       f"{all_options}\n")
                    llm_config[key] = LLM_CONFIG_KEYS_INDEXED_OPTIONS[key][choice]
            else:
                config_approved = True
    return llm_config


def handle_llm_participation(args, player_configs):
    num_llms = args.llm
    print(f"Using {num_llms} LLM player{'' if num_llms == 1 else ''}")
    if num_llms > 0:
        # Social Turing Test: AI is ALWAYS the Imposter
        # Find the player that was assigned is_mafia=True
        mafia_player = [player for player in player_configs if player.is_mafia][0]
        
        # Assign the LLM to be the Imposter
        mafia_player.is_llm = True
        mafia_player.real_name = "LLM0"
        mafia_player.llm_config = get_llm_config(mafia_player.real_name, args)
        
        print(f"Social Turing Test: The AI is assigned as the Imposter")


def assign_real_names(args, player_configs):
    human_players = [player_config for player_config in player_configs if not player_config.is_llm]
    if args.names_file is None:
        real_names = []
    else:  # split() removes the '\n' and ignores empty lines
        real_names = Path(args.names_file).read_text().split()
    if len(set(real_names)) < len(real_names):
        raise ValueError("The provided names file contain reoccurrence of the same name!")
    if real_names:
        print("The given real names of participating players:")
        print(",  ".join([f"{i + 1}. {name}" for i, name in enumerate(real_names)]))
    if len(human_players) < len(real_names):
        print(f"Warning: {len(real_names)} participating names given, "
              f"only {len(human_players)} needed for human players, "
              f"using only the first {len(human_players)}...")
        real_names = real_names[:len(human_players)]
    elif len(human_players) > len(real_names):
        while len(human_players) > len(real_names):
            new_real_name = input("Still not enough real names of participating players, "
                                  "provide another one: ").strip()
            if not new_real_name or new_real_name in real_names:
                print("This name belongs to a player that was already listed!")
            else:
                real_names.append(new_real_name)
    # now len(human_players) == len(real_names)
    for human_player, real_name in zip(human_players, real_names):
        human_player.real_name = real_name


def save_config(args, output_file, player_configs):
    # Social Turing Test: no night phase, so nighttime = 0
    config = {PLAYERS_KEY_IN_CONFIG: [asdict(player_config) for player_config in player_configs],
              DAYTIME_MINUTES_KEY: args.daytime_minutes,
              NIGHTTIME_MINUTES_KEY: 0,  # Always 0 for Social Turing Test (no night phase)
              ANONYMOUS_VOTING_KEY: args.anonymous_voting,
              "notes": input("Add notes to this config: [or enter to skip] ").strip(),
              "preparation_command": " ".join(sys.argv)}
    with open(output_file, "w") as f:
        json.dump(config, f, indent=4)
    print("Configuration was created and saved to:", colored(output_file, "green"))


def main():
    args = parse_args()
    output_file = handle_output_file(args)  # done first to immediately raise error if invalid
    validate_names_file(args)
    player_configs = handle_num_players(args)
    handle_llm_participation(args, player_configs)
    assign_real_names(args, player_configs)
    save_config(args, output_file, player_configs)


if __name__ == '__main__':
    main()
