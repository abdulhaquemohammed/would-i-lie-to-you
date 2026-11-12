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


def build_prompt(count, style_examples, avoid, as_object=True, good_lies=()):
    examples = "\n".join(f"- {s}" for s in style_examples[:6]) or "- (none given)"
    good = "\n".join(f"- {s}" for s in good_lies) or "- (none given)"
    avoid_text = "\n".join(f"- {s}" for s in avoid[-40:]) or "- (none yet)"
    return (
        f"Write {count} different lies for the game.\n\n"
        "Rules:\n"
        "- First person, one or two sentences, 15 to 40 words.\n"
        "- Surprising but believable: odd, specific, everyday details, like the real show.\n"
        "- It must sound like it could really have happened to an ordinary person. No superpowers, "
        "talking animals, lottery wins, fame, world records or impossible skills.\n"
        "- Include small concrete details: a place, an age, a family member, an object.\n"
        "- British English and UK settings (pounds, UK towns, school years), as the players are in the UK.\n"
        "- Family-friendly: no swearing, sex, drugs, violence or anything offensive.\n"
        "- Every lie must be about a different topic.\n"
        "- Do not copy or reuse details from the example stories below; only match their tone and length.\n"
        "- Do not repeat or closely reword anything in the 'already used' list.\n\n"
        f"Examples of good lies (match this level of believability, do not copy them):\n{good}\n\n"
        f"Example true stories from the players (style only):\n{examples}\n\n"
        f"Already used, do not reuse:\n{avoid_text}\n\n"
        + ('Reply with only JSON in this shape: {"lies": ["first lie", "second lie"]}'
           if as_object else "Reply with only a JSON array of strings, nothing else.")
    )


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
