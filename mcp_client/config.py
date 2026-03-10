from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


def _parse_int_env(name: str) -> Optional[int]:
    """Parse env var as int; returns None if unset or empty."""
    val = os.getenv(name)
    if val is None or (isinstance(val, str) and val.strip() == ""):
        return None
    try:
        return int(val)
    except ValueError:
        return None


def _parse_float_env(name: str) -> Optional[float]:
    """Parse env var as float; returns None if unset or empty."""
    val = os.getenv(name)
    if val is None or (isinstance(val, str) and val.strip() == ""):
        return None
    try:
        return float(val)
    except ValueError:
        return None


@dataclass(frozen=True)
class ClientSettings:
    """MCP client configuration."""

    provider: str
    mcp_server_url: str
    system_prompt: str
    max_tool_iterations: int
    openai_api_key: Optional[str]
    openai_model: str
    openai_base_url: Optional[str]
    openai_max_tokens: Optional[int]
    openai_top_p: Optional[float]
    ollama_base_url: str
    ollama_model: str
    # Local HuggingFace model
    hf_model_path: str
    hf_use_4bit: bool
    temperature: float
    # RAG
    enable_rag: bool
    rag_persist_directory: str
    rag_collection_name: str
    rag_embedding_model: str
    rag_top_k: int
    rag_chunk_size: int
    rag_chunk_overlap: int
    # Planning
    enable_planning: bool
    planning_system_prompt: Optional[str]
    # Agent Skills
    enable_skills: bool
    default_skill: str
    skills_directory: str

    @classmethod
    def from_env(cls) -> "ClientSettings":
        """Build config from environment variables."""
        provider = os.getenv("LLM_PROVIDER", "openai").lower()
        return cls(
            provider=provider,
            mcp_server_url=os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8765/mcp"),
            system_prompt=os.getenv(
                "LLM_SYSTEM_PROMPT",
                "You are a CAD assistant for Fusion 360.\n\n"
                "Core Rules (STRICT):\n"
                "0) Complete all tasks in the user prompt; for multiple objects/steps, call tools in sequence until done.\n"
                "1) Only call create_entity_relative when user explicitly mentions relative placement (above/below/left/right/etc.); otherwise use create_box/create_cylinder with absolute coords.\n"
                "2) create_entity_relative requires: base_body_name (or parent_body_name) AND size params:\n"
                "   - box: width, height, depth (or dimensions/size). Do not call if any is missing.\n"
                "   - cylinder: radius, cylinder_height. Do not call if any is missing.\n"
                "3) Param mapping: height/thickness → depth (Z); length → width (X); width → height (Y).\n"
                "   '1*2*3' or '1x2x3' → width=1, height=2, depth=3 (mm).\n"
                "4) Modify existing body → modify_body_dimensions; create new → create_box/create_cylinder.\n"
                "5) Ensure required info (body name, size) before calling; if missing, ask or call get_document_content once and reuse.\n"
                "6) Shell thickness change → shell(thickness=X); shell thickness cannot be changed via modify_body_dimensions.\n"
                "7) Call get_document_content at most once per task.\n"
                "8) For multi-step tasks, do not stop after one success; complete all steps.\n"
                "9) When a tool returns an error, analyze the error message, correct the parameters, and retry the same tool. Do not give up after one failure.\n\n"
                "Output: Call tools only, no extra explanation. Units: mm.",
            ),
            max_tool_iterations=int(os.getenv("MAX_TOOL_CALL_ITERATIONS", "8")),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_model=os.getenv("OPENAI_MODEL", "qwen"),
            openai_base_url=os.getenv("OPENAI_BASE_URL"),
            openai_max_tokens=_parse_int_env("OPENAI_MAX_TOKENS"),
            openai_top_p=_parse_float_env("OPENAI_TOP_P"),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            ollama_model=os.getenv("OLLAMA_MODEL", "qwen2.5:latest"),
            # Local HuggingFace model
            hf_model_path=os.getenv("HF_MODEL_PATH", "../merged_qwen2.5_fusion360"),
            hf_use_4bit=os.getenv("HF_USE_4BIT", "true").lower() == "true",
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
            # RAG
            # RAG disabled by default
            enable_rag=False,
            rag_persist_directory=os.getenv("RAG_PERSIST_DIRECTORY", "./.chroma_db"),
            rag_collection_name=os.getenv("RAG_COLLECTION_NAME", "documents"),
            rag_embedding_model=os.getenv("RAG_EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
            rag_top_k=int(os.getenv("RAG_TOP_K", "5")),
            rag_chunk_size=int(os.getenv("RAG_CHUNK_SIZE", "1000")),
            rag_chunk_overlap=int(os.getenv("RAG_CHUNK_OVERLAP", "200")),
            # Planning: plan first when user says create/generate
            enable_planning=os.getenv("ENABLE_PLANNING", "true").lower() == "true",
            planning_system_prompt=os.getenv("PLANNING_SYSTEM_PROMPT") or None,
            # Agent Skills
            enable_skills=os.getenv("ENABLE_SKILLS", "true").lower() == "true",
            default_skill=os.getenv("AGENT_SKILL", "cad"),
            skills_directory=os.getenv(
                "SKILLS_DIRECTORY",
                os.path.join(os.path.dirname(__file__), "skills"),
            ),
        )
    
    def with_provider(self, provider: str, **overrides) -> "ClientSettings":
        """Create new config with modified provider and fields."""
        current_values = {
            "provider": provider,
            "mcp_server_url": self.mcp_server_url,
            "system_prompt": self.system_prompt,
            "max_tool_iterations": self.max_tool_iterations,
            "openai_api_key": self.openai_api_key,
            "openai_model": self.openai_model,
            "openai_base_url": self.openai_base_url,
            "openai_max_tokens": self.openai_max_tokens,
            "openai_top_p": self.openai_top_p,
            "ollama_base_url": self.ollama_base_url,
            "ollama_model": self.ollama_model,
            "hf_model_path": self.hf_model_path,
            "hf_use_4bit": self.hf_use_4bit,
            "temperature": self.temperature,
            "enable_rag": self.enable_rag,
            "rag_persist_directory": self.rag_persist_directory,
            "rag_collection_name": self.rag_collection_name,
            "rag_embedding_model": self.rag_embedding_model,
            "rag_top_k": self.rag_top_k,
            "rag_chunk_size": self.rag_chunk_size,
            "rag_chunk_overlap": self.rag_chunk_overlap,
            "enable_planning": self.enable_planning,
            "planning_system_prompt": self.planning_system_prompt,
            "enable_skills": self.enable_skills,
            "default_skill": self.default_skill,
            "skills_directory": self.skills_directory,
        }
        # Apply overrides
        current_values.update(overrides)
        return ClientSettings(**current_values)


