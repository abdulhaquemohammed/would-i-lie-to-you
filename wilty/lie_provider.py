"""M7: the one place the game gets lies from: the local AI model or the lie bank."""
from difflib import SequenceMatcher

from .ai_prompt import LEVELS, AIError, is_clean
from .models import Statement

COPY_RATIO = 0.6  # a lie this similar to a true story is a copy, not a new lie (CR-03, defect D1)


LEVEL_EXAMPLES = [e for _, examples in LEVELS.values() for e in examples]


def copies_a_story(lie, stories):
    lie = lie.lower()
    return any(SequenceMatcher(None, lie, s.lower()).ratio() >= COPY_RATIO for s in stories)

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
            batch = self.client.generate_lies(needed + 2, style_examples, self.history.avoid_list())
            for lie in batch:
                if len(accepted) >= count:
                    break
                if (is_clean(lie)  # FR17
                        and not copies_a_story(lie, [*style_examples, *LEVEL_EXAMPLES])  # CR-03
                        and not self.history.is_duplicate(lie, extra=accepted)):  # FR19
                    accepted.append(lie)
        return accepted

    def next_lie(self):
        while self.queue:
            text = self.queue.pop(0)
            if not self.history.is_duplicate(text):
                return Statement(text, False, self.source)
        return Statement(self.bank.pick(self.history), False, "bank")
