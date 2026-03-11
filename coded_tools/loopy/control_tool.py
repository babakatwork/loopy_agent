"""CodedTool wrapper that lets NeuroSAN agents control a loopy agent runner.

One tool, three actions:
- start: create a runner_id bound to an agent_name and interval
- send: send an interactive message, returns the agent response
- stop: stop a running runner_id

The tool calls the LoopRunner HTTP service.

Note on configuration:
- base_url can be provided via sly_data["loopy_base_url"] (preferred)
- otherwise defaults to http://127.0.0.1:8088

"""

from __future__ import annotations

from typing import Any, Dict

import httpx
import logging

from neuro_san.interfaces.coded_tool import CodedTool

logger = logging.getLogger(__name__)

def _as_int(value, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    s = str(value).strip()
    if s == "":
        return default
    return int(s)

def _as_float(value, default: float) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if s == "":
        return default
    return float(s)

def _as_dict(value) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        s = value.strip()
        if s == "":
            return {}
        import json
        return json.loads(s)
    raise ValueError(f"Expected dict or JSON string, got: {type(value)}")


class LoopyControlTool(CodedTool):
    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        print("[LoopyControlTool] ENTER async_invoke args=", args, "sly_data_keys=", list((sly_data or {}).keys()), flush=True)
        action = args.get("action")

        if action not in {"start", "send", "stop", "signal"}:
            return {"ok": False, "error": f"Unknown action: {action}"}

        if action == "start":
            if not args.get("runner_id"):
                return {"ok": False, "error": "runner_id is required for start"}
            if not args.get("agent_name"):
                return {"ok": False, "error": "agent_name is required for start"}

        if action in {"send", "stop"}:
            if not args.get("runner_id"):
                return {"ok": False, "error": "runner_id is required"}
        
        base_url = (sly_data or {}).get("loopy_base_url") or "http://127.0.0.1:8088"
        runner_id = args.get("runner_id")

        logger.info(
            "LoopyControlTool called action=%s runner_id=%s base_url=%s",
            action, runner_id, base_url,
        )
        print(f"[LoopyControlTool] HTTP {action} -> {base_url}", flush=True)
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                if action == "start":
                    payload = {
                        "runner_id": args["runner_id"],
                        "agent_name": args["agent_name"],
                        "interval_s": None if args.get("interval_s") in (None, "", "none", "null") else _as_float(args.get("interval_s"), 5.0),
                        "tick_prompt": args.get("tick_prompt", "tick"),
                        # optional override: where the NeuroSAN server is
                        "host": args.get("ns_host", "localhost"),
                        "port": _as_int(args.get("ns_port"), 30011),
                        "trigger_method": args.get("trigger_method"),
                        "trigger_args": _as_dict(args.get("trigger_args")),
                    }

                    logger.info(
                        "LoopyControlTool start runner_id=%s agent_name=%s interval_s=%s tick_prompt=%s ns_host=%s ns_port=%s",
                        payload["runner_id"],
                        payload["agent_name"],
                        payload["interval_s"],
                        payload["tick_prompt"],
                        payload["host"],
                        payload["port"],
                    )

                    r = await client.post(f"{base_url}/start", json=payload)
                    logger.info("LoopRunner /start status=%s runner_id=%s", r.status_code, payload["runner_id"])

                    if r.status_code == 409:
                        return {"ok": False, "error": r.json().get("detail", "runner_id already exists")}
                    r.raise_for_status()
                    return {"ok": True, "runner_id": args["runner_id"]}

                if action == "send":

                    msg = args.get("message", "")
                    logger.info("LoopyControlTool send runner_id=%s message_len=%d", runner_id, len(msg))

                    r = await client.post(f"{base_url}/send", json={"runner_id": args["runner_id"], "message": args["message"]})
                    logger.info("LoopRunner /send status=%s runner_id=%s", r.status_code, runner_id)

                    if r.status_code == 404:
                        return {"ok": False, "error": r.json().get("detail", "unknown runner_id")}
                    r.raise_for_status()
                    return {"ok": True, "response": r.json().get("response", "")}

                if action == "signal":
                    payload = {
                        "runner_id": args["runner_id"],
                        "event": _as_dict(args.get("event")),
                        "sly_data": _as_dict(args.get("signal_sly_data")),
                    }
                    logger.info("LoopyControlTool signal runner_id=%s event=%s", runner_id, payload["event"])
                    r = await client.post(f"{base_url}/signal", json=payload)
                    logger.info("LoopRunner /signal status=%s runner_id=%s", r.status_code, runner_id)

                    if r.status_code == 404:
                        return {"ok": False, "error": r.json().get("detail", "unknown runner_id")}
                    r.raise_for_status()
                    body = r.json()
                    return {
                        "ok": True,
                        "triggered": body.get("triggered", False),
                        "prompt": body.get("prompt"),
                        "response": body.get("response"),
                    }

                if action == "stop":
                    logger.info("LoopyControlTool stop runner_id=%s", runner_id)
                    r = await client.post(f"{base_url}/stop", json={"runner_id": args["runner_id"]})
                    logger.info("LoopRunner /stop status=%s runner_id=%s", r.status_code, runner_id)
                    if r.status_code == 404:
                        return {"ok": False, "error": r.json().get("detail", "unknown runner_id")}
                    r.raise_for_status()
                    return {"ok": True}
        except httpx.RequestError:
            logger.exception("LoopRunner request failed action=%s runner_id=%s base_url=%s", action, runner_id, base_url)
            return {"ok": False, "error": "LoopRunner request failed (network/connection)"}
        except httpx.HTTPStatusError:
            logger.exception("LoopRunner HTTP error action=%s runner_id=%s base_url=%s", action, runner_id, base_url)
            return {"ok": False, "error": "LoopRunner returned an HTTP error"}
        except Exception:
            logger.exception("LoopyControlTool unexpected error action=%s runner_id=%s", action, runner_id)
            return {"ok": False, "error": "Unexpected error in LoopyControlTool"}

        return {"ok": False, "error": f"unknown action: {action}. expected one of start|send|stop|signal"}
