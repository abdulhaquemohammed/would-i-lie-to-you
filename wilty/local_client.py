"""M4b: free local AI. Asks a model running in Ollama on this laptop for lies (CR-01).

The prompt lives in ai_prompt.py.
Ollama: https://ollama.com  ->  `ollama pull llama3.2:3b`
"""
import json
import urllib.error
import urllib.request

from .ai_prompt import SYSTEM_PROMPT, AIError, build_prompt, parse_lies


class LocalModelError(AIError):
    """Local model not running, not downloaded, too slow, or gave unusable output."""


class LocalClient:
    def __init__(self, url, model, timeout=90):
        self.url = url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.source = "local"
        self.display_name = "the local AI model"

    def generate_lies(self, count, style_examples, avoid, good_lies=()):
        body = {
            "model": self.model,
            "stream": False,
            "format": "json",  # makes Ollama return valid JSON
            "options": {"temperature": 0.9},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_prompt(count, style_examples, avoid, as_object=True, good_lies=good_lies)},
            ],
        }
        request = urllib.request.Request(
            f"{self.url}/api/chat",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise LocalModelError(f"Model '{self.model}' is not downloaded. Run: ollama pull {self.model}") from exc
            raise LocalModelError(f"Ollama error {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LocalModelError("Ollama is not running on this laptop.") from exc

        text = data.get("message", {}).get("content", "")
        try:
            return parse_lies(text)
        except AIError as exc:
            raise LocalModelError(str(exc)) from exc
