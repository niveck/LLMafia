import re
from game_constants import REMAINING_PLAYERS_FILE, GAME_MANAGER_NAME, MESSAGE_PARSING_PATTERN
from game_status_checks import is_nighttime
from llm_players.llm_constants import turn_task_into_prompt, SCHEDULE_THEN_GENERATE_TYPE, \
    make_more_human_like, SCHEDULING_GENERATION_PARAMETERS, TALKATIVE_PROMPT, QUIETER_PROMPT
from llm_players.llm_player import LLMPlayer
from llm_players.llm_wrapper import LLMWrapper


def no_one_has_talked_yet_in_current_phase(message_history):
    if not message_history:
        return True
    matcher = re.match(MESSAGE_PARSING_PATTERN, message_history[-1])
    if not matcher:
        return True
    name = matcher.group(4)  # depends on MESSAGE_PARSING_PATTERN
    return name == GAME_MANAGER_NAME


class ScheduleThenGeneratePlayer(LLMPlayer):

    TYPE_NAME = SCHEDULE_THEN_GENERATE_TYPE

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # scheduler_kwargs = kwargs.get("scheduler_kwargs", kwargs)
        # self.scheduler = LLMWrapper(**scheduler_kwargs)
        self.scheduler = self.llm  # using the same one for generation...

    def should_generate_message(self, message_history):
        if no_one_has_talked_yet_in_current_phase(message_history):
            return False
        prompt = self.create_scheduling_prompt(message_history)
        self.logger.log("prompt in should_generate_message", prompt)
        decision = self.scheduler.generate(
            prompt, self.get_system_info_message(only_special_tokens=True),
            SCHEDULING_GENERATION_PARAMETERS)
        self.logger.log("decision in should_generate_message", decision)
        return self.interpret_scheduling_decision(decision)

    def generate_message(self, message_history):
        if self.should_generate_message(message_history):
            prompt = self.create_generation_prompt(message_history)
            self.logger.log("prompt in generate_message", prompt)
            message = self.llm.generate(
                prompt, self.get_system_info_message(attention_to_not_repeat=True))
            message = make_more_human_like(message)
            return message
        else:
            return ""

    def talkative_scheduling_prompt_modifier(self, message_history):
        if not message_history or is_nighttime(self.game_dir):
            return TALKATIVE_PROMPT
        all_players = (self.game_dir / REMAINING_PLAYERS_FILE).read_text().splitlines()
        players_counts = {player: 0 for player in all_players}
        for message in message_history[::-1]:
            if f"] {GAME_MANAGER_NAME}: " in message and "voted for" in message:
                continue
            elif f"] {GAME_MANAGER_NAME}: " in message and "has ended, now it's time to vote!" in message:
                break
            for player in players_counts:
                if f"] {player}: " in message:
                    players_counts[player] += 1
        all_player_messages = sum(players_counts.values())
        if not all_player_messages or players_counts[self.name] / all_player_messages < 1 / len(all_players):
            return TALKATIVE_PROMPT
        else:
            return QUIETER_PROMPT

    def create_scheduling_prompt(self, message_history):
        task = f"Do you want to send a message to the group chat now, or do you prefer to wait " \
               f"for now and see what messages others will send? " \
               f"Act like a natural human player - participate in the discussion but don't dominate it. " \
               f"{self.talkative_scheduling_prompt_modifier(message_history).strip()} " \
               f"Reply only with `{self.use_turn_token}` if you want to send a message now, " \
               f"or only with `{self.pass_turn_token}` if you want to wait for now. "
        return turn_task_into_prompt(task, message_history)

    def create_generation_prompt(self, message_history):
        task = f"Add a very short, casual message to the chat. " \
               f"Write like a human player would - keep it natural and conversational. " \
               f"Your message should be one short sentence that responds to the current discussion. " \
               f"Try to identify who might be the AI among the other players, or deflect suspicion naturally. " \
               f"Don't repeat messages you've already sent! " \
               f"Match the casual, informal style of other players' recent messages. " \
               f"Examples of natural player messages: 'i think alex is sus', 'why would i do that if i was the ai', " \
               f"'jordan has been way too quiet', 'exactly', 'that makes no sense'.\n"
        return turn_task_into_prompt(task, message_history)
