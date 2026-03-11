"""LoopRunner: a small HTTP service that runs NeuroSAN agents on a periodic tick,
while also supporting interactive messages.

Run:
  python apps/loopy_runner/app.py --host 127.0.0.1 --port 8088

Endpoints:
  POST /start  {runner_id, agent_name, interval_s, tick_prompt?}
  POST /send   {runner_id, message}
  POST /stop   {runner_id}
  GET  /list
  GET  /status/{runner_id}

Design goals:
- Serialize access to each agent's `thread` state (no races)
- Allow periodic ticks and interactive messages to share the same state
"""

from __future__ import annotations


# very top of app.py, before neuro_san imports
import os
import sys
from pathlib import Path

REPO_ROOT = str(Path(__file__).resolve().parents[2])
TOOL_ROOT = REPO_ROOT + "/coded_tools"
MANIFEST = REPO_ROOT + "/registries/manifest.hocon"

os.environ["AGENT_MANIFEST_FILE"] = str(MANIFEST)
os.environ["AGENT_TOOL_PATH"] = str(TOOL_ROOT)

if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

print("AGENT_TOOL_PATH =", repr(os.environ.get("AGENT_TOOL_PATH")))
print("sys.path[0]     =", sys.path[0])


import argparse
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import uvicorn
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("loopy_runner")

from apps.loopy_runner.loopy_agent_wrapper import create_loopy_agent, LoopyAgent


class StartReq(BaseModel):
    runner_id: str = Field(..., description="Unique ID for this running loopy agent instance")
    agent_name: str = Field(..., description="NeuroSAN agent name to run (must exist in your manifest)")
    interval_s: Optional[float] = Field(None, description="Loop interval in seconds; omit or <= 0 for no loop")
    tick_prompt: str = Field("tick", description="Message to send on each tick")
    host: Optional[str] = Field("localhost", description="NeuroSAN server host")
    port: Optional[int] = Field(30011, description="NeuroSAN server gRPC port")
    trigger_method: Optional[str] = Field(
        None,
        description="Python dotted path for trigger function, e.g. apps.loopy_runner.triggers.contains_keyword",
    )
    trigger_args: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arguments for trigger_method",
    )



class SendReq(BaseModel):
    runner_id: str
    message: str


class SignalReq(BaseModel):
    runner_id: str
    event: Dict[str, Any] = Field(default_factory=dict)
    sly_data: Optional[Dict[str, Any]] = None


class StopReq(BaseModel):
    runner_id: str


@dataclass
class Runner:
    loopy_agent: LoopyAgent
    interval_s: Optional[float]
    tick_prompt: str
    created_at: float = field(default_factory=time.time)
    ticks: int = 0
    loop_iterations: int = 0
    task: Optional[asyncio.Task] = None
    last_tick_ts: Optional[float] = None
    last_trigger_ts: Optional[float] = None

    async def loop_forever(self, runner_id: str):
        while True:
            self.loop_iterations += 1
            event = {
                "kind": "tick",
                "runner_id": runner_id,
                "tick_index": self.loop_iterations,
                "tick_prompt": self.tick_prompt,
                "ts": time.time(),
            }

            logger.info(
                "TICK runner=%s agent=%s tick_index=%s trigger=%s",
                runner_id,
                self.loopy_agent.agent_name,
                self.loop_iterations,
                self.loopy_agent.trigger_method,
            )

            result = await self.loopy_agent.maybe_run_trigger(event)
            self.last_tick_ts = time.time()

            if result["triggered"]:
                self.ticks += 1
                self.last_trigger_ts = time.time()
                logger.info(
                    "TRIGGER FIRED runner=%s prompt=%s response=%s",
                    runner_id,
                    result["prompt"],
                    result["response"],
                )
            else:
                logger.info("TRIGGER SKIPPED runner=%s", runner_id)

            await asyncio.sleep(self.interval_s or 0.0)

class Registry:
    def __init__(self):
        self._runners: Dict[str, Runner] = {}
        self._lock = asyncio.Lock()

    async def start(
        self,
        runner_id: str,
        agent_name: str,
        interval_s: Optional[float],
        tick_prompt: str,
        host: str,
        port: int,
        trigger_method: Optional[str],
        trigger_args: Dict[str, Any],
    ):    
        async with self._lock:
            logger.info(
                "START request received: runner_id=%s agent=%s interval=%s tick_prompt=%s trigger_method=%s trigger_args=%s",
                runner_id,
                agent_name,
                interval_s,
                tick_prompt,
                trigger_method,
                trigger_args,
            )
            if runner_id in self._runners:
                raise ValueError(f"runner_id already exists: {runner_id}")

            agent = await create_loopy_agent(
                agent_name,
                host=host,
                port=port,
                trigger_method=trigger_method,
                trigger_args=trigger_args,
            )
            r = Runner(loopy_agent=agent, interval_s=interval_s, tick_prompt=tick_prompt)

            if interval_s is not None and interval_s > 0:
                r.task = asyncio.create_task(r.loop_forever(runner_id))

            self._runners[runner_id] = r
            logger.info("Runner %s successfully started", runner_id)

    async def send(self, runner_id: str, message: str) -> str:
        logger.info("SEND request: runner=%s message=%s", runner_id, message)
        r = self._runners.get(runner_id)
        if not r:
            raise KeyError(runner_id)

        try:
            response = await r.loopy_agent.run_turn(message)
        except Exception:
            logger.exception("Agent execution failed for runner=%s", runner_id)
            raise

        logger.info("SEND response: runner=%s response=%s", runner_id, response)
        return response

    async def stop(self, runner_id: str):
        async with self._lock:
            logger.info("STOP request received for runner=%s", runner_id)            
            r = self._runners.pop(runner_id, None)
            if not r:
                raise KeyError(runner_id)
            if r.task:
                r.task.cancel()
            logger.info("Runner %s stopped", runner_id)

    def list(self):
        out = []
        for rid, r in self._runners.items():
            out.append(
                {
                    "runner_id": rid,
                    "agent_name": r.loopy_agent.agent_name,
                    "interval_s": r.interval_s,
                    "tick_prompt": r.tick_prompt,
                    "created_at": r.created_at,
                    "ticks": r.ticks,
                    "last_tick_ts": r.last_tick_ts,
                }
            )
        return out

    def status(self, runner_id: str):
        r = self._runners.get(runner_id)
        if not r:
            raise KeyError(runner_id)
        return {
            "runner_id": runner_id,
            "agent_name": r.loopy_agent.agent_name,
            "interval_s": r.interval_s,
            "tick_prompt": r.tick_prompt,
            "created_at": r.created_at,
            "ticks": r.ticks,
            "last_tick_ts": r.last_tick_ts,
            "loop_iterations": r.loop_iterations,
            "last_trigger_ts": r.last_trigger_ts,
            "trigger_method": r.loopy_agent.trigger_method,
            "trigger_args": r.loopy_agent.trigger_args,
        }

    async def signal(self, runner_id: str, event: Dict[str, Any], sly_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        logger.info("SIGNAL request: runner=%s event=%s", runner_id, event)
        r = self._runners.get(runner_id)
        if not r:
            raise KeyError(runner_id)

        result = await r.loopy_agent.maybe_run_trigger(event, sly_data=sly_data)
        if result["triggered"]:
            r.last_trigger_ts = time.time()
        return result


registry = Registry()
app = FastAPI(title="NeuroSAN LoopRunner", version="0.1")


@app.post("/start")
async def start(req: StartReq):
    try:
        await registry.start(
            req.runner_id,
            req.agent_name,
            req.interval_s,
            req.tick_prompt,
            req.host or "localhost",
            req.port or 30011,
            req.trigger_method,
            req.trigger_args,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"ok": True, "runner_id": req.runner_id}


@app.post("/send")
async def send(req: SendReq):
    try:
        resp = await registry.send(req.runner_id, req.message)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown runner_id: {req.runner_id}")
    return {"ok": True, "response": resp}


@app.post("/stop")
async def stop(req: StopReq):
    try:
        await registry.stop(req.runner_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown runner_id: {req.runner_id}")
    return {"ok": True}


@app.get("/list")
def list_runners():
    return {"ok": True, "runners": registry.list()}


@app.post("/signal")
async def signal(req: SignalReq):
    try:
        result = await registry.signal(req.runner_id, req.event, sly_data=req.sly_data)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown runner_id: {req.runner_id}")
    return {"ok": True, **result}


@app.get("/status/{runner_id}")
def status(runner_id: str):
    try:
        return {"ok": True, "status": registry.status(runner_id)}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown runner_id: {runner_id}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8088)
    args = p.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
