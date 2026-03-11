from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

TriggerResult = Tuple[bool, Optional[str]]


def always(event: Dict[str, Any], thread: Dict[str, Any], trigger_args: Dict[str, Any]) -> TriggerResult:
    """
    Always fire.
    Prompt precedence:
      event["prompt"] > event["message"] > event["tick_prompt"] > trigger_args["prompt"] > "tick"
    """
    prompt = (
        event.get("prompt")
        or event.get("message")
        or event.get("tick_prompt")
        or trigger_args.get("prompt")
        or "tick"
    )
    return True, prompt


def contains_keyword(event: Dict[str, Any], thread: Dict[str, Any], trigger_args: Dict[str, Any]) -> TriggerResult:
    """
    Fire only if event text contains one of the keywords.
    trigger_args:
      - keywords: list[str] or comma-separated string
      - prompt: optional override prompt
      - use_message_as_prompt: bool (default True)
    """
    raw_keywords = trigger_args.get("keywords") or trigger_args.get("keyword") or []
    if isinstance(raw_keywords, str):
        keywords = [x.strip().lower() for x in raw_keywords.split(",") if x.strip()]
    else:
        keywords = [str(x).strip().lower() for x in raw_keywords if str(x).strip()]

    text = str(event.get("message") or event.get("prompt") or "").lower()
    fired = any(k in text for k in keywords)

    if not fired:
        return False, None

    if trigger_args.get("use_message_as_prompt", True):
        prompt = event.get("message") or event.get("prompt") or trigger_args.get("prompt") or "tick"
    else:
        prompt = trigger_args.get("prompt") or "tick"
    return True, prompt


def regex_match(event: Dict[str, Any], thread: Dict[str, Any], trigger_args: Dict[str, Any]) -> TriggerResult:
    """
    Fire only if regex matches event text.
    trigger_args:
      - pattern: required
      - flags: optional string with chars i,m,s
      - prompt: optional override prompt
      - use_message_as_prompt: bool (default True)
    """
    pattern = trigger_args.get("pattern")
    if not pattern:
        return False, None

    flag_bits = 0
    flags_str = str(trigger_args.get("flags") or "")
    if "i" in flags_str:
        flag_bits |= re.IGNORECASE
    if "m" in flags_str:
        flag_bits |= re.MULTILINE
    if "s" in flags_str:
        flag_bits |= re.DOTALL

    text = str(event.get("message") or event.get("prompt") or "")
    fired = re.search(pattern, text, flags=flag_bits) is not None
    if not fired:
        return False, None

    if trigger_args.get("use_message_as_prompt", True):
        prompt = event.get("message") or event.get("prompt") or trigger_args.get("prompt") or "tick"
    else:
        prompt = trigger_args.get("prompt") or "tick"
    return True, prompt


def every_n_ticks(event: Dict[str, Any], thread: Dict[str, Any], trigger_args: Dict[str, Any]) -> TriggerResult:
    """
    Fire every Nth loop tick.
    trigger_args:
      - n: int
      - prompt: optional prompt override
    """
    n = int(trigger_args.get("n") or 1)
    tick_index = int(event.get("tick_index") or 0)
    if n <= 1 or (tick_index % n == 0):
        prompt = event.get("tick_prompt") or trigger_args.get("prompt") or "tick"
        return True, prompt
    return False, None