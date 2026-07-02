"""
Multi-agent system with MCP tools integration.
Supports Mistral and Google providers with human-in-the-loop approval for file operations.
Features Firestore-backed persistence and message trimming for context management.
"""

import asyncio
import json
import os
import sys
import re
import base64
from pathlib import Path
from contextlib import AsyncExitStack
from typing import Any, Optional
from copy import deepcopy

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.agents.factory import AgentMiddleware
from langchain.agents.middleware import (
    HumanInTheLoopMiddleware,
    before_model,
    after_model,
    AgentState,
)
from langchain.tools import tool
from langchain_core.language_models.chat_models import BaseChatModel
from langchain.messages import (
    AIMessageChunk,
    AIMessage,
    ToolMessage,
    AnyMessage,
    RemoveMessage,
)
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph_checkpoint_firestore import FirestoreSaver
from langgraph.types import Command, Interrupt
from langgraph.types import interrupt as lg_interrupt
from langgraph.runtime import Runtime
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
import langchain.agents.middleware.human_in_the_loop as hitl_mod

from utils import (
    force_text_only,
    strip_block_id,
    patch_tools_text_only_for_mistral,
    load_prompts,
)

from tools.crops import get_crop_recommendations
from tools.fertilizer import get_fertilizer_recommendations, get_recommendations_simple
from tools.construction import unwrap_to_bigquery_row, get_construction_recommendations

# Windows event loop policy fix
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

load_dotenv()

# Global configuration
PROVIDER = os.getenv("LLM_PROVIDER", "google")  # Default: google
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
key_b64 = os.environ["LANGGRAPH_AES_KEY"]
key = base64.b64decode(key_b64)


#########################################################################
# Provider-Specific Middleware
#########################################################################

@before_model
@before_model
def mistral_tool_content_to_string(
    state: AgentState,
    runtime: Runtime
) -> Optional[dict[str, Any]]:
    """
    Convert ToolMessage content from list format to string for Mistral compatibility.
    Preserves tool_call_id and cleans up extras/signatures.
    """
    new_messages = []
    changed = False

    for m in state["messages"]:
        if isinstance(m, ToolMessage) and isinstance(m.content, list):
            parts = []
            for block in m.content:
                if isinstance(block, dict):
                    block = strip_block_id(block)
                    extras = block.get("extras")
                    if isinstance(extras, dict):
                        extras.pop("signature", None)
                    if block.get("type") == "text":
                        parts.append(block.get("text", ""))
                    else:
                        parts.append(json.dumps(block, ensure_ascii=False))
                else:
                    parts.append(str(block))

            stitched = "\n".join(p for p in parts if p).strip()
            new_m = deepcopy(m)
            new_m.content = stitched
            new_messages.append(new_m)
            changed = True
        else:
            new_messages.append(m)

    return {"messages": new_messages} if changed else None


@after_model
def gemini_output_stitcher(
    state: AgentState,
    runtime: Runtime
) -> Optional[dict[str, Any]]:
    """
    Stitch Gemini's multipart AI message content into a single text string.
    Filters out 'thought' blocks and flattens text blocks.
    """
    messages = list(state.get("messages", []))
    if not messages:
        return None

    last_msg = messages[-1]

    # Debug logging (BEFORE stitching)
    try:
        print("\n[GEMINI DEBUG] last_msg class:", type(last_msg))
        print("[GEMINI DEBUG] content type:", type(getattr(last_msg, "content", None)))
        print("[GEMINI DEBUG] is content list:", isinstance(getattr(last_msg, "content", None), list))

        if hasattr(last_msg, "content") and isinstance(last_msg.content, list):
            print("[GEMINI DEBUG] block count:", len(last_msg.content))
            print("[GEMINI DEBUG] block types:",
                  [b.get("type") if isinstance(b, dict) else "str" for b in last_msg.content])

            # Show preview of each block
            for i, b in enumerate(last_msg.content):
                if isinstance(b, dict):
                    t = b.get("type")
                    txt = b.get("text") or b.get("thought") or ""
                    print(f"[GEMINI DEBUG] block[{i}] type={t} preview={repr(str(txt)[:80])}")
                else:
                    print(f"[GEMINI DEBUG] block[{i}] str preview={repr(str(b)[:80])}")
    except Exception as e:
        print("[GEMINI DEBUG] debug print failed:", e)

    # Only stitch AI messages with multipart list content
    if isinstance(last_msg, AIMessage) and isinstance(last_msg.content, list):
        stitched_text = flatten_content_to_text(last_msg.content)
        last_msg.content = stitched_text
        messages[-1] = last_msg

        # Debug logging (AFTER stitching)
        print("[GEMINI DEBUG] stitched content type:", type(last_msg.content))
        print("[GEMINI DEBUG] stitched length:", len(last_msg.content))
        print("[GEMINI DEBUG] stitched preview:", repr(last_msg.content[:120]))

        return {"messages": messages}

    return None


# Middleware wrapper classes
class MistralMiddleware(AgentMiddleware):
    """Wrapper for Mistral middleware compatibility."""
    async def __call__(self, state: AgentState, runtime: Runtime):
        return mistral_tool_content_to_string(state, runtime)


class GeminiMiddleware(AgentMiddleware):
    """Wrapper for Gemini middleware compatibility."""
    async def __call__(self, state: AgentState, runtime: Runtime):
        return gemini_output_stitcher(state, runtime)


def provider_middleware(provider: str) -> list:
    """Return middleware list based on LLM provider."""
    if provider == "google":
        return [gemini_output_stitcher]
    if provider == "mistral":
        return [MistralMiddleware()]
    return []


#########################################################################
# LLM Provider Configuration
#########################################################################

def make_llm(provider: str) -> BaseChatModel:
    """Create and configure LLM based on provider."""
    if provider == "mistral":
        from langchain_mistralai import ChatMistralAI
        return ChatMistralAI(
            model="mistral-large-latest",
            temperature=0,
            max_retries=2,
            mistral_api_key=os.getenv("MISTRAL_API_KEY"),
        )

    if provider == "google":
        from langchain_google_genai import (
            ChatGoogleGenerativeAI,
            HarmBlockThreshold,
            HarmCategory,
        )
        return ChatGoogleGenerativeAI(
            model=GEMINI_MODEL,
            temperature=0,
            max_retries=2,
            vertexai=True,
            streaming=True,
            max_output_tokens=4096,
            project=os.getenv("GOOGLE_CLOUD_PROJECT"),
            location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
            # Thinking configuration
            thinking_config={"include_thoughts": True, "thinking_budget": 1024},
            # Safety settings (permissive for development)
            safety_settings={
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }
        )

    raise ValueError(f"Unknown provider: {provider}")


#########################################################################
# Content Processing Utilities
#########################################################################

def flatten_content_to_text(content):
    """
    Convert various content formats to plain text.
    Filters out 'thought' blocks and extracts text from structured content.
    """
    if isinstance(content, str):
        return content

    parts = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                # Skip thought blocks
                if block.get("type") == "thought":
                    continue

                # Extract text content
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif "text" in block:
                    parts.append(block["text"])

            elif isinstance(block, str):
                parts.append(block)

        return "".join(parts).strip()

    return str(content)


#########################################################################
# Context Management and Interrupt Handling
#########################################################################

def _text_to_decisions(text: str) -> dict:
    """
    Parse text input into HITL decision format.
    Supports approve, reject, and edit commands.
    """
    t = text.strip().lower()

    # Approve
    if t in {"a", "approve", "yes", "y"}:
        return {"decisions": [{"type": "approve"}]}

    # Reject
    if t in {"r", "reject", "no", "n"}:
        return {"decisions": [{"type": "reject"}]}

    # Edit with syntax: "edit: <new query>" or "e <new query>"
    m = re.match(r"^(e|edit)\s*:?\s*(.+)$", text.strip(), flags=re.IGNORECASE)
    if m:
        new_query = m.group(2).strip()
        return {
            "decisions": [
                {
                    "type": "edit",
                    "edited_action": {
                        "name": "ops_files",
                        "args": {"query": new_query},
                    },
                }
            ]
        }

    # Default: reject with explanation
    return {"decisions": [{"type": "reject", "reason": f"Unrecognized input: {text}"}]}


def interrupt_parsed(request):
    """
    Wrap LangGraph interrupt() to accept JSON strings from Studio.
    Parses string responses and converts to decision format.
    """
    value = lg_interrupt(request)

    # Studio sometimes returns JSON as a string
    if isinstance(value, str):
        s = value.strip()

        # Try parsing as JSON first
        if s.startswith("{") or s.startswith("["):
            try:
                obj = json.loads(s)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                pass

        # Otherwise interpret as text command
        return _text_to_decisions(value)

    return value


# Monkey-patch for HumanInTheLoopMiddleware Studio compatibility
hitl_mod.interrupt = interrupt_parsed


@before_model
def trim_messages(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
    """
    Keep only the last few messages to fit the context window.
    Preserves the first message (system/instructions) and recent tail.
    """
    messages = state["messages"]

    # Keep small threads untouched
    if len(messages) <= 8:
        return None

    # Preserve the first message (typically system prompt)
    first_msg = messages[0]

    # Keep a small tail of recent messages
    # Use even count when possible to preserve human/AI pairs
    tail = messages[-8:] if len(messages) % 2 == 0 else messages[-9:]
    new_messages = [first_msg] + tail

    return {
        "messages": [
            RemoveMessage(id=REMOVE_ALL_MESSAGES),
            *new_messages,
        ]
    }


#########################################################################
# Agent and Tool Setup
#########################################################################

async def build_agents(provider: str = "mistral"):
    """
    Build supervisor agent with web and ops subagents.
    Uses Firestore for persistent checkpointing.
    Returns supervisor agent and async context stack.
    """
    llm = make_llm(provider=provider)
    py = str(Path(sys.executable).resolve())
    prompts = load_prompts(Path(__file__).parent / "system_prompts.yaml")

    # Configure MCP server paths
    here = Path(__file__).resolve().parent
    tools_dir = here / "tools"

    ###################################################
    #Khatib's tools'
    from langchain.tools import tool
    from typing import Optional
    import json


    @tool(
        "crop_recommendations",
        description=(
            "Recommend suitable crops from soil properties. "
            "Returns JSON with top crops, constraints, and soil summary."
        ),
    )
    def crop_recommendations() -> str:
        """
        get crop recommendations
        """
        result = get_crop_recommendations()
        return json.dumps(result, ensure_ascii=False)


    @tool(
        "fertilizer_recommendations",
        description=(
            "Generate fertilizer/amendment recommendations.  Returns JSON."
        ),
    )
    def fertilizer_recommendations(
    ) -> str:
        result = get_fertilizer_recommendations(
        )
        return json.dumps(result, ensure_ascii=False)
    

    #############################################################3

    from typing import Dict
    import ast
    @tool
    def get_construction_recommendations_from_file() -> Dict[str, Any]:
        """
        Load the farm value TXT (python dict literal), unwrap into BigQuery-like format,
        and run construction recommendations.
        """

        # Works in scripts + notebooks
        try:
            base_dir = Path(__file__).resolve().parent
        except NameError:
            base_dir = Path.cwd()

        file_path = base_dir / "farm_value_file.txt"

        if not file_path.exists():
            return {"error": "farm_value_file.txt not found", "searched_path": str(file_path)}

        # Read and parse Python dict literal safely
        text = file_path.read_text(encoding="utf-8").strip()
        nested_row = ast.literal_eval(text)

        bigquery_row = unwrap_to_bigquery_row(nested_row)
        return get_construction_recommendations(bigquery_row)

    ###########################################################

    supervisor_server = tools_dir / "supervisor_tools_server.py"
    web_server = tools_dir / "web_tools_server.py"
    ops_server = tools_dir / "ops_tools_server.py"

    # Initialize MCP client with all servers
    client = MultiServerMCPClient(
        {
            "supervisor_tools": {
                "transport": "stdio",
                "command": py,
                "args": [str(supervisor_server)],
            },
            "web_tools": {
                "transport": "stdio",
                "command": py,
                "args": [str(web_server)],
            },
            "ops_tools": {
                "transport": "stdio",
                "command": py,
                "args": [str(ops_server)],
            },
        },
        tool_interceptors=[force_text_only],
    )

    # Create and manage async resources
    stack = AsyncExitStack()

    # PostgreSQL checkpointer (commented out - using Firestore instead)
    # DB_URI = os.getenv("LANGGRAPH_DB_URI")
    # if not DB_URI:
    #     raise RuntimeError("Missing LANGGRAPH_DB_URI env var")
    # checkpointer = await stack.enter_async_context(
    #     AsyncPostgresSaver.from_conn_string(DB_URI)
    # )
    # await checkpointer.setup()

    # Initialize Firestore checkpointer
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        raise RuntimeError("Missing GOOGLE_CLOUD_PROJECT env var for FirestoreSaver")

    # Optional: allow overriding collection names via env vars
    checkpoints_collection = os.getenv(
        "LANGGRAPH_CHECKPOINTS_COLLECTION",
        "langgraph_checkpoints"
    )
    writes_collection = os.getenv(
        "LANGGRAPH_WRITES_COLLECTION",
        "langgraph_writes"
    )

    # FirestoreSaver is a sync context manager; register with async stack
    checkpointer_cm = FirestoreSaver.from_conn_info(
        project_id=project_id,
        checkpoints_collection=checkpoints_collection,
        writes_collection=writes_collection,
    )
    checkpointer = stack.enter_context(checkpointer_cm)

    # Create MCP sessions
    web_session = await stack.enter_async_context(client.session("web_tools"))
    ops_session = await stack.enter_async_context(client.session("ops_tools"))
    sup_session = await stack.enter_async_context(client.session("supervisor_tools"))

    # Load tools from sessions
    web_tools = await load_mcp_tools(web_session)
    ops_tools = await load_mcp_tools(ops_session)
    supervisor_native_tools = await load_mcp_tools(sup_session)

    # Apply provider-specific patches
    if provider == "mistral":
        web_tools = patch_tools_text_only_for_mistral(web_tools)
        ops_tools = patch_tools_text_only_for_mistral(ops_tools)
        supervisor_native_tools = patch_tools_text_only_for_mistral(supervisor_native_tools)

    # Create web research subagent
    web_subagent = create_agent(
        model=llm,
        tools=web_tools,
        system_prompt=prompts["web_subagent"]["system"],
        middleware=provider_middleware(provider),
    )

    # Create ops/files subagent
    ops_subagent = create_agent(
        model=llm,
        tools=ops_tools,
        system_prompt=prompts["ops_subagent"]["system"],
        middleware=provider_middleware(provider),
    )

    # Wrap subagents as tools for supervisor
    @tool(
        "delegate_web_research",
        description="Web research specialist. Use for web search and opening pages, then summarize findings."
    )
    async def call_web_subagent(query: str) -> str:
        """Invoke web research subagent and return results."""
        result = await web_subagent.ainvoke(
            {"messages": [{"role": "user", "content": query}]}
        )
        content = result["messages"][-1].content
        return flatten_content_to_text(content)

    @tool(
        "ops_files",
        description="Ops/files specialist. Use for listing/reading/writing local files and simple extraction tasks."
    )
    async def call_ops_subagent(query: str) -> str:
        """Invoke ops subagent and return results."""
        result = await ops_subagent.ainvoke(
            {"messages": [{"role": "user", "content": query}]}
        )
        content = result["messages"][-1].content
        return flatten_content_to_text(content)

    # Use MemorySaver for in-memory checkpointing (temporary override)
    from langgraph.checkpoint.memory import MemorySaver
    checkpointer = FirestoreSaver(
    project_id=os.environ["GOOGLE_CLOUD_PROJECT"],  
    checkpoints_collection="langgraph_checkpoints",
    )

    # Create supervisor agent with HITL for ops_files tool
    supervisor = create_agent(
        model=llm,
        tools=[*supervisor_native_tools, call_web_subagent, call_ops_subagent, crop_recommendations, fertilizer_recommendations, get_construction_recommendations_from_file],
        system_prompt=prompts["supervisor"]["system"],
        middleware=[
            *provider_middleware(provider),
            # trim_messages,  # Commented out for now
            HumanInTheLoopMiddleware(interrupt_on={"ops_files": True}),
        ],
        checkpointer=checkpointer,
    )

    return supervisor, stack


#########################################################################
# CLI Interaction and Streaming
#########################################################################

# Globals for streaming preview handling
_stream_preview_printed = False
_stream_first_preview_text = None


def _render_message_chunk(token: AIMessageChunk) -> None:
    """
    Lightweight streaming UI with progress dots and preview.
    Shows a one-time short preview (first ~200 chars) so user sees progress.
    """
    global _stream_preview_printed, _stream_first_preview_text

    # Show progress dot for every chunk
    print(".", end="", flush=True)

    # Only capture a single short preview (first non-empty chunk)
    if _stream_preview_printed:
        return

    preview_txt = None

    # Prefer structured content if present
    if hasattr(token, "content") and isinstance(token.content, list):
        preview_txt = flatten_content_to_text(token.content)[:200]
    elif getattr(token, "text", None):
        preview_txt = token.text[:200]

    if preview_txt:
        preview_txt = preview_txt.strip().replace("\r", "")
        if preview_txt:
            # Print small labeled preview and save for later comparison
            print("\n\n[stream preview]\n" + preview_txt + "\n\n", flush=True)
            _stream_first_preview_text = preview_txt
            _stream_preview_printed = True


def _render_completed_message(message: AnyMessage) -> None:
    """Render completed messages to console."""
    if isinstance(message, AIMessage) and message.tool_calls:
        print(f"\nTool calls: {message.tool_calls}")
    if isinstance(message, ToolMessage):
        print(f"\nTool response: {message.content}")


def _render_interrupt(interrupt: Interrupt) -> None:
    """Render interrupt requests to console."""
    for req in interrupt.value["action_requests"]:
        print("\n--- HUMAN APPROVAL REQUIRED ---")
        print(req["description"])


async def run_supervisor_cli(supervisor, user_text: str) -> None:
    """
    Run supervisor agent with CLI streaming and interrupt handling.
    Continues execution loop until all interrupts are resolved.
    """
    final_model_message = None
    final_tool_message = None

    config = {"configurable": {"thread_id": "supervisor_thread_1"}}
    pending_resume: Command | None = None

    while True:
        interrupts: list[Interrupt] = []
        input_payload: Any = pending_resume or {
            "messages": [{"role": "user", "content": user_text}]
        }

        # Stream execution with support for subgraph interrupts
        async for _, stream_mode, data in supervisor.astream(
            input_payload,
            config=config,
            stream_mode=["messages", "updates"],
            subgraphs=True,  # Enable sub-agent interrupt/token support
        ):
            if stream_mode == "messages":
                token, metadata = data
                if isinstance(token, AIMessageChunk):
                    _render_message_chunk(token)

                    # Debug: check for finish reason and safety ratings
                    if token.response_metadata.get("finish_reason"):
                        print(f"\n[DEBUG] Finish Reason: {token.response_metadata.get('finish_reason')}")
                    if token.response_metadata.get("safety_ratings"):
                        print(f"[DEBUG] Safety Ratings: {token.response_metadata.get('safety_ratings')}")

            elif stream_mode == "updates":
                for source, update in data.items():
                    # Skip empty/None updates
                    if update is None:
                        continue

                    # Handle interrupts
                    if source == "__interrupt__":
                        interrupts.extend(update)
                        _render_interrupt(update[0])
                        continue

                    # Normal node updates
                    if isinstance(update, dict) and update.get("messages"):
                        msg = update["messages"][-1]
                        if source == "model":
                            final_model_message = msg
                        elif source == "tools":
                            final_tool_message = msg

                        _render_completed_message(msg)

        # Exit loop if no interrupts remain
        if not interrupts:
            if final_model_message and hasattr(final_model_message, "content"):
                final_text = flatten_content_to_text(final_model_message.content)

                print("\n\n===== FINAL ANSWER =====\n")
                print(final_text)
                print("\n========================\n")

                # Debug: show tool message details
                if final_tool_message and hasattr(final_tool_message, "content"):
                    c = final_tool_message.content
                    if isinstance(c, str):
                        print("\nFINAL TOOL MESSAGE LENGTH:", len(c))
                        print("FINAL TOOL MESSAGE PREVIEW:", c[:300])
                    else:
                        print("\nFINAL TOOL MESSAGE TYPE:", type(c))
                        print("FINAL TOOL MESSAGE PREVIEW:", str(c)[:300])

                print("\n")
                return

        # Collect decisions for all interrupts
        decisions: dict[str, dict[str, list[dict]]] = {}
        for intr in interrupts:
            d = await get_interrupt_decisions_cli(intr)
            decisions[intr.id] = {"decisions": d}

        pending_resume = Command(resume=decisions)


async def _ask(prompt: str) -> str:
    """Async-friendly CLI input."""
    return (await asyncio.to_thread(input, prompt)).strip()


async def get_interrupt_decisions_cli(interrupt: Interrupt) -> list[dict]:
    """
    Collect human decisions for interrupt requests via CLI.
    Returns list of decision dicts matching the order of action_requests.
    
    Supported decision types:
    - approve: {"type": "approve"}
    - reject: {"type": "reject", "message": "..."}
    - edit: {"type": "edit", "edited_action": {"name": "...", "args": {...}}}
    """
    requests = interrupt.value["action_requests"]
    decisions: list[dict] = []

    for i, req in enumerate(requests, start=1):
        print("\n--- HUMAN APPROVAL REQUIRED ---")
        print(f"Request {i}/{len(requests)}")
        print(req["description"])

        # Present decision menu
        while True:
            choice = (await _ask("Choose: [a]pprove / [r]eject / [e]dit ? ")).lower()

            if choice in ("a", "approve"):
                decisions.append({"type": "approve"})
                break

            if choice in ("r", "reject", "n", "no"):
                msg = await _ask("Rejection message (optional): ")
                decisions.append({
                    "type": "reject",
                    "message": msg or "Rejected by human via CLI.",
                })
                break

            if choice in ("e", "edit"):
                # Edit requires both name and args per LangGraph docs
                edited_name = await _ask("Edited tool name (required, e.g. ops_files): ")
                if not edited_name:
                    print("Tool name is required for edit.")
                    continue

                print("Enter edited args as JSON (required).")
                print('Example: {"query": "Write \'o\' to demo2.txt"}')
                edited_args_raw = await _ask("Edited args JSON: ")
                if not edited_args_raw:
                    print("Args JSON is required for edit.")
                    continue

                try:
                    edited_args = json.loads(edited_args_raw)
                except json.JSONDecodeError as e:
                    print(f"Invalid JSON: {e}. Try again.")
                    continue

                decisions.append({
                    "type": "edit",
                    "edited_action": {
                        "name": edited_name,
                        "args": edited_args,
                    },
                })
                break

            print("Invalid choice. Please enter a/r/e.")

    return decisions


#########################################################################
# Main Execution
#########################################################################

async def test_inmemory_multiple_turns(supervisor):
    """Test supervisor with conversational turns to verify persistent memory."""
    # Turn 1: Test query
    await run_supervisor_cli(
        supervisor,
        "say ' slksjfd ksjdf lksjd fsdlkjf skdj' 10 times",
    )

    # Additional turns can be uncommented for extended testing
    # await run_supervisor_cli(
    #     supervisor,
    #     "What was my name?",
    # )


async def main():
    """Initialize agents and run test scenario."""
    supervisor, stack = await build_agents(provider=PROVIDER)
    try:
        await test_inmemory_multiple_turns(supervisor)
    finally:
        await stack.aclose()


if __name__ == "__main__":
    asyncio.run(main())