"""Shared test helpers: a scripted fake model so episodes run with no network."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harness import prompts  # noqa: E402
from harness.models import Reply  # noqa: E402


class FakeModels:
    """Plays the peer from a script; monitors always answer score 6; probe answers 'same'."""

    def __init__(self, peer_script, monitor_reply='{"score": 6, "reason": "pasted rows"}', requester_text="Please add the rows."):
        self.peer_script = list(peer_script)
        self.monitor_reply = monitor_reply
        self.requester_text = requester_text
        self.calls = []

    def __call__(self, model_key, system, messages, max_tokens):
        self.calls.append((model_key, system, messages))
        if system == prompts.MONITOR_SYSTEM:
            text = self.monitor_reply
        elif system == prompts.freeform_requester_system():
            text = self.requester_text
        elif prompts.RECOGNITION_PROBE in messages[-1]["content"]:
            text = "same"
        else:
            step = self.peer_script.pop(0) if self.peer_script else {"final": "done"}
            text = step if isinstance(step, str) else json.dumps(step)
        return Reply(text=text, reasoning=None, tokens_in=100, tokens_out=10, cost_usd=0.001,
                     cost_source="fake", meta={"provider": "fake", "model_returned": model_key})
