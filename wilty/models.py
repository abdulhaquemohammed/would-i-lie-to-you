"""M2: plain data classes describing a game. No logic beyond small helpers."""
from dataclasses import dataclass, field
from typing import Optional

TRUTH = "T"
LIE = "L"


@dataclass
class Player:
    name: str
    stories: list = field(default_factory=list)
    used_stories: set = field(default_factory=set)

    def unused_story_indexes(self):
        return [i for i in range(len(self.stories)) if i not in self.used_stories]


@dataclass
class Team:
    name: str
    players: list
    score: int = 0


@dataclass
class Statement:
    text: str
    is_true: bool
    source: str  # "player", "local" or "bank"


@dataclass
class Round:
    number: int  # 1-based
    speaker_team: int  # 0 or 1
    speaker_index: int  # 0..2 within the team
    statement: Statement
    sudden_death: bool = False
    guess: Optional[str] = None
    correct: Optional[bool] = None
    point_to: Optional[int] = None  # team index that got the point

    @property
    def guessing_team(self):
        return 1 - self.speaker_team


LIE_SOURCES = ("local", "offline")


@dataclass
class Settings:
    lie_source: str = "local"  # "local" (Ollama) or "offline" (lie bank)
    test_mode: bool = False

    @property
    def offline(self):
        return self.lie_source == "offline"
