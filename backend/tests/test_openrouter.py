import json
import unittest
from unittest.mock import patch

import httpx
from openai import OpenAI

from app.rag.openrouter import DEFAULT_EMBEDDER, OpenRouterProvider
from app.rag.providers import ProviderError


class OpenRouterTests(unittest.TestCase):
    def setUp(self):
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test"}, clear=True):
            self.ai = OpenRouterProvider()
        self.assertEqual(str(self.ai.client.base_url), "https://openrouter.ai/api/v1/")
        self.ai.client.close()

    def transport(self, handler):
        self.ai.client = OpenAI(api_key="test", base_url="https://openrouter.ai/api/v1",
                                http_client=httpx.Client(transport=httpx.MockTransport(handler)))
        self.addCleanup(self.ai.client.close)

    def test_embeddings(self):
        def handler(request):
            self.assertEqual(request.url.path, "/api/v1/embeddings")
            payload = json.loads(request.content)
            self.assertEqual(payload["model"], DEFAULT_EMBEDDER)
            self.assertEqual(payload["input_type"], "document")
            self.assertEqual(payload["encoding_format"], "float")
            return httpx.Response(200, json={"data": [
                {"index": i, "embedding": [float(i + 1)] * 2048} for i in (1, 0)
            ]})

        self.transport(handler)
        self.assertEqual(self.ai.embed(["one", "two"], input_type="document"),
                         [[1.0] * 1536, [2.0] * 1536])

    def test_bad_dimensions(self):
        self.transport(lambda request: httpx.Response(200, json={
            "data": [{"index": 0, "embedding": [0.2, 0.3]}]
        }))
        with self.assertRaises(ProviderError):
            self.ai.embed(["question"], input_type="query")

    def test_free_chat(self):
        def handler(request):
            self.assertEqual(request.url.path, "/api/v1/chat/completions")
            payload = json.loads(request.content)
            self.assertEqual(payload["model"], "openrouter/free")
            context = json.loads(payload["messages"][1]["content"])
            self.assertEqual(context["passages"], [{"number": 1, "text": "text"}])
            return httpx.Response(200, json={"choices": [
                {"finish_reason": "stop", "message": {"role": "assistant", "content": "ok [1]"}}
            ]})

        self.transport(handler)
        self.assertEqual(self.ai.answer("question", ["text"]), "ok [1]")

    def test_truncated_answer_is_not_returned_as_complete(self):
        self.transport(lambda request: httpx.Response(200, json={"choices": [
            {"finish_reason": "length", "message": {"role": "assistant", "content": "Only half an answer"}}
        ]}))
        with self.assertRaisesRegex(ProviderError, "did not finish"):
            self.ai.answer("question", ["text"])

    def test_repeated_stream_role_can_be_sent_back_after_tool_call(self):
        def handler(request):
            chunks = []
            for delta, reason in [
                ({"role": "assistant", "tool_calls": [{"index": 0, "id": "t1", "type": "function",
                    "function": {"name": "get_tasks", "arguments": "{"}}]}, None),
                ({"role": "assistant", "tool_calls": [{"index": 0, "function": {"arguments": "}"}}]}, None),
                ({}, "tool_calls"),
            ]:
                chunk = {"id": "stream1", "model": "test", "created": 1, "object": "chat.completion.chunk",
                         "choices": [{"index": 0, "delta": delta, "finish_reason": reason}]}
                chunks.append("data: " + json.dumps(chunk))
            content = "\n\n".join([*chunks, "data: [DONE]", ""])
            return httpx.Response(200, headers={"Content-Type": "text/event-stream"}, text=content)

        self.transport(handler)
        with self.assertRaises(StopIteration) as end:
            next(self.ai.stream_tool_turn([], []))
        reply = end.exception.value
        self.assertEqual(reply["role"], "assistant")
        self.assertEqual(reply["tool_calls"], [{"id": "t1", "type": "function",
                                                "function": {"name": "get_tasks", "arguments": "{}"}}])
