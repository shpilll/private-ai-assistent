from dataclasses import dataclass
from collections.abc import Generator as EventGenerator
from typing import Literal, Protocol

InputType = Literal["query", "document"]


class ProviderError(Exception):
    pass


class Embeddings(Protocol):
    provider_name: str
    model: str
    configured: bool

    def embed(self, inputs: list[str], *, input_type: InputType) -> list[list[float]]: ...


class Generator(Protocol):
    def answer(self, question: str, passages: list[str]) -> str: ...


class ToolCaller(Protocol):
    def tool_turn(self, messages: list[dict], tools: list[dict]) -> dict: ...
    def stream_tool_turn(self, messages: list[dict], tools: list[dict]) -> EventGenerator[tuple[str, str], None, dict]: ...


@dataclass(frozen=True)
class Providers:
    embeddings: Embeddings
    generator: Generator
    tool_caller: ToolCaller
