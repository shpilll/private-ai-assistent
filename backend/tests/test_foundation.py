import json
import unittest
from urllib.request import urlopen

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from app.db.database import make_engine


class FoundationTests(unittest.TestCase):
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
