"""
MCP client example for LLM-controlled Fusion 360.

Before running, ensure:
- MCP server is started via HTTP/StreamableHTTP (example port 8765);
- Environment variables set for MCP_SERVER_URL (optional) and LLM API keys.
"""

from __future__ import annotations

import asyncio
import os
from typing import List, Optional

from fastmcp import Client as MCPClient

from mcp_client.config import ClientSettings
from mcp_client.conversation import ConversationEngine, ConversationState
from mcp_client.planner import create_plan
from mcp_client.plan_executor import execute_plan
from mcp_client.providers import create_provider
from mcp_client.rag import DocumentLoader, RAGRetriever, VectorStore
from mcp_client.skill_loader import (
    build_system_prompt_with_skill,
    load_skills,
)
from mcp_client.tooling import build_function_schemas
from mcp_client.logger import get_default_logger

logger = get_default_logger()


async def _get_user_input(prompt: str) -> str:
    return await asyncio.to_thread(input, prompt)


def _select_provider() -> Optional[str]:
    """Interactive LLM provider selection."""
    print("\n=== Select LLM Provider ===")
    print("1. Local LLM (Ollama) - No API key, use local model")
    print("2. Cloud API (OpenAI/Qwen) - Requires API key, use cloud model")
    print("3. Local HuggingFace model - Direct use of merged model (recommended)")
    print("4. Use environment variables (default)")
    print()
    
    while True:
        try:
            choice = input("Choose (1/2/3/4, press Enter for env): ").strip()
            if not choice:
                return None
            if choice == "1":
                return "ollama"
            elif choice == "2":
                return "openai"
            elif choice == "3":
                return "huggingface"
            elif choice == "4":
                return None
            else:
                print("Invalid choice, enter 1, 2, 3, or 4")
        except (EOFError, KeyboardInterrupt):
            logger.info("Using environment variables")
            return None


def _configure_provider(provider: str, settings: ClientSettings) -> ClientSettings:
    """Configure settings for the selected provider. Use env vars if already set."""
    if provider == "ollama":
        print("\n=== Local LLM (Ollama) ===")
        print(f"Ollama URL: {settings.ollama_base_url}")
        print(f"Ollama model: {settings.ollama_model}")
        print("✓ Using environment configuration")
        logger.info(f"Ollama config: {settings.ollama_base_url}, model: {settings.ollama_model}")
        return settings.with_provider("ollama")
    
    elif provider == "huggingface" or provider == "hf" or provider == "local":
        print("\n=== Local HuggingFace Model ===")
        print(f"Model path: {settings.hf_model_path}")
        print(f"4-bit quantization: {settings.hf_use_4bit}")
        
        model_path = settings.hf_model_path
        if not os.path.isabs(model_path):
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            model_path = os.path.join(base_dir, "..", model_path)
            model_path = os.path.normpath(model_path)
        
        if not os.path.exists(model_path):
            print(f"Warning: Model path not found: {model_path}")
            print("Set HF_MODEL_PATH to the merged model directory")
            new_path = input(f"Enter model path (default: {settings.hf_model_path}): ").strip()
            if new_path:
                model_path = new_path
            else:
                model_path = settings.hf_model_path
        
        print("✓ Using environment configuration")
        logger.info(f"HuggingFace model: {model_path}")
        return settings.with_provider("huggingface", hf_model_path=model_path)
    
    elif provider == "openai":
        print("\n=== Cloud API (OpenAI/Qwen) ===")
        print(f"Model: {settings.openai_model}")
        if settings.openai_base_url:
            print(f"API URL: {settings.openai_base_url}")
        else:
            print("API URL: default")
        
        if settings.openai_api_key:
            masked_key = settings.openai_api_key[:8] + "..." + settings.openai_api_key[-4:] if len(settings.openai_api_key) > 12 else "***"
            print(f"API Key: {masked_key} (configured)")
            print("✓ Using environment configuration")
            logger.info(f"OpenAI config: model={settings.openai_model}, base_url={settings.openai_base_url}")
            return settings.with_provider("openai")
        else:
            print("API Key: not configured")
            api_key = input("Enter API Key: ").strip()
            if not api_key:
                logger.warning("API Key not set. Ensure OPENAI_API_KEY is configured.")
                api_key = None
            
            model = input(f"Model (default: {settings.openai_model}): ").strip()
            if not model:
                model = settings.openai_model
            
            base_url = input("API URL (blank for default): ").strip()
            if not base_url:
                base_url = settings.openai_base_url
            
            return settings.with_provider(
                "openai",
                openai_api_key=api_key,
                openai_model=model,
                openai_base_url=base_url,
            )
    
    return settings


async def run_agent(settings: Optional[ClientSettings] = None, interactive_config: bool = True) -> None:
    """Run LLM-controlled Fusion 360 in interactive conversation mode.
    
    Args:
        settings: Optional client settings; if None, load from env
        interactive_config: Enable interactive provider selection (default True)
    """
    base_settings = settings or ClientSettings.from_env()
    
    if interactive_config:
        selected_provider = _select_provider()
        if selected_provider:
            settings = _configure_provider(selected_provider, base_settings)
        else:
            settings = base_settings
    else:
        settings = base_settings

    print("=== Fusion 360 LLM Client ===")
    print(f"MCP Server: {settings.mcp_server_url}")
    print(f"LLM Provider: {settings.provider}")
    if settings.provider == "openai":
        print(f"OpenAI model: {settings.openai_model}")
        if settings.openai_base_url:
            print(f"API URL: {settings.openai_base_url}")
        if getattr(settings, "openai_max_tokens", None) is not None:
            print(f"Max tokens: {settings.openai_max_tokens}")
        if getattr(settings, "openai_top_p", None) is not None:
            print(f"Top-P: {settings.openai_top_p}")
    elif settings.provider == "ollama":
        print(f"Ollama model: {settings.ollama_model}")
        print(f"Ollama URL: {settings.ollama_base_url}")
    elif settings.provider in ["huggingface", "hf", "local"]:
        print(f"Local model path: {settings.hf_model_path}")
        print(f"4-bit quantization: {settings.hf_use_4bit}")
    print(f"Temperature: {settings.temperature}")
    if settings.enable_rag:
        print(f"RAG embedding model: {settings.rag_embedding_model}")
    plan_cmd = ", /plan <request> for forced planning" if settings.enable_planning else ""
    skill_cmd = ", /skill <name> to switch skill, /skills to list" if getattr(settings, "enable_skills", True) else ""
    print(f"Commands: /tools, /reload, /reset, /exit{plan_cmd}{skill_cmd}")
    
    logger.info(f"Client started - MCP: {settings.mcp_server_url}, provider: {settings.provider}")

    skills: dict = {}
    active_skill_ref: List[Optional[str]] = [None]
    if getattr(settings, "enable_skills", True):
        skills = load_skills(settings.skills_directory)
        active_skill_ref[0] = settings.default_skill
        if skills:
            logger.info(f"[Skills] Loaded {len(skills)} skills: {', '.join(skills)}")
            if active_skill_ref[0] in skills:
                print(f"Current skill: {active_skill_ref[0]}")

    def _get_effective_system_prompt() -> str:
        name = active_skill_ref[0]
        skill = skills.get(name) if name else None
        return build_system_prompt_with_skill(settings.system_prompt, skill)

    def _get_planning_prompt() -> Optional[str]:
        name = active_skill_ref[0]
        if name and name in skills:
            return skills[name].get_planning_prompt()
        return None

    provider = create_provider(settings)
    mcp_client = MCPClient(settings.mcp_server_url, name="FusionLLMAgent")
    conversation = ConversationState(
        [{"role": "system", "content": _get_effective_system_prompt()}]
    )

    rag_retriever = None
    if settings.enable_rag:
        try:
            logger.info("[RAG] Initializing...")
            vector_store = VectorStore(
                persist_directory=settings.rag_persist_directory,
                collection_name=settings.rag_collection_name,
                embedding_model=settings.rag_embedding_model,
            )
            document_loader = DocumentLoader(
                chunk_size=settings.rag_chunk_size,
                chunk_overlap=settings.rag_chunk_overlap,
            )
            rag_retriever = RAGRetriever(vector_store, document_loader)
            info = vector_store.get_collection_info()
            logger.info(f"[RAG] Initialized, {info['count']} chunks in store")
            print("Commands: /rag-load <path>, /rag-load-dir <dir>, /rag-info")
        except Exception as e:
            logger.error(f"[RAG] Init failed: {e}", exc_info=True)

    engine = ConversationEngine(provider, mcp_client, settings.max_tool_iterations, rag_retriever)

    async with mcp_client:
        tools = await mcp_client.list_tools()
        function_defs = build_function_schemas(tools)
        if tools:
            tool_names = ", ".join(tool.name for tool in tools)
            print(f"Loaded {len(tools)} tools: {tool_names}")
            logger.info(f"Loaded {len(tools)} tools: {tool_names}")
        else:
            logger.warning("No tools exposed by MCP server")
            print("Warning: No tools available.")

        while True:
            try:
                user_input = (await _get_user_input("User> ")).strip()
            except (EOFError, KeyboardInterrupt):
                print("\nAssistant> Session ended. Goodbye!")
                break

            if not user_input:
                continue

            normalized = user_input.lower()
            if normalized in {"exit", "quit", "/exit", "/quit"}:
                print("\nAssistant> Session ended. Goodbye!")
                break

            if normalized == "/reset":
                conversation = ConversationState(
                    [{"role": "system", "content": _get_effective_system_prompt()}]
                )
                print("Assistant> Conversation reset.")
                continue

            if normalized in {"/tools", "/tool"}:
                if tools:
                    print("Tools:", ", ".join(sorted(tool.name for tool in tools)))
                else:
                    print("Assistant> No tools available.")
                continue

            if normalized in {"/reload", "/reload-tools"}:
                tools = await mcp_client.list_tools()
                function_defs = build_function_schemas(tools)
                if tools:
                    print(f"Assistant> Reloaded {len(tools)} tools: {', '.join(tool.name for tool in tools)}")
                else:
                    print("Assistant> Tool list empty.")
                continue

            if normalized == "/skills":
                if skills:
                    for name, cfg in skills.items():
                        current = " (current)" if name == active_skill_ref[0] else ""
                        desc = cfg.description[:80] + "..." if len(cfg.description) > 80 else cfg.description
                        print(f"  - {name}{current}: {desc}")
                else:
                    print("Assistant> No skills loaded (ENABLE_SKILLS=false or empty skills dir).")
                continue

            if user_input.lower().startswith("/skill"):
                parts = user_input.split(maxsplit=1)
                if len(parts) < 2:
                    print(f"Assistant> Current skill: {active_skill_ref[0] or 'none'}")
                    continue
                new_skill = parts[1].strip().lower()
                if new_skill in skills:
                    active_skill_ref[0] = new_skill
                    conversation.messages[0] = {
                        "role": "system",
                        "content": _get_effective_system_prompt(),
                    }
                    print(f"Assistant> Switched to skill: {new_skill}")
                else:
                    print(f"Assistant> Unknown skill '{new_skill}', available: {', '.join(skills)}")
                continue

            force_plan = False
            effective_input = user_input
            if user_input.lower().startswith("/plan "):
                force_plan = True
                effective_input = user_input[6:].strip()
                if not effective_input:
                    print("Assistant> Enter request after /plan, e.g.: /plan create a cup")
                    continue

            def _should_use_planning() -> bool:
                if not settings.enable_planning:
                    return False
                if force_plan:
                    return True
                lowered = effective_input.lower()
                prefixes = ("create", "generate", "make", "build")
                return any(lowered.startswith(p) for p in prefixes) and len(effective_input) > 4

            if _should_use_planning():
                conversation.append({"role": "user", "content": effective_input})
                try:
                    planning_prompt = _get_planning_prompt() or settings.planning_system_prompt
                    plan = await asyncio.to_thread(
                        create_plan,
                        effective_input,
                        provider,
                        function_defs,
                        planning_prompt,
                    )
                except Exception as exc:
                    logger.error(f"[Plan] Planning failed: {exc}", exc_info=True)
                    plan = None

                if plan and plan.steps:
                    logger.info(f"[Plan] {plan.goal}, {len(plan.steps)} steps")
                    print(f"Assistant> Plan: {plan.goal} ({len(plan.steps)} steps)")
                    try:
                        exec_result = await execute_plan(
                            plan,
                            mcp_client,
                            provider=provider,
                            max_recovery_retries=2,
                        )
                        if exec_result.success:
                            print(f"Assistant> {exec_result.message}")
                            reply = exec_result.message
                        else:
                            print(f"Assistant> Execution failed: {exec_result.message}")
                            reply = f"Execution failed: {exec_result.message}"
                    except Exception as exc:
                        reply = f"Execution error: {exc}"
                        logger.error(f"[Plan] Execution error: {exc}", exc_info=True)
                        print(f"Assistant> {reply}")
                    conversation.append({"role": "assistant", "content": reply})
                    continue
                else:
                    logger.info("[Plan] No valid plan, falling back to chat")
                    conversation.messages.pop()
                    user_input = effective_input

            if rag_retriever:
                if user_input.startswith("/rag-load "):
                    file_path = user_input[len("/rag-load "):].strip()
                    try:
                        count = rag_retriever.add_documents_from_file(file_path)
                        print(f"Assistant> Loaded {count} chunks into vector store")
                        logger.info(f"Loaded {count} chunks: {file_path}")
                    except Exception as e:
                        logger.error(f"Failed to load docs: {e}", exc_info=True)
                        print(f"Assistant> Load failed: {e}")
                    continue

                if user_input.startswith("/rag-load-dir "):
                    dir_path = user_input[len("/rag-load-dir "):].strip()
                    try:
                        count = rag_retriever.add_documents_from_directory(dir_path)
                        print(f"Assistant> Loaded {count} chunks into vector store")
                        logger.info(f"Loaded {count} chunks: {dir_path}")
                    except Exception as e:
                        logger.error(f"Failed to load dir: {e}", exc_info=True)
                        print(f"Assistant> Load failed: {e}")
                    continue

                if normalized == "/rag-info":
                    info = rag_retriever.vector_store.get_collection_info()
                    print("Assistant> RAG info:")
                    print(f"  - Collection: {info['name']}")
                    print(f"  - Chunks: {info['count']}")
                    print(f"  - Embedding model: {info.get('embedding_model', 'unknown')}")
                    print(f"  - Persist dir: {info['persist_directory']}")
                    continue

            conversation.append({"role": "user", "content": user_input})

            try:
                response = await engine.process_turn(conversation, function_defs)
            except Exception as exc:
                error_text = f"Processing failed: {exc}"
                logger.error(f"[LLMError] {error_text}", exc_info=True)
                conversation.append({"role": "assistant", "content": error_text})
                continue

            reply_text = provider.render_text(response) or "[No text reply]"
            print(f"Assistant> {reply_text}")
            conversation.append({"role": "assistant", "content": reply_text})


def main() -> None:
    """Entry point with CLI args."""
    import sys
    
    skip_interactive = "--no-interactive" in sys.argv or "-n" in sys.argv
    
    asyncio.run(run_agent(interactive_config=not skip_interactive))


if __name__ == "__main__":
    main()
