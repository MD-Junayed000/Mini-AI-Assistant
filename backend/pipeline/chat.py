"""Chat pipeline orchestrator.

Flow:
  1. Acquire per-session lock
  2. Score input for prompt-injection
  3. Compose context blocks from hybrid retrieval
  4. Gate check (sufficient evidence → RAG, else exact fallback)
  5. If tool intent parsed, call the tool and add result to context
  6. Final answer from Ollama Cloud (with retrieval + tool context)
  7. Persist to memory, return
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.errors import RetrieverEmptyError
from backend.llm.client import ChatRequest, OllamaCloudChatClient
from backend.locks import session_lock
from backend.memory import Memory, Message
from backend.observability.logging_config import get_logger
from backend.observability.metrics import ANSWERABILITY, PROMPT_INJECTION, STAGE_LATENCY
from backend.retrieval.gate import evaluate as gate_evaluate
from backend.retrieval.hybrid import retrieve as hybrid_retrieve, Retrieved
from backend.security.injection_guard import score as score_injection
from backend.tools.router import dispatch as dispatch_tool, parse_tool_intent

log = get_logger("pipeline")

_FALLBACK_ANSWER = "I don't know based on the available information."


@dataclass
class ChatResult:
    answer: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    injection_risk: float = 0.0
    fallback_used: bool = False


async def run_chat(
    *,
    session_id: str,
    user_message: str,
    memory: Memory,
) -> ChatResult:
    async with session_lock(session_id):
        # 1. Injection scoring on the user message + any prior context
        #    (we'd add doc-text scoring at /ingest time in production,
        #    but we re-check here for live turns).
        verdict = score_injection(user_message)
        if verdict.is_injection:
            PROMPT_INJECTION.labels(surface="user").inc()
            log.warning("prompt_injection_detected", session=session_id, signals=verdict.signals)
        # Persist user turn regardless.
        await memory.append(Message(session_id=session_id, role="user", content=user_message))

        # 2. Load history (skip the just-appended user turn to keep the
        #    system prompt lean — it goes in as the final user message).
        history_docs = await memory.history(session_id=session_id, limit=20)
        history = [
            {"role": d["role"], "content": d["content"]}
            for d in history_docs
            if d.get("role") in ("user", "assistant")
        ]
        if history and history[-1]["role"] == "user" and history[-1]["content"] == user_message:
            history = history[:-1]

        # 3. Try to parse a tool intent directly from the user message.
        #    Cheap shortcut for short messages.
        try:
            early_tool = parse_tool_intent(user_message)
        except Exception:  # noqa: BLE001
            early_tool = None

        tool_calls_made: list[dict[str, Any]] = []
        extra_context_blocks: list[str] = []

        if early_tool is not None:
            with STAGE_LATENCY.labels(stage="tool").time():
                result = dispatch_tool(early_tool)
            tool_calls_made.append({"tool": early_tool.name, "args": early_tool.args, "result": result})
            extra_context_blocks.append(
                f"[tool-result {early_tool.name}] {result!r}"
            )

        # 4. Always retrieve, to feed the LLM with grounded context for
        #    both RAG-style answers and tool-result summaries.
        with STAGE_LATENCY.labels(stage="retrieve_rerank").time():
            retrieved: list[Retrieved] = await hybrid_retrieve(user_message, top_k=8)

        gate = gate_evaluate(retrieved)
        context_blocks: list[str] = list(extra_context_blocks)
        sources: list[dict[str, Any]] = []
        for i, r in enumerate(retrieved[:6]):
            context_blocks.append(f"[doc-{i + 1}] {r.text}")
            sources.append(
                {
                    "id": r.id,
                    "preview": r.text[:160],
                    "metadata": r.metadata,
                    "rerank_score": r.rerank_score,
                }
            )

        if not gate.is_sufficient and not tool_calls_made:
            answer = _FALLBACK_ANSWER
            ANSWERABILITY.labels(decision="fallback").inc()
            await memory.append(
                Message(
                    session_id=session_id,
                    role="assistant",
                    content=answer,
                    metadata={"gate": gate.signals, "fallback": True},
                )
            )
            return ChatResult(
                answer=answer,
                sources=sources,
                tool_calls=tool_calls_made,
                evidence={"gate": gate.signals, "gate_decision": gate.decision},
                injection_risk=verdict.score,
                fallback_used=True,
            )

        # 5. Ask the LLM.
        try:
            client = OllamaCloudChatClient()
            with STAGE_LATENCY.labels(stage="llm_chat").time():
                resp = await client.chat(
                    ChatRequest(
                        user=user_message,
                        history=history,
                        context_blocks=context_blocks,
                    )
                )
            answer = resp.text
        except Exception as e:  # noqa: BLE001
            log.error("llm_chat_failed", error=str(e))
            # If we have a tool result, surface it instead of crashing.
            if tool_calls_made:
                return ChatResult(
                    answer=_format_tool_summary(tool_calls_made),
                    sources=sources,
                    tool_calls=tool_calls_made,
                    evidence={"gate": gate.signals, "gate_decision": gate.decision},
                    injection_risk=verdict.score,
                    fallback_used=False,
                )
            raise RetrieverEmptyError("llm_chat_failed") from e

        # If the LLM replied with a tool intent (model-decided), run it.
        try:
            late_tool = parse_tool_intent(answer)
        except Exception:  # noqa: BLE001
            late_tool = None
        if late_tool is not None and not tool_calls_made:
            with STAGE_LATENCY.labels(stage="tool").time():
                result = dispatch_tool(late_tool)
            tool_calls_made.append({"tool": late_tool.name, "args": late_tool.args, "result": result})
            answer = _format_tool_summary(tool_calls_made)

        await memory.append(
            Message(
                session_id=session_id,
                role="assistant",
                content=answer,
                metadata={"gate": gate.signals, "tool_calls": tool_calls_made},
            )
        )

        return ChatResult(
            answer=answer,
            sources=sources,
            tool_calls=tool_calls_made,
            evidence={
                "gate": gate.signals,
                "gate_decision": gate.decision,
                "model": resp.model,
                "fallback_used": resp.fallback_used,
            },
            injection_risk=verdict.score,
            fallback_used=False,
        )


def _format_tool_summary(calls: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for c in calls:
        lines.append(f"**{c['tool']}**:")
        v = c["result"]
        if isinstance(v, list):
            for row in v[:5]:
                lines.append(f"- {row}")
        elif isinstance(v, dict):
            for k, val in v.items():
                lines.append(f"- {k}: {val}")
        else:
            lines.append(f"- {v}")
    return "\n".join(lines)