"""AI lie evaluation for Would I Lie to You?

Runs the game's real lie pipeline (LocalClient -> LieProvider -> LieHistory) against a
running Ollama model for several simulated games, then scores every lie the model wrote.

    python -m evals.lie_eval --games 10
    python -m evals.lie_eval --games 4 --stories calm --judge --out evals/results/cr03-calm

Needs Ollama running with the model pulled. Writes to evals/results/:
    lies.csv          every lie the model returned, with checks and the game's decision
    summary.json      totals and rates
    rating_sheet.csv  blind believability sheet (AI lies mixed with hand-written bank lies)
    rating_key.csv    which sheet rows are AI and which are bank (keep away from raters)
"""
import argparse
import csv
import json
import random
import re
import tempfile
import time
from difflib import SequenceMatcher
from pathlib import Path

from config import Config
from wilty.ai_prompt import AIError, is_clean
from wilty.lie_bank import LieBank
from wilty.lie_history import LieHistory, is_near_duplicate
from wilty.lie_provider import LEVEL_EXAMPLES, LieProvider, copies_a_story
from wilty.local_client import LocalClient

RESULTS = Path(__file__).resolve().parent / "results"

# 6 players x 2 true stories, as players would type them in. "mixed" was used before CR-03.
TRUE_STORIES = [
    "I once fell asleep on the train home and woke up in Cardiff.",
    "My nan taught me to drive in the Tesco car park on a Sunday morning.",
    "I broke my arm falling off a trampoline at my cousin's tenth birthday party.",
    "In Year 7 I accidentally locked my PE teacher in the equipment cupboard.",
    "Our cat went missing for a week and came back wearing a collar that wasn't ours.",
    "I've been to the same chip shop in Mumbles every Friday for six years.",
    "I once got a parking ticket while I was sitting in the car.",
    "My dad has kept every Argos catalogue since 1998 in the loft.",
    "I was sick on a school trip to the Big Pit museum.",
    "I got lost in IKEA for an hour when I was eight.",
    "My brother and I share a birthday but are three years apart.",
    "I once ate eleven Welsh cakes in one sitting for a bet.",
]

CALM_STORIES = [
    "I have the same cereal for breakfast every single day and have done since primary school.",
    "I once missed my bus because I was tying my shoelace at the stop.",
    "My nan still calls me by my cousin's name about half the time.",
    "I got a B in my Year 9 science test after revising the wrong chapter.",
    "I can't whistle, no matter how many times my dad has tried to teach me.",
    "I once left my PE kit on the bus and had to borrow shorts from lost property.",
    "Our neighbour's cat sleeps on our garden wall every afternoon.",
    "I've never been to London even though I've lived in Wales my whole life.",
    "I once put salt in my tea instead of sugar at my auntie's house.",
    "I fell asleep during a film at the cinema in Swansea and missed the ending.",
    "My mum keeps every birthday card I've ever been given in a shoebox.",
    "I once walked into a glass door at the dentist.",
]

EXTREME_STORIES = [
    "When I was six I got stuck inside a claw machine at Porthcawl funfair and the fire brigade had to come.",
    "My grandad accidentally sold our family car at a car boot sale while we were still using it.",
    "I once got locked in a portable toilet at a festival and was rescued by a man dressed as a banana.",
    "A seagull stole my entire birthday cake off the table at Barry Island and dropped it in the sea.",
    "On a school trip I got on the wrong coach and ended up at a stranger's wedding in Bristol.",
    "My uncle once reversed his van into the duck pond at the village fete in front of everyone.",
    "I found a live crab in my wellies after a family holiday in Tenby, three days after we got home.",
    "Our dog ate a whole Christmas pudding and we had to take him to an emergency vet on Boxing Day.",
    "I once set off the fire alarm at my sixth form by making toast in the staff room.",
    "My brother got his head stuck in a bucket at a farm park and it had to be cut off with garden shears.",
    "I accidentally walked into the background of the BBC Wales weather forecast in Cardiff in my pyjamas.",
    "A runaway sheep followed me all the way home from the bus stop and into our kitchen.",
]

STORY_SETS = {"mixed": TRUE_STORIES, "calm": CALM_STORIES, "extreme": EXTREME_STORIES}

# Checks taken from the rules in the prompt (wilty/ai_prompt.py). The game itself only
# enforces the offensive-word filter and the no-repeat rule; these measure the rest.
BANNED_THEMES = [
    r"super ?power", r"lottery", r"\bfamous\b", r"celebrit", r"world record", r"\brecord\b",
    r"only person", r"\btalking\b", r"\bmillion", r"\bmagic", r"\bthe queen\b", r"\bthe king\b",
]
US_TERMS = [
    r"\bbackyard\b", r"\bmom\b", r"\bdollars?\b", r"\$", r"\bapartment\b", r"\bsidewalk\b",
    r"\bcolor\b", r"\bfavorite\b", r"\bvacation\b", r"\bsoccer\b", r"\bcandy\b", r"\bgrade \d",
    r"\bfreeway\b", r"\bmall\b",
]
FIRST_PERSON = re.compile(r"\b(i|my|me|we|our|us)\b", re.I)
COPY_RATIO = 0.6


def word_count(text):
    return len(re.findall(r"[A-Za-z0-9'£]+", text))


def quality_flags(lie, examples):
    flags = []
    words = word_count(lie)
    if words < 15:
        flags.append("too short")
    if words > 40:
        flags.append("too long")
    if not FIRST_PERSON.search(lie):
        flags.append("not first person")
    low = lie.lower()
    if any(re.search(p, low) for p in BANNED_THEMES):
        flags.append("banned theme")
    if any(re.search(p, low) for p in US_TERMS):
        flags.append("not British")
    if any(SequenceMatcher(None, low, e.lower()).ratio() >= COPY_RATIO for e in examples):
        flags.append("copied example")
    return flags


class RecordingClient:
    """Wraps the real client and keeps every batch, its timing and any error."""

    def __init__(self, client):
        self.client = client
        self.source = client.source
        self.display_name = client.display_name
        self.calls = []

    def generate_lies(self, count, style_examples, avoid, good_lies=()):
        start = time.perf_counter()
        call = {"requested": count, "good_lies": list(good_lies), "lies": [], "error": None}
        try:
            call["lies"] = self.client.generate_lies(count, style_examples, avoid, good_lies=good_lies)
            return call["lies"]
        except AIError as exc:
            call["error"] = str(exc)
            raise
        finally:
            call["seconds"] = round(time.perf_counter() - start, 1)
            self.calls.append(call)


# Scale used only to check CR-03: how unusual a statement is, with anchor examples
JUDGE_SCALE = """1 = everyday: small things that happen to most people (e.g. missed the bus tying a shoelace)
2 = a bit odd: a small mishap that makes people smile (e.g. put salt in my tea instead of sugar)
3 = unusual: a story you would tell at a party (e.g. accidentally locked my PE teacher in a cupboard)
4 = very unusual: rare and dramatic but possible (e.g. fire brigade had to free my head from railings)
5 = outrageous: hard to believe but possible (e.g. chased an escaped cow through the city centre in pyjamas)"""


def judge_levels(url, model, statements):
    """Rates how unusual each statement is (1 to 5) on the same scale the game's prompt uses.
    An automatic estimate from a small model: check the spread, not single scores."""
    import urllib.request
    levels = []
    for i in range(0, len(statements), 10):
        chunk = statements[i:i + 10]
        numbered = "\n".join(f"{n}. {t}" for n, t in enumerate(chunk, 1))
        prompt = (f"How unusual is each statement, from 1 to 5?\n{JUDGE_SCALE}\n\nStatements:\n{numbered}\n\n"
                  f'Reply with only JSON: {{"levels": [one whole number per statement, {len(chunk)} in total]}}')
        body = {"model": model, "stream": False, "format": "json", "options": {"temperature": 0},
                "messages": [{"role": "system", "content": "You rate statements for a party game. Be consistent."},
                             {"role": "user", "content": prompt}]}
        req = urllib.request.Request(f"{url.rstrip('/')}/api/chat", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=600) as r:
            text = json.loads(r.read())["message"]["content"]
        try:
            got = [int(x) for x in json.loads(text)["levels"]]
        except (ValueError, KeyError, TypeError):
            got = []
        got = (got + [None] * len(chunk))[:len(chunk)]
        levels.extend(x if x in (1, 2, 3, 4, 5) else None for x in got)
    return levels


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 2) if xs else None


def decide(lie, history, accepted_so_far, stories):
    """Mirrors LieProvider._from_ai so each lie gets the reason the game kept or dropped it."""
    if not is_clean(lie):
        return "rejected: offensive word"
    if copies_a_story(lie, [*stories, *LEVEL_EXAMPLES]):
        return "rejected: copies a story"
    if history.is_duplicate(lie, extra=accepted_so_far):
        return "rejected: repeat"
    return "accepted"


def run(games, url, model, seed, stories="mixed", out=None, judge=False, judge_model=None):
    rng = random.Random(seed)
    results = Path(out) if out else RESULTS
    results.mkdir(parents=True, exist_ok=True)
    story_set = STORY_SETS[stories]
    needed = Config.REGULAR_ROUNDS + Config.EXTRA_LIES
    history_file = Path(tempfile.mkdtemp()) / "history.json"
    rows, game_stats, all_accepted = [], [], []
    bank_lies = LieBank(Config.LIE_BANK_PATH).lies

    for g in range(1, games + 1):
        history = LieHistory(history_file, Config.NO_REPEAT_GAMES)
        game_id = f"eval-{g}"
        history.start_game(game_id)
        bank = LieBank(Config.LIE_BANK_PATH, rng=random.Random(rng.random()))
        client = RecordingClient(LocalClient(url, model, timeout=600))
        provider = LieProvider(bank, history, client)
        examples = rng.sample(story_set, len(story_set))

        start = time.perf_counter()
        provider.prepare(needed, examples)
        prep_seconds = round(time.perf_counter() - start, 1)

        # replay each batch through the same rules to label every lie
        accepted = []
        for c_no, call in enumerate(client.calls, 1):
            for lie in call["lies"]:
                if len(accepted) >= needed:
                    decision = "spare (not needed)"
                else:
                    decision = decide(lie, history, accepted, examples)
                    if decision == "accepted":
                        accepted.append(lie)
                rows.append({
                    "game": g, "call": c_no, "lie": lie, "words": word_count(lie),
                    "game_decision": decision,
                    "quality_flags": "; ".join(quality_flags(lie, examples + call["good_lies"])),
                })
        if accepted != provider.queue:
            # a later call failed, so the game threw the whole AI batch away (lie_provider.py)
            assert provider.queue == [] and any(c["error"] for c in client.calls)
            for r in rows:
                if r["game"] == g and r["game_decision"] == "accepted":
                    r["game_decision"] = "discarded: later call failed"
            accepted = []

        # play the 6 regular rounds so the no-repeat window fills like real games
        for _ in range(Config.REGULAR_ROUNDS):
            history.record_lie(game_id, provider.next_lie().text)
        all_accepted.append(accepted)
        game_stats.append({
            "game": g, "calls": len(client.calls), "prep_seconds": prep_seconds,
            "call_seconds": [c["seconds"] for c in client.calls],
            "errors": [c["error"] for c in client.calls if c["error"]],
            "returned": sum(len(c["lies"]) for c in client.calls),
            "accepted": len(accepted), "needed": needed,
            "fell_back_to_bank": len(accepted) < needed, "notice": provider.status,
            "model_story_level": getattr(client.client, "last_story_level", None),
        })
        print(f"game {g}: {len(accepted)}/{needed} AI lies, {len(client.calls)} call(s), {prep_seconds}s")

    # cross-game repeats in what players would actually hear (window of 10 games)
    played = [lie for game in all_accepted for lie in game[:Config.REGULAR_ROUNDS]]
    repeats = sum(1 for i, a in enumerate(played) for b in played[i + 1:] if is_near_duplicate(a, b))

    checked = [r for r in rows if r["game_decision"] != "spare (not needed)"]
    kept = [r for r in rows if r["game_decision"] == "accepted"]
    flag_counts = {}
    for r in kept:
        for f in filter(None, r["quality_flags"].split("; ")):
            flag_counts[f] = flag_counts.get(f, 0) + 1
    calls = [s for g in game_stats for s in g["call_seconds"]]
    level_stats = {}
    if judge and kept:
        story_levels = judge_levels(url, judge_model or model, story_set)
        lie_levels = judge_levels(url, judge_model or model, [r["lie"] for r in kept])
        for r, lv in zip(kept, lie_levels):
            r["judged_level"] = lv
        story_mean = mean(story_levels)
        level_stats = {
            "judged_story_levels": story_levels, "judged_story_level_avg": story_mean,
            "judged_lie_level_avg": mean(lie_levels),
            "lies_more_than_1_level_above_stories": sum(1 for x in lie_levels if x and story_mean and x > story_mean + 1),
            "lies_more_than_1_level_below_stories": sum(1 for x in lie_levels if x and story_mean and x < story_mean - 1),
            "lie_level_counts": {str(n): lie_levels.count(n) for n in range(1, 6)},
            "model_story_level_avg": mean([g["model_story_level"] for g in game_stats]),
        }
    summary = {
        "model": model, "games": games, "seed": seed, "stories": stories,
        "judge_model": (judge_model or model) if judge else None, **level_stats,
        "lies_returned": len(rows), "lies_checked_by_game": len(checked),
        "accepted": len(kept),
        "rejected_offensive": sum(r["game_decision"] == "rejected: offensive word" for r in rows),
        "rejected_repeat": sum(r["game_decision"] == "rejected: repeat" for r in rows),
        "rejected_copy": sum(r["game_decision"] == "rejected: copies a story" for r in rows),
        "games_needing_bank_fallback": sum(g["fell_back_to_bank"] for g in game_stats),
        "model_calls": len(calls), "failed_calls": sum(len(g["errors"]) for g in game_stats),
        "seconds_per_call_avg": round(sum(calls) / len(calls), 1) if calls else None,
        "seconds_per_call_max": max(calls) if calls else None,
        "prep_seconds_avg": round(sum(g["prep_seconds"] for g in game_stats) / games, 1),
        "played_lies_repeated_across_games": repeats,
        "accepted_with_no_quality_flags": sum(1 for r in kept if not r["quality_flags"]),
        "quality_flags_on_accepted": dict(sorted(flag_counts.items(), key=lambda kv: -kv[1])),
        "avg_words_accepted": round(sum(r["words"] for r in kept) / len(kept), 1) if kept else None,
        "per_game": game_stats,
    }

    with open(results / "lies.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["game", "call", "lie", "words", "game_decision", "quality_flags"] + (["judged_level"] if level_stats else []))
        w.writeheader()
        w.writerows(rows)
    (results / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # blind believability sheet: 20 AI lies the game kept + 20 hand-written bank lies
    ai_pick = rng.sample([r["lie"] for r in kept], min(20, len(kept)))
    bank_pick = rng.sample(bank_lies, len(ai_pick))
    items = [(t, "AI") for t in ai_pick] + [(t, "bank") for t in bank_pick]
    rng.shuffle(items)
    with open(results / "rating_sheet.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ID", "Statement", "Believable? 1 (obvious lie) to 5 (could be true)"])
        for i, (t, _) in enumerate(items, 1):
            w.writerow([i, t, ""])
    with open(results / "rating_key.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ID", "Source"])
        for i, (_, s) in enumerate(items, 1):
            w.writerow([i, s])
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--games", type=int, default=10)
    parser.add_argument("--url", default=Config.OLLAMA_URL)
    parser.add_argument("--model", default=Config.OLLAMA_MODEL)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--stories", choices=sorted(STORY_SETS), default="mixed",
                        help="which set of true stories the simulated players type in")
    parser.add_argument("--out", help="results folder (default evals/results)")
    parser.add_argument("--judge", action="store_true",
                        help="also rate how unusual the stories and lies are (CR-03 check)")
    parser.add_argument("--judge-model", help="model used to rate how unusual lies are (default: --model). "
                        "llama3.1:8b tells calm and wild stories apart far better than llama3.2:3b")
    args = parser.parse_args()
    s = run(args.games, args.url, args.model, args.seed, args.stories, args.out, args.judge, args.judge_model)
    print(json.dumps({k: v for k, v in s.items() if k != "per_game"}, indent=2))


if __name__ == "__main__":
    main()
