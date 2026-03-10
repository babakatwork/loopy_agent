# NeuroSAN Loopy Agents (minimal example)

This is a small, runnable example showing how to:

1) run a NeuroSAN agent in an infinite loop ("ticks") via a separate LoopRunner service, and
2) send interactive messages to that same agent at any time, and
3) control all of that from a NeuroSAN agent network using a **coded tool**.

The agent network has **two agents**:

- `loopy_manager` (top agent)
- `loopy_control` (coded tool agent)

The LoopRunner is a small FastAPI service that runs the loopy agent and exposes HTTP endpoints.

## Folder structure

- `apps/loopy_runner/app.py` – LoopRunner HTTP service (start/send/stop)
- `coded_tools/loopy/control_tool.py` – a single coded tool with actions start/send/stop
- `registries/basic/loopy_demo.hocon` – 2-agent network (manager + coded tool)
- `registries/basic/loopy_echo.hocon` – loopy target agent network (counter + echo)
- `registries/manifest.hocon` – registers `basic/loopy_demo.hocon` and `basic/loopy_echo.hocon`
- `apps/demo/demo_chat.py` – CLI to talk to the top agent (no web UI required)

## Prereqs

- Python version supported by your NeuroSAN setup (commonly 3.12+ in neuro-san repos)
- `OPENAI_API_KEY` (or set up a different provider in your environment)

This repo assumes you already have a working `requirements.txt` that includes:
- `neuro-san`
- `fastapi`, `uvicorn`, `httpx`

## Setup

From the project root:

```bash
python -m venv venv
source venv/bin/activate
export PYTHONPATH=`pwd`

pip install -r requirements.txt

export AGENT_MANIFEST_FILE=`pwd`/registries/manifest.hocon
export AGENT_TOOL_PATH=`pwd`/coded_tools
```

## 1) Start the NeuroSAN server

In terminal A:

```bash
# gRPC server (port 30011 by default)
python -m neuro_san.service.main_loop.server_main_loop
```

(That’s the standard dev-mode server entrypoint in the neuro-san docs.)

(If your setup uses a different entrypoint, use whatever you normally run for the NeuroSAN gRPC server.)

## 2) Make sure you have a loopy target agent

The LoopRunner needs an **agent name** that exists on your server.

For this demo, we include a simple loopy target agent network named `loopy_echo`.

It does two things:
- On each tick, it increments an internal counter and responds with `tick <n>`.
- On interactive messages like "what is the counter?" it reports the current value.

## 3) Start LoopRunner

In terminal B:

```bash
python -m apps.loopy_runner.app --host 127.0.0.1 --port 8088
```

## 4) Talk to the top agent (CLI demo)

In terminal C:

```bash
# Optional if LoopRunner is not on localhost:8088
export LOOPY_BASE_URL=http://127.0.0.1:8088

python apps/demo/demo_chat.py
```

Try:

```text
start demo basic/loopy_echo 2 tick
send demo what is the counter?
send demo hello
send demo reset the counter
send demo what is the counter?
stop demo
```

What’s happening:
- the CLI talks to `loopy_manager`
- `loopy_manager` calls the coded tool agent `loopy_control`
- `loopy_control` calls LoopRunner over HTTP
- LoopRunner advances the loopy agent state either on ticks or on demand

## Notes

- The coded tool reads the LoopRunner URL from `sly_data["loopy_base_url"]` (preferred) and defaults to `http://127.0.0.1:8088`.
- This is the simplest reliable pattern for "loopy agents" because it avoids keeping infinite background tasks inside the NeuroSAN server process.

## References

- NeuroSAN repo: https://github.com/cognizant-ai-lab/neuro-san
