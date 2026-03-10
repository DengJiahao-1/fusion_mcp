from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from fastmcp import Client as MCPClient

from .plan_executor import _normalize_arguments
from .providers import BaseLLMProvider, LLMResponse, ToolCall
from .rag import RAGRetriever
from .tooling import stringify
from .logger import get_default_logger

logger = get_default_logger()

# Keywords indicating user wants create_entity_relative (above/below/next to entity)
_RELATIVE_POSITION_KEYWORDS = (
    "above", "above the", "below", "below the", "next to", "left of", "right of",
    "in front of", "behind", "relative to", "on top of", "under",
)


def _user_wants_relative_placement(conversation: "ConversationState") -> bool:
    """Check if recent user message contains relative placement description."""
    for msg in reversed(conversation.messages):
        if msg.get("role") == "user":
            content = (msg.get("content") or "").lower()
            return any(kw in content for kw in _RELATIVE_POSITION_KEYWORDS)
    return False


@dataclass
class ConversationState:
    """Encapsulates conversation context."""

    messages: List[Dict[str, Any]]

    def append(self, message: Dict[str, Any]) -> None:
        self.messages.append(message)


class ConversationEngine:
    """Manages LLM interaction and tool-calling flow."""

    def __init__(
        self,
        provider: BaseLLMProvider,
        mcp_client: MCPClient,
        max_tool_iterations: int,
        rag_retriever: Optional[RAGRetriever] = None,
    ) -> None:
        self.provider = provider
        self.mcp_client = mcp_client
        self.max_tool_iterations = max_tool_iterations
        self.rag_retriever = rag_retriever

    async def process_turn(
        self,
        conversation: ConversationState,
        function_defs: Sequence[Dict[str, Any]],
    ) -> LLMResponse:
        """Run one LLM turn, loop through tool calls if needed, return final response."""
        seen_signatures: set[str] = set()
        seen_tool_names: set[str] = set()

        has_rag_context = any(
            msg.get("role") == "system" and "Retrieved context" in str(msg.get("content", ""))
            for msg in conversation.messages
        )

        if self.rag_retriever and conversation.messages and not has_rag_context:
            last_user_message = None
            for msg in reversed(conversation.messages):
                if msg.get("role") == "user":
                    last_user_message = msg.get("content", "")
                    break

            if last_user_message:
                try:
                    results = self.rag_retriever.retrieve(
                        query=last_user_message,
                        top_k=5,
                    )
                    if results:
                        context = self.rag_retriever.format_context(results)
                        if context:
                            rag_context_msg = {
                                "role": "system",
                                "content": f"Retrieved context:\n{context}\n\nAnswer based on the above context.",
                            }
                            messages_with_context = []
                            system_added = False
                            for msg in conversation.messages:
                                if msg.get("role") == "system" and not system_added:
                                    messages_with_context.append(msg)
                                    messages_with_context.append(rag_context_msg)
                                    system_added = True
                                else:
                                    messages_with_context.append(msg)
                            if not system_added:
                                # If no system msg, add at start
                                messages_with_context.insert(0, rag_context_msg)
                            conversation.messages = messages_with_context
                            logger.info(f"[RAG] Retrieved {len(results)} docs")
                except Exception as e:
                    logger.error(f"[RAG] Retrieve error: {e}", exc_info=True)

        for _ in range(self.max_tool_iterations):
            response = self.provider.call(conversation.messages, list(function_defs))
            tool_calls = self.provider.extract_tool_calls(response)

            if not tool_calls:
                return response

            # Append assistant message with tool_calls to history
            assistant_message, tool_call_id_map = self._build_assistant_message_with_tool_calls(response, tool_calls)
            conversation.append(assistant_message)

            for call in tool_calls:
                # Get corresponding tool_call_id
                tool_call_id = tool_call_id_map.get(id(call), None)
                await self._handle_tool_call(conversation, call, seen_signatures, seen_tool_names, tool_call_id)

        raise RuntimeError(
            f"Tool call limit exceeded ({self.max_tool_iterations}). Possible loop."
        )

    def _convert_tool_call_to_dict(self, tool_call: Any) -> Dict[str, Any]:
        """Convert tool_call to dict (serializable). Ollama needs object args; OpenAI may use string."""
        if isinstance(tool_call, dict):
            # If dict, check if args format needs conversion
            tool_call = tool_call.copy()
            if "function" in tool_call and isinstance(tool_call["function"], dict):
                function = tool_call["function"].copy()
                arguments = function.get("arguments")
                
                # If args is str, parse to object (for Ollama)
                if isinstance(arguments, str) and self.provider.settings.provider == "ollama":
                    try:
                        arguments = json.loads(arguments)
                        function["arguments"] = arguments
                        tool_call["function"] = function
                    except (json.JSONDecodeError, TypeError):
                        # Parse failed, keep as is
                        pass
                
            return tool_call
        
        # If object, extract attributes
        result = {
            "id": getattr(tool_call, "id", None),
            "type": getattr(tool_call, "type", "function"),
        }
        
        # Extract function info
        function = getattr(tool_call, "function", None)
        if function:
            if isinstance(function, dict):
                result["function"] = function.copy()
                # For Ollama, ensure args is object
                if self.provider.settings.provider == "ollama":
                    arguments = result["function"].get("arguments")
                    if isinstance(arguments, str):
                        try:
                            result["function"]["arguments"] = json.loads(arguments)
                        except (json.JSONDecodeError, TypeError):
                            # Parse failed, use empty dict
                            result["function"]["arguments"] = {}
            else:
                arguments = getattr(function, "arguments", "")
                # For Ollama, if args is str, try parse
                if self.provider.settings.provider == "ollama" and isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except (json.JSONDecodeError, TypeError):
                        arguments = {}
                
                result["function"] = {
                    "name": getattr(function, "name", ""),
                    "arguments": arguments,
                }
        else:
            result["function"] = {}
        
        return result

    def _build_assistant_message_with_tool_calls(
        self, response: LLMResponse, tool_calls: List[ToolCall]
    ) -> tuple[Dict[str, Any], Dict[int, str]]:
        """Build assistant message with tool_calls. Returns (msg, tool_call_id_map)."""
        # Extract raw tool_calls (with ID) from response
        raw = response.payload
        tool_calls_payload = []
        tool_call_id_map: Dict[int, str] = {}
        
        # Ollama format: {"message": {"tool_calls": [...]}}
        is_ollama = self.provider.settings.provider == "ollama"
        if is_ollama and isinstance(raw, dict):
            message = raw.get("message", {})
            raw_tool_calls = message.get("tool_calls", [])
            if raw_tool_calls:
                for raw_call in raw_tool_calls:
                    tool_call_dict = self._convert_tool_call_to_dict(raw_call)
                    tool_calls_payload.append(tool_call_dict)
                    
                    # Build mapping
                    call_id = tool_call_dict.get("id")
                    if call_id:
                        function_name = tool_call_dict.get("function", {}).get("name") if isinstance(tool_call_dict.get("function"), dict) else None
                        if function_name:
                            for call in tool_calls:
                                if call.name == function_name and id(call) not in tool_call_id_map:
                                    tool_call_id_map[id(call)] = call_id
                                    break
        
        # Try Responses API format
        if not tool_calls_payload:
            for block in getattr(raw, "output", []):
                if getattr(block, "type", None) != "message":
                    continue
                for item in block.content:
                    if item.get("type") != "tool_call":
                        continue
                    tool_call = item.get("tool_call", {})
                    if tool_call:
                        # Convert to dict
                        tool_call_dict = self._convert_tool_call_to_dict(tool_call)
                        tool_calls_payload.append(tool_call_dict)
                        # Match to ToolCall
                        tool_call_id = tool_call_dict.get("id")
                        if tool_call_id:
                            # Match by function name
                            function_name = tool_call_dict.get("function", {}).get("name") if isinstance(tool_call_dict.get("function"), dict) else None
                            if not function_name and tool_call_dict.get("function"):
                                func = tool_call_dict.get("function")
                                function_name = getattr(func, "name", None) if hasattr(func, "name") else None
                            
                            if function_name:
                                for call in tool_calls:
                                    if call.name == function_name:
                                        tool_call_id_map[id(call)] = tool_call_id
                                        break
                        break
                if tool_calls_payload:
                    break
        
        # If Responses API failed, try Chat Completions format
        if not tool_calls_payload:
            choices = getattr(raw, "choices", None) or []
            for choice in choices:
                message = None
                if isinstance(choice, dict):
                    message = choice.get("message")
                else:
                    message = getattr(choice, "message", None)
                if message:
                    raw_tool_calls = None
                    if isinstance(message, dict):
                        raw_tool_calls = message.get("tool_calls") or []
                    else:
                        raw_tool_calls = getattr(message, "tool_calls", None) or []
                    if raw_tool_calls:
                        # Convert to dict
                        for raw_call in raw_tool_calls:
                            tool_call_dict = self._convert_tool_call_to_dict(raw_call)
                            tool_calls_payload.append(tool_call_dict)
                            
                            # Build mapping
                            call_id = tool_call_dict.get("id")
                            if call_id:
                                # Match by function name
                                function_name = tool_call_dict.get("function", {}).get("name") if isinstance(tool_call_dict.get("function"), dict) else None
                                if not function_name and tool_call_dict.get("function"):
                                    func = tool_call_dict.get("function")
                                    function_name = getattr(func, "name", None) if hasattr(func, "name") else None
                                
                                if function_name:
                                    for call in tool_calls:
                                        if call.name == function_name and id(call) not in tool_call_id_map:
                                            tool_call_id_map[id(call)] = call_id
                                            break
                        break
        
        # If still not found, build manually from extracted tool_calls
        if not tool_calls_payload:
            # Check provider for args format: Ollama=object, OpenAI=string
            is_ollama = self.provider.settings.provider == "ollama"
            
            for idx, call in enumerate(tool_calls):
                call_id = f"call_{call.name}_{idx}_{id(call)}"
                
                # Set args format by provider
                if is_ollama:
                    # Ollama needs object
                    arguments = call.arguments if isinstance(call.arguments, dict) else {}
                else:
                    # OpenAI needs string
                    arguments = json.dumps(call.arguments, ensure_ascii=False) if isinstance(call.arguments, dict) else str(call.arguments)
                
                tool_calls_payload.append({
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": arguments
                    }
                })
                tool_call_id_map[id(call)] = call_id
        
        message = {
            "role": "assistant",
            "tool_calls": tool_calls_payload
        }
        
        # If text content, include it
        text_content = self.provider.render_text(response)
        if text_content and text_content != "[No text reply]":
            message["content"] = text_content
        else:
            message["content"] = None
        
        return message, tool_call_id_map

    async def _handle_tool_call(
        self,
        conversation: ConversationState,
        call: ToolCall,
        seen_signatures: set[str],
        seen_tool_names: set[str],
        tool_call_id: Optional[str] = None,
    ) -> None:
        signature = call.signature
        
            # Check for identical call (same tool + args)
        if signature in seen_signatures:
            if call.name == "get_document_content":
                warning_msg = (
                    f"Tool {call.name} already called, document unchanged. "
                    f"Use previous entity info. Use entity names for create_entity_relative."
                )
            else:
                warning_msg = f"Tool {call.name} already called with same args. Reusing previous result."
            logger.warning(f"[ToolSkip] {warning_msg}")
            tool_msg = {
                "role": "tool",
                "name": call.name,
                "content": json.dumps({"warning": warning_msg}, ensure_ascii=False),
            }
            if tool_call_id:
                tool_msg["tool_call_id"] = tool_call_id
            conversation.append(tool_msg)
            return
        
        # If create_box/cylinder/sphere already succeeded, block create_sketch/extrude; allow create_entity_relative if user intent matches
        has_created_entity = "create_box" in seen_tool_names or "create_cylinder" in seen_tool_names or "create_sphere" in seen_tool_names

        if has_created_entity:
            if call.name in ["create_sketch", "extrude", "revolve", "sweep", "loft"]:
                warning_msg = (
                    f"create_box/create_cylinder/create_sphere already succeeded. "
                    f"These create bodies directly. Return success. Do not call {call.name}."
                )
                logger.warning(f"[ToolSkip] {warning_msg}")
                tool_msg = {
                    "role": "tool",
                    "name": call.name,
                    "content": json.dumps({"warning": warning_msg}, ensure_ascii=False),
                }
                if tool_call_id:
                    tool_msg["tool_call_id"] = tool_call_id
                conversation.append(tool_msg)
                return
            elif call.name == "create_entity_relative":
                # If user mentioned above/below/next to/relative, allow create_entity_relative
                if _user_wants_relative_placement(conversation):
                    pass  # Don't skip, continue
                else:
                    warning_msg = (
                        f"create_box/create_cylinder/create_sphere already succeeded. "
                        f"create_entity_relative is only for creating above/below/next to existing body. "
                        f"For simple box, create_box is enough. Return success message."
                    )
                    logger.warning(f"[ToolSkip] {warning_msg}")
                    tool_msg = {
                        "role": "tool",
                        "name": call.name,
                        "content": json.dumps({"warning": warning_msg}, ensure_ascii=False),
                    }
                    if tool_call_id:
                        tool_msg["tool_call_id"] = tool_call_id
                    conversation.append(tool_msg)
                    return
        
        # Tools support repeated calls (different args); skip only when tool+args identical
        seen_signatures.add(signature)

        if call.parse_error:
            logger.warning(
                f"[ToolCall] {call.name} argument parse issue: {call.parse_error}. Using empty dict."
            )

        # Normalize LLM output (e.g. start_point/end_point -> x1,y1,x2,y2)
        args = _normalize_arguments(call.name, dict(call.arguments or {}))

        logger.info(f"[ToolCall] {call.name} -> {stringify(args)}")

        try:
            tool_result = await self._invoke_tool(call.name, args)
        except Exception as exc:
            err_str = str(exc)
            error_payload = {"error": err_str}
            # If error says body not found and lists available names, retry with first available
            retry_name = self._extract_suggested_body_name(err_str)
            if retry_name and "body_name" in args:
                body_tools = {"modify_body_dimensions", "shell", "rotate_body", "move_body", "chamfer", "fillet", "delete_body"}
                if call.name in body_tools and retry_name != args.get("body_name"):
                    retry_args = {**args, "body_name": retry_name}
                    logger.info(f"[ToolRetry] {call.name} retry with body_name={retry_name}")
                    try:
                        tool_result = await self._invoke_tool(call.name, retry_args)
                        error_payload = None
                    except Exception as retry_exc:
                        error_payload = {"error": str(retry_exc)}
                        logger.error(f"[ToolError] {call.name} retry failed: {retry_exc}")
            # If create_entity_relative cylinder error: missing radius/cylinder_height, try height -> cylinder_height
            if error_payload and call.name == "create_entity_relative":
                if ("radius" in err_str and "cylinder_height" in err_str) or "需要提供" in err_str:
                    retry_args = None
                    if args.get("height") is not None and args.get("cylinder_height") is None:
                        retry_args = {**args, "cylinder_height": args["height"]}
                    if args.get("radius") is None and args.get("diameter") is not None:
                        try:
                            retry_args = retry_args or dict(args)
                            retry_args["radius"] = float(args["diameter"]) / 2.0
                            retry_args.pop("diameter", None)
                        except (TypeError, ValueError):
                            pass
                    if retry_args:
                        logger.info(f"[ToolRetry] {call.name} retry with cylinder params fix: {retry_args}")
                        try:
                            tool_result = await self._invoke_tool(call.name, retry_args)
                            error_payload = None
                        except Exception as retry_exc:
                            error_payload = {"error": str(retry_exc)}
                            logger.error(f"[ToolError] {call.name} cylinder retry failed: {retry_exc}")
            if error_payload:
                logger.error(f"[ToolError] {call.name}: {err_str}", exc_info=True)
            content = json.dumps(error_payload, ensure_ascii=False) if error_payload else json.dumps(tool_result, ensure_ascii=False)
            tool_msg = {
                "role": "tool",
                "name": call.name,
                "content": content,
            }
            if tool_call_id:
                tool_msg["tool_call_id"] = tool_call_id
            conversation.append(tool_msg)
            if not error_payload:
                seen_tool_names.add(call.name)
        else:
            # Mark as called only on success to avoid duplicate success
            seen_tool_names.add(call.name)
            logger.debug(f"[ToolResult] {call.name}: {stringify(tool_result)}")
            tool_msg = {
                "role": "tool",
                "name": call.name,
                "content": json.dumps(tool_result, ensure_ascii=False),
            }
            if tool_call_id:
                tool_msg["tool_call_id"] = tool_call_id
            conversation.append(tool_msg)

    def _extract_suggested_body_name(self, error_msg: str) -> Optional[str]:
        """Parse suggested body name from error, e.g. 'Available body names: Body1' -> Body1"""
        has_available = "Available body names" in error_msg
        has_not_found = "not found" in error_msg or "named" in error_msg
        if not has_available or not has_not_found:
            return None
        match = re.search(r"Available body names[：:]\s*([^\s.\n]+)", error_msg)
        if match:
            names_str = match.group(1).strip()
            first = names_str.replace("，", ",").split(",")[0].strip()
            if first and first.startswith("Body"):
                return first
        return None

    async def _invoke_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        async def _call() -> Any:
            result = await self.mcp_client.call_tool(name, arguments)
            return result.data or result.content

        if self.mcp_client.is_connected():
            return await _call()

        async with self.mcp_client:
            return await _call()


