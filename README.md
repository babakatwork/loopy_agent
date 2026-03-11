# NeuroSAN Loopy Agents (minimal example)

This is a small, runnable example showing how to:

1.  run a NeuroSAN agent in a periodic loop ("ticks") via a separate
    **LoopRunner service**
2.  send interactive messages to that same agent at any time
3.  **trigger agents based on conditions**
4.  control everything from a NeuroSAN agent network using a **coded
    tool**

The agent network has **two agents**:

-   `loopy_manager` (top agent)
-   `loopy_control` (coded tool agent)

The LoopRunner is a small **FastAPI service** that runs the loopy agent
and exposes HTTP endpoints.

------------------------------------------------------------------------

# Folder structure

    apps/
      loopy_runner/
        app.py
        loopy_agent_wrapper.py
        triggers.py

    coded_tools/
      loopy/
        control_tool.py

    registries/
      basic/
        loopy_demo.hocon
        loopy_echo.hocon
      manifest.hocon

    apps/demo/
      demo_chat.py

------------------------------------------------------------------------

# Prerequisites

-   Python supported by NeuroSAN (3.12+ typical)
-   `OPENAI_API_KEY` or other model provider

Example requirements:

    neuro-san
    fastapi
    uvicorn
    httpx

------------------------------------------------------------------------

# Setup

From the project root:

    python -m venv venv
    source venv/bin/activate
    export PYTHONPATH=`pwd`

    pip install -r requirements.txt

    export AGENT_MANIFEST_FILE=`pwd`/registries/manifest.hocon
    export AGENT_TOOL_PATH=`pwd`/coded_tools

------------------------------------------------------------------------

# 1) Start the NeuroSAN server

Terminal A:

    python -m neuro_san.service.main_loop.server_main_loop

(default gRPC port: `30011`)

------------------------------------------------------------------------

# 2) Confirm the demo agent exists

This example includes a simple target agent:

    basic/loopy_echo

Behavior:

-   On each **tick**, increments a counter
-   Responds with:

```{=html}
<!-- -->
```
    tick <counter>

------------------------------------------------------------------------

# 3) Start LoopRunner

Terminal B:

    python -m apps.loopy_runner.app --host 127.0.0.1 --port 8088

LoopRunner exposes endpoints:

    POST /start
    POST /send
    POST /signal
    POST /stop
    POST /status

------------------------------------------------------------------------

# 4) Talk to the top agent

Terminal C:

    export LOOPY_BASE_URL=http://127.0.0.1:8088

    python apps/demo/demo_chat.py

------------------------------------------------------------------------

# Basic Loopy Agent Example

Start a looping agent:

    start demo basic/loopy_echo 2 tick

Meaning:

    runner_id = demo
    agent_name = basic/loopy_echo
    interval = 2 seconds
    tick_prompt = "tick"

Example interaction:

    send demo what is the counter?
    send demo hello
    send demo reset the counter
    send demo what is the counter?
    stop demo

------------------------------------------------------------------------

# Triggered Agents

Agents can run **only when a trigger condition fires**.

A trigger is defined by:

    trigger_method
    trigger_args

Example trigger:

    apps.loopy_runner.triggers.contains_keyword

Trigger functions receive:

    (event, thread, trigger_args)

and return:

    (fired: bool, prompt: str | None)

------------------------------------------------------------------------

# Example Trigger Methods

Provided examples:

    apps.loopy_runner.triggers.always
    apps.loopy_runner.triggers.contains_keyword
    apps.loopy_runner.triggers.regex_match
    apps.loopy_runner.triggers.every_n_ticks

------------------------------------------------------------------------

# Example 1 --- Looping agent with trigger

Start an agent that runs **every 3 ticks**:

    start demo basic/loopy_echo 2 tick \
    trigger_method apps.loopy_runner.triggers.every_n_ticks \
    trigger_args {"n":3}

Behavior:

    tick 1 → skipped
    tick 2 → skipped
    tick 3 → agent runs
    tick 4 → skipped
    tick 5 → skipped
    tick 6 → agent runs

------------------------------------------------------------------------

# Example 2 --- Signal-only agent (no loop)

Start:

    start sensor1 basic/loopy_echo none
    trigger_method apps.loopy_runner.triggers.contains_keyword
    trigger_args {"keywords":["alert"]}

Because `interval_s` is `none`, **no loop runs**.

------------------------------------------------------------------------

# Example signal

    signal sensor1 {"message":"temperature alert in zone 4"}

This triggers the agent.

This will not:

    signal sensor1 {"message":"all clear"}

------------------------------------------------------------------------

# Signal events

Signals send an event payload:

    {
      "event": {
        "message": "temperature alert"
      }
    }

------------------------------------------------------------------------

# Non-loop agents

`interval_s = none` means the agent only reacts to signals or direct
messages.

Internally:

    interval_s = None

so the loop task is not created.

------------------------------------------------------------------------

# Summary of coded tool actions

  action   description
  -------- --------------------------
  start    start a runner
  send     send interactive message
  signal   send trigger event
  stop     stop runner

------------------------------------------------------------------------

# Notes

The coded tool reads the LoopRunner URL from:

    sly_data["loopy_base_url"]

Default:

    http://127.0.0.1:8088

------------------------------------------------------------------------

# Why LoopRunner exists

Running infinite loops inside NeuroSAN can be unreliable because servers
may restart or fork workers.

LoopRunner keeps:

    agent sessions
    thread state
    trigger logic
    loop scheduling

stable.

------------------------------------------------------------------------

# NeuroSAN repository

https://github.com/cognizant-ai-lab/neuro-san
