from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx
import os
import torch

from .config import ClientSettings
from .tooling import make_json_safe, stringify


@dataclass(frozen=True)
class LLMResponse:
    """Unified LLM response wrapper."""

    provider: str
    payload: Any


@dataclass(frozen=True)
class ToolCall:
    """MCP tool call from LLM."""

    name: str
    arguments: Dict[str, Any]
    raw_arguments: Any
    parse_error: Optional[str] = None

    @property
    def signature(self) -> str:
        """Generate call signature for dedup."""
        return json.dumps(
            {"name": self.name, "arguments": self.arguments},
            ensure_ascii=False,
            sort_keys=True,
        )


class BaseLLMProvider(ABC):
    """Unified LLM interface for multiple providers."""

    def __init__(self, settings: ClientSettings):
        self.settings = settings

    @abstractmethod
    def call(self, messages: List[Dict[str, Any]], functions: List[Dict[str, Any]]) -> LLMResponse:
        ...

    @abstractmethod
    def extract_tool_calls(self, response: LLMResponse) -> List[ToolCall]:
        ...

    @abstractmethod
    def render_text(self, response: LLMResponse) -> str:
        ...


def _parse_json_arguments(raw_arguments: Any) -> tuple[Dict[str, Any], Optional[str]]:
    if isinstance(raw_arguments, str):
        try:
            parsed = json.loads(raw_arguments or "{}")
            if isinstance(parsed, dict):
                return parsed, None
            return {}, "Parsed args not dict, using empty."
        except json.JSONDecodeError as exc:
            return {}, f"Args parse failed: {exc}"
    if isinstance(raw_arguments, dict):
        return raw_arguments, None
    return {}, "Unknown args format, using empty dict."


class OpenAIProvider(BaseLLMProvider):
    """OpenAI Responses API wrapper."""

    def call(
        self,
        messages: List[Dict[str, Any]],
        functions: List[Dict[str, Any]],
    ) -> LLMResponse:
        def build_tools_payload() -> List[Dict[str, Any]]:
            return [
                {
                    "type": "function",
                    "function": {
                        "name": fn["name"],
                        "description": fn.get("description", ""),
                        "parameters": make_json_safe(fn.get("parameters", {})),
                    },
                }
                for fn in functions
            ]

        try:
            from openai import OpenAI  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("Missing openai. Run `pip install openai`.") from exc

        api_key = self.settings.openai_api_key
        if not api_key:
            raise RuntimeError("Set OPENAI_API_KEY in environment.")


        # Custom base_url for Qwen etc.
        client_kwargs: Dict[str, Any] = {"api_key": api_key}
        if self.settings.openai_base_url:
            client_kwargs["base_url"] = self.settings.openai_base_url
        timeout = float(os.getenv("OPENAI_TIMEOUT", "300"))
        client_kwargs["timeout"] = timeout

        client = OpenAI(**client_kwargs)
        tools_payload = build_tools_payload()

        response_kwargs: Dict[str, Any] = {
            "model": self.settings.openai_model,
            "input": messages,
            "temperature": self.settings.temperature,
        }
        if tools_payload:
            response_kwargs["tools"] = tools_payload
        if getattr(self.settings, "openai_max_tokens", None) is not None:
            response_kwargs["max_output_tokens"] = self.settings.openai_max_tokens
        if getattr(self.settings, "openai_top_p", None) is not None:
            response_kwargs["top_p"] = self.settings.openai_top_p

        try:
            response = self._call_with_retry(
                client.responses.create,
                response_kwargs,
            )
        except Exception as exc:
            if not self._is_not_found_error(exc):
                raise

            # 回退到 Chat Completions 兼容接口（部分代理或旧版服务仅支持该端点）
            chat_kwargs: Dict[str, Any] = {
                "model": self.settings.openai_model,
                "messages": messages,
                "temperature": self.settings.temperature,
            }
            if tools_payload:
                chat_kwargs["tools"] = tools_payload
            if getattr(self.settings, "openai_max_tokens", None) is not None:
                chat_kwargs["max_tokens"] = self.settings.openai_max_tokens
            if getattr(self.settings, "openai_top_p", None) is not None:
                chat_kwargs["top_p"] = self.settings.openai_top_p

            response = self._call_with_retry(
                client.chat.completions.create,
                chat_kwargs,
            )

        return LLMResponse(provider="openai", payload=response)

    def extract_tool_calls(self, response: LLMResponse) -> List[ToolCall]:
        tool_calls: List[ToolCall] = []
        raw = response.payload
        for block in getattr(raw, "output", []):
            if getattr(block, "type", None) != "message":
                continue
            for item in block.content:
                if item.get("type") != "tool_call":
                    continue
                tool_call = item["tool_call"]
                function = tool_call.get("function") or {}
                name = function.get("name")
                if not name:
                    continue
                raw_arguments = function.get("arguments", {})
                arguments, error = _parse_json_arguments(raw_arguments)
                tool_calls.append(
                    ToolCall(
                        name=name,
                        arguments=arguments,
                        raw_arguments=raw_arguments,
                        parse_error=error,
                    )
                )
        if tool_calls:
            return tool_calls

        # Chat Completions 响应
        choices = getattr(raw, "choices", None) or []
        for choice in choices:
            message = None
            if isinstance(choice, dict):
                message = choice.get("message")
            else:
                message = getattr(choice, "message", None)
            if not message:
                continue

            raw_tool_calls = None
            if isinstance(message, dict):
                raw_tool_calls = message.get("tool_calls") or []
            else:
                raw_tool_calls = getattr(message, "tool_calls", None) or []

            for call in raw_tool_calls:
                function = None
                if isinstance(call, dict):
                    function = call.get("function") or {}
                else:
                    function = getattr(call, "function", None) or {}

                name = None
                if isinstance(function, dict):
                    name = function.get("name")
                else:
                    name = getattr(function, "name", None)
                if not name:
                    continue

                raw_arguments: Any
                if isinstance(function, dict):
                    raw_arguments = function.get("arguments", {})
                else:
                    raw_arguments = getattr(function, "arguments", {})

                arguments, error = _parse_json_arguments(raw_arguments)
                tool_calls.append(
                    ToolCall(
                        name=name,
                        arguments=arguments,
                        raw_arguments=raw_arguments,
                        parse_error=error,
                    )
                )
        return tool_calls

    def render_text(self, response: LLMResponse) -> str:
        text = getattr(response.payload, "output_text", None)
        if text:
            return str(text).strip()

        # Chat Completions 响应
        choices = getattr(response.payload, "choices", None)
        if choices:
            for choice in choices:
                message = getattr(choice, "message", None)
                if not message:
                    continue
                content = getattr(message, "content", None)
                extracted = self._extract_message_text(content)
                if extracted:
                    return extracted
                
                # 检查是否有工具调用
                tool_calls = getattr(message, "tool_calls", None)
                if tool_calls:
                    # 如果有工具调用但内容为空，说明模型只进行了工具调用
                    return ""

        # 如果没有找到任何文本内容，返回空字符串而不是整个对象
        # main.py 中会处理空字符串并显示 "[无文本回复]"
        return ""

    @staticmethod
    def _is_not_found_error(exc: Exception) -> bool:
        status_code = getattr(exc, "status_code", None)
        if status_code == 404:
            return True

        response = getattr(exc, "response", None)
        if response is not None and getattr(response, "status_code", None) == 404:
            return True

        message = str(exc).lower()
        return "404" in message and ("not found" in message or "page not found" in message)

    @staticmethod
    def _is_retryable_error(exc: Exception) -> bool:
        if isinstance(exc, httpx.HTTPError):
            return True
        name = exc.__class__.__name__.lower()
        if "apiconnectionerror" in name:
            return True
        if "timeout" in name or "readerror" in name:
            return True
        return False

    def _call_with_retry(self, func: Any, kwargs: Dict[str, Any]) -> Any:
        max_retries = int(os.getenv("OPENAI_RETRIES", "3"))
        backoff = float(os.getenv("OPENAI_RETRY_BACKOFF", "0.5"))
        last_exc: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                return func(**kwargs)
            except Exception as exc:
                last_exc = exc
                if not self._is_retryable_error(exc) or attempt == max_retries - 1:
                    raise
                time.sleep(backoff * (2 ** attempt))
        if last_exc:
            raise last_exc
            raise RuntimeError("OpenAI call failed, no exception captured.")

    @staticmethod
    def _extract_message_text(content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content.strip()

        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                text = ""
                if isinstance(item, dict):
                    text = str(item.get("text", "") or "")
                else:
                    text = str(getattr(item, "text", "") or "")
                if text:
                    parts.append(text)
            return "".join(parts).strip()

        return str(content).strip()


class OllamaProvider(BaseLLMProvider):
    """Ollama Chat API wrapper."""

    def call(
        self,
        messages: List[Dict[str, Any]],
        functions: List[Dict[str, Any]],
    ) -> LLMResponse:
        tools_payload = [
            {
                "type": "function",
                "function": {
                    "name": fn["name"],
                    "description": fn.get("description", ""),
                    "parameters": make_json_safe(fn.get("parameters", {})),
                },
            }
            for fn in functions
        ]

        payload = {
            "model": self.settings.ollama_model,
            "messages": messages,
            "tools": tools_payload,
            "stream": False,
        }

        base_url = self.settings.ollama_base_url.rstrip("/")
        try:
            response = httpx.post(
                f"{base_url}/api/chat",
                json=payload,
                timeout=120.0,
            )
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Cannot connect to Ollama {base_url}: {exc}") from exc

        if response.status_code != 200:
            raise RuntimeError(
                f"Ollama error {response.status_code}: {response.text}"
            )

        return LLMResponse(provider="ollama", payload=response.json())

    def extract_tool_calls(self, response: LLMResponse) -> List[ToolCall]:
        message = response.payload.get("message") or {}
        calls = message.get("tool_calls") or []
        result: List[ToolCall] = []
        for call in calls:
            function = call.get("function") or {}
            name = function.get("name")
            if not name:
                continue
            raw_arguments = function.get("arguments", {})
            
            # Ollama 返回的 arguments 可能是对象格式，需要保持原样
            # 如果已经是字典，直接使用；如果是字符串，尝试解析
            if isinstance(raw_arguments, dict):
                # 已经是对象格式，直接使用
                arguments = raw_arguments
                error = None
            else:
                # 尝试解析字符串格式
                arguments, error = _parse_json_arguments(raw_arguments)
            
            result.append(
                ToolCall(
                    name=name,
                    arguments=arguments,
                    raw_arguments=raw_arguments,
                    parse_error=error,
                )
            )
        return result

    def render_text(self, response: LLMResponse) -> str:
        message = response.payload.get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        return stringify(message)


class HuggingFaceLocalProvider(BaseLLMProvider):
    """Local HuggingFace model provider (supports merged models)."""
    
    def __init__(self, settings: ClientSettings):
        super().__init__(settings)
        self.model = None
        self.tokenizer = None
        self._load_model()
    
    def _load_model(self):
        """Load local model."""
        model_path = self.settings.hf_model_path
        
        # 转换为绝对路径
        if not os.path.isabs(model_path):
            # 计算项目根目录（llm）
            current_file_dir = os.path.dirname(os.path.abspath(__file__))  # fusion_helper/mcp_client
            fusion_helper_dir = os.path.dirname(current_file_dir)          # fusion_helper
            project_root = os.path.dirname(fusion_helper_dir)              # llm

            # 处理相对路径：
            # - 以 ../ 开头：相对于项目根目录解析
            # - 其他相对路径：也以项目根目录为基准，避免跳到上层目录
            if model_path.startswith("../"):
                relative_path = model_path[3:]
                model_path = os.path.join(project_root, relative_path)
            elif model_path.startswith("./"):
                relative_path = model_path[2:]
                model_path = os.path.join(project_root, relative_path)
            else:
                model_path = os.path.join(project_root, model_path)

            model_path = os.path.normpath(model_path)
        
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model path not found: {model_path}")
        
        print(f"Loading model: {model_path}")
        
        # 加载分词器
        from transformers import AutoTokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_path,
            trust_remote_code=True,
            padding_side="right"
        )
        
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
            self.tokenizer.pad_token_id = self.tokenizer.eos_token_id
        
        # 加载模型
        from transformers import AutoModelForCausalLM
        load_kwargs = {
            "trust_remote_code": True,
            "device_map": "auto",
            "torch_dtype": torch.float16 if torch.cuda.is_available() else torch.float32,
        }
        
        # 使用 4-bit 量化（如果启用）
        if self.settings.hf_use_4bit and torch.cuda.is_available():
            try:
                from transformers import BitsAndBytesConfig
                load_kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=torch.float16,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_use_double_quant=True,
                )
                print("Loading with 4-bit quantization")
            except ImportError:
                print("Warning: bitsandbytes not installed, 4-bit disabled")
        
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path,
            **load_kwargs
        )
        self.model.eval()
        print("Model loaded")
    
    def call(self, messages: List[Dict[str, Any]], functions: List[Dict[str, Any]]) -> LLMResponse:
        """Run model inference."""
        # 构建工具描述
        tools_text = ""
        if functions:
            tools_text = "\n\n可用工具:\n"
            for fn in functions:
                tools_text += f"- {fn['name']}: {fn.get('description', '')}\n"
        
        # 格式化消息（转换为 Qwen 格式）
        formatted_prompt = ""
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if role == "system":
                formatted_prompt += f"系统: {content}\n\n"
            elif role == "user":
                formatted_prompt += f"用户: {content}\n"
            elif role == "assistant":
                formatted_prompt += f"助手: {content}\n"
            elif role == "tool":
                tool_name = msg.get("name", "")
                tool_content = msg.get("content", "")
                formatted_prompt += f"工具调用结果 ({tool_name}): {tool_content}\n"
        
        formatted_prompt += tools_text + "\n助手: "
        
        # Tokenize
        inputs = self.tokenizer(
            formatted_prompt,
            return_tensors="pt",
            truncation=True,
            max_length=2048
        ).to(self.model.device)
        
        # 生成
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=512,
                temperature=self.settings.temperature,
                top_p=0.9,
                do_sample=True,
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
            )
        
        # 解码
        generated_text = self.tokenizer.decode(
            outputs[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True
        ).strip()
        
        # 构建响应（模拟 Ollama 格式以兼容现有代码）
        response_payload = {
            "message": {
                "content": generated_text,
                "tool_calls": []  # 简化版，需要时可以解析工具调用
            }
        }
        
        return LLMResponse(provider="huggingface_local", payload=response_payload)
    
    def extract_tool_calls(self, response: LLMResponse) -> List[ToolCall]:
        """Extract tool calls from generated text."""
        message = response.payload.get("message", {})
        content = message.get("content", "")
        
        if not content:
            return []
        
        # 尝试从文本中解析工具调用
        # 模型可能生成类似 "调用工具 create_box(width=20, height=20, depth=10)" 的文本
        # 或者 JSON 格式的工具调用
        
        tool_calls: List[ToolCall] = []
        
        # 方法1: 尝试解析 JSON 格式的工具调用
        import re
        json_pattern = r'\{[^{}]*"name"[^{}]*"arguments"[^{}]*\}'
        json_matches = re.findall(json_pattern, content, re.DOTALL)
        
        for match in json_matches:
            try:
                tool_data = json.loads(match)
                if "name" in tool_data:
                    name = tool_data.get("name")
                    arguments = tool_data.get("arguments", {})
                    tool_calls.append(
                        ToolCall(
                            name=name,
                            arguments=arguments if isinstance(arguments, dict) else {},
                            raw_arguments=arguments,
                        )
                    )
            except json.JSONDecodeError:
                continue
        
        # 方法2: 尝试从文本中提取函数调用模式
        # 例如: create_box(width=20, height=20, depth=10)
        if not tool_calls:
            function_pattern = r'(\w+)\s*\(([^)]*)\)'
            matches = re.finditer(function_pattern, content)
            
            for match in matches:
                func_name = match.group(1)
                # 检查是否是已知的工具名称（从 functions 列表中）
                # 这里简化处理，实际应该从 functions 参数中获取
                if func_name.startswith("create_") or func_name.startswith("modify_") or func_name.startswith("get_"):
                    # 尝试解析参数
                    args_str = match.group(2)
                    arguments = {}
                    
                    # 简单的参数解析（key=value 格式）
                    arg_pattern = r'(\w+)\s*=\s*([^,)]+)'
                    arg_matches = re.findall(arg_pattern, args_str)
                    for arg_name, arg_value in arg_matches:
                        # 尝试转换为数字
                        try:
                            if '.' in arg_value:
                                arguments[arg_name] = float(arg_value.strip())
                            else:
                                arguments[arg_name] = int(arg_value.strip())
                        except ValueError:
                            # 保持字符串
                            arguments[arg_name] = arg_value.strip().strip('"\'')
                    
                    tool_calls.append(
                        ToolCall(
                            name=func_name,
                            arguments=arguments,
                            raw_arguments=args_str,
                        )
                    )
        
        return tool_calls
    
    def render_text(self, response: LLMResponse) -> str:
        """Render text response."""
        message = response.payload.get("message", {})
        content = message.get("content", "")
        if isinstance(content, str):
            return content.strip()
        return ""


def create_provider(settings: ClientSettings) -> BaseLLMProvider:
    """Create LLM provider from config."""
    provider = settings.provider
    if provider == "openai":
        return OpenAIProvider(settings)
    if provider == "ollama":
        return OllamaProvider(settings)
    if provider == "huggingface" or provider == "hf" or provider == "local":
        return HuggingFaceLocalProvider(settings)
    raise NotImplementedError(f"LLM_PROVIDER={provider!r} not supported. Extend create_provider.")


