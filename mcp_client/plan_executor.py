"""
Plan executor.

Executes tool calls in CadPlan order, resolves placeholders and passes prior step results.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from fastmcp import Client as MCPClient

from .planner import CadPlan, PlanStep, _extract_json_from_text
from .logger import get_default_logger

if TYPE_CHECKING:
    from .providers import BaseLLMProvider

logger = get_default_logger()

PLACEHOLDER_LAST_SKETCH = "${last_sketch_name}"
PLACEHOLDER_LAST_BODY = "${last_body}"

# create_sketch return: "Sketch 'Sketch1' created" or "Offset sketch 'Sketch1' created"
SKETCH_NAME_PATTERN = re.compile(r"['\"]([^'\"]+)['\"]\s*created", re.IGNORECASE)

# create_box/cylinder/sphere return: "Entity name: 'Body1'" or "body name: 'Body1'"
BODY_NAME_PATTERN = re.compile(
    r"(?:Entity name|body name)[：:\s]*['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)


def _parse_sketch_name(result: Any) -> Optional[str]:
    """Parse sketch name from create_sketch result."""
    text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
    match = SKETCH_NAME_PATTERN.search(text)
    if match:
        return match.group(1)
    return None


def _parse_body_name_from_create_result(result: Any) -> Optional[str]:
    """Parse body name from create_box/create_cylinder/create_sphere result."""
    text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
    match = BODY_NAME_PATTERN.search(text)
    if match:
        return match.group(1).strip()
    return None


def _parse_last_body_name(result: Any) -> Optional[str]:
    """
    Parse last body name from get_document_content result.
    Format: Body N: ... Name: XXX
    Fallback for "Document content unchanged (bodies: 1, ...)" -> Body1
    """
    if isinstance(result, dict):
        text = result.get("content") or result.get("message") or json.dumps(result, ensure_ascii=False)
    else:
        text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
    bodies_section = text
    if "Sketch count" in text:
        bodies_section = text.split("Sketch count")[0]
    matches = re.findall(r"Name:\s*(.+)", bodies_section)
    if matches:
        return matches[-1].strip()
    match = re.search(r"bodies[:\s]*(\d+)", text, re.IGNORECASE)
    if match:
        return f"Body{match.group(1)}"
    return None


# LLM arg aliases -> tool param names
_ARG_ALIASES: Dict[str, Dict[str, str]] = {
    "sketch_polyline": {"sketch": "sketch_name"},
    "extrude": {"profile": "profile_name", "sketch": "profile_name", "extrude_distance": "distance", "height": "distance"},
    "revolve": {"profile": "profile_name", "sketch": "profile_name", "angle": "angle_degrees"},
    "sweep": {"profile": "profile_name"},
    "shell": {"body": "body_name"},
    "create_cylinder": {"cylinder_height": "height"},
    "create_entity_relative": {
        "parent_body_name": "base_body_name",
        "shape_type": "entity_type",
        "base_entity": "base_body_name",
    },
    "move_body": {
        "body": "body_name",
        "delta_x": "offset_x",
        "delta_y": "offset_y",
        "delta_z": "offset_z",
        "translation_x": "offset_x",
        "translation_y": "offset_y",
        "translation_z": "offset_z",
    },
}


def _normalize_arguments(tool: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize LLM arg aliases to tool param names and values."""
    tool_key = (tool or "").strip().lower()
    aliases = _ARG_ALIASES.get(tool_key, {})
    result = dict(arguments)
    for wrong_name, correct_name in aliases.items():
        if wrong_name in result and correct_name not in result:
            result[correct_name] = result.pop(wrong_name)
    # revolve: normalize angle/angle_degrees; Fusion Y-up, axis="Y" for cup
    if "revolve" in tool_key:
        if "axis" not in result:
            result["axis"] = "Y"
        angle_val = None
        for k in list(result.keys()):
            if k.lower() in ("angle", "angle_degrees", "degrees"):
                angle_val = result.pop(k)
                break
        if angle_val is not None:
            if isinstance(angle_val, str):
                num_str = re.sub(r"[^\d.\-]", "", angle_val) or "360"
                try:
                    result["angle_degrees"] = float(num_str)
                except ValueError:
                    result["angle_degrees"] = 360.0
            elif isinstance(angle_val, (int, float)):
                result["angle_degrees"] = float(angle_val)
            else:
                result["angle_degrees"] = 360.0
    # shell: default thickness=2 when missing; fallback body_name "Body1" when empty
    if "shell" in tool_key:
        if "thickness" not in result:
            result["thickness"] = 2.0
        if not result.get("body_name") and not result.get("body"):
            result["body_name"] = "Body1"
    # sketch_rectangle_corners: point1/point2 -> x1,y1,x2,y2
    if tool_key == "sketch_rectangle_corners":
        if "point1" in result or "point2" in result: 
            pt1 = result.pop("point1", None)
            pt2 = result.pop("point2", None)
            if pt1 is not None and pt2 is not None and "x1" not in result:
                x1, y1 = (float(pt1[0]), float(pt1[1])) if len(pt1) >= 2 else (0.0, 0.0)
                x2, y2 = (float(pt2[0]), float(pt2[1])) if len(pt2) >= 2 else (0.0, 0.0)
                result["x1"], result["y1"], result["x2"], result["y2"] = x1, y1, x2, y2
    # sketch_polyline: auto-close if first!=last (append first point)
    if tool_key == "sketch_polyline" and "points" in result:
        pts = result["points"]
        if isinstance(pts, list) and len(pts) >= 3:
            p0, pn = pts[0], pts[-1]
            if len(p0) >= 2 and len(pn) >= 2:
                if abs(float(p0[0]) - float(pn[0])) > 1e-9 or abs(float(p0[1]) - float(pn[1])) > 1e-9:
                    result["points"] = list(pts) + [list(p0[:2])]
    # move_body: translation/delta array -> offset_x, offset_y, offset_z
    if tool_key == "move_body":
        trans = result.pop("translation", None) or result.pop("delta", None) or result.pop("offset", None)
        if isinstance(trans, (list, tuple)) and len(trans) >= 3 and "offset_x" not in result:
            result["offset_x"] = float(trans[0])
            result["offset_y"] = float(trans[1])
            result["offset_z"] = float(trans[2])
        elif isinstance(trans, dict) and "offset_x" not in result:
            result["offset_x"] = float(trans.get("x", trans.get("offset_x", 0.0)))
            result["offset_y"] = float(trans.get("y", trans.get("offset_y", 0.0)))
            result["offset_z"] = float(trans.get("z", trans.get("offset_z", 0.0)))
    # sketch_line: start_point/end_point -> x1,y1,x2,y2
    if tool_key == "sketch_line":
        if "start_point" in result or "end_point" in result:
            pt1 = result.pop("start_point", None)
            pt2 = result.pop("end_point", None)
            if pt1 is not None and pt2 is not None and "x1" not in result:
                x1, y1 = (float(pt1[0]), float(pt1[1])) if len(pt1) >= 2 else (0.0, 0.0)
                x2, y2 = (float(pt2[0]), float(pt2[1])) if len(pt2) >= 2 else (0.0, 0.0)
                result["x1"], result["y1"], result["x2"], result["y2"] = x1, y1, x2, y2
    # create_box/cylinder/sphere: position/center array -> center_x, center_y, center_z
    if tool_key in ("create_box", "create_cylinder", "create_sphere"):
        pos = result.pop("position", None) or result.pop("center", None)
        if isinstance(pos, (list, tuple)) and len(pos) >= 3 and "center_x" not in result:
            result["center_x"] = float(pos[0])
            result["center_y"] = float(pos[1])
            result["center_z"] = float(pos[2])
        elif isinstance(pos, dict):
            result["center_x"] = float(pos.get("x", pos.get("center_x", 0.0)))
            result["center_y"] = float(pos.get("y", pos.get("center_y", 0.0)))
            result["center_z"] = float(pos.get("z", pos.get("center_z", 0.0)))
    # create_box: cube "side 5" -> width=height=depth=5; single dim -> cube
    if tool_key == "create_box":
        for k in ("size", "length"):
            if k in result:
                v = result.pop(k)
                if isinstance(v, (int, float)) and v > 0:
                    have = sum(1 for x in ("width", "height", "depth") if x in result)
                    if have == 0:
                        result["width"] = result["height"] = result["depth"] = float(v)
                    elif have < 2 and "width" not in result:
                        result["width"] = float(v)
                break
        # If single dim (e.g. width=5) and cube intent, fill others
        if "width" in result and "height" not in result and "depth" not in result:
            w = result["width"]
            if isinstance(w, (int, float)) and w > 0:
                result["height"] = result["depth"] = float(w)
    # create_entity_relative: cube "side 3" -> width=height=depth=3; default direction="above"
    if tool_key == "create_entity_relative":
        if "direction" not in result:
            result["direction"] = "above"
        for k in ("size", "length"):
            if k in result:
                v = result.pop(k)
                if isinstance(v, (int, float)) and v > 0:
                    have = sum(1 for x in ("width", "height", "depth") if x in result)
                    if have == 0:
                        result["width"] = result["height"] = result["depth"] = float(v)
                break
        if "width" in result and "height" not in result and "depth" not in result:
            w = result["width"]
            if isinstance(w, (int, float)) and w > 0:
                result["height"] = result["depth"] = float(w)
        # Cylinder: when entity_type is cylinder, height -> cylinder_height (LLM may use "height" for 高/高度)
        if (result.get("entity_type") == "cylinder" or result.get("shape_type") == "cylinder"):
            if "height" in result and "cylinder_height" not in result and result.get("height") is not None:
                result["cylinder_height"] = result.pop("height")
    return result


def _resolve_placeholders(
    arguments: Dict[str, Any],
    context: Dict[str, str],
) -> Dict[str, Any]:
    """Replace placeholders in arguments with context values."""

    def _replace(s: str) -> str:
        s = s.replace(PLACEHOLDER_LAST_SKETCH, context.get("last_sketch_name", ""))
        s = s.replace(PLACEHOLDER_LAST_BODY, context.get("last_body", ""))
        return s

    def _recurse(val: Any) -> Any:
        if isinstance(val, str):
            return _replace(val)
        if isinstance(val, dict):
            return {k: _recurse(v) for k, v in val.items()}
        if isinstance(val, list):
            return [_recurse(v) for v in val]
        return val

    return _recurse(arguments)


@dataclass
class StepResult:
    """Single step execution result."""

    step_index: int
    tool: str
    arguments: Dict[str, Any]
    success: bool
    result: Any
    error: Optional[str] = None


@dataclass
class ExecutionResult:
    """Execution summary."""

    plan: CadPlan
    steps_completed: int
    results: List[StepResult] = field(default_factory=list)
    success: bool = False
    message: str = ""

    @property
    def last_result(self) -> Any:
        """Last step result."""
        if self.results:
            return self.results[-1].result
        return None


RECOVERY_SYSTEM_PROMPT = """You are a CAD parameter corrector. A tool call failed due to invalid or missing parameters.

Given: tool name, original arguments, error message, and task goal.
Output ONLY a JSON object with the corrected arguments. Use exact parameter names expected by the tool.
Example output: {"radius": 0.5, "cylinder_height": 0.8, "base_body_name": "Body1"}
No explanations, no markdown, just the JSON object."""


def _ask_llm_to_fix_step(
    provider: "BaseLLMProvider",
    goal: str,
    tool: str,
    args: Dict[str, Any],
    error: str,
) -> Optional[Dict[str, Any]]:
    """
    Ask LLM to fix failed step arguments. Returns corrected args or None.
    """
    user_content = (
        f"Goal: {goal}\n"
        f"Tool: {tool}\n"
        f"Original arguments: {json.dumps(args, ensure_ascii=False)}\n"
        f"Error: {error}\n\n"
        "Output the corrected arguments as JSON only."
    )
    messages = [
        {"role": "system", "content": RECOVERY_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
    try:
        response = provider.call(messages, [])
        text = provider.render_text(response) or ""
        json_str = _extract_json_from_text(text)
        if not json_str:
            return None
        data = json.loads(json_str)
        if isinstance(data, dict):
            return data.get("arguments", data)
        return None
    except Exception as e:
        logger.warning(f"[PlanRecovery] LLM fix failed: {e}")
        return None


async def execute_plan(
    plan: CadPlan,
    mcp_client: MCPClient,
    provider: Optional["BaseLLMProvider"] = None,
    max_recovery_retries: int = 2,
) -> ExecutionResult:
    """
    Execute tool calls in plan order. plan: CadPlan. mcp_client: MCP client (connected or in async with).
    """
    context: Dict[str, str] = {}
    results: List[StepResult] = []

    async def _invoke(tool: str, args: Dict[str, Any]) -> Any:
        result = await mcp_client.call_tool(tool, args)
        return getattr(result, "data", None) or getattr(result, "content", None) or result

    for i, step in enumerate(plan.steps):
        tool = step.tool
        args = _resolve_placeholders(step.arguments.copy(), context)
        args = _normalize_arguments(tool, args)
        # Force use of actual sketch name from create_sketch
        if context.get("last_sketch_name"):
            if tool == "sketch_polyline" and "sketch_name" in args:
                args["sketch_name"] = context["last_sketch_name"]
            elif tool in ("sketch_rectangle_corners", "sketch_rectangle_center", "sketch_circle", "sketch_arc_3pt") and "sketch_name" in args:
                args["sketch_name"] = context["last_sketch_name"]
            elif tool == "revolve" and "profile_name" in args:
                args["profile_name"] = context["last_sketch_name"]
        # create_entity_relative: use last_body from context when base_body_name empty
        if tool == "create_entity_relative" and context.get("last_body"):
            if not args.get("base_body_name"):
                args["base_body_name"] = context["last_body"]
        # If plan has revolve, create_sketch must use plane="XY"
        if tool == "create_sketch" and any(s.tool == "revolve" for s in plan.steps):
            args["plane"] = "XY"

        logger.info(f"[PlanExec] Step {i + 1}/{len(plan.steps)}: {tool} {json.dumps(args, ensure_ascii=False)[:200]}")

        try:
            raw = await _invoke(tool, args)

            # Normalize to serializable
            if hasattr(raw, "__dict__") and not isinstance(raw, (str, dict, list)):
                result = str(raw)
            elif isinstance(raw, (dict, list, str, int, float, bool)) or raw is None:
                result = raw
            else:
                result = str(raw)

            results.append(
                StepResult(
                    step_index=i + 1,
                    tool=tool,
                    arguments=args,
                    success=True,
                    result=result,
                )
            )

            # Update context for placeholders
            if tool == "create_sketch":
                name = _parse_sketch_name(result)
                if name:
                    context["last_sketch_name"] = name
                    logger.debug(f"[PlanExec] context.last_sketch_name = {name}")
            elif tool == "get_document_content":
                name = _parse_last_body_name(result)
                if name:
                    context["last_body"] = name
                    logger.debug(f"[PlanExec] context.last_body = {name}")
            elif tool in ("create_box", "create_cylinder", "create_sphere"):
                name = _parse_body_name_from_create_result(result)
                if name:
                    context["last_body"] = name
                    logger.debug(f"[PlanExec] context.last_body = {name} (from {tool})")

        except Exception as exc:
            err_msg = str(exc)
            logger.error(f"[PlanExec] Step {i + 1} failed: {tool} - {err_msg}", exc_info=True)
            recovered = False
            last_error = err_msg
            if provider and max_recovery_retries > 0:
                for attempt in range(max_recovery_retries):
                    fixed_args = await asyncio.to_thread(
                        _ask_llm_to_fix_step,
                        provider,
                        plan.goal,
                        tool,
                        args,
                        last_error,
                    )
                    if not fixed_args or not isinstance(fixed_args, dict):
                        logger.warning(f"[PlanRecovery] Attempt {attempt + 1}: no valid fixed args")
                        break
                    fixed_args = _resolve_placeholders(fixed_args, context)
                    fixed_args = _normalize_arguments(tool, fixed_args)
                    if context.get("last_sketch_name"):
                        if tool == "sketch_polyline" and "sketch_name" in fixed_args:
                            fixed_args["sketch_name"] = context["last_sketch_name"]
                        elif tool in ("sketch_rectangle_corners", "sketch_rectangle_center", "sketch_circle", "sketch_arc_3pt") and "sketch_name" in fixed_args:
                            fixed_args["sketch_name"] = context["last_sketch_name"]
                        elif tool == "revolve" and "profile_name" in fixed_args:
                            fixed_args["profile_name"] = context["last_sketch_name"]
                    if tool == "create_entity_relative" and context.get("last_body"):
                        if not fixed_args.get("base_body_name"):
                            fixed_args["base_body_name"] = context["last_body"]
                    if tool == "create_sketch" and any(s.tool == "revolve" for s in plan.steps):
                        fixed_args["plane"] = "XY"
                    logger.info(f"[PlanRecovery] Attempt {attempt + 1}: {tool} {json.dumps(fixed_args, ensure_ascii=False)[:200]}")
                    try:
                        raw = await _invoke(tool, fixed_args)
                        if hasattr(raw, "__dict__") and not isinstance(raw, (str, dict, list)):
                            result = str(raw)
                        elif isinstance(raw, (dict, list, str, int, float, bool)) or raw is None:
                            result = raw
                        else:
                            result = str(raw)
                        results.append(
                            StepResult(
                                step_index=i + 1,
                                tool=tool,
                                arguments=fixed_args,
                                success=True,
                                result=result,
                            )
                        )
                        if tool == "create_sketch":
                            name = _parse_sketch_name(result)
                            if name:
                                context["last_sketch_name"] = name
                        elif tool == "get_document_content":
                            name = _parse_last_body_name(result)
                            if name:
                                context["last_body"] = name
                        elif tool in ("create_box", "create_cylinder", "create_sphere"):
                            name = _parse_body_name_from_create_result(result)
                            if name:
                                context["last_body"] = name
                        recovered = True
                        logger.info(f"[PlanRecovery] Step {i + 1} recovered successfully")
                        break
                    except Exception as retry_exc:
                        last_error = str(retry_exc)
                        logger.warning(f"[PlanRecovery] Attempt {attempt + 1} retry failed: {last_error}")
            if not recovered:
                results.append(
                    StepResult(
                        step_index=i + 1,
                        tool=tool,
                        arguments=args,
                        success=False,
                        result=None,
                        error=err_msg,
                    )
                )
                return ExecutionResult(
                    plan=plan,
                    steps_completed=i,
                    results=results,
                    success=False,
                    message=f"Step {i + 1} ({tool}) failed: {err_msg}",
                )

    return ExecutionResult(
        plan=plan,
        steps_completed=len(plan.steps),
        results=results,
        success=True,
        message=f"Plan completed ({len(plan.steps)} steps)",
    )
