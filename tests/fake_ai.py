"""A stand-in for the local AI client so tests never need Ollama running."""
from wilty.ai_prompt import AIError

SAMPLE_LIES = [
    "I once rode a camel across a car park in Swansea for charity.",
    "My uncle keeps a pet tortoise that is older than the Eiffel Tower.",
    "I won a pie throwing contest against a local vicar last summer.",
    "Our fridge broke so we kept milk in the bath for a whole week.",
    "I accidentally reversed into a parade float shaped like a dragon.",
    "At seven I convinced my class that our caretaker was a retired astronaut.",
    "We found a vintage typewriter buried in the garden under the shed.",
    "My hamster escaped and lived inside the piano for three months.",
    "I taught a parrot to say 'goal' during the World Cup final.",
    "Grandma beat me at arm wrestling on her eightieth birthday.",
    "During a power cut I learned to play chess by candlelight with a plumber.",
    "My first concert was a brass band playing on a ferry to Ireland.",
    "I was an extra in a cereal advert but only my elbow made the final cut.",
    "Someone mistook my lunchbox for a bomb and the bus was stopped for an hour.",
]


class FakeAI:
    source = "local"
    display_name = "the local AI model"

    def __init__(self, batches=None, error=None):
        """batches: list of lists; each generate_lies call returns the next one."""
        self.batches = list(batches or [])
        self.error = error
        self.calls = 0

    def generate_lies(self, count, style_examples, avoid, good_lies=()):
        self.calls += 1
        if self.error:
            raise AIError(self.error)
        if not self.batches:
            return []
        return self.batches.pop(0)
