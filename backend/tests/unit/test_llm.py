from __future__ import annotations

import json

import pytest

from app.llm.cache import LlmCache
from app.llm.client import (
    DataZoneViolation,
    ExtractionFailed,
    LlmBackend,
    StructuredLlm,
    extract_json,
    load_prompt,
)
from app.llm.schemas import PriorExtraction


class Sequence(LlmBackend):
    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self.seen: list[list[dict]] = []

    def complete(self, model, messages, max_tokens, json_mode):  # noqa: ANN001
        self.seen.append(messages)
        return self.replies.pop(0)


def llm(replies: list[str], tmp_path) -> tuple[StructuredLlm, Sequence]:
    backend = Sequence(replies)
    return StructuredLlm(backend, cache=LlmCache(tmp_path / "cache")), backend


GOOD = json.dumps({"references": [{"modality": "CT", "quote": "q", "confidence": 0.8}]})


def test_extract_json_handles_fences_and_prose():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Here it is: {"a": 1} thanks') == {"a": 1}
    with pytest.raises(json.JSONDecodeError):
        extract_json("no json at all")


def test_prompts_have_a_version_line():
    for name in ("extract_priors", "extract_planned"):
        version, body = load_prompt(name)
        assert version and "JSON" in body


def test_report_text_is_refused_for_non_eu_deployments(tmp_path):
    client, backend = llm([GOOD], tmp_path)
    with pytest.raises(DataZoneViolation):
        client.run("extract_priors", "text", PriorExtraction, model="gpt-6-astra-global")
    assert backend.seen == []
    client.run("extract_priors", "text", PriorExtraction, model="gpt-6-luna-dz-eu")
    assert len(backend.seen) == 1


def test_invalid_reply_is_retried_once_with_the_error_then_fails(tmp_path):
    client, backend = llm(["not json", "still not json"], tmp_path)
    with pytest.raises(ExtractionFailed):
        client.run("extract_priors", "text", PriorExtraction)
    assert len(backend.seen) == 2 and "invalid" in backend.seen[1][-1]["content"]


def test_retry_can_recover(tmp_path):
    client, backend = llm(["oops", GOOD], tmp_path)
    result = client.run("extract_priors", "text", PriorExtraction)
    assert result.references[0].modality == "CT" and len(backend.seen) == 2


def test_out_of_range_confidence_is_clamped_and_results_are_cached(tmp_path):
    reply = json.dumps({"references": [{"quote": "q", "confidence": 7}]})
    client, backend = llm([reply], tmp_path)
    assert client.run("extract_priors", "same", PriorExtraction).references[0].confidence == 1.0
    assert client.run("extract_priors", "same", PriorExtraction).references[0].confidence == 1.0
    assert len(backend.seen) == 1
