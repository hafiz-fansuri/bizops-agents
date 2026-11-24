from __future__ import annotations

from langchain_ollama import ChatOllama

from bizops.config import Settings


def get_llm(s: Settings, role: str = "worker") -> ChatOllama:
    model = s.supervisor_model if role == "supervisor" and s.supervisor_model else s.model
    # temperature 0: routing/tool calls should be deterministic
    return ChatOllama(model=model, base_url=s.ollama_url, temperature=0, num_ctx=8192)
