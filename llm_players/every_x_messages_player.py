from game_constants import REMAINING_PLAYERS_FILE, GAME_MANAGER_NAME, MESSAGE_PARSING_PATTERN
from llm_players.llm_constants import turn_task_into_prompt, EVERY_X_MESSAGES_TYPE, \
    make_more_human_like
from llm_players.llm_player import LLMPlayer


class EveryXMessagesPlayer(LLMPlayer):  # TODO implement this!

    TYPE_NAME = EVERY_X_MESSAGES_TYPE

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # TODO implement!
        # self.every_x = number_of_active_players?...
        # # scheduler_kwargs = kwargs.get("scheduler_kwargs", kwargs)
        # # self.scheduler = LLMWrapper(**scheduler_kwargs)
        # self.scheduler = self.llm  # trying to use the same one for generation...

    def should_generate_message(self, message_history):
        # Social Turing Test: no nighttime, always use number of remaining players
        every_x = len((self.game_dir / REMAINING_PLAYERS_FILE).read_text().splitlines())
        current_phase_messages = 0
        for message in message_history[::-1]:
            if f"] {GAME_MANAGER_NAME}: " in message and "voted for" in message:
                continue
            elif f"] {GAME_MANAGER_NAME}: " in message and "has ended, now it's time to vote!" in message:
                break
            if f"] " in message and ": " in message:
                current_phase_messages += 1
        self.logger.log("scheduling current_phase_messages", f"{current_phase_messages}")
        self.logger.log("scheduling every_x", f"{every_x}")
        return current_phase_messages % every_x == every_x - 1

    def generate_message(self, message_history):
        if self.should_generate_message(message_history):
            prompt = self.create_generation_prompt(message_history)
            self.logger.log("prompt in generate_message", prompt)
            message = self.llm.generate(prompt, self.get_system_info_message())
            message = make_more_human_like(message)
            return message
        else:
            return ""

    def create_generation_prompt(self, message_history):  # TODO: implement
        raise NotImplementedError()
