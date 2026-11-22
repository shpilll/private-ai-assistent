from app.db.search import IndexStore, Snapshot
from app.rag.chunks import index_profile, split_text
from app.rag.providers import Embeddings, Generator, ProviderError


def index_source(store: IndexStore, source: Snapshot, embeddings: Embeddings):
    profile = index_profile(embeddings)
    parts = list(split_text(source.body))
    chunks = []
    try:
        for start in range(0, len(parts), 32):
            batch = parts[start:start + 32]
            vectors = embeddings.embed([part.text for part in batch], input_type="document")
            for part, vector in zip(batch, vectors, strict=True):
                chunks.append({"start": part.start, "text": part.text, "embedding": vector})
    except ProviderError as exc:
        store.publish(source, profile, [], error=str(exc))
        return
    store.publish(source, profile, chunks)


def retrieve(store: IndexStore, embeddings: Embeddings, query):
    vector, = embeddings.embed([query.question], input_type="query")
    matches = store.search(vector, index_profile(embeddings), query.limit, query.category_id, query.kind)
    for match in matches:
        url = f"/api/{match['kind']}/{match['source_id']}"
        match["url"] = url + "/content" if match["kind"] == "documents" else url
    return matches


def answer(store: IndexStore, embeddings: Embeddings, generator: Generator, query):
    sources = retrieve(store, embeddings, query)
    if not sources:
        return {"answer": "По этому запросу в индексе нет доступных фрагментов.", "sources": []}
    result = generator.answer(query.question, [s["title"] + "\n" + s["text"] for s in sources])
    return {"answer": result, "sources": sources}
