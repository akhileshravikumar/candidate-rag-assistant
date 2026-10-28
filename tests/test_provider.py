import json

import httpx
from openai import OpenAI

from app.config import DIMENSIONS
from app.models import Answer
from app.providers import Gateway


def test_sdk_embedding_and_structured_response_contract(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    seen = []
    empty = Answer(status="abstained", findings=[], unknowns=[], shortlist=[])

    def handler(request):
        payload = json.loads(request.content)
        seen.append(payload)
        if request.url.path.endswith("/embeddings"):
            assert payload["dimensions"] == DIMENSIONS
            return httpx.Response(200, json={
                "object": "list", "model": payload["model"],
                "data": [{"object": "embedding", "index": 0, "embedding": [1.0] * DIMENSIONS}],
                "usage": {"prompt_tokens": 2, "total_tokens": 2},
            })
        assert payload["store"] is False
        assert payload["text"]["format"]["type"] == "json_schema"
        assert payload["text"]["format"]["strict"] is True
        return httpx.Response(200, json={
            "id": "resp_test", "object": "response", "created_at": 1,
            "model": payload["model"], "status": "completed",
            "output": [{
                "id": "msg_test", "type": "message", "role": "assistant", "status": "completed",
                "content": [{"type": "output_text", "text": empty.model_dump_json(), "annotations": []}],
            }],
        })

    gateway = Gateway()
    gateway.client = OpenAI(api_key="test-only", http_client=httpx.Client(
        transport=httpx.MockTransport(handler)
    ))
    assert len(gateway.embed(["Python"])[0]) == DIMENSIONS
    assert gateway.answer({"question": "Any evidence?"}) == empty
    assert len(seen) == 2