import json
import unittest
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.schema import CreateSchema, DropSchema

from app.db.database import Base, make_engine
from app.db.search import IndexStore
from app.main import app
from app.rag.chunks import index_profile
from app.rag.providers import ProviderError
from app.rag.service import index_source


def calls(*items):
    return {"role": "assistant", "tool_calls": [
        {"id": uuid4().hex, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
        for name, args in items
    ]}


class ScriptedModel:
    def __init__(self):
        self.steps = []

    def tool_turn(self, messages, tools):
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return step

    def stream_tool_turn(self, messages, tools):
        self.last_messages = list(messages)
        reply = self.tool_turn(messages, tools)
        for word in reply.get("content", "").split():
            yield "delta", word
        return reply


class AgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "agent_test_" + uuid4().hex
        cls.engine = make_engine().execution_options(schema_translate_map={None: cls.schema})
        with cls.engine.begin() as conn:
            conn.execute(CreateSchema(cls.schema))
            Base.metadata.create_all(conn)
        cls.client = TestClient(app)
        cls.model = ScriptedModel()
        cls.original_state = dict(app.state._state)
        app.state.engine = cls.engine
        app.state.ai = SimpleNamespace(tool_caller=cls.model)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        app.state._state.clear()
        app.state._state.update(cls.original_state)
        with cls.engine.begin() as conn:
            conn.execute(DropSchema(cls.schema, cascade=True))
        cls.engine.dispose()

    def setUp(self):
        app.state.ai.embeddings = SimpleNamespace(
            provider_name="fixture", model="test", embed=lambda inputs, **kw: [[1.0] * 1536]
        )

    def turn(self, *steps, code=200):
        self.model.steps = [*steps, {"role": "assistant", "content": "Готово"}]
        reply = self.client.post("/api/agent/run", json={"message": "тест"})
        self.assertEqual(reply.status_code, code, reply.text)
        return reply.json()

    def test_tools(self):
        row = self.turn(calls(("create_task", {"title": "Первая"}), ("create_goal", {"title": "Цель"}),
                              ("save_note", {"title": "Заметка", "body": "Текст"})))["tools"]
        tid, gid = [event["result"]["id"] for event in row[:2]]
        results = self.turn(calls(("update_task", {"id": tid, "changes": {"goal_id": gid, "status": "done"}}),
                                  ("update_goal", {"id": gid, "changes": {"description": "updated"}}),
                                  ("get_tasks", {}), ("get_projects", {}), ("search_knowledge", {"question": "?"})))
        task, goal, tasks, projects, matches = [entry["result"] for entry in results["tools"]]
        self.assertEqual((task["goal_id"], task["status"]), (gid, "done"))
        self.assertEqual(goal["description"], "updated")
        self.assertIn(tid, [t["id"] for t in tasks])
        self.assertEqual(projects, [])
        self.assertEqual(matches, [])

    def test_delete_needs_separate_decision(self):
        task = self.client.post("/api/tasks", json={"title": "Удалить"}).json()
        path = f"/api/tasks/{task['id']}"

        def propose():
            result = self.turn(calls(("delete_task", {"id": task["id"]})))
            return "/api/agent/confirmations/" + result["confirmations"][0]["id"]

        first = propose()
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.post(first, json={"confirm": False}).json()["status"], "cancelled")
        self.assertEqual(self.client.post(first, json={"confirm": True}).status_code, 404)
        stale = propose()
        self.client.patch(path, json={"title": "Изменилось"})
        self.assertEqual(self.client.post(stale, json={"confirm": True}).status_code, 409)
        self.assertEqual(self.client.get(path).status_code, 200)
        action = propose()
        self.assertEqual(self.client.post(action, json={"confirm": True}).json()["status"], "deleted")
        self.assertEqual(self.client.post(action, json={"confirm": True}).status_code, 404)
        self.assertEqual(self.client.get(path).status_code, 404)

    def test_rollback_on_provider_failure(self):
        before = self.client.get("/api/tasks").json()
        self.turn(calls(("create_task", {"title": "Rollback"})), ProviderError("offline"), code=503)
        self.assertEqual(before, self.client.get("/api/tasks").json())

    def test_validation_and_duplicate_calls(self):
        create = ("create_task", {"title": "only once"})
        trace = self.turn(calls(("execute_sql", {}), ("create_task", {"title": ""}), create, create))
        self.assertIn("error", trace["tools"][0])
        self.assertIn("error", trace["tools"][1])
        self.assertEqual(trace["tools"][2]["result"]["id"], trace["tools"][3]["result"]["id"])

    def test_chat_context_replay_and_stream_failure(self):
        chat_id = self.client.post("/api/chats").json()["id"]
        path = "/api/chats/" + chat_id

        def send(prompt, key):
            r = self.client.post(path + "/messages", json={"message": prompt, "request_id": key})
            return [json.loads(line) for line in r.iter_lines()]

        key = str(uuid4())
        self.model.steps = [calls(("create_task", {"title": "chat task"})), {"content": "Ответ готов"}]
        events = send("Запиши задачу", key)
        self.assertEqual([e["type"] for e in events], ["tool", "delta", "delta", "done"])
        self.assertEqual(send("Запиши задачу", key), [events[-1]])
        self.assertEqual(send("Другой запрос", key)[0]["type"], "error")
        self.model.steps = [{"content": "Помню"}]
        send("Помнишь?", str(uuid4()))
        self.assertEqual(self.model.last_messages[1]["content"], "Запиши задачу")
        self.assertIn("create_task id=", self.model.last_messages[2]["content"])
        self.assertEqual(len(self.client.get(path).json()["turns"]), 2)
        self.model.steps = [calls(("create_goal", {"title": "rolled back"})), ProviderError("offline")]
        before = self.client.get("/api/goals").json()
        self.assertEqual(send("ошибка", str(uuid4()))[-1]["type"], "error")
        self.assertEqual(self.client.get("/api/goals").json(), before)
        self.assertEqual(len(self.client.get(path).json()["turns"]), 2)

    def test_chat_search_links_back_to_uploaded_text(self):
        body = "The orchard team waters the apple trees every Wednesday morning."
        response = self.client.post("/api/documents", files={"file": ("garden.txt", body, "text/plain")})
        self.assertEqual(response.status_code, 201)
        document_id = response.json()["id"]
        self.addCleanup(self.client.delete, f"/api/documents/{document_id}")

        store = IndexStore(self.engine)
        embeddings = app.state.ai.embeddings
        source = store.candidate("documents", index_profile(embeddings))
        self.assertEqual(source.id, document_id)
        index_source(store, source, embeddings)

        question = "When are the apple trees watered?"
        self.model.steps = [
            calls(("search_knowledge", {"question": question, "kind": "documents"})),
            {"content": "Every Wednesday morning."},
        ]
        chat_id = self.client.post("/api/chats").json()["id"]
        chat_path = f"/api/chats/{chat_id}"
        reply = self.client.post(chat_path + "/messages", json={"message": question, "request_id": str(uuid4())})
        events = [json.loads(line) for line in reply.iter_lines()]
        self.assertEqual(events[-1]["type"], "done")
        turn = events[-1]["data"]
        self.assertEqual(turn["answer"], "Every Wednesday morning.")
        hit, = turn["tools"][0]["result"]
        self.assertEqual(hit["source_id"], document_id)
        self.assertEqual(hit["text"], body)
        self.assertEqual(self.client.get(hit["url"]).text, body)
        self.assertIn(body, self.model.last_messages[-1]["content"])
        self.assertEqual(self.client.get(chat_path).json()["turns"], [turn])
