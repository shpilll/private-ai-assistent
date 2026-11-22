import json
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class KnowledgeTests(unittest.TestCase):
    def http(self, method, path, data=None, expected=200):
        body = json.dumps(data).encode() if data is not None else None
        request = Request(f"http://127.0.0.1:8000/api/{path}", data=body, method=method,
                          headers={"Content-Type": "application/json"})
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            payload = response.read()
            self.assertEqual(response.status, expected, payload)
            return json.loads(payload) if payload else None

    def create(self, resource, **fields):
        result = self.http("POST", resource, fields, 201)
        path = f"{resource}/{result['id']}"
        self.addCleanup(self.remove_if_present, path)
        return path, result["id"]

    def remove_if_present(self, path):
        try:
            with urlopen(Request(f"http://127.0.0.1:8000/api/{path}", method="DELETE"), timeout=5):
                pass
        except HTTPError as error:
            if error.code != 404:
                raise

    def test_crud_for_each_resource(self):
        for resource in ("categories", "projects", "goals", "tasks", "notes"):
            with self.subTest(resource=resource):
                fields = {"body": "Текст заметки"} if resource == "notes" else {}
                path, record_id = self.create(resource, title="Черновик", **fields)
                self.assertEqual(self.http("GET", path)["title"], "Черновик")
                self.assertIsInstance(self.http("GET", f"{resource}?limit=1"), list)
                updated = self.http("PATCH", path, {"title": " Готово "})
                self.assertEqual(updated["id"], record_id)
                self.assertEqual(self.http("GET", path)["title"], "Готово")
                self.http("DELETE", path, expected=204)
                for method in ("GET", "DELETE", "PATCH"):
                    self.http(method, path, {} if method == "PATCH" else None, 404)

    def test_links_and_partial_updates(self):
        category, category_id = self.create("categories", title="Личное")
        project, project_id = self.create("projects", title="Переезд", category_id=category_id)
        goal, goal_id = self.create("goals", title="Закончить к лету", target_date="2027-06-01")
        task, _ = self.create("tasks", title="Заказать коробки", project_id=project_id,
                              goal_id=goal_id, category_id=category_id, due_date="2027-05-10")
        note, _ = self.create("notes", title="Размеры", body="50 × 40", project_id=project_id)
        updated = self.http("PATCH", task, {"status": "done", "priority": "high", "due_date": None})
        self.assertIsNone(updated["due_date"])
        self.assertEqual(updated["project_id"], project_id)
        self.http("DELETE", project, expected=204)
        self.http("DELETE", category, expected=204)
        self.http("DELETE", goal, expected=204)
        updated = self.http("GET", task)
        for field in ("project_id", "category_id", "goal_id"):
            self.assertIsNone(updated[field])
        self.assertEqual(updated["status"], "done")
        self.assertIsNone(self.http("GET", note)["project_id"])
        self.http("PATCH", task, {"title": "Ошибка", "goal_id": goal_id}, 422)
        self.assertEqual(self.http("GET", task)["title"], "Заказать коробки")

    def test_invalid_inputs(self):
        task, _ = self.create("tasks", title="Проверка")
        for fields in ({"status": "closed"}, {"title": "  "}, {"title": None},
                       {"description": None}, {"due_date": "tomorrow"}, {"unknown_field": 1}):
            with self.subTest(fields=fields):
                self.http("PATCH", task, fields, 422)
        self.http("POST", "notes", {"title": "Без текста"}, 422)
        self.http("GET", "tasks?limit=0", expected=422)
