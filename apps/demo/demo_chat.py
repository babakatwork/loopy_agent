import os
import json
import asyncio
from pathlib import Path
from typing import Optional

# Optional environment bootstrap for local runs
REPO_ROOT = Path(__file__).resolve().parents[2] if len(Path(__file__).resolve().parents) >= 3 else Path.cwd()
os.environ.setdefault("AGENT_MANIFEST_FILE", str(REPO_ROOT / "registries" / "manifest.hocon"))
os.environ.setdefault("AGENT_TOOL_PATH", str(REPO_ROOT / "coded_tools"))

from neuro_san.client.agent_session_factory import AgentSessionFactory
from neuro_san.client.streaming_input_processor import StreamingInputProcessor


DEFAULT_TOP_AGENT = "basic/loopy_manager"
DEFAULT_NS_HOST = os.environ.get("NS_HOST", "localhost")
DEFAULT_NS_PORT = int(os.environ.get("NS_PORT", "30011"))
DEFAULT_LOOPY_BASE_URL = os.environ.get("LOOPY_BASE_URL", "http://127.0.0.1:8088")


HELP_TEXT = """
Commands:
  help
  quit | exit

Top-agent chat:
  <any free-form text>

Convenience commands (converted into a natural-language request to loopy_manager):
  start <runner_id> <agent_name> <interval_s|none> [tick_prompt]
  send <runner_id> <message>
  signal <runner_id> <json_event>
  stop <runner_id>
  status <runner_id>

Trigger examples:
  start demo basic/loopy_echo 2 tick
  start demo basic/loopy_echo 2 tick --trigger apps.loopy_runner.triggers.every_n_ticks --trigger-args '{"n":3}'
  start sensor1 basic/loopy_echo none --trigger apps.loopy_runner.triggers.contains_keyword --trigger-args '{"keywords":["alert"]}'
  signal sensor1 {"message":"temperature alert in zone 4"}

Notes:
  - interval_s can be a number or 'none' for a signal-only runner.
  - tick_prompt may contain spaces.
  - --trigger and --trigger-args are optional on start.
  - signal expects a valid JSON object.
""".strip()


def make_thread():
    return {
        "last_chat_response": None,
        "prompt": "",
        "timeout": 5000.0,
        "num_input": 0,
        "user_input": None,
        "sly_data": {"loopy_base_url": DEFAULT_LOOPY_BASE_URL},
        "chat_filter": {"chat_filter_type": "MAXIMAL"},
    }


def create_session(agent_name: str):
    factory = AgentSessionFactory()
    return factory.create_session(
        "direct",
        agent_name,
        DEFAULT_NS_HOST,
        DEFAULT_NS_PORT,
        False,
        {"user_id": os.environ.get("USER") or os.environ.get("USERNAME") or "demo"},
    )


def run_turn(session, thread, user_input: str):
    ip = StreamingInputProcessor("DEFAULT", "/tmp/agent_thinking.txt", session, None)
    thread["user_input"] = user_input
    return ip.process_once(thread)


def _extract_flag_value(parts: list[str], flag: str) -> Optional[str]:
    if flag not in parts:
        return None
    idx = parts.index(flag)
    if idx + 1 >= len(parts):
        return None
    return parts[idx + 1]


def _strip_flag_pair(parts: list[str], flag: str) -> list[str]:
    if flag not in parts:
        return parts
    idx = parts.index(flag)
    end = idx + 2 if idx + 1 < len(parts) else idx + 1
    return parts[:idx] + parts[end:]


def normalize_user_input(raw: str) -> str:
    text = raw.strip()
    if not text:
        return text

    parts = text.split()
    cmd = parts[0].lower()

    if cmd == "start":
        trigger_method = _extract_flag_value(parts, "--trigger")
        trigger_args_raw = _extract_flag_value(parts, "--trigger-args")
        stripped = _strip_flag_pair(_strip_flag_pair(parts, "--trigger"), "--trigger-args")

        if len(stripped) < 4:
            return text

        runner_id = stripped[1]
        agent_name = stripped[2]
        interval_s = stripped[3]
        tick_prompt = " ".join(stripped[4:]).strip() or "tick"

        out = [
            f"Use loopy_control to start runner_id={runner_id}",
            f"agent_name={agent_name}",
            f"interval_s={interval_s}",
            f"tick_prompt={json.dumps(tick_prompt)}",
            f"ns_host={DEFAULT_NS_HOST}",
            f"ns_port={DEFAULT_NS_PORT}",
        ]
        if trigger_method:
            out.append(f"trigger_method={trigger_method}")
        if trigger_args_raw:
            out.append(f"trigger_args={trigger_args_raw}")
        return "; ".join(out) + "."

    if cmd == "send" and len(parts) >= 3:
        runner_id = parts[1]
        message = text.split(None, 2)[2]
        return f'Use loopy_control to send message={json.dumps(message)} to runner_id={runner_id}.'

    if cmd == "signal" and len(parts) >= 3:
        runner_id = parts[1]
        event_json = text.split(None, 2)[2]
        try:
            json.loads(event_json)
        except json.JSONDecodeError:
            return text
        return f"Use loopy_control to signal runner_id={runner_id} with event={event_json}."

    if cmd == "stop" and len(parts) >= 2:
        runner_id = parts[1]
        return f"Use loopy_control to stop runner_id={runner_id}."

    if cmd == "status" and len(parts) >= 2:
        runner_id = parts[1]
        return (
            f"Use loopy_control to get the status for runner_id={runner_id}. "
            f"If there is no explicit status tool, explain how to inspect it via "
            f"the LoopRunner /status endpoint at {DEFAULT_LOOPY_BASE_URL}/status?runner_id={runner_id}."
        )

    return text


async def main():
    print(f"Top agent: {DEFAULT_TOP_AGENT}")
    print(f"NeuroSAN: {DEFAULT_NS_HOST}:{DEFAULT_NS_PORT}")
    print(f"LoopRunner: {DEFAULT_LOOPY_BASE_URL}")
    print()
    print(HELP_TEXT)
    print()

    session = create_session(DEFAULT_TOP_AGENT)
    thread = make_thread()

    while True:
        try:
            raw = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not raw:
            continue
        if raw.lower() in {"quit", "exit"}:
            break
        if raw.lower() == "help":
            print(HELP_TEXT)
            continue

        user_input = normalize_user_input(raw)
        try:
            thread = run_turn(session, thread, user_input)
            print(thread.get("last_chat_response") or "")
        except Exception as e:
            print(f"ERROR: {e}")


if __name__ == "__main__":
    asyncio.run(main())
