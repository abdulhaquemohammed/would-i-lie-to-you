"""M6: remembers which lies have been played so they do not repeat (FR19, FR20).

Stored file holds lies only, never names or true stories (NFR6).
"""
import json
import re
from difflib import SequenceMatcher
from pathlib import Path

NEAR_DUPLICATE_RATIO = 0.85


def _norm(text):
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", text.lower()).split())


def is_near_duplicate(a, b):
    a, b = _norm(a), _norm(b)
    if a == b:
        return True
    return SequenceMatcher(None, a, b).ratio() >= NEAR_DUPLICATE_RATIO


class LieHistory:
    """
    persist=False is used in test mode (FR23): the history is still read so test games
    avoid repeats, but nothing a test game plays is written back.
    """

    def __init__(self, path, window_games=10, persist=True):
        self.path = Path(path)
        self.window_games = window_games
        self.persist = persist
        self.data = {"games": [], "bank_cycle": []}
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                self.data["games"] = list(loaded.get("games", []))
                self.data["bank_cycle"] = list(loaded.get("bank_cycle", []))
            except (json.JSONDecodeError, OSError):
                pass  # a broken history file should never stop a game

    # ---- games -------------------------------------------------------------

    def start_game(self, game_id):
        self.data["games"].append({"id": game_id, "lies": []})
        self._save()

    def record_lie(self, game_id, text):
        for game in reversed(self.data["games"]):
            if game["id"] == game_id:
                game["lies"].append(text)
                break
        else:
            self.data["games"].append({"id": game_id, "lies": [text]})
        self._save()

    def window_lies(self):
        """Lies in the current game plus the previous 9: any 10 games in a row share no lie."""
        lies = []
        for game in self.data["games"][-self.window_games:]:
            lies.extend(game["lies"])
        return lies

    def avoid_list(self, limit=60):
        """Most recent lies, newest last, to pass to the AI as 'do not reuse' (FR20)."""
        lies = []
        for game in self.data["games"]:
            lies.extend(game["lies"])
        return lies[-limit:]

    def is_duplicate(self, text, extra=()):
        return any(is_near_duplicate(text, old) for old in [*self.window_lies(), *extra])

    # ---- lie bank cycle (FR20) ---------------------------------------------

    def bank_cycle_used(self):
        return set(self.data["bank_cycle"])

    def mark_bank_used(self, text):
        self.data["bank_cycle"].append(text)
        self._save()

    def reset_bank_cycle(self):
        self.data["bank_cycle"] = []
        self._save()

    # ---- file --------------------------------------------------------------

    def _save(self):
        if not self.persist:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        tmp.replace(self.path)
