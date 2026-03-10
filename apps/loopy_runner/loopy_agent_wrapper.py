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
from typing import Any, Dict, Optional, Tuple

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


def create_session(agent_name: str, host: str = "localhost", port: int = 30011) -> Any:
    """Create a NeuroSAN agent session (direct gRPC)."""
    factory = AgentSessionFactory()
    connection = "direct"
    local_externals_direct = False
    metadata = {"user_id": os.environ.get("USER")}

    os.environ["AGENT_TOOL_PATH"] = "/Users/m_754339/PycharmProjects/neuro-san-mods/loopy_agent/coded_tools"

    return factory.create_session(connection, agent_name, host, port, local_externals_direct, metadata)


@dataclass
class LoopyAgent:
    agent_name: str
    host: str = "localhost"
    port: int = 30011
    thinking_file: str = "/tmp/agent_thinking.txt"
    session: Any = field(init=False)
    thread: Dict[str, Any] = field(init=False)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    def __post_init__(self):
        self.session = create_session(self.agent_name, self.host, self.port)
        self.thread = _default_thread(prompt="")

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
            # Only set sly_data if provided; leave existing otherwise.
            if sly_data is not None:
                self.thread["sly_data"] = sly_data
            self.thread = ip.process_once(self.thread)
            return self.thread.get("last_chat_response") or ""


async def create_loopy_agent(agent_name: str, host: str = "localhost", port: int = 30011) -> LoopyAgent:
    # Small helper so callers can stay async-friendly.
    return LoopyAgent(agent_name=agent_name, host=host, port=port)
