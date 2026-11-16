"""M4: the prompt and the checks shared by the AI lie generator."""
import json
import re

SYSTEM_PROMPT = (
    "You write statements for a family-friendly party game based on the TV show "
    "'Would I Lie to You?'. Players read a statement aloud as if it happened to them, "
    "and the other team guesses if it is true or a lie. You write the lies."
)

# FR17: a simple safety net on top of the instructions in the prompt
BLOCKED_WORDS = {
    "fuck", "shit", "bitch", "cunt", "dick", "piss", "bastard", "slut", "whore",
    "sex", "sexy", "nude", "naked", "drugs", "cocaine", "heroin", "kill", "murder",
    "suicide", "rape", "racist", "nazi",
}


class AIError(RuntimeError):
    """Anything that stops us getting usable lies from the AI model."""


def is_clean(text):
    words = set(re.findall(r"[a-z]+", text.lower()))
    return not (words & BLOCKED_WORDS)


# CR-03: lies match how unusual the players' true stories are. Each level has example lies
# so the model can see what the level means.
LEVELS = {
    1: ("everyday: small things that happen to most people", [
        "I once got lost in a supermarket car park for twenty minutes because I forgot which entrance I came in.",
        "I have never finished a whole cup of tea without it going cold first.",
    ]),
    2: ("a bit odd: a small mishap or habit that makes people smile", [
        "I have a scar on my thumb from being bitten by a goose at a petting zoo in Cardiff.",
        "I once wore my school jumper inside out for a whole day and nobody told me.",
    ]),
    3: ("unusual: a story you would tell at a party", [
        "I once won a local pie-eating contest by accident because I thought it was a free buffet.",
        "I once got stuck in a lift at Swansea Library for an hour with my old maths teacher.",
    ]),
    4: ("very unusual: rare and dramatic, but it really could happen", [
        "When I was nine I got my head stuck in the railings outside my school and the fire brigade had to butter my ears to get me out.",
        "I once got locked inside a garden centre overnight and slept in a display shed.",
    ]),
    5: ("outrageous: hard to believe, but still possible for an ordinary person", [
        "I once ended up on the local news after chasing an escaped cow through Swansea city centre in my pyjamas.",
        "My uncle accidentally drove the wrong way onto a ferry and we spent a weekend in Ireland instead of Tenby.",
    ]),
}


def level_scale():
    lines = []
    for n, (meaning, examples) in LEVELS.items():
        lines.append(f"Level {n}, {meaning}:")
        lines.extend(f"  - {e}" for e in examples)
    return "\n".join(lines)


def build_prompt(count, style_examples, avoid, as_object=True, good_lies=()):
    examples = "\n".join(f"- {s}" for s in style_examples[:12]) or "- (none given)"
    avoid_text = "\n".join(f"- {s}" for s in avoid[-40:]) or "- (none yet)"
    return (
        "The players' true stories for this game:\n"
        f"{examples}\n\n"
        "How unusual a story is, from 1 to 5:\n"
        f"{level_scale()}\n\n"
        "Step 1: decide which level the true stories are on average.\n"
        f"Step 2: write {count} different lies on that SAME level: not calmer and not wilder than the true "
        "stories, so a lie cannot be spotted by how unusual it is. If the stories are everyday, the lies "
        "must be everyday too. If the stories are wild, the lies must be just as wild.\n\n"
        "Rules for every lie:\n"
        "- First person, one or two sentences, 15 to 40 words.\n"
        "- It must be possible for an ordinary person. No superpowers, talking animals, lottery wins, "
        "celebrities, royalty, world records or impossible skills, at any level.\n"
        "- Include small concrete details: a place, an age, a family member, an object.\n"
        "- British English and UK settings (pounds, UK towns, school years), as the players are in the UK.\n"
        "- Family-friendly: no swearing, sex, drugs, violence or anything offensive.\n"
        "- Every lie must be about a different topic.\n"
        "- Match the stories' tone and how unusual they are, but never retell a true story or copy its details.\n"
        "- Do not repeat or closely reword anything in the 'already used' list.\n\n"
        f"Already used, do not reuse:\n{avoid_text}\n\n"
        + ('Reply with only JSON in this shape: {"story_level": 2, "lies": ["first lie", "second lie"]}'
           if as_object else "Reply with only a JSON array of strings, nothing else.")
    )


def parse_story_level(text):
    """The level the model gave the true stories, if it said one (logged by evals)."""
    try:
        level = json.loads(text).get("story_level")
    except (json.JSONDecodeError, TypeError, AttributeError):
        return None
    return level if isinstance(level, int) and 1 <= level <= 5 else None


def parse_lies(text):
    """Accepts a JSON list of strings, or an object holding one (local models often wrap it)."""
    data = None
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        match = re.search(r"\[.*\]", text or "", re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    if isinstance(data, dict):
        data = next((v for v in data.values() if isinstance(v, list)), None)
    if not isinstance(data, list):
        raise AIError("The AI did not return a JSON list of lies.")
    lies = [s.strip() for s in data if isinstance(s, str) and s.strip()]
    if not lies:
        raise AIError("The AI returned no lies.")
    return lies
