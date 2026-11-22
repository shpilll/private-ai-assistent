from contextlib import contextmanager
from collections.abc import Iterator

from app.rag.openrouter import OpenRouterProvider
from app.rag.providers import Providers


@contextmanager
def open_providers() -> Iterator[Providers]:
    router = OpenRouterProvider()
    try:
        yield Providers(embeddings=router, generator=router, tool_caller=router)
    finally:
        router.close()
