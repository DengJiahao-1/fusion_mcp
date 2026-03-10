"""
CAD workflow planner.

Given a user request (e.g. "create a cup"), generates structured tool call plan for PlanExecutor.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .providers import BaseLLMProvider

PLANNING_SYSTEM_PROMPT = """You are a Fusion 360 CAD workflow planner. Given a user request to create a 3D model, output a JSON plan with the exact tool calls needed to complete the task.

[Output Format]
Output ONLY valid JSON. You may wrap it in ```json ... ```. No other text.

[Schema]
{
  "goal": "Short description of user request",
  "reasoning": "Brief rationale for these steps",
  "steps": [
    {"tool": "tool_name", "arguments": {...}},
    ...
  ]
}

[Strict Rules - MUST Follow]
1. Placeholders: sketch_polyline/revolve use sketch_name/profile_name="${last_sketch_name}"; shell use body_name="${last_body}"; create_entity_relative use base_body_name="${last_body}" (auto-filled from prior create_box). Never hardcode "Sketch1"/"Body1".
2. Param names (exact match):
   - sketch_polyline: sketch_name, points (2D array [[x,y],...])
   - revolve: profile_name, angle_degrees (number 360), axis="Y" (cup/bottle must Y)
   - extrude: profile_name, distance
   - shell: body_name="${last_body}", thickness (number, e.g. 2)
   - create_box: width, height, depth, center_x, center_y, center_z (position in center_x/y/z, mm)
   - create_cylinder: radius, height, center_x, center_y, center_z, axis
   - create_sphere: radius, center_x, center_y, center_z
   - create_entity_relative: entity_type, base_body_name (or ${last_body}), direction ("above"/"below"/...), width, height, depth (box)
3. User says "create at (x,y,z)" -> must pass center_x, center_y, center_z. "directly above" -> create_entity_relative(direction="above").
4. Cup/bottle/bowl: create_sketch(plane="XY") -> sketch_polyline -> revolve(axis="Y") -> get_document_content -> shell.
5. revolve must follow create_sketch + sketch_polyline; axis must be in sketch plane, XY sketch use axis="Y".

[Few-Shot Examples]

Example 1 - Cup:
User: "create a cup"
```json
{
  "goal": "Create cup",
  "reasoning": "Cup is revolved solid, need sketch profile then revolve, then shell",
  "steps": [
    {"tool": "create_sketch", "arguments": {"plane": "XY"}},
    {"tool": "sketch_polyline", "arguments": {"sketch_name": "${last_sketch_name}", "points": [[0,0],[40,0],[40,80],[35,80],[35,5],[0,0]]}},
    {"tool": "revolve", "arguments": {"profile_name": "${last_sketch_name}", "angle_degrees": 360, "axis": "Y"}},
    {"tool": "get_document_content", "arguments": {}},
    {"tool": "shell", "arguments": {"body_name": "${last_body}", "thickness": 2}}
  ]
}
```

Example 2 - Box at position:
User: "create a cube of side 5 at (1,1,1)"
```json
{
  "goal": "Create cube at (1,1,1)",
  "reasoning": "Cube = equal sides, use create_box, center (1,1,1)",
  "steps": [
    {"tool": "create_box", "arguments": {"width": 5, "height": 5, "depth": 5, "center_x": 1, "center_y": 1, "center_z": 1}}
  ]
}
```

Example 3 - Cylinder:
User: "create a cylinder radius 10 height 20"
```json
{
  "goal": "Create cylinder",
  "reasoning": "Simple revolve, use create_cylinder",
  "steps": [
    {"tool": "create_cylinder", "arguments": {"radius": 10, "height": 20}}
  ]
}
```

Example 4 - Create above:
User: "at (0,0,0) create a box 2x1x1, then create a cube of side 3 directly above"
```json
{
  "goal": "Box + cube above",
  "reasoning": "First create_box, then create_entity_relative above",
  "steps": [
    {"tool": "create_box", "arguments": {"width": 2, "height": 1, "depth": 1, "center_x": 0, "center_y": 0, "center_z": 0}},
    {"tool": "create_entity_relative", "arguments": {"entity_type": "box", "base_body_name": "${last_body}", "direction": "above", "width": 3, "height": 3, "depth": 3}}
  ]
}
```
Note: base_body_name uses ${last_body}, auto-filled from prior create_box.

[Sketch Profile for Revolve]
- XY sketch: x=radius, y=height. Cup profile [[0,0],[40,0],[40,80],[35,80],[35,5],[0,0]]
- revolve must axis="Y" (Y in XY plane)

[Available Tools Summary]
{tools_summary}

Output the plan JSON now."""


@dataclass
class PlanStep:
    """Single tool call in plan."""

    tool: str
    arguments: Dict[str, Any]


@dataclass
class CadPlan:
    """CAD workflow plan."""

    goal: str
    reasoning: str
    steps: List[PlanStep]


def _build_tools_summary(function_defs: List[Dict[str, Any]]) -> str:
    """Extract short tool list from schema to reduce tokens."""
    lines = []
    for fn in function_defs:
        name = fn.get("name", "?")
        desc = fn.get("description", "")
        first_line = desc.split("\n")[0].strip() if desc else ""
        lines.append(f"- {name}: {first_line[:80]}")
    return "\n".join(lines) if lines else "No tools available."


def _extract_json_from_text(text: str) -> Optional[str]:
    """Extract JSON from LLM output, supports ```json ... ```."""
    text = text.strip()
    if not text:
        return None

    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()

    start = text.find("{")
    if start >= 0:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
    return None


def parse_plan(raw: str) -> Optional[CadPlan]:
    """Parse LLM JSON output to CadPlan."""
    json_str = _extract_json_from_text(raw)
    if not json_str:
        return None

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        return None

    goal = data.get("goal", "")
    reasoning = data.get("reasoning", "")
    steps_data = data.get("steps", [])

    if not isinstance(steps_data, list):
        return None

    steps: List[PlanStep] = []
    for item in steps_data:
        if isinstance(item, dict):
            tool = item.get("tool") or item.get("name")
            args = item.get("arguments") or item.get("args") or {}
            if tool:
                steps.append(PlanStep(tool=str(tool), arguments=dict(args)))

    return CadPlan(goal=goal, reasoning=reasoning, steps=steps)


def create_plan(
    user_input: str,
    provider: BaseLLMProvider,
    function_defs: List[Dict[str, Any]],
    planning_prompt: Optional[str] = None,
) -> Optional[CadPlan]:
    """
    Call LLM to generate CAD workflow plan.

    Args:
        user_input: User request (e.g. "create a cup")
        provider: LLM provider
        function_defs: Tool schema list (for tools summary)
        planning_prompt: Optional planning system prompt override

    Returns:
        Parsed CadPlan, or None on failure
    """
    tools_summary = _build_tools_summary(function_defs)
    system_content = (planning_prompt or PLANNING_SYSTEM_PROMPT).replace(
        "{tools_summary}", tools_summary
    )

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_input},
    ]

    response = provider.call(messages, [])
    text = provider.render_text(response)

    if not text:
        return None

    return parse_plan(text)
