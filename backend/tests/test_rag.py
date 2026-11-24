import json
import os
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema

from app.db.database import Base, make_engine
from app.db.models import Category, Chunk, Document, Note
from app.db.records import Records
from app.db.search import IndexStore
from app.rag.chunks import index_profile, split_text
from app.rag.providers import ProviderError
from app.rag.routes import SearchQuery
from app.rag.service import answer, index_source, retrieve


class FixtureEmbeddings:
    """Known vectors exercise PostgreSQL ordering without an external API call."""
    model = "test-vectors"
    provider_name = "fixture"
    configured = True
    fail = False

    def embed(self, inputs, *, input_type):
        if self.fail:
            raise ProviderError("test failure")
        return [([1, 0] if "синий" in value else [0, 1]) + [0] * 1534 for value in inputs]


class FixtureGenerator:
    def answer(self, question, passages):
        return passages[0]


class RagTests(unittest.TestCase):
    def setUp(self):
        # Roll back the whole private schema, including commits made by repositories.
        engine = make_engine()
        self.addCleanup(engine.dispose)
        conn = engine.connect()
        self.addCleanup(conn.close)
        schema = "rag_test_" + uuid4().hex
        conn.execute(CreateSchema(schema))
        conn.execution_options(schema_translate_map={None: schema})
        Base.metadata.create_all(conn)
        self.session = Session(conn, expire_on_commit=False)
        self.addCleanup(self.session.close)
        self.store = IndexStore(conn)
        self.ai = FixtureEmbeddings()
        self.profile = index_profile(self.ai)

    def index_next(self, kind):
        source = self.store.candidate(kind, self.profile)
        self.assertIsNotNone(source)
        index_source(self.store, source, self.ai)
        return source

    def test_chunk_offsets(self):
        text = ("Личный план на год. " * 300) + "Конец"
        parts = list(split_text(text))
        self.assertGreater(len(parts), 1)
        self.assertEqual(parts[-1].start + len(parts[-1].text), len(text))
        for part in parts:
            self.assertEqual(part.text, text[part.start:part.start + len(part.text)])
        for left, right in zip(parts, parts[1:]):
            self.assertLess(right.start, left.start + len(left.text))

    def test_search_and_source_lifecycle(self):
        category = Records(self.session, Category).create({"title": "Цвет"})
        notes = Records(self.session, Note)
        note = notes.create({"title": "Краска", "body": "синий", "category_id": category.id})
        docs = Records(self.session, Document)
        doc = docs.create({"title": "other.txt", "body": "красный"})
        old = self.index_next("notes")
        self.index_next("documents")
        query = SearchQuery(question="синий", limit=1)
        result = answer(self.store, self.ai, FixtureGenerator(), query)
        self.assertEqual(result["sources"][0]["url"], f"/api/notes/{note.id}")
        self.assertIn("синий", result["answer"])
        doc_query = SearchQuery(question="синий", kind="documents")
        self.assertEqual(retrieve(self.store, self.ai, doc_query)[0]["url"],
                         f"/api/documents/{doc.id}/content")
        doc_query.category_id = category.id
        self.assertEqual(retrieve(self.store, self.ai, doc_query), [])
        scoped = SearchQuery(question="синий", category_id=category.id)
        notes.update(note.id, {"body": "новый цвет"})
        index_source(self.store, old, self.ai)
        self.assertEqual(retrieve(self.store, self.ai, scoped), [])
        self.index_next("notes")
        self.assertEqual(retrieve(self.store, self.ai, scoped)[0]["text"], "новый цвет")
        self.ai.provider_name = "second-provider"
        self.assertEqual(retrieve(self.store, self.ai, scoped), [])
        self.assertIsNotNone(self.store.candidate("notes", index_profile(self.ai)))
        notes.delete(note.id)
        docs.delete(doc.id)
        self.assertEqual(self.session.scalar(select(func.count()).select_from(Chunk)), 0)

    def test_failed_job_can_be_retried(self):
        row = Records(self.session, Note).create({"title": "Test", "body": "body"})
        self.ai.fail = True
        self.index_next("notes")
        self.assertEqual(self.store.status("notes", row.id, self.profile)["state"], "failed")
        self.assertIsNone(self.store.candidate("notes", self.profile))
        self.ai.fail = False
        self.store.requeue("notes", row.id)
        self.index_next("notes")
        self.assertEqual(self.store.status("notes", row.id, self.profile)["state"], "ready")

    def test_late_failure_cannot_erase_a_successful_index(self):
        note = Records(self.session, Note).create({"title": "Delivery", "body": "Wednesday"})
        slow_job = self.store.candidate("notes", self.profile)
        self.index_next("notes")
        self.ai.fail = True
        index_source(self.store, slow_job, self.ai)
        self.assertEqual(self.store.status("notes", note.id, self.profile)["state"], "ready")
        self.ai.fail = False
        hits = retrieve(self.store, self.ai, SearchQuery(question="Delivery"))
        self.assertEqual([hit["text"] for hit in hits], ["Wednesday"])


class DocumentHTTPTests(unittest.TestCase):
    base = "http://127.0.0.1:8000/api"

    def upload(self, path, method, content):
        boundary = uuid4().hex
        data = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
                f"filename=\"file.txt\"\r\nContent-Type: text/plain\r\n\r\n").encode()
        return urlopen(Request(self.base + path, data=data + content + f"\r\n--{boundary}--\r\n".encode(),
                               method=method, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}),
                       timeout=10)

    def test_upload_replace_and_delete(self):
        original = "Текст\r\n".encode("utf-8-sig")
        with self.upload("/documents", "POST", original) as response:
            self.assertEqual(response.status, 201)
            identifier = json.load(response)["id"]
        path = f"/documents/{identifier}"
        try:
            with urlopen(self.base + path + "/content") as response:
                self.assertEqual(response.read(), original)
            with self.upload(path, "PUT", b"replacement") as response:
                self.assertEqual(response.status, 200)
            with urlopen(self.base + f"/index/documents/{identifier}") as response:
                self.assertEqual(json.load(response)["revision"], 2)
            with urlopen(self.base + path + "/content") as response:
                self.assertEqual(response.read(), b"replacement")
        finally:
            with urlopen(Request(self.base + path, method="DELETE")) as response:
                self.assertEqual(response.status, 204)

    def test_invalid_uploads(self):
        for data, status in [(b"\xff", 422), (b"  ", 422), (b"x" * (1024**2 + 1), 413)]:
            with self.assertRaises(HTTPError) as error:
                self.upload("/documents", "POST", data)
            self.assertEqual(error.exception.code, status)

    def test_change_document_category_preserves_content_revision(self):
        headers = {"Content-Type": "application/json"}
        with urlopen(Request(self.base + "/categories", data=b'{"title":"Category test"}', headers=headers)) as r:
            category = json.load(r)["id"]
        self.addCleanup(lambda: urlopen(Request(f"{self.base}/categories/{category}", method="DELETE")).close())
        with self.upload("/documents", "POST", b"category test") as r:
            doc = json.load(r)["id"]
        path = f"{self.base}/documents/{doc}"
        self.addCleanup(lambda: urlopen(Request(path, method="DELETE")).close())
        for value in (category, None):
            data = json.dumps({"category_id": value}).encode()
            with urlopen(Request(path, method="PATCH", headers=headers, data=data)) as r:
                self.assertEqual(json.load(r)["category_id"], value)
        with urlopen(f"{self.base}/index/documents/{doc}") as r:
            self.assertEqual(json.load(r)["revision"], 1)
        with urlopen(path + "/content") as r:
            self.assertEqual(r.read(), b"category test")

    @unittest.skipIf(os.getenv("OPENROUTER_API_KEY"), "Only applies to unconfigured provider")
    def test_missing_provider(self):
        with self.assertRaises(HTTPError) as error:
            urlopen(Request(self.base + "/rag/ask", data=b'{"question":"hello"}',
                            headers={"Content-Type": "application/json"}))
        self.assertEqual(error.exception.code, 503)
