import json
import re
import numpy as np
from pathlib import Path
from collections import defaultdict
from matplotlib import pyplot as plt
from sklearn.neighbors import KernelDensity

from game_constants import DIRS_PREFIX, PLAYER_NAMES_FILE, LLM_LOG_FILE_FORMAT, METRICS_TO_SCORE, \
    MESSAGE_PARSING_PATTERN, GAME_MANAGER_NAME, LLM_IDENTIFICATION, PERSONAL_SURVEY_FILE_FORMAT, \
    SURVEY_COMMENTS_TITLE, METRIC_NAME_AND_SCORE_DELIMITER, MAFIA_WINS_MESSAGE, WHO_WINS_FILE, \
    GAME_CONFIG_FILE, PLAYERS_KEY_IN_CONFIG, CUTTING_TO_VOTE_MESSAGE, VOTING_MESSAGE_FORMAT, \
    VOTED_OUT_MESSAGE_FORMAT, VOTING_TIME_MESSAGE_FORMAT, DAYTIME_START_PREFIX, DAYTIME, \
    NIGHTTIME_START_PREFIX, NIGHTTIME, PUBLIC_MANAGER_CHAT_FILE, PUBLIC_DAYTIME_CHAT_FILE, \
    PUBLIC_NIGHTTIME_CHAT_FILE, MAFIA_NAMES_FILE, DAYTIME_MINUTES_KEY, NIGHTTIME_MINUTES_KEY, \
    MAFIA_ROLE, BYSTANDER_ROLE, REAL_NAMES_FILE, REAL_NAME_CODENAME_DELIMITER, ALL_MESSAGES_FILE, \
    strip_special_chars
from game_status_checks import is_voted_out, all_players_joined
from llm_players.llm_constants import LLM_CONFIG_KEY


LAST_GAME_FROM_PILOT = 37
NUM_GAMES_WITH_8B_MODEL = 21

ANALYSIS_DIR = Path("./analysis")

MESSAGE_HISTOGRAM_Y_LIM = (0, 30)

MEAN_MARKER_STYLE = dict(marker="x", markersize=8, color="navy", markeredgewidth=3)

# manager messages types
PHASE_START = "Now it's PHASE for X minutes"
CUT_TO_VOTE = "There is only one mafia member left"
PHASE_END = "PHASE has ended, now it's time to vote"
WHO_VOTE_FOR = "X voted for Y"
WAS_VOTED_OUT = "X was voted out"
# manager messages signals
VOTING_MESSAGE_SIGNAL = VOTING_MESSAGE_FORMAT.replace("{}", "")
VOTED_OUT_SIGNAL = VOTED_OUT_MESSAGE_FORMAT.replace("{}", "")
PHASE_END_SIGNAL = VOTING_TIME_MESSAGE_FORMAT.replace("{}", "")

# message content empiric metrics
LENGTH, REPETITION, NUM_UNIQUE_WORDS = "length", "repetition", "num_unique_words"
CONTENT_METRICS = [LENGTH, REPETITION, NUM_UNIQUE_WORDS]

# SENTENCE_EMBEDDING_MODEL = "prdev/mini-gte"
# SENTENCE_EMBEDDING_MODELS = ["prdev/mini-gte", "all-MiniLM-L6-v2", "all-MiniLM-L12-v2",
#                              "BAAI/bge-m3", "Alibaba-NLP/gte-multilingual-base"]
SENTENCE_EMBEDDING_MODELS = ["BAAI/bge-m3"]
REDUCED_DIM = 3
PLOT_3D_COLOR_MAP = {
    'Human-bystander-daytime': 'lightskyblue',
    'Human-mafia-daytime': 'blue',
    'Human-mafia-nighttime': 'darkblue',
    'LLM-bystander-daytime': 'salmon',
    'LLM-mafia-daytime': 'red',
    'LLM-mafia-nighttime': 'darkred'
}

ANONYMIZED_NAME = "ANONYMIZED"


def avg(scores): return sum(scores) / len(scores)


class ParsedMessage:

    def __init__(self, message, llm_player_name=None):
        self.original = message
        hrs, mins, secs, name, content = re.match(MESSAGE_PARSING_PATTERN, message).groups()
        self.timestamp = 3600 * int(hrs) + 60 * int(mins) + int(secs)  # in seconds
        self.name = name
        self.is_manager = name == GAME_MANAGER_NAME
        self.is_llm = name == llm_player_name
        self.content = content
        self.words_in_message = content.split()
        self.num_words = len(self.words_in_message)
        self.manager_message_type, self.manager_message_subject = self.parse_manager_message()

    def parse_manager_message(self):
        if not self.is_manager:
            return None, None
        elif self.content.startswith(DAYTIME_START_PREFIX):
            return PHASE_START, DAYTIME
        elif self.content.startswith(NIGHTTIME_START_PREFIX):
            return PHASE_START, NIGHTTIME
        elif self.content == CUTTING_TO_VOTE_MESSAGE:
            return CUT_TO_VOTE, None
        elif self.content.endswith(PHASE_END_SIGNAL):
            return PHASE_END, self.content.removesuffix(PHASE_END_SIGNAL)
        elif VOTING_MESSAGE_SIGNAL in self.content:
            return WHO_VOTE_FOR, self.content.split(VOTING_MESSAGE_SIGNAL)  # [voter, voted for]
        elif VOTED_OUT_SIGNAL in self.content:
            return WAS_VOTED_OUT, self.content.split(VOTED_OUT_SIGNAL)[0]
        else:
            return NotImplementedError("This manager message type is new!")

    def __repr__(self):
        return self.original
    
    def copy(self):  # allows resetting timestamps in phases without overrunning them
        message_copy = ParsedMessage(self.original)
        message_copy.is_llm = self.is_llm  # otherwise will stay False as default
        return message_copy


class Phase:
    def __init__(self, messages: list[ParsedMessage] = None, active_players=None,
                 is_daytime=True, voted_out_player=None):
        self.messages = messages.copy() if messages else []
        self.active_players = active_players.copy() if active_players else []
        self.is_daytime = is_daytime
        self.voted_out_player = voted_out_player

    def __repr__(self):
        phase_type = DAYTIME if self.is_daytime else NIGHTTIME
        return f"{phase_type} Phase (w/ {len(self.active_players)} active players)"

    def copy(self):  # to use in case I don't want to overrun the timestamps in reset_timestamps
        messages = [message.copy() for message in self.messages]
        return Phase(messages, self.active_players.copy(), self.is_daytime, self.voted_out_player)

    def reset_timestamps(self, start_timestamp=None):
        if not self.messages:
            return
        if start_timestamp is None:
            min_timestamp = self.messages[0].timestamp  # a Phase instance is created after sorting
        else:
            min_timestamp = start_timestamp
        for message in self.messages:
            message.timestamp -= min_timestamp


def get_llm_player_name(all_players, game_dir):
    llm_player_name = None
    for player_name in all_players:
        if (game_dir / LLM_LOG_FILE_FORMAT.format(player_name)).exists():
            if llm_player_name is None:
                llm_player_name = player_name
            else:
                raise NotImplementedError(f"This game (ID {game_dir.name}) has more than one LLM")
    return llm_player_name


def get_survey_results(game_dir, player_name, all_metrics):
    lines = (game_dir / PERSONAL_SURVEY_FILE_FORMAT.format(player_name)).read_text().splitlines()
    results = {}
    new_line_is_comments = False
    for line in lines:
        if new_line_is_comments:
            results[SURVEY_COMMENTS_TITLE] = line
        elif line == SURVEY_COMMENTS_TITLE:
            new_line_is_comments = True
        for metric in all_metrics:
            if line.startswith(metric):
                score = int(re.match(fr"{metric}{METRIC_NAME_AND_SCORE_DELIMITER}(\d+)",
                                     line).group(1))
                results[metric] = score if int(game_dir.name) > LAST_GAME_FROM_PILOT else score / 20
    return results


def parse_messages_by_phase(parsed_messages: list[ParsedMessage], all_players, mafia_players):
    all_phases = []
    is_daytime = True
    current_players = [player for player in all_players]
    current_mafia = [player for player in all_players if player in mafia_players]
    current_phase = Phase(active_players=current_players, is_daytime=is_daytime,
                          messages=parsed_messages[:1])
    assert parsed_messages[0].manager_message_type == PHASE_START, "PROBLEM IN PARSING!"
    for message in parsed_messages[1:]:  # first one is always daytime announcement
        if message.manager_message_type == PHASE_START:  # first one is skipped
            all_phases.append(current_phase)
            is_daytime = message.manager_message_subject == DAYTIME
            active_players = current_players if is_daytime else current_mafia
            current_phase = Phase(active_players=active_players, is_daytime=is_daytime)  # new phase
        elif message.manager_message_type == WAS_VOTED_OUT:
            voted_out_player = message.manager_message_subject
            current_players.remove(voted_out_player)
            if voted_out_player in current_mafia:
                current_mafia.remove(voted_out_player)
            current_phase.voted_out_player = voted_out_player
        current_phase.messages.append(message)
    all_phases.append(current_phase)  # the last one, since a new one wasn't started
    return all_phases


def decide_message_order(message: ParsedMessage):
    """
    An example from game 0030 that shows many Game-Manager of the same timestamp,
    and their proper order - without this function their order was mixed!
    [13:59:04] Ariel: Looks like he's looking to take out people
    [13:59:09] Game-Manager: Daytime has ended, now it's time to vote! Waiting for all players to vote...
    [13:59:19] Game-Manager: Adrian voted for Lennon
    [13:59:25] Game-Manager: Ariel voted for Lennon
    [13:59:27] Game-Manager: Jamie voted for Ariel
    [13:59:27] Game-Manager: Morgan voted for Ariel
    (now the conflict - pay attention for votes in both phases! - probably not possible to solve)
    [13:59:39] Game-Manager: Lennon voted for Ariel
    [13:59:39] Game-Manager: Ariel was voted out. Their role was mafia
    [13:59:39] Game-Manager: Now it's Nighttime for 1 minutes, only mafia can communicate and see messages and votes.
    [13:59:39] Game-Manager: There is only one mafia member left, so no need for discussion - cutting straight to voting!
    [13:59:39] Game-Manager: Nighttime has ended, now it's time to vote! Waiting for all players to vote...
    [13:59:39] Game-Manager: Adrian voted for Lennon
    [13:59:39] Game-Manager: Lennon was voted out. Their role was bystander
    [13:59:39] Game-Manager: Now it's Daytime for 3 minutes, everyone can communicate and see messages and votes.
    """
    if not message.is_manager:
        return 7
    if message.manager_message_type == WHO_VOTE_FOR:
        return 1
    if message.manager_message_type == WAS_VOTED_OUT:
        return 2
    if message.manager_message_type == PHASE_START:
        if message.manager_message_subject == NIGHTTIME:
            return 3
        else:  # == DAYTIME
            return 6
    if message.manager_message_type == CUT_TO_VOTE:
        return 4
    if message.manager_message_type == PHASE_END:
        if message.manager_message_subject == NIGHTTIME:
            return 5
        else:  # == DAYTIME
            return 0
    assert False, "An edge case was forgotten!"


def parse_messages(game_dir, all_players, mafia_players, llm_player_name):
    manager_messages = (game_dir / PUBLIC_MANAGER_CHAT_FILE).read_text().splitlines()
    daytime_messages = (game_dir / PUBLIC_DAYTIME_CHAT_FILE).read_text().splitlines()
    nighttime_messages = (game_dir / PUBLIC_NIGHTTIME_CHAT_FILE).read_text().splitlines()
    all_messages = manager_messages + daytime_messages + nighttime_messages
    # in some games there was a bug that multiplied messages: (still unique by timestamp and name)
    all_messages = set(all_messages)
    parsed_messages = [ParsedMessage(message, llm_player_name) for message in all_messages]
    parsed_messages.sort(key=lambda x: (x.timestamp, decide_message_order(x)))
    parsed_messages_by_phase = parse_messages_by_phase(parsed_messages, all_players, mafia_players)
    return parsed_messages_by_phase


def get_single_game_results(game_id):
    game_dir = Path(DIRS_PREFIX) / game_id
    all_players = (game_dir / PLAYER_NAMES_FILE).read_text().splitlines()
    mafia_players = (game_dir / MAFIA_NAMES_FILE).read_text().splitlines()
    llm_player_name = get_llm_player_name(all_players, game_dir)
    assert llm_player_name, "This game has no LLM, so analysis is meaningless"
    with open(game_dir / GAME_CONFIG_FILE) as f:
        config = json.load(f)
    # llm_config = [player[LLM_CONFIG_KEY] for player in config[PLAYERS_KEY_IN_CONFIG]
    #               if player["name"] == llm_player_name][0]
    human_players = [player for player in all_players if player != llm_player_name]
    all_metrics = [LLM_IDENTIFICATION] + METRICS_TO_SCORE
    metrics_results = {metric: [] for metric in all_metrics}
    all_comments = []
    for player_name in human_players:
        survey_results = get_survey_results(game_dir, player_name, all_metrics)
        for metric in all_metrics:
            # in case there was a problem and not all metrics were scored
            if metric in survey_results:
                metrics_results[metric].append(survey_results[metric])
        if SURVEY_COMMENTS_TITLE in survey_results:
            all_comments.append(survey_results[SURVEY_COMMENTS_TITLE])
    parsed_messages_by_phase = parse_messages(game_dir, all_players, mafia_players, llm_player_name)
    was_llm_voted_out = is_voted_out(llm_player_name, game_dir)
    is_llm_mafia = llm_player_name in mafia_players
    did_mafia_win = MAFIA_WINS_MESSAGE in (game_dir / WHO_WINS_FILE).read_text()
    did_llm_win = did_mafia_win == is_llm_mafia
    return llm_player_name, all_players, mafia_players, human_players, config, \
        metrics_results, all_comments, parsed_messages_by_phase, was_llm_voted_out, is_llm_mafia, \
        did_mafia_win, did_llm_win  # num_daytime_phases, num_nighttime_phases, and more from doc - will be in the next function to analyze


def plot_game_flow(game_id, all_players, parsed_messages_by_phase: list[Phase], llm_player_name):
    player_message_lengths = {player: [] for player in all_players}
    player_voted_out = {player: None for player in all_players}
    player_color = {player: f"C{i}" for i, player in enumerate(all_players)}
    if "C10" in player_color.values():
        # raise UserWarning("More than 10 players, which means repetition of colors in plot")
        print(UserWarning("More than 10 players, which means repetition of colors in plot"))
    title = f"Game {game_id} Flow"
    plt.title(title)
    all_timestamps = []
    phase_limits = get_game_flow_info(all_timestamps, parsed_messages_by_phase,
                                      player_message_lengths, player_voted_out)
    for player in all_players:
        if player_voted_out[player]:
            plt.scatter([player_voted_out[player]], [MESSAGE_HISTOGRAM_Y_LIM[1]],
                        color=player_color[player], alpha=0.3)
        player_label = player + " (LLM)" if player == llm_player_name else player
        plt.bar(*zip(*player_message_lengths[player]), width=7,
                label=player_label, color=player_color[player], alpha=0.3)
    for (timestamp, is_phase_end, is_daytime) in phase_limits:
        color = "dark" if is_phase_end else ""
        color += "blue" if is_daytime else "red"
        plt.axvline(timestamp, *plt.ylim(), color=color, linewidth=0.5)
    plt.xlim(min(all_timestamps) - 10, max(all_timestamps) + 10)
    plt.ylim(MESSAGE_HISTOGRAM_Y_LIM)
    plt.xlabel("timestamp")
    plt.ylabel("Number of words in message")
    plt.legend(bbox_to_anchor=(1.05, 0.5), loc="center left")
    plt.tight_layout()
    plt.savefig(ANALYSIS_DIR / (title + ".png"))
    plt.show()


def get_game_flow_info(all_timestamps, parsed_messages_by_phase, player_message_lengths,
                       player_voted_out, human_messages=True, llm_messages=True):
    phase_limits = []
    for phase in parsed_messages_by_phase:
        for message in phase.messages:
            if (message.is_llm and not llm_messages) or (not message.is_llm and not human_messages):
                continue
            all_timestamps.append(message.timestamp)
            if message.manager_message_type in (PHASE_START, PHASE_END):
                phase_limits.append((message.timestamp, message.manager_message_type == PHASE_END,
                                     message.manager_message_subject == DAYTIME))
            elif message.manager_message_type == WAS_VOTED_OUT \
                    and message.manager_message_subject in player_voted_out:
                player_voted_out[message.manager_message_subject] = message.timestamp
            elif not message.is_manager and message.name in player_message_lengths:
                player_message_lengths[message.name].append((message.timestamp, message.num_words))
    return phase_limits


def plot_messages_histogram_in_phase(all_players, phases: list[Phase], game_id=None,
                                     human_messages=True, llm_messages=True, llm_player_name=None,
                                     daytime_phases=True, nighttime_phases=False,
                                     plot_for_each_player=True, plot_general_histogram=True):
    assert daytime_phases or nighttime_phases
    if daytime_phases and nighttime_phases:
        raise UserWarning("Best to use only for daytime phases or only for nighttime phases")
    if llm_messages and plot_for_each_player and llm_player_name is None:
        raise UserWarning("You want to plot for each player separately, and to plot for the LLM, "
                          "but you haven't given the LLM name in the llm_player_name parameter")
    player_message_lengths = {player: [] for player in all_players}
    # player_voted_out = {player: None for player in all_players}
    all_timestamps = []
    color = "C0"
    for phase in phases:
        if (phase.is_daytime and not daytime_phases) \
                or (not phase.is_daytime and not nighttime_phases):
            continue
        phase_reset = phase.copy()
        phase_reset.reset_timestamps()
        get_game_flow_info(all_timestamps, [phase_reset],
                           # creates unified histogram per player across phases
                           player_message_lengths, {},  # player_voted_out,
                           human_messages=human_messages,
                           llm_messages=llm_messages)
    game_in_title = f" in game {game_id}" if game_id is not None else ""
    phase_in_title = get_phase_name(daytime_phases, nighttime_phases)
    # plot for each player separately:
    if plot_for_each_player:
        for player in all_players:
            player_label = player + " (LLM)" if player == llm_player_name else player
            title = f"Messages histogram of {player_label} for {phase_in_title}" + game_in_title
            plt.title(title)
            messages_lengths = player_message_lengths[player] if player_message_lengths[player] else [(0, 0)]
            plt.bar(*zip(*messages_lengths), width=7, color=color, alpha=0.3)
            plt.xlim(min(all_timestamps) - 10, max(all_timestamps) + 10)
            plt.ylim(MESSAGE_HISTOGRAM_Y_LIM)
            plt.xlabel("timestamp")
            plt.ylabel("Number of words in message")
            plt.savefig(ANALYSIS_DIR / (title + ".png"))
            plt.show()
    if plot_general_histogram:
        for player in all_players:
            messages_lengths = player_message_lengths[player] if player_message_lengths[player] else [(0, 0)]
            plt.bar(*zip(*messages_lengths), width=7, color=color, alpha=0.3)
        title = f"Unified Messages histogram for {phase_in_title}" + game_in_title
        plt.title(title)
        if plot_for_each_player:  # do it will be easy to compare
            plt.xlim(min(all_timestamps) - 10, max(all_timestamps) + 10)
        plt.ylim(MESSAGE_HISTOGRAM_Y_LIM)
        plt.xlabel("timestamp")
        plt.ylabel("Number of words in message")
        plt.savefig(ANALYSIS_DIR / (title + ".png"))
        plt.show()
    return player_message_lengths  # , player_voted_out


def plot_messages_histogram_in_all_games(reset_message_lengths_across_all_games, player_name=None,
                                         phase_name=None):
    color = "C0"
    plt.bar(*zip(*reset_message_lengths_across_all_games), width=7, color=color, alpha=0.3)
    player_title = "" if player_name is None else f"of {player_name} "
    phase_title = "" if phase_name is None else f"for {phase_name} "
    title = f"Unified Messages histogram {player_title}{phase_title}across all games"
    plt.title(title)
    plt.ylim(MESSAGE_HISTOGRAM_Y_LIM)
    plt.xlabel("timestamp")
    plt.ylabel("Number of words in message")
    plt.savefig(ANALYSIS_DIR / (title + ".png"))
    plt.show()


def get_phase_name(daytime_phases, nighttime_phases):
    if daytime_phases and nighttime_phases:
        return f"{DAYTIME} and {NIGHTTIME}"
    elif daytime_phases:
        return DAYTIME
    elif nighttime_phases:
        return NIGHTTIME
    else:
        raise ValueError("Must choose at least one phase")


def plot_single_pie_chart(title, result_on_all_games, true_label, false_label):
    plt.title(title)
    num_true = sum(result_on_all_games)
    num_false = len(result_on_all_games) - num_true
    plt.pie([num_true, num_false], labels=[true_label, false_label], autopct="%1.1f%%")
    plt.savefig(ANALYSIS_DIR / (title + ".png"))
    plt.show()


def plot_all_pie_charts(did_mafia_win_all_games, did_llm_win_all_games,
                        was_llm_voted_out_all_games, is_llm_mafia_all_games):
    plot_single_pie_chart("Mafia wins percentage across all games", did_mafia_win_all_games,
                          "Mafia win", "Mafia lose")
    plot_single_pie_chart("LLM win percentage across all games", did_llm_win_all_games,
                          "LLM win", "LLM lose")
    plot_single_pie_chart("Percentage of games where LLM plays as mafia", is_llm_mafia_all_games,
                          "LLM is mafia", "LLM is bystander")
    did_llm_win_as_mafia = []
    did_llm_win_as_bystander = []
    for i, is_llm_mafia in enumerate(is_llm_mafia_all_games):
        if is_llm_mafia:
            did_llm_win_as_mafia.append(did_llm_win_all_games[i])
        else:
            did_llm_win_as_bystander.append(did_llm_win_all_games[i])
    if did_llm_win_as_mafia:
        plot_single_pie_chart("LLM win percentage out of games played as mafia",
                              did_llm_win_as_mafia, "LLM win as mafia", "LLM lose as mafia")
    if did_llm_win_as_bystander:
        plot_single_pie_chart("LLM win percentage out of games played as bystander",
                              did_llm_win_as_bystander, "LLM win as bystander", "LLM lose as bystander")


def plot_scores_for_single_metric(metric, scores_by_game):
    title = f"{metric.capitalize()} scores across all games"
    plt.title(title + f"\n(with {MEAN_MARKER_STYLE['marker']}-markers "
                      f"for means and error bars for +-STD)")
    plt.xlabel("games")
    plt.ylabel(metric)
    x = []
    y = []
    means = []
    stds = []
    for i, game in enumerate(scores_by_game):
        x += [i] * len(game)
        y += [score for score in game]
        means.append(np.mean(game))
        stds.append(np.std(game))
    plt.scatter(x, y)
    plt.errorbar(range(len(scores_by_game)), means, stds, linestyle="none", **MEAN_MARKER_STYLE)
    plt.xticks([], [])
    plt.savefig(ANALYSIS_DIR / (title + ".png"))
    plt.show()
    return np.mean(y), np.std(y)


def plot_metric_scores(metrics_results_all_games):
    metrics = list(metrics_results_all_games.keys())  # to ensure order
    means_by_metrics = []
    stds_by_metrics = []
    for metric in metrics:
        mean, std = plot_scores_for_single_metric(metric, metrics_results_all_games[metric])
        means_by_metrics.append(mean)
        stds_by_metrics.append(std)
        print(f"\nMetric: {metric}\nMean: {mean:.2f}, STD: {std:.2f}\n")
    title = "Distributions of all metrics across all games"
    plt.title(title + f"\n(with {MEAN_MARKER_STYLE['marker']}-markers "
                      f"for means and error bars for +-STD)")
    plt.errorbar(metrics, means_by_metrics, stds_by_metrics, linestyle="none", **MEAN_MARKER_STYLE)
    plt.savefig(ANALYSIS_DIR / (title + ".png"))
    plt.show()


def preliminary_analysis_by_game():
    # game_ids = ["0036", "0037", "0027", "0028", "0030", "0032"]
    # game_ids = ["0051"]
    # game_ids = ["0051", "0056", "0057", "0058", "0059", "0060"]
    # game_ids = ["0064", "0065", "0067", "0068", "0069", "0070", "0071", "0072", "0073"]
    # game_ids = ["0051", "0056", "0057", "0058", "0059", "0060", "0064", "0065", "0067", "0068", "0069", "0070", "0071", "0072", "0073"]
    # game_ids = ["0051", "0056", "0057", "0058", "0059", "0060", "0064", "0065", "0067", "0068", "0069", "0070", "0071", "0072", "0073"]
    game_ids = [game_dir.name for game_dir in Path(DIRS_PREFIX).glob("*")
                if game_dir.is_dir() and game_dir.name.isdigit() and "00001" not in game_dir.name]

    hist_for_daytime_phases = True
    hist_for_nighttime_phases = False

    did_mafia_win_all_games = []
    did_llm_win_all_games = []
    was_llm_voted_out_all_games = []
    is_llm_mafia_all_games = []
    metrics_results_all_games = defaultdict(list)

    reset_message_lengths_across_all_games = []
    for game_id in game_ids:

        llm_player_name, all_players, mafia_players, human_players, config, \
            metrics_results, all_comments, parsed_messages_by_phase, was_llm_voted_out, \
            is_llm_mafia, did_mafia_win, did_llm_win = get_single_game_results(game_id)

        (ANALYSIS_DIR / ("game" + game_id + "_comments.txt")).write_text("\n".join(all_comments))

        if LLM_IDENTIFICATION in metrics_results:
            plot_single_pie_chart(f"Percentage of LLM identification in game {game_id}",
                                  metrics_results[LLM_IDENTIFICATION],
                                  "LLM was identified", "LLM was not identified")

        did_mafia_win_all_games.append(did_mafia_win)
        did_llm_win_all_games.append(did_llm_win)
        was_llm_voted_out_all_games.append(was_llm_voted_out)
        is_llm_mafia_all_games.append(is_llm_mafia)
        for metric in metrics_results:
            metrics_results_all_games[metric].append(metrics_results[metric])

        plot_game_flow(game_id, all_players, parsed_messages_by_phase, llm_player_name)
        # # plot_game_flow(game_id, human_players, parsed_messages_by_phase, llm_player_name)
        # plot_game_flow(game_id, [llm_player_name], parsed_messages_by_phase, llm_player_name)
        player_message_lengths = plot_messages_histogram_in_phase(
            all_players, parsed_messages_by_phase, game_id=game_id, llm_player_name=llm_player_name,
            daytime_phases=hist_for_daytime_phases, nighttime_phases=hist_for_nighttime_phases,
        )
        for player in player_message_lengths:
            reset_message_lengths_across_all_games += player_message_lengths[player]

    phase_name = get_phase_name(hist_for_daytime_phases, hist_for_nighttime_phases)
    plot_messages_histogram_in_all_games(reset_message_lengths_across_all_games,
                                         phase_name=phase_name)

    plot_all_pie_charts(did_mafia_win_all_games, did_llm_win_all_games,
                        was_llm_voted_out_all_games, is_llm_mafia_all_games)

    plot_metric_scores(metrics_results_all_games)

    llm_only_reset_message_lengths_across_all_games = []
    human_only_reset_message_lengths_across_all_games = []
    for game_id in game_ids:  # Yes, I'm aware this is currently repetition of calculation...
        llm_player_name, all_players, mafia_players, human_players, config, \
            metrics_results, all_comments, parsed_messages_by_phase, was_llm_voted_out, \
            is_llm_mafia, did_mafia_win, did_llm_win = get_single_game_results(game_id)
        player_message_lengths = plot_messages_histogram_in_phase(
            [llm_player_name], parsed_messages_by_phase, game_id=game_id,
            llm_player_name=llm_player_name, plot_general_histogram=False, plot_for_each_player=False,
            daytime_phases=hist_for_daytime_phases, nighttime_phases=hist_for_nighttime_phases,
        )
        llm_only_reset_message_lengths_across_all_games += player_message_lengths[llm_player_name]
        player_message_lengths = plot_messages_histogram_in_phase(
            human_players, parsed_messages_by_phase, game_id=game_id,
            plot_general_histogram=False, plot_for_each_player=False,
            daytime_phases=hist_for_daytime_phases, nighttime_phases=hist_for_nighttime_phases,
        )
        for player in player_message_lengths:
            human_only_reset_message_lengths_across_all_games += player_message_lengths[player]
    phase_name = get_phase_name(hist_for_daytime_phases, hist_for_nighttime_phases)
    plot_messages_histogram_in_all_games(llm_only_reset_message_lengths_across_all_games,
                                         phase_name=phase_name, player_name="LLM")
    plot_messages_histogram_in_all_games(human_only_reset_message_lengths_across_all_games,
                                         phase_name=phase_name, player_name="human-players")


def get_games_statistics():
    all_games = []
    number_of_phases_per_game = {}
    all_messages_per_game = {}
    llm_messages_per_game = {}
    all_players_per_game = {}
    did_llm_win_per_game = {}
    all_metrics = [LLM_IDENTIFICATION] + METRICS_TO_SCORE
    metrics_per_game = {metric: {} for metric in all_metrics}
    for game_dir in Path(DIRS_PREFIX).glob("*"):
        if game_dir.is_dir() and game_dir.name.isdigit() and "00001" not in game_dir.name:
            all_games.append(game_dir)
            __llm_player_name, all_players, __mafia_players, __human_players, __config, \
                metrics_results, __all_comments, parsed_messages_by_phase, __was_llm_voted_out, \
                __is_llm_mafia, __did_mafia_win, did_llm_win = get_single_game_results(game_dir.name)
            number_of_phases_per_game[game_dir.name] = len(parsed_messages_by_phase)
            all_messages_including_manager = sum([phase.messages for phase in parsed_messages_by_phase], [])
            all_messages_per_game[game_dir.name] = [msg for msg in all_messages_including_manager if not msg.is_manager]
            llm_messages_per_game[game_dir.name] = [msg for msg in all_messages_per_game[game_dir.name] if msg.is_llm]
            all_players_per_game[game_dir.name] = all_players
            did_llm_win_per_game[game_dir.name] = did_llm_win
            for metric in metrics_results:
                if int(game_dir.name) < 40:  # no identification and others are 0 to 100
                    if metric in METRICS_TO_SCORE:
                        metrics_per_game[metric][game_dir.name] = avg([score / 100 for score in metrics_results[metric]])
                else:
                    metrics_per_game[metric][game_dir.name] = avg(metrics_results[metric])
    num_players = [len(v) for v in all_players_per_game.values()]
    print(f"# Games: {len(all_games)}\n"
          f"Avg # Phases: {avg(number_of_phases_per_game.values())}\n"
          f"Avg # Players: {avg(num_players)}\n"
          f"\tSTD of # Players: {np.std(num_players)}\n"
          f"\tMin of # Players: {min(num_players)}\n"
          f"\tMax of # Players: {max(num_players)}\n"
          f"Avg # Messages: {avg([len(v) for v in all_messages_per_game.values()])}\n"
          f"LLM Avg # Messages: {avg([len(v) for v in llm_messages_per_game.values()])}\n"
          f"Win %: {avg(did_llm_win_per_game.values())}\n"
          f"\n")
    for metric in metrics_per_game:
        print(f"{metric}: {avg(metrics_per_game[metric].values())}")
    print()
    multiple_games_stats = [3] * (7 * 2) + [2] + [1] * 8 + [1] * (6 * 3) + [1] * 4 + [2] * 2 + [
        1] * 4 + [3] * 2 + [5] * (2 + 2) + [4] * 3 + [6] * 4 +  [7] * 6 + [1] * 11 + [2] * 5 + [
        1] * 11
    print(f"statistics of players playing in multiple games:\n"
          f"Average: {avg(multiple_games_stats)}\n"
          f"STD: {np.std(multiple_games_stats)}\n"
          f"Min: {min(multiple_games_stats)}\n"
          f"Max: {max(multiple_games_stats)}\n"
          f"Total number of players: {len(multiple_games_stats)}")


def calculate_timing_diffs(phase: Phase, this_game_human_player_messages_timing_diffs,
                           this_game_llm_player_messaging_timing_diffs):
    for i, message in enumerate(phase.messages):
        if message.is_manager:
            continue
        timing_diff = message.timestamp - phase.messages[i - 1].timestamp  # phase.messages[0] is manager!
        if message.is_llm:
            this_game_llm_player_messaging_timing_diffs.append(timing_diff)
        else:
            this_game_human_player_messages_timing_diffs[message.name].append(timing_diff)


def calculate_self_timing_diffs(phase: Phase, this_game_human_player_self_timing_diffs,
                                this_game_llm_player_self_timing_diffs):
    start_phase_message = phase.messages[0]
    for player in phase.active_players:
        messages = [start_phase_message] + [message for message in phase.messages
                                            if message.name == player]
        for i, message in enumerate(messages):
            if i == 0:
                continue
            timing_diff = message.timestamp - phase.messages[i - 1].timestamp
            if message.is_llm:
                this_game_llm_player_self_timing_diffs.append(timing_diff)
            else:
                this_game_human_player_self_timing_diffs[player].append(timing_diff)


def get_message_timings_statistics():
    all_games = []
    daytime_minutes_by_game = {}
    nighttime_minutes_by_game = {}
    all_daytime_messages_by_game = {}
    all_nighttime_messages_by_game = {}
    number_of_messages_by_humans_in_daytime = []
    number_of_messages_by_llm_in_daytime = []
    # timing diff (1): between a message and the previous one in the conversation
    timing_diff_of_messages_sent_by_humans = []
    timing_diff_of_messages_sent_by_llm = []
    mean_per_game_of_timing_diff_of_messages_sent_by_humans = []
    mean_per_game_of_timing_diff_of_messages_sent_by_llm = []
    # timing diff (2): between a message and the same player's previous one
    timing_diff_of_self_messages_by_humans = []
    timing_diff_of_self_messages_by_llm = []
    mean_per_game_of_timing_diff_of_self_messages_by_humans = []
    mean_per_game_of_timing_diff_of_self_messages_by_llm = []
    for game_dir in Path(DIRS_PREFIX).glob("*"):
        if game_dir.is_dir() and game_dir.name.isdigit() and "00001" not in game_dir.name:
            all_games.append(game_dir)
            llm_player_name, __all_players, __mafia_players, human_players, config, \
                __metrics_results, __all_comments, parsed_messages_by_phase, __was_llm_voted_out, \
                __is_llm_mafia, __did_mafia_win, __did_llm_win = get_single_game_results(game_dir.name)
            game_name = game_dir.name
            # timing diff (1)
            this_game_human_player_messages_timing_diffs = {player: [] for player in human_players}
            this_game_llm_player_messaging_timing_diffs = []
            # timing diff (2)
            this_game_human_player_self_timing_diffs = {player: [] for player in human_players}
            this_game_llm_player_self_timing_diffs = []
            for phase in parsed_messages_by_phase:
                phase.reset_timestamps()
                # timing diff (1)
                calculate_timing_diffs(phase, this_game_human_player_messages_timing_diffs,
                                       this_game_llm_player_messaging_timing_diffs)
                # timing diff (2)
                calculate_self_timing_diffs(phase, this_game_human_player_self_timing_diffs,
                                            this_game_llm_player_self_timing_diffs)
                player_messages = [message for message in phase.messages if not message.is_manager]
                if phase.is_daytime:
                    all_daytime_messages_by_game[game_name] = player_messages
                    num_messages_by_humans = {player: len([msg for msg in phase.messages if msg.name == player])
                                              for player in phase.active_players if player != llm_player_name}
                    number_of_messages_by_humans_in_daytime.extend(list(num_messages_by_humans.values()))
                    if llm_player_name in phase.active_players:
                        number_of_messages_by_llm_in_daytime.append(len([msg for msg in phase.messages
                                                                          if msg.name == llm_player_name]))
                else:
                    all_nighttime_messages_by_game[game_name] = player_messages
            # timing diff (1)
            ## record the mean time diff for each player in the game
            mean_per_game_of_timing_diff_of_messages_sent_by_humans.extend(
                [np.mean(player_time_diffs) for player_time_diffs
                 in this_game_human_player_messages_timing_diffs.values()])
            mean_per_game_of_timing_diff_of_messages_sent_by_llm.append(
                np.mean(this_game_llm_player_messaging_timing_diffs))
            ## just in case still have all time diffs together
            timing_diff_of_messages_sent_by_humans.extend(
                sum(this_game_human_player_messages_timing_diffs.values(), []))
            timing_diff_of_messages_sent_by_llm.extend(this_game_llm_player_messaging_timing_diffs)
            # timing diff (2)
            ## record the mean time diff for each player in the game
            mean_per_game_of_timing_diff_of_self_messages_by_humans.extend(
                [np.mean(player_time_diffs) for player_time_diffs
                 in this_game_human_player_self_timing_diffs.values()])
            mean_per_game_of_timing_diff_of_self_messages_by_llm.append(
                np.mean(this_game_llm_player_self_timing_diffs))
            ## just in case still have all time diffs together
            timing_diff_of_self_messages_by_humans.extend(
                sum(this_game_human_player_self_timing_diffs.values(), []))
            timing_diff_of_self_messages_by_llm.extend(this_game_llm_player_self_timing_diffs)
            daytime_minutes_by_game[game_name] = config[DAYTIME_MINUTES_KEY]
            nighttime_minutes_by_game[game_name] = config[NIGHTTIME_MINUTES_KEY]
            print("break")

    # timing diff (1)
    print(f"Time between a player's message and the previous message:")
    for player_type, timing_diffs in [("Human", timing_diff_of_messages_sent_by_humans),
                                      ("LLM", timing_diff_of_messages_sent_by_llm),
                                      ("All Players", timing_diff_of_messages_sent_by_humans
                                                      + timing_diff_of_messages_sent_by_llm)]:
        print(f"{player_type}: mean = {np.mean(timing_diffs):.2f}, "
              f"std = {np.std(timing_diffs):.2f}")

    # timing diff (2)
    print(f"Time between a player's message and his own previous message:")
    for player_type, timing_diffs in [("Human", timing_diff_of_self_messages_by_humans),
                                      ("LLM", timing_diff_of_self_messages_by_llm),
                                      ("All Players", timing_diff_of_self_messages_by_humans
                                                      + timing_diff_of_self_messages_by_llm)]:
        print(f"{player_type}: mean = {np.mean(timing_diffs):.2f}, "
              f"std = {np.std(timing_diffs):.2f}")
    title = "Density of a Player's Mean Time Difference\nBetween Messages in a Game"
    xlabel = "Player's Mean Time Difference Between Messages in a Game (in seconds)"
    plot_timing_diffs_histogram(timing_diff_of_self_messages_by_humans,
                                timing_diff_of_self_messages_by_llm,
                                title, xlabel)  # needs to be adjusted to the function modification

    print(f"Number of messages by a player per daytime phase:")
    for player_type, num_of_messages in [("Human", number_of_messages_by_humans_in_daytime),
                                         ("LLM", number_of_messages_by_llm_in_daytime),
                                         ("All Players", number_of_messages_by_humans_in_daytime
                                                         + number_of_messages_by_llm_in_daytime)]:
        print(f"{player_type}: mean = {np.mean(num_of_messages):.2f}, "
              f"std = {np.std(num_of_messages):.2f}")

    games_by_daytime_minutes = {length: [] for length in set(daytime_minutes_by_game.values())}
    games_by_nighttime_minutes = {length: [] for length in set(nighttime_minutes_by_game.values())}
    for game_name, length in daytime_minutes_by_game.items():
        games_by_daytime_minutes[length].append(game_name)
    for game_name, length in nighttime_minutes_by_game.items():
        games_by_nighttime_minutes[length].append(game_name)
    all_daytime_messages_by_daytime_length = {length: [] for length in games_by_daytime_minutes.keys()}
    for length in games_by_daytime_minutes.keys():
        for game_name in games_by_daytime_minutes[length]:
            all_daytime_messages_by_daytime_length[length].extend(all_daytime_messages_by_game[game_name])
    all_daytime_messages = sum(all_daytime_messages_by_daytime_length.values(), [])
    all_nighttime_messages_by_nighttime_length = {length: [] for length in games_by_nighttime_minutes.keys()}
    for length in games_by_nighttime_minutes.keys():
        for game_name in games_by_nighttime_minutes[length]:
            all_nighttime_messages_by_nighttime_length[length].extend(all_daytime_messages_by_game[game_name])
    all_nighttime_messages = sum(all_nighttime_messages_by_nighttime_length.values(), [])
    # plots:
    # ## timing density plots by daytime length
    # for length, messages in all_daytime_messages_by_daytime_length.items():
    #     title = (f"Density of Message Timings During Daytime Phase,\n"
    #              f"for Games with Daytime of Length {length}")
    #     plot_timing_histogram(messages, title)
    # ## timing density plot for all messages in all games:
    # title = (f"Density of Message Timings During Daytime Phase,"
    #          f"\nfor All Message in All Games")
    # plot_timing_histogram(all_daytime_messages, title)
    # ## violin plots of timings:
    # plt.violinplot([[message.timestamp for message in all_daytime_messages
    #                  if message.is_llm is b] for b in (True, False)],
    #                vert=False, showmeans=True)
    # plt.show()

    print("break")


def plot_timing_histogram(messages, title):
    plt.title(title)
    for player_type, is_llm, density_color, mean_color, std_color in [
        ("LLM", True, "red", "darkred", "indianred"),
        ("Human", False, "blue", "darkblue", "slateblue")]:
        player_type_messages = [message for message in messages
                                if message.is_llm == is_llm]
        timings = [message.timestamp for message in player_type_messages]
        mean = np.mean(timings)
        std = np.std(timings)
        plt.hist(timings, density=True, bins=20, alpha=0.5, color=density_color,
                 label=fr"{player_type}")
        plt.axvline(mean, color=mean_color, linestyle="-", label=fr"{player_type} $\mu = {mean:.2f}$")
        plt.axvline(mean + std, color=std_color, linestyle="--",
                    label=fr"{player_type} $\mu \pm \sigma$ $(\sigma = {std:.2f})$")
        plt.axvline(mean - std, color=std_color, linestyle="--")
    plt.xlabel("Seconds Within a Daytime Phase")
    plt.ylabel("Density of Sent Messages")
    plt.legend()
    plt.show()


def plot_timing_diffs_histogram(human_timing_diffs, llm_timing_diffs, title,
                                xlabel, plot_name, ax, kde_bandwidth: float = 1, extend_xlim=False,
                                plot_separately_by_base_models=False):
    # plt.title(title)
    # plt.xlabel(xlabel)
    # plt.ylabel("Proportion (density)")
    ax.set_title(title, fontsize=15)
    ax.set_xlabel(xlabel, fontsize=14)
    ax.set_ylabel("Proportion (density)", fontsize=14)
    max_x = max(human_timing_diffs + llm_timing_diffs)
    if plot_separately_by_base_models:
        classes = [("Human", human_timing_diffs, "blue"),
                   ("Agent (Llama3.1 8B)", llm_timing_diffs[:NUM_GAMES_WITH_8B_MODEL], "orange"),
                   ("Agent (Llama3.3 70B)", llm_timing_diffs[NUM_GAMES_WITH_8B_MODEL:], "red")]
    else:
        classes = [("Human", human_timing_diffs, "blue"), ("Agent", llm_timing_diffs, "red")]
    for player_type, timing_diffs, color in classes:
        # plt.hist(timing_diffs, density=True, bins=20, alpha=0.5, color=color,
        #          label=fr"{player_type} $(\mu = {np.mean(timing_diffs):.2f}, "
        #                fr"\sigma = {np.std(timing_diffs):.2f})$")
        timing_diffs_squeezed = np.array(timing_diffs)[:, np.newaxis]
        kde_timing_diffs = KernelDensity(
            kernel="gaussian", bandwidth=kde_bandwidth).fit(timing_diffs_squeezed)
        x_range = np.linspace(0, max_x + 5, 1000)
        log_density = kde_timing_diffs.score_samples(x_range[:, np.newaxis])
        # plt.fill_between(
        ax.fill_between(
            x_range, np.exp(log_density), 0, alpha=0.5, color=color,
            label=fr"{player_type}{'\n'}$(\mu = {np.mean(timing_diffs):.2f}, "
                  fr"\sigma = {np.std(timing_diffs):.2f})$")
    # plt.ylim(0, np.exp(max(log_density)) * 1.1)
    ax.set_ylim(0, np.exp(max(log_density)) * 1.1)
    if extend_xlim:
        ax.set_xlim(ax.get_xlim()[0] + 2, ax.get_xlim()[1] * 1.3)
    ax.legend(fontsize=14)
    # plt.savefig(ANALYSIS_DIR / f"{plot_name}.png")
    # plt.show()


def separate_embedding_classes(embeddings: np.ndarray, model_name: str,
                               named_classes: list[tuple[list[bool], str]]):
    # local imports to reduce time when not running this analysis
    from sklearn.svm import SVC
    from sklearn.linear_model import LogisticRegression
    from sklearn.discriminant_analysis import LinearDiscriminantAnalysis, \
        QuadraticDiscriminantAnalysis
    from sklearn.metrics import classification_report
    named_classifiers = [
        (SVC, dict(kernel="linear"), "Linear SVM"),
        (SVC, dict(kernel="poly", degree=3), "Polynomial (deg=3) SVM"),
        (SVC, dict(kernel="rbf"), "Gaussiam SVM"),
        (SVC, dict(kernel="sigmoid"), "Sigmoid SVM"),
        (LogisticRegression, dict(solver="liblinear"), "Logistic Regression"),
        (LinearDiscriminantAnalysis, {}, "LDA"),
        (QuadraticDiscriminantAnalysis, dict(reg_param=0.5), "QDA"),
    ]
    print(f"\nSeparating the embeddings of {model_name} with classifiers:\n")
    for classes, class_name in named_classes:
        print(f"Separating by {class_name}:\n")
        for classifier, params, classifier_name in named_classifiers:
            print(f"Performance of {classifier_name}:")
            prediction = classifier(**params).fit(embeddings, classes).predict(embeddings)
            print(classification_report(classes, prediction))


def analyze_embeddings(messages: list[ParsedMessage], is_mafia_all_messages: list[bool],
                       is_daytime_all_messages: list[bool]):
    is_llm_all_messages = [message.is_llm for message in messages]
    labels, colors = [], []
    for i, is_llm in enumerate(is_llm_all_messages):
        player_type = "LLM" if is_llm else "Human"
        role = MAFIA_ROLE if is_mafia_all_messages[i] else BYSTANDER_ROLE
        phase = DAYTIME if is_daytime_all_messages[i] else NIGHTTIME
        if role == BYSTANDER_ROLE and phase == NIGHTTIME:
            phase = DAYTIME  # message was sent in a delay due to a bug
            is_daytime_all_messages[i] = True
        label = f"{player_type}-{role}-{phase.lower()}"
        labels.append(label)
    np.random.seed(0)
    import plotly.express as px
    import pandas as pd
    from sklearn.decomposition import PCA
    for model_name in SENTENCE_EMBEDDING_MODELS:
        embeddings = get_embeddings(messages, model_name=model_name)
        named_classes = [(is_llm_all_messages, "is_llm"), (is_mafia_all_messages, "is_mafia"),
                         (is_daytime_all_messages, "is_daytime")]
        separate_embedding_classes(embeddings, model_name, named_classes)
        embedding_pca_3d = PCA(n_components=3).fit(embeddings)
        embeddings_3d = embedding_pca_3d.transform(embeddings)
        explain_variance_ratios = embedding_pca_3d.explained_variance_ratio_
        print(f"Explained variance ratios for PCA 3D on {model_name}'s embeddings:")
        print(*[f"PC{i + 1}: {ratio:.3}" for i, ratio in enumerate(explain_variance_ratios)], sep="\n")
        print(f"Sum of explained variance ratios: {sum(explain_variance_ratios):.3}")
        # compare classifiers to 3D embeddings
        separate_embedding_classes(embeddings_3d, model_name, named_classes)
        full_df = pd.DataFrame(embeddings_3d, columns=["PC1", "PC2", "PC3"])
        full_df["labels"] = labels
        for df, title_addition in [
            (full_df, " - all"),
            (full_df[is_llm_all_messages], " - only LLM"),
            (full_df[~np.array(is_llm_all_messages)], " - only Human"),
            (full_df[is_mafia_all_messages], " - only mafia"),
            (full_df[~np.array(is_mafia_all_messages)], " - only bystander"),
            (full_df[is_daytime_all_messages], " - only daytime"),
            (full_df[~np.array(is_daytime_all_messages)], " - only nighttime"),
        ]:
            fig = px.scatter_3d(df, x="PC1", y="PC2", z="PC3",
                                color="labels", size=np.ones(len(df)) * 0.5, opacity=1,
                                color_discrete_map=PLOT_3D_COLOR_MAP,
                                category_orders={"color": sorted(PLOT_3D_COLOR_MAP.keys())},
                                title='3D PCA Visualization' + title_addition)
            model_name = model_name.replace('/', '_')
            title_addition = title_addition.replace(" ", "_")
            fig.write_html(ANALYSIS_DIR / f"{model_name}_3d_plot{title_addition}.html")
        print("wait after saving HTMLs")


def get_embeddings(messages: list[ParsedMessage], model_name=SENTENCE_EMBEDDING_MODELS[0]):
    model_name_for_path = model_name.replace("/", "_")
    embeddings_path = ANALYSIS_DIR / f"embeddings_full_{model_name_for_path}.npy"
    if embeddings_path.exists():
        embeddings = np.load(embeddings_path)
        if len(embeddings) == len(messages):
            return embeddings  # else, they are not updated
    # local imports to reduce time when not running this analysis
    from sentence_transformers import SentenceTransformer
    try:
        model = SentenceTransformer(model_name)
    except ValueError:
        model = SentenceTransformer(model_name, trust_remote_code=True)
    embeddings = model.encode([message.content for message in messages])
    np.save(embeddings_path, embeddings)
    return embeddings


def plot_percentage_bars_chart(did_llm_win, is_llm_mafia,
                               did_human_win_as_mafia, did_human_win_as_bystander,
                               plot_separately_by_base_models=False,
                               plot_separately_by_role=False):
    did_llm_win_as_mafia = []
    did_llm_win_as_bystander = []
    did_small_llm_win_as_mafia = []
    did_small_llm_win_as_bystander = []
    did_large_llm_win_as_mafia = []
    did_large_llm_win_as_bystander = []
    for i, llm_win in enumerate(did_llm_win):
        if plot_separately_by_base_models:
            mafia_win_list = did_small_llm_win_as_mafia if i < NUM_GAMES_WITH_8B_MODEL else did_large_llm_win_as_mafia
            bystander_win_list = did_small_llm_win_as_bystander if i < NUM_GAMES_WITH_8B_MODEL else did_large_llm_win_as_bystander
        else:
            mafia_win_list = did_llm_win_as_mafia
            bystander_win_list = did_llm_win_as_bystander
        if is_llm_mafia[i]:
            mafia_win_list.append(llm_win)
        else:
            bystander_win_list.append(llm_win)
    # default_true_color, default_false_color = "royalblue", "lightblue"  # "darkblue", "slateblue"  # "darkred", "indianred"
    human_true_color, human_false_color = "mediumblue", "cornflowerblue"
    llm_true_color, llm_false_color = "darkred", "indianred"  # also used as large LLM
    small_llm_true_color, small_llm_false_color = "sienna", "sandybrown"  # "goldenrod", "khaki"  # "darkorange", "gold"

    if plot_separately_by_base_models:
        false_classes = [
            ("Human Loses\nas Bystander", human_false_color),
            ("  Agent Loses\n(Llama3.1 8B)\nas Bystander", small_llm_false_color),
            ("   Agent Loses\n(Llama3.3 70B)\nas Bystander", llm_false_color),
            ("Human Loses\nas Mafia", human_false_color),
            ("  Agent Loses\n(Llama3.1 8B)\nas Mafia", small_llm_false_color),
            ("   Agent Loses\n(Llama3.3 70B)\nas Mafia", llm_false_color)
        ]
        true_classes = [
            ("Human Wins\nas Bystander", did_human_win_as_bystander, human_true_color),
            ("Agent Wins  \n(Llama3.1 8B)\nas Bystander", did_small_llm_win_as_bystander, small_llm_true_color),
            ("Agent Wins   \n(Llama3.3 70B)\nas Bystander", did_large_llm_win_as_bystander, llm_true_color),
            ("Human Wins\nas Mafia", did_human_win_as_mafia, human_true_color),
            ("Agent Wins  \n(Llama3.1 8B)\nas Mafia", did_small_llm_win_as_mafia, small_llm_true_color),
            ("Agent Wins   \n(Llama3.3 70B)\nas Mafia", did_large_llm_win_as_mafia, llm_true_color),
        ]
    else:
        false_classes = [
            # ("Human Loses", human_false_color),
            # ("Agent Loses", llm_false_color),
            ("Human Loses\nas Bystander", human_false_color),
            ("Agent Loses\nas Bystander", llm_false_color),
            ("Human Loses\nas Mafia", human_false_color),
            ("Agent Loses\nas Mafia", llm_false_color)
        ]
        true_classes = [
            # ("Human Wins", did_human_win_as_mafia + did_human_win_as_bystander, human_true_color),
            # ("LLM Wins", did_llm_win, llm_true_color),
            ("Human Wins\nas Bystander", did_human_win_as_bystander, human_true_color),
            ("Agent Wins\nas Bystander", did_llm_win_as_bystander, llm_true_color),
            ("Human Wins\nas Mafia", did_human_win_as_mafia, human_true_color),
            ("Agent Wins\nas Mafia", did_llm_win_as_mafia, llm_true_color),
        ]

    if plot_separately_by_role:
        fig, axes = plt.subplots(2, 1, figsize=(5, 3.5), sharex=True)

        # --- BYSTANDER ---
        # set background to the first subplot slot and draw the lose-background bars there
        plt.sca(axes[0])
        axes[0].yaxis.tick_right()

        # draw the background "loses" bars on the background axes
        for false_label, false_color in false_classes[::-1]:
            if "Mafia" in false_label:
                continue
            plt.barh(false_label.replace("\nas Bystander", ""), 1, color=false_color)

        # overlay a new (frameless) axes in the same subplot slot for the true bars
        plt.subplot(2, 1, 1, sharex=axes[0], frameon=False)
        for true_label, values, true_color in true_classes[::-1]:
            if "Mafia" in true_label:
                continue
            true_label = true_label.replace("\nas Bystander", "")
            plot_true_label_bars(true_color, true_label, values)
        plt.xlim(0, 1)
        plt.xlabel("Winning Percentage as Bystander", fontsize=12)

        # --- MAFIA ---
        # set background to the first subplot slot and draw the lose-background bars there
        plt.sca(axes[1])
        axes[1].yaxis.tick_right()

        # draw the background "loses" bars on the background axes
        for false_label, false_color in false_classes[::-1]:
            if "Bystander" in false_label:
                continue
            plt.barh(false_label.replace("\nas Mafia", ""), 1, color=false_color)

        # overlay a new (frameless) axes in the same subplot slot for the true bars
        plt.subplot(2, 1, 2, sharex=axes[1], frameon=False)
        for true_label, values, true_color in true_classes[::-1]:
            if "Bystander" in true_label:
                continue
            true_label = true_label.replace("\nas Mafia", "")
            plot_true_label_bars(true_color, true_label, values)
        plt.xlim(0, 1)
        plt.xlabel("Winning Percentage as Mafia", fontsize=12)

    else:
        figsize = (5, 3.5) if plot_separately_by_base_models else (5, 2.5)
        plt.figure(figsize=figsize)
        ax = plt.subplot(1, 1, 1)  # used to merge X-axis
        ax.yaxis.tick_right()
        for false_label, false_color in false_classes[::-1]:
            plt.barh(false_label, 1, color=false_color)
        plt.subplot(1, 1, 1, sharex=ax, frameon=False)
        for true_label, values, true_color in true_classes[::-1]:
            plot_true_label_bars(true_color, true_label, values)
        plt.xlim(0, 1)
        plt.xlabel("Winning Percentage", fontsize=12)

    plt.xticks([0, 0.2, 0.4, 0.6, 0.8, 1], ["0%", "20%", "40%", "60%", "80%", "100%"])
    plt.tight_layout()
    plt.savefig(ANALYSIS_DIR / "llm_performance_in_game.png")
    plt.show()


def plot_true_label_bars(true_color, true_label, values):
    true_percent = avg(values)
    plt.barh(true_label, true_percent, color=true_color)
    plt.text(true_percent, true_label, f"{true_percent * 100:.2f}% ", va="center", ha="right",
             c="white")
    if true_percent != 1:
        plt.text(true_percent, true_label, f" {(1 - true_percent) * 100:.2f}%", va="center",
                 ha="left")


def calc_message_amount_by_player_during_daytime(parsed_messages_by_phase_all_games: list[list[Phase]],
                                                 llm_names_all_games: list[str]):
    human_player_daytime_message_amount = []
    llm_player_daytime_message_amount = []
    for phases_in_game, llm_name in zip(parsed_messages_by_phase_all_games, llm_names_all_games):
        for phase in phases_in_game:
            if not phase.is_daytime:
                continue
            for player_name in phase.active_players:
                message_amounts = llm_player_daytime_message_amount if player_name == llm_name \
                    else human_player_daytime_message_amount
                message_amounts.append(len([msg for msg in phase.messages
                                            if msg.name == player_name]))
    print("Now in Latex table format:")
    print(fr"\textbf{{Player Type}} & \textbf{{Avg \# Msg ($\pm$ STD)}} \\")
    for player_type, all_amounts in [("Human", human_player_daytime_message_amount),
                                     ("LLM", llm_player_daytime_message_amount),
                                     # ("All players", human_player_daytime_message_amount + llm_player_daytime_message_amount)
                                     ]:
        print(fr"{player_type} & {display_mean_std(all_amounts)} \\")
    print("\n")


def calc_game_mean_timing_diffs(parsed_messages_by_phase, human_players,
                                mean_per_game_of_timing_diff_of_messages_sent_by_humans,
                                mean_per_game_of_timing_diff_of_messages_sent_by_llm,
                                mean_per_game_of_timing_diff_of_self_messages_by_humans,
                                mean_per_game_of_timing_diff_of_self_messages_by_llm):
    # timing diff (1)
    this_game_human_player_messages_timing_diffs = {player: [] for player in human_players}
    this_game_llm_player_messaging_timing_diffs = []
    # timing diff (2)
    this_game_human_player_self_timing_diffs = {player: [] for player in human_players}
    this_game_llm_player_self_timing_diffs = []
    for phase in parsed_messages_by_phase:
        phase_copy = phase.copy()  # to not change the original phase for the rest of analysis
        phase_copy.reset_timestamps()
        # timing diff (1)
        calculate_timing_diffs(phase_copy, this_game_human_player_messages_timing_diffs,
                               this_game_llm_player_messaging_timing_diffs)
        # timing diff (2)
        calculate_self_timing_diffs(phase_copy, this_game_human_player_self_timing_diffs,
                                    this_game_llm_player_self_timing_diffs)
    # timing diff (1)
    mean_per_game_of_timing_diff_of_messages_sent_by_humans.extend(
        [np.mean(player_time_diffs) for player_time_diffs
         in this_game_human_player_messages_timing_diffs.values()])
    mean_per_game_of_timing_diff_of_messages_sent_by_llm.append(
        np.mean(this_game_llm_player_messaging_timing_diffs))
    # timing diff (2)
    mean_per_game_of_timing_diff_of_self_messages_by_humans.extend(
        [np.mean(player_time_diffs) for player_time_diffs
         in this_game_human_player_self_timing_diffs.values()])
    mean_per_game_of_timing_diff_of_self_messages_by_llm.append(
        np.mean(this_game_llm_player_self_timing_diffs))


def plot_merged_timing_diff_hists(mean_per_game_of_timing_diff_of_messages_sent_by_humans,
                                  mean_per_game_of_timing_diff_of_messages_sent_by_llm,
                                  mean_per_game_of_timing_diff_of_self_messages_by_humans,
                                  mean_per_game_of_timing_diff_of_self_messages_by_llm,
                                  plot_separately_by_base_models=False):
    fig, axs = plt.subplots(nrows=1, ncols=2, figsize=(11, 5))
    plot_timing_diffs_histogram(mean_per_game_of_timing_diff_of_messages_sent_by_humans,
                                mean_per_game_of_timing_diff_of_messages_sent_by_llm,
                                "Distribution of Average Time Between a Player's Message\n"
                                "and the Previous Message by Any Other Player",
                                "Player's Average Waiting Time\nFrom Previous Message (seconds)",
                                "mean_time_diff_msg_to_any_prev",
                                axs[0], kde_bandwidth=1.5,
                                plot_separately_by_base_models=plot_separately_by_base_models)
    plot_timing_diffs_histogram(mean_per_game_of_timing_diff_of_self_messages_by_humans,
                                mean_per_game_of_timing_diff_of_self_messages_by_llm,
                                "Distribution of Average Time Difference\n"
                                "Between Messages of the Same Player",
                                "Player's Average Waiting Time\nBetween Self Messages (seconds)",
                                "mean_time_diff_same_player_msg",
                                axs[1], kde_bandwidth=5,
                                extend_xlim=True,
                                plot_separately_by_base_models=plot_separately_by_base_models)
    fig.tight_layout()
    plt.savefig(ANALYSIS_DIR / "mean_time_diff_hists.png")
    plt.show()


def calc_num_unique_words(messages):
    words = []
    for message in messages:
        raw_words = message.lower().split()  # split() also strips each word
        for word in raw_words:
            stripped_word = strip_special_chars(word)
            if stripped_word:
                words.append(stripped_word)
    return len(set(words))


def calc_content_metrics_from_messages(content_metrics, messages):
    lengths = [len(message.split()) for message in messages]
    content_metrics[LENGTH].append(np.mean(lengths))
    content_metrics[REPETITION].append(len(messages) - len(set(messages)))
    content_metrics[NUM_UNIQUE_WORDS].append(calc_num_unique_words(messages))


def calc_mean_message_content_empiric_metrics(parsed_messages_by_phase, human_players,
                                              human_content_metrics, llm_content_metrics):
    human_messages_by_name = {player: [] for player in human_players}
    llm_messages = []
    for phase in parsed_messages_by_phase:
        for message in phase.messages:
            if message.is_manager:
                continue
            if message.is_llm:
                llm_messages.append(message.content)
            else:
                human_messages_by_name[message.name].append(strip_special_chars(message.content))
    for player, messages in human_messages_by_name.items():
        calc_content_metrics_from_messages(human_content_metrics, messages)
    calc_content_metrics_from_messages(llm_content_metrics, llm_messages)


def display_mean_std(metric_list):
    return rf"{np.mean(metric_list):.2f} ($\pm$ {np.std(metric_list):.2f})"


def calc_message_content_empiric_metrics(human_content_metrics, llm_content_metrics):
    print("Player type, then metrics by order:", ", ".join(CONTENT_METRICS))
    print("Now in Latex table format:")
    print(fr"\textbf{{Player Type}} & \textbf{{\# Words Per Message}} & "
          fr"\textbf{{\# Repeated Messages}} & \textbf{{\#  Unique Words}} \\")
    for player_type, metric_lists in [("Human", human_content_metrics),
                                      ("LLM", llm_content_metrics)]:
        print(f"{player_type} & {' & '.join([display_mean_std(metric_lists[metric]) for metric in CONTENT_METRICS])}" + " \\\\")


def calc_players_metric(metrics_results_all_games: defaultdict[str, list[int]]):
    for metric, results_by_game in metrics_results_all_games.items():
        all_results = sum(results_by_game, [])
        if metric == LLM_IDENTIFICATION:
            print(f"\n{metric}: {np.mean(all_results) * 100:.2f}%\n")
        else:
            print(f"% {metric.upper()}: MEAN, STD -\n"
                  f"{{COPY_HERE_NAME}} & {display_mean_std(all_results)} \\\\")


def calc_dataset_metadata(parsed_messages_by_phase_all_games: list[list[Phase]]):
    print("*** Dataset Metadata ***")
    all_messages_by_game = [sum([phase.messages for phase in game], [])
                            for game in parsed_messages_by_phase_all_games]
    all_messages_unified = sum(all_messages_by_game, [])
    num_games = len(parsed_messages_by_phase_all_games)
    num_messages = len(all_messages_unified)
    avg_num_messages_per_game = num_messages / num_games
    num_llm_messages = sum([message.is_llm for message in all_messages_unified])
    avg_num_llm_messages_per_game = num_llm_messages / num_games
    avg_num_phases = avg([len(game) for game in parsed_messages_by_phase_all_games])
    num_players_per_game = [len(game[0].active_players) for game in parsed_messages_by_phase_all_games]
    avg_num_players = avg(num_players_per_game)
    print(f"Our dataset consists of {num_games} games, with a total of {num_messages} messages "
          f"({avg_num_messages_per_game:.2f} messages per game on average), "
          f"{num_llm_messages} of which were sent by the LLM agent "
          f"({avg_num_llm_messages_per_game:.2f} per game on average).\n")
    print(f"NOW in Latex table format:")
    print(fr"{num_games} & {avg_num_phases:.2f} & {avg_num_players:.2f} "
          fr"& {avg_num_messages_per_game:.2f} & {avg_num_llm_messages_per_game:.2f} \\")
    print(f"\nGames Played.\n")
    print(f"The number of players per game ranged from {min(num_players_per_game)} "
          f"to {max(num_players_per_game)} ({avg_num_players:.2f} average, "
          f"{np.std(num_players_per_game):.2f} STD). "
          f"Games with 10 or fewer players included 2 mafia members, "
          f"while games with more than 10 players included 3. "
          f"Every game included one LLM agent as a player.")
    print("\n***\nREMEMBER to manually check statistics for num games played by a player!\n")


def add_human_winning_statistics(human_players, mafia_players, did_mafia_win,
                                 did_human_win_as_mafia_all_games,
                                 did_human_win_as_bystander_all_games):
    for player in human_players:
        if player in mafia_players:
            did_human_win_as_mafia_all_games.append(did_mafia_win)
        else:
            did_human_win_as_bystander_all_games.append(not did_mafia_win)


def check_variance_of_num_messages_through_time(parsed_messages_by_phase_all_games: list[list[Phase]]):
    MAX_DAYTIME_NUM = 6
    num_seconds_window = 90
    num_messages_per_time_window = defaultdict(list)
    for game in parsed_messages_by_phase_all_games:
        timestamp_offset = 0
        for phase in game[:2 * MAX_DAYTIME_NUM]:  # without outlier
            if not phase.is_daytime:
                continue
            phase_start_timestamp = phase.messages[0].timestamp
            phase_copy = phase.copy()  # to not change the original phase for the rest of analysis
            phase_copy.reset_timestamps(phase_start_timestamp - timestamp_offset)
            phase_start_timestamp = phase_copy.messages[0].timestamp
            phase_end_timestamp = phase_start_timestamp  # only initiation, gets updated
            num_messages_per_time_window_in_phase = defaultdict(int)
            for message in phase_copy.messages:
                if message.is_manager:
                    continue
                phase_end_timestamp = message.timestamp  # update until last non manager
                time_window = message.timestamp // num_seconds_window * num_seconds_window
                num_messages_per_time_window_in_phase[time_window] += 1
            timestamp_offset += phase_end_timestamp - phase_start_timestamp
            num_players = len(phase.active_players)
            for time_window, num_messages in num_messages_per_time_window_in_phase.items():
                num_messages_per_time_window[time_window].append(num_messages / num_players)
    ordered_timestamps = sorted(num_messages_per_time_window.keys())
    means, means_p_std, means_m_std = [], [], []
    for timestamp in ordered_timestamps:
        num_messages = num_messages_per_time_window[timestamp]
        mean, std = np.mean(num_messages), np.std(num_messages)
        means.append(mean)
        means_p_std.append(mean + std)
        means_m_std.append(mean - std)
    plt.title("Number of Messages Per Player Throughout the Game")
    plt.fill_between(ordered_timestamps, means_p_std, means_m_std, alpha=0.3,
                     label=r"mean $\pm$ STD", color="C0")
    plt.plot(ordered_timestamps, means, label="mean", color="C0")
    # plt.ylim(0, max(sum(num_messages_per_time_window.values(), [])))
    plt.ylim(0, max(means_p_std) * 1.3)
    plt.xlabel("Time From Game Start (in seconds)")
    plt.ylabel("Number of Messages Per Player")
    plt.legend()
    plt.savefig(ANALYSIS_DIR / "num_msg_per_player_by_time.png")
    plt.show()


def check_variance_of_num_messages_throughout_phases(parsed_messages_by_phase_all_games: list[list[Phase]]):
    MAX_DAYTIME_NUM = 6
    num_messages_per_phase = {i + 1: [] for i in range(MAX_DAYTIME_NUM)}  # by phase index
    num_players_per_phase = {i + 1: [] for i in range(MAX_DAYTIME_NUM)}  # by phase index
    for game in parsed_messages_by_phase_all_games:
        phase_counter = 0
        for phase in game:
            if not phase.is_daytime:
                continue
            phase_counter += 1
            if phase_counter not in num_messages_per_phase:
                continue
            player_messages = [msg for msg in phase.messages if not msg.is_manager]
            num_messages_per_phase[phase_counter].append(len(player_messages) / len(phase.active_players))
            num_players_per_phase[phase_counter].append(len(phase.active_players))
    means, means_p_std, means_m_std = [], [], []
    for num_messages in num_messages_per_phase.values():
        mean, std = np.mean(num_messages), np.std(num_messages)
        means.append(mean)
        means_p_std.append(mean + std)
        means_m_std.append(mean - std)
    # plt.title("Number of Messages Per Player By\nDaytime Phase Throughout the Game", fontsize=17)
    plt.fill_between(num_messages_per_phase.keys(), means_p_std, means_m_std, alpha=0.3,
                     label=r"mean $\pm$ STD", color="C0")
    plt.plot(num_messages_per_phase.keys(), means, label="mean", color="C0")
    plt.ylim(0, max(sum(num_messages_per_phase.values(), [])))
    plt.xlabel("Daytime Phases Since Beginning of Game", fontsize=16)
    plt.ylabel("Number of Messages Per Player", fontsize=16)
    plt.legend(fontsize=14)
    plt.tight_layout()
    plt.savefig(ANALYSIS_DIR / "num_msg_per_player_by_daytime_phase.png")
    plt.show()


def plot_voting_out_by_speaking_rank_histogram(parsed_messages_by_phase_all_games: list[list[Phase]]):
    voted_out_ranks = []
    for game in parsed_messages_by_phase_all_games:
        for phase in game:
            if not phase.is_daytime:
                continue
            # message_count_by_player = defaultdict(int)
            message_count_by_player = {player: 0 for player in phase.active_players}
            for message in phase.messages:
                if message.is_manager:
                    continue
                try:
                    message_count_by_player[message.name] += 1
                except KeyError:  # bug caused message to be sent on the next phase
                    pass
            sorted_counter = sorted((count, name) for name, count in message_count_by_player.items())
            for i, (count, name) in enumerate(sorted_counter):
                if name == phase.voted_out_player:
                    voted_out_ranks.append(i / (len(phase.active_players) - 1))  # normalized
    plt.hist(voted_out_ranks, bins=15, alpha=0.7)
    # plt.title("Histogram of Voted Out Players\nby Speaking Rank", fontsize=17)
    plt.xlabel("Normalized Player Rank by Number of Messages", fontsize=15)
    plt.ylabel("Number of Times the Player Was Voted Out    ", fontsize=15)
    # KDE_BANDWIDTH = 0.03
    # voted_out_ranks_squeezed = np.array(voted_out_ranks)[:, np.newaxis]
    # kde_voted_out_ranks = KernelDensity(
    #     kernel="gaussian", bandwidth=KDE_BANDWIDTH).fit(voted_out_ranks_squeezed)
    # x_range = np.linspace(-0.1, 1.1, 1000)
    # log_density = kde_voted_out_ranks.score_samples(x_range[:, np.newaxis])
    # plt.fill_between(x_range, np.exp(log_density), 0, alpha=0.5)
    # # plt.ylim(0, np.exp(max(log_density)) * 1.1)
    # # if extend_xlim:
    # #     ax.set_xlim(ax.get_xlim()[0], ax.get_xlim()[1] * 1.1)
    plt.tight_layout()
    plt.savefig(ANALYSIS_DIR / "speaking_rank_voted_out_hist.png")
    plt.show()


def main():
    # Should include:
    # 0. Dataset metadata
    # 0.1. Consisting of # games & # messages
    # 0.2. Table: General information for all games in dataset
    # 0.3. Number of players per game
    # 1. LLM Agent Performance in Game:
    # 1.1 Percentage plots (instead of Pie Chats like in LIMA) of winning percentage, winning as Mafia, winning as bystander, playing as mafia, mafia is winning
    # 2. Message Quantity:
    # 2.1 Table: Amount of messages sent by a player during a daytime phase.
    # 2.1.1. Plot or just check: average and STD of num messages per phase (check if stays similar through the phases - indicating that the fewer people need to fill the void with more messages)
    # 2.2 Smoothed Histograms - averaged time differences for a player in a game:
    # 2.2.1 between a message and the previous one by anyone
    # 2.2.2 between a message and the previous one by the same player!
    # 3. Message Content:
    # 3.1 Table: table of averaged + STD message length, repetition (unique messages), # unique words
    # 4. Embedding Analysis:
    # 4.1 before visual plots (Table?): try to have linear(/non linear?) separation of human and LLM, and also mafia and bystanders, and also humans before LLM was voted out and after!
    # 4.2 visualize with 2D and 3D - colors for human and LLM, subcolors for mafia and bystanders
    # 4.3 visualize again with colors for human/LLM but this time with subcolor for humans after LLM was voted out
    # 5. Participant’s Feedback
    # 5.1 overall average (for all players in all games together) of identification (no need for STD)
    # 5.2 Table: means and STDs (overall, like above) for the 3 human-ranked scores
    # 6. Speaking Rank - Voting Out Distribution
    # 6.1. Plot: histogram of voted out player by their normalized speaking rank in that phase

    did_mafia_win_all_games = []
    did_llm_win_all_games = []
    was_llm_voted_out_all_games = []
    is_llm_mafia_all_games = []
    did_human_win_as_mafia_all_games = []
    did_human_win_as_bystander_all_games = []

    parsed_messages_by_phase_all_games = []
    llm_names_all_games = []

    # timing diff (1): between a message and the previous one in the conversation
    mean_per_game_of_timing_diff_of_messages_sent_by_humans = []
    mean_per_game_of_timing_diff_of_messages_sent_by_llm = []
    # timing diff (2): between a message and the same player's previous one
    mean_per_game_of_timing_diff_of_self_messages_by_humans = []
    mean_per_game_of_timing_diff_of_self_messages_by_llm = []

    human_content_metrics = {metric: [] for metric in CONTENT_METRICS}
    llm_content_metrics = {metric: [] for metric in CONTENT_METRICS}

    all_player_messages = []
    is_mafia_all_player_messages = []
    is_daytime_all_player_messages = []

    metrics_results_all_games = defaultdict(list)

    for game_dir in Path(DIRS_PREFIX).glob("*"):
        game_id = game_dir.name
        if not (game_dir.is_dir() and game_id.isdigit() and "00001" not in game_id):
            continue

        llm_player_name, __all_players, mafia_players, human_players, __config, \
            metrics_results, __all_comments, parsed_messages_by_phase, was_llm_voted_out, \
            is_llm_mafia, did_mafia_win, did_llm_win = get_single_game_results(game_id)

        did_mafia_win_all_games.append(did_mafia_win)
        did_llm_win_all_games.append(did_llm_win)
        was_llm_voted_out_all_games.append(was_llm_voted_out)
        is_llm_mafia_all_games.append(is_llm_mafia)
        add_human_winning_statistics(human_players, mafia_players, did_mafia_win,
                                     did_human_win_as_mafia_all_games,
                                     did_human_win_as_bystander_all_games)

        parsed_messages_by_phase_all_games.append(parsed_messages_by_phase)
        llm_names_all_games.append(llm_player_name)

        calc_game_mean_timing_diffs(parsed_messages_by_phase, human_players,
                                    mean_per_game_of_timing_diff_of_messages_sent_by_humans,
                                    mean_per_game_of_timing_diff_of_messages_sent_by_llm,
                                    mean_per_game_of_timing_diff_of_self_messages_by_humans,
                                    mean_per_game_of_timing_diff_of_self_messages_by_llm)

        calc_mean_message_content_empiric_metrics(parsed_messages_by_phase, human_players,
                                                  human_content_metrics, llm_content_metrics)
        for phase in parsed_messages_by_phase:
            player_messages = [message for message in phase.messages if not message.is_manager]
            is_mafia_by_order = [message.name in mafia_players for message in player_messages]
            all_player_messages.extend(player_messages)
            is_mafia_all_player_messages.extend(is_mafia_by_order)
            is_daytime_all_player_messages.extend([phase.is_daytime] * len(player_messages))

        for metric in metrics_results:
            metrics_results_all_games[metric].append(metrics_results[metric])

    # 0.
    calc_dataset_metadata(parsed_messages_by_phase_all_games)

    # 1.
    plot_percentage_bars_chart(did_llm_win_all_games, is_llm_mafia_all_games,
                               did_human_win_as_mafia_all_games,
                               did_human_win_as_bystander_all_games,
                               plot_separately_by_base_models=True,
                               plot_separately_by_role=True)

    # 2.1.
    calc_message_amount_by_player_during_daytime(parsed_messages_by_phase_all_games,
                                                 llm_names_all_games)
    check_variance_of_num_messages_throughout_phases(parsed_messages_by_phase_all_games)

    # 2.2.
    plot_merged_timing_diff_hists(mean_per_game_of_timing_diff_of_messages_sent_by_humans,
                                  mean_per_game_of_timing_diff_of_messages_sent_by_llm,
                                  mean_per_game_of_timing_diff_of_self_messages_by_humans,
                                  mean_per_game_of_timing_diff_of_self_messages_by_llm,
                                  plot_separately_by_base_models=True)

    # 3.
    calc_message_content_empiric_metrics(human_content_metrics, llm_content_metrics)

    # 4.
    # remember is_daytime is fixed here!
    analyze_embeddings(all_player_messages, is_mafia_all_player_messages,
                       is_daytime_all_player_messages)

    # 5.
    calc_players_metric(metrics_results_all_games)

    # 6.
    plot_voting_out_by_speaking_rank_histogram(parsed_messages_by_phase_all_games)

    print()  # Allowing breaking point before end


def add_all_messages_file(game_dir):
    all_players = (game_dir / PLAYER_NAMES_FILE).read_text().splitlines()
    mafia_players = (game_dir / MAFIA_NAMES_FILE).read_text().splitlines()
    llm_player_name = get_llm_player_name(all_players, game_dir)
    parsed_messages_by_phase = parse_messages(game_dir, all_players, mafia_players, llm_player_name)
    all_messages = [message.original
                    for phase in parsed_messages_by_phase
                    for message in phase.messages]
    (game_dir / ALL_MESSAGES_FILE).write_text("\n".join(all_messages))


def preprocess_games_for_dataset():
    for game_dir in Path(DIRS_PREFIX).glob("*"):
        # add ALL_MESSAGES_FILE
        add_all_messages_file(game_dir)
        # anonymize config
        with open(game_dir / GAME_CONFIG_FILE, "r") as f:
            config = json.load(f)
        for player in config[PLAYERS_KEY_IN_CONFIG]:
            player["real_name"] = ANONYMIZED_NAME
        with open(game_dir / GAME_CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
        # anonymize real names mapping file
        real_names = (game_dir / REAL_NAMES_FILE).read_text()
        anonymized = re.sub(rf"([\w ]+)({REAL_NAME_CODENAME_DELIMITER}.+)",
                            rf"{ANONYMIZED_NAME}\2", real_names)
        (game_dir / REAL_NAMES_FILE).write_text(anonymized)
    print()  # Allowing breaking point before end


if __name__ == "__main__":
    print("CODE STARTED RUNNING (envs finished loading)")
    preprocess_games_for_dataset()
    # preliminary_analysis_by_game()
    # get_games_statistics()
    # get_message_timings_statistics()
    # get_message_content_analysis()
    # main()
