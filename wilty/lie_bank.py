"""M5: the built-in lies used in offline mode or when the local AI is unreachable (FR6, FR21)."""
import json
import random
from pathlib import Path

MIN_BANK_SIZE = 60  # 6 lies a game x 10 games, so FR19 holds offline


class LieBank:
    def __init__(self, path, rng=None):
        lies = json.loads(Path(path).read_text(encoding="utf-8"))
        lies = [lie.strip() for lie in lies if isinstance(lie, str) and lie.strip()]
        if len(set(lies)) != len(lies):
            raise ValueError("lie_bank.json contains duplicate lies.")
        self.lies = lies
        self.rng = rng or random.Random()

    def __len__(self):
        return len(self.lies)

    def pick(self, history):
        """
        Pick a lie that has not been used in this cycle of the bank and is not in the
        no-repeat window. Every entry is used once before any entry repeats (FR20).
        """
        used = history.bank_cycle_used()
        candidates = [l for l in self.lies if l not in used and not history.is_duplicate(l)]
        if not candidates:
            history.reset_bank_cycle()
            candidates = [l for l in self.lies if not history.is_duplicate(l)]
        if not candidates:
            candidates = list(self.lies)  # last resort: never stop the game
        choice = self.rng.choice(candidates)
        history.mark_bank_used(choice)
        return choice
