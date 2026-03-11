"""A tiny stateful counter tool for the `loopy_echo` agent.

This demonstrates an important pattern for loopy agents:

- The loopy agent's `thread[\"sly_data\"]` dict persists across turns
  (because the LoopRunner holds the thread and reuses it).
- A coded tool can safely store/read state in sly_data.

We store the counter under sly_data["loopy_echo.counter"].
"""

from __future__ import annotations

from typing import Any, Dict

from neuro_san.interfaces.coded_tool import CodedTool


class CounterTool(CodedTool):
    """Increment or read a per-runner counter stored in sly_data."""

    KEY = "loopy_echo_counter"

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        # Defensive: NeuroSAN intends sly_data to be a dict, but keep it robust.
        if sly_data is None:
            sly_data = {}

        op = (args.get("op") or "get").lower()
        step = int(args.get("step") or 1)

        current = int(sly_data.get(self.KEY) or 0)

        if op == "inc":
            current += step
            sly_data[self.KEY] = current
            print("============counter_tool, key=" + str(sly_data[self.KEY]))
            return {"counter": current, "op": "inc", "step": step}

        if op == "reset":
            sly_data[self.KEY] = 0
            print("============counter_tool, key=" + str(sly_data[self.KEY]))
            return {"counter": 0, "op": "reset"}

        # default: get
        print("============counter_tool, key=" + str(current))
        return {"counter": current, "op": "get"}
