"""M7: the one place the game gets lies from: the local AI model or the lie bank."""
from .ai_prompt import AIError, is_clean
from .models import Statement

MAX_AI_ATTEMPTS = 3


class LieProvider:
    def __init__(self, bank, history, client=None):
        self.bank = bank
        self.history = history
        self.client = client  # None = offline mode (lie bank only)
        self.name = getattr(client, "display_name", "the local AI model")
        self.source = getattr(client, "source", "local")
        self.queue = []
        self.status = None  # message shown to players, if any

    def prepare(self, count, style_examples):
        """NFR5: all AI lies are fetched once, before round 1."""
        if self.client is None:
            return
        try:
            self.queue = self._from_ai(count, style_examples)
        except AIError:
            self.queue = []
            self.status = f"Couldn't reach {self.name}, so this game uses the built-in lie bank."
            return
        if len(self.queue) < count:
            self.status = f"{self.name[0].upper() + self.name[1:]} gave fewer lies than needed, so some come from the built-in lie bank."

    def _from_ai(self, count, style_examples):
        accepted = []
        for _ in range(MAX_AI_ATTEMPTS):
            needed = count - len(accepted)
            if needed <= 0:
                break
            # ask for a few spare in case some are rejected
            # few-shot: show the AI 5 hand-written lies from the bank as the quality bar
            good = self.bank.rng.sample(self.bank.lies, min(5, len(self.bank.lies)))
            batch = self.client.generate_lies(needed + 2, style_examples, self.history.avoid_list(), good_lies=good)
            for lie in batch:
                if len(accepted) >= count:
                    break
                if is_clean(lie) and not self.history.is_duplicate(lie, extra=accepted):  # FR17, FR19
                    accepted.append(lie)
        return accepted

    def next_lie(self):
        while self.queue:
            text = self.queue.pop(0)
            if not self.history.is_duplicate(text):
                return Statement(text, False, self.source)
        return Statement(self.bank.pick(self.history), False, "bank")
