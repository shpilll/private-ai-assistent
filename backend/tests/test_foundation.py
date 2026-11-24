import json
from html.parser import HTMLParser
import unittest
from urllib.parse import urljoin
from urllib.request import urlopen

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from app.db.database import make_engine


class ModuleScripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sources = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "script" and attributes.get("type") == "module" and attributes.get("src"):
            self.sources.append(attributes["src"])


class FoundationTests(unittest.TestCase):
    def test_serves_built_web_app(self):
        base = "http://127.0.0.1:8000/"
        parser = ModuleScripts()
        with urlopen(base, timeout=5) as response:
            self.assertEqual(response.headers.get_content_type(), "text/html")
            parser.feed(response.read().decode())
        self.assertTrue(parser.sources, "Expected a compiled JavaScript entry point")
        for src in parser.sources:
            with urlopen(urljoin(base, src), timeout=5) as response:
                self.assertIn("javascript", response.headers.get_content_type())
                self.assertTrue(response.read(1))

    def test_openapi_stream_and_document_content_types(self):
        with urlopen("http://127.0.0.1:8000/openapi.json", timeout=5) as response:
            paths = json.load(response)["paths"]
        stream = paths["/api/chats/{chat_id}/messages"]["post"]
        document = paths["/api/documents/{source_id}/content"]["get"]
        self.assertEqual(set(stream["responses"]["200"]["content"]), {"application/x-ndjson"})
        self.assertEqual(set(document["responses"]["200"]["content"]), {"text/plain"})

    def test_http_health(self):
        for path, status in [("live", "alive"), ("ready", "ready")]:
            with self.subTest(path=path):
                with urlopen(f"http://127.0.0.1:8000/health/{path}", timeout=5) as response:
                    self.assertEqual(json.load(response), {"status": status})

    def test_database_at_head(self):
        head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
        engine = make_engine()
        try:
            with engine.connect() as connection:
                revision = MigrationContext.configure(connection).get_current_revision()
                self.assertEqual(revision, head)
        finally:
            engine.dispose()
