import logging
import time

from sqlalchemy.exc import SQLAlchemyError

from app.db.database import make_engine
from app.db.search import IndexStore, SOURCES
from app.rag.chunks import index_profile
from app.rag.providers import Embeddings
from app.rag.wiring import open_providers
from app.rag.service import index_source


def main():
    logging.basicConfig(level=logging.INFO)
    with open_providers() as providers:
        run_indexer(providers.embeddings)


def run_indexer(provider: Embeddings):
    if not provider.configured:
        logging.info("Indexing paused until the embedding provider is configured")
        while True:
            time.sleep(60)
    store = IndexStore(make_engine())
    profile = index_profile(provider)
    while True:
        busy = False
        try:
            for kind in SOURCES:
                source = store.candidate(kind, profile)
                if source:
                    index_source(store, source, provider)
                    busy = True
        except SQLAlchemyError:
            logging.exception("Index database unavailable")
            time.sleep(5)
        if not busy:
            time.sleep(2)


if __name__ == "__main__":
    main()
