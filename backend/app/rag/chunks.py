from dataclasses import dataclass

from app.rag.providers import Embeddings

SIZE = 1200
OVERLAP = 160


def index_profile(embeddings: Embeddings) -> str:
    return f"{embeddings.provider_name}:{embeddings.model}:1536:char-v1:{SIZE}:{OVERLAP}"


@dataclass(frozen=True)
class Passage:
    start: int
    text: str


def split_text(body: str):
    start = 0
    while start < len(body):
        end = min(start + SIZE, len(body))
        if end < len(body):
            boundary = body.rfind(" ", start + SIZE // 2, end)
            if boundary != -1:
                end = boundary + 1
        part = body[start:end]
        if part.strip():
            yield Passage(start, part)
        if end == len(body):
            break
        start = end - OVERLAP
