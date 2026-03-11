"""A tiny, thread-safe-ish wrapper around a NeuroSAN agent session.

This mirrors the pattern in business.py:
- create AgentSession via AgentSessionFactory
- maintain a per-agent `thread` dict
- call StreamingInputProcessor.process_once(thread)

The wrapper is designed to be driven by an asyncio event loop, and protects
state with an asyncio.Lock so that periodic ticks and interactive messages
can't corrupt the shared thread state.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple, Callable
from importlib import import_module

from neuro_san.client.agent_session_factory import AgentSessionFactory
from neuro_san.client.streaming_input_processor import StreamingInputProcessor


def _default_thread(prompt: str = "") -> Dict[str, Any]:
    return {
        "last_chat_response": None,
        "prompt": prompt,
        "timeout": 5000.0,
        "num_input": 0,
        "user_input": None,
        # Keep a dict here so coded tools can safely store state across turns.
        # (e.g., our loopy_echo counter)
        "sly_data": {},
        "chat_filter": {"chat_filter_type": "MAXIMAL"},
    }

TriggerFn = Callable[[Dict[str, Any], Dict[str, Any], Dict[str, Any]], Tuple[bool, Optional[str]]]


def resolve_trigger_method(trigger_method: Optional[str]) -> Optional[TriggerFn]:
    """
    Accepts:
      - None
      - "apps.loopy_runner.triggers.always"
      - "apps.loopy_runner.triggers:always"
    """
    if not trigger_method:
        return None

    if ":" in trigger_method:
        module_name, func_name = trigger_method.split(":", 1)
    else:
        module_name, func_name = trigger_method.rsplit(".", 1)

    module = import_module(module_name)
    fn = getattr(module, func_name)
    return fn

def create_session(agent_name: str, host: str = "localhost", port: int = 30011) -> Any:
    """Create a NeuroSAN agent session (direct gRPC)."""
    factory = AgentSessionFactory()
    connection = "direct"
    local_externals_direct = False
    metadata = {"user_id": os.environ.get("USER")}

    return factory.create_session(connection, agent_name, host, port, local_externals_direct, metadata)


@dataclass
class LoopyAgent:
    agent_name: str
    host: str = "localhost"
    port: int = 30011
    thinking_file: str = "/tmp/agent_thinking.txt"
    trigger_method: Optional[str] = None
    trigger_args: Dict[str, Any] = field(default_factory=dict)

    session: Any = field(init=False)
    thread: Dict[str, Any] = field(init=False)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    trigger_fn: Optional[TriggerFn] = field(default=None, init=False)

    def __post_init__(self):
        self.session = create_session(self.agent_name, self.host, self.port)
        self.thread = _default_thread(prompt="")
        self.trigger_fn = resolve_trigger_method(self.trigger_method)

    async def run_turn(self, user_input: str, sly_data: Optional[Dict[str, Any]] = None) -> str:
        """Run a single turn and return the agent's last chat response."""
        async with self.lock:
            ip = StreamingInputProcessor(
                "DEFAULT",
                self.thinking_file,
                self.session,
                None,
            )
            self.thread["user_input"] = user_input
            if sly_data is not None:
                self.thread["sly_data"] = sly_data
            self.thread = ip.process_once(self.thread)
            return self.thread.get("last_chat_response") or ""

    async def maybe_run_trigger(
        self,
        event: Dict[str, Any],
        sly_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate trigger_method, and only run the agent if it fires.
        Returns:
          {
            "triggered": bool,
            "prompt": str | None,
            "response": str | None
          }
        """
        thread_view = dict(self.thread)
        if sly_data is not None:
            merged_sly = dict(thread_view.get("sly_data") or {})
            merged_sly.update(sly_data)
            thread_view["sly_data"] = merged_sly

        if self.trigger_fn is None:
            prompt = (
                event.get("prompt")
                or event.get("message")
                or event.get("tick_prompt")
                or "tick"
            )
            response = await self.run_turn(prompt, sly_data=sly_data)
            return {"triggered": True, "prompt": prompt, "response": response}

        fired, prompt = self.trigger_fn(event, thread_view, dict(self.trigger_args))
        if not fired:
            return {"triggered": False, "prompt": None, "response": None}

        prompt = prompt or event.get("prompt") or event.get("message") or event.get("tick_prompt") or "tick"
        response = await self.run_turn(prompt, sly_data=sly_data)
        return {"triggered": True, "prompt": prompt, "response": response}


async def create_loopy_agent(
    agent_name: str,
    host: str = "localhost",
    port: int = 30011,
    trigger_method: Optional[str] = None,
    trigger_args: Optional[Dict[str, Any]] = None,
) -> LoopyAgent:
    return LoopyAgent(
        agent_name=agent_name,
        host=host,
        port=port,
        trigger_method=trigger_method,
        trigger_args=trigger_args or {},
    )

