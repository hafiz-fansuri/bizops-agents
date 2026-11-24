from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class Scripted(BaseChatModel):
    """Deterministic stand-in for Ollama: returns queued AIMessages in call order and records every prompt."""
    script: list = []
    seen: list = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kw):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kw):
        self.seen.append(list(messages))
        if not self.script:
            raise AssertionError("scripted model ran out of responses (unexpected extra LLM call)")
        return ChatResult(generations=[ChatGeneration(message=self.script.pop(0))])


def route(agent: str, instruction: str = "do it") -> AIMessage:
    return AIMessage(content=f'{{"next": "{agent}", "instruction": "{instruction}"}}')


FINISH = AIMessage(content='{"next": "FINISH"}')


def call(name: str, args: dict, cid: str = "c1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": cid, "type": "tool_call"}])
