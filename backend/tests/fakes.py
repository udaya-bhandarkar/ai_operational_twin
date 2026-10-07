"""Test doubles: a scripted chat model that lets the real graph run with no API calls."""
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class ScriptedChatModel(BaseChatModel):
    """Returns the given AIMessages in order; accepts tool binding (create_agent needs it).

    `replies` is a plain list consumed front-to-back. Middleware may shallow-copy the model
    (request.override), and a shared list survives that where an iterator does not.
    """

    replies: list
    calls: list = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.calls.append(list(messages))
        if not self.replies:
            raise AssertionError("ScriptedChatModel ran out of replies")
        return ChatResult(generations=[ChatGeneration(message=self.replies.pop(0))])

    def bind_tools(self, tools, **kwargs):
        return self


def scripted_model(*replies: AIMessage) -> ScriptedChatModel:
    return ScriptedChatModel(replies=list(replies), calls=[])


def tool_call(name: str, args: dict, call_id: str = "call_1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])
