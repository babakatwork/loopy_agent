"""CLI demo: talk to the top agent (loopy_manager) over direct gRPC.

Usage:
  python apps/demo/demo_chat.py

Then type commands like:
  start demo loopy_echo 5 "tick: say hi"
  send demo "what's the last thing you did?"
  stop demo
"""

import os
from pathlib import Path

# Make sure NeuroSAN can find our manifest + coded tools.
os.environ["AGENT_MANIFEST_FILE"] = str(Path.cwd()) + "/registries/manifest.hocon"
os.environ["AGENT_TOOL_PATH"] = str(Path.cwd()) + "/coded_tools"

from neuro_san.client.agent_session_factory import AgentSessionFactory
from neuro_san.client.streaming_input_processor import StreamingInputProcessor


def set_up_agent(agent_name: str):
    connection = "direct"
    host = "localhost"
    port = 30011
    local_externals_direct = False
    metadata = {"user_id": os.environ.get("USER")}

    factory = AgentSessionFactory()
    session = factory.create_session(connection, agent_name, host, port, local_externals_direct, metadata)

    thread = {
        "last_chat_response": None,
        "prompt": "",
        "timeout": 5000.0,
        "num_input": 0,
        "user_input": None,
        "sly_data": {
            # tell tools where LoopRunner lives
            "loopy_base_url": os.environ.get("LOOPY_BASE_URL", "http://127.0.0.1:8088"),
        },
        "chat_filter": {"chat_filter_type": "MAXIMAL"},
    }
    return session, thread


def call_agent(session, thread, user_input: str):
    ip = StreamingInputProcessor("DEFAULT", "/tmp/agent_thinking.txt", session, None)
    thread["user_input"] = user_input
    thread = ip.process_once(thread)
    return thread.get("last_chat_response"), thread


HELP = """\
Commands:
  start <runner_id> <agent_name> <interval_s> <tick_prompt>
  send  <runner_id> <message>
  stop  <runner_id>
  quit
"""


def main():
    session, thread = set_up_agent("basic/loopy_manager")
    print("Connected to loopy_manager.\n")
    print(HELP)

    while True:
        line = input("loopy> ").strip()
        print ("line:" + line)
        if not line:
            continue
        if line == "quit":
            break

        # Turn simple commands into a single natural-language instruction for the top agent.
        # (Keeps this demo minimal; you can also call loopy_control directly from another agent.)
        if line.startswith("start "):
            _, runner_id, agent_name, interval_s, *rest = line.split(" ")
            tick_prompt = " ".join(rest).strip() or "tick"
            msg = f"Start a loopy agent runner_id={runner_id} agent_name={agent_name} interval_s={interval_s} tick_prompt={tick_prompt}"
        elif line.startswith("send "):
            _, runner_id, *rest = line.split(" ")
            message = " ".join(rest)
            msg = f"Send message to runner_id={runner_id}: {message}"
        elif line.startswith("stop "):
            _, runner_id = line.split(" ")
            msg = f"Stop runner_id={runner_id}"
        else:
            msg = line

        print(f"\nMESSAGE: {msg}\n")
        resp, thread = call_agent(session, thread, msg)
        print(f"\nRESPONSE:{resp}\n")


if __name__ == "__main__":
    main()
