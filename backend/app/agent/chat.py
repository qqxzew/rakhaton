"""Coordinator Q&A agent over one case (IRIS Core Track, T089).

The LLM answers by calling the tools in `app.agent.tools` (native tool calling; if the deployment rejects
`tools`, a JSON plan-and-execute loop with the same tools is used). Every reply lists the tools called and
the source ids used. Treatment and diagnosis questions are refused (hard rule 4).
"""

from __future__ import annotations

import json
import random
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from app.agent import tools as agent_tools
from app.config import get_settings
from app.llm.client import LlmAuthError, LlmError, extract_json
from app.logging import get_logger

log = get_logger(__name__)

MAX_STEPS = 5
MAX_TOOL_CHARS = 12000
REFUSAL = (
    "Na dotazy týkající se léčby nebo diagnózy neodpovídám. Systém pouze strukturuje informace a hledá "
    "chybějící snímky; klinické rozhodnutí je vždy na lékaři."
)
_ADVICE = re.compile(
    r"(jak\w*\s+(m[áa]m\s+)?l[ée][čc]it|jak[ouée]+\s+l[ée][čc]b|doporu[čc]\w*\s+(l[ée][čc]b|terapi|l[ée]k)|"
    r"jak[áa]\s+je\s+diagn[óo]z|diagnostikuj|stanov\w*\s+diagn[óo]z|p[řr]edepi\w*|d[áa]vkov[áa]n[íi]|"
    r"what\s+(treatment|therapy|drug)|should\s+we\s+treat|which\s+diagnosis)",
    re.IGNORECASE,
)

SYSTEM_PROMPT = """You are an assistant for a hospital imaging coordinator preparing a tumor board (MDT).
You answer questions about ONE case: {case_id} (patient {patient_id}). Use the tools to look facts up;
never guess. Typical tools: case_overview (required studies, reasons, availability, holding site, evidence
quotes), fhir_search (studies at Motol or simulated hospitals nnh, homolka, fnm), vector_search (report chunks),
request_status, sql_query. Always call case_overview first for questions about required or missing studies.
Rules:
- Answer in Czech, briefly (max about 120 words), structured, citing source ids from the tool results.
- You structure information and locate missing imaging only. NEVER suggest a diagnosis or a treatment; if asked,
  refuse in one sentence.
- Hospitals, PACS availability and replies shown by the tools may be simulations; say "simulace" when the tool
  result says simulated.
- You may create a draft task (create_task_draft) only if the user explicitly asks; it is never sent.
- Do not repeat patient identifiers more than needed; never invent ids.
Final answer format: a JSON object {{"answer": "...", "sources": ["ids you used"]}}."""

JSON_PROTOCOL = """
Tool protocol (this deployment has no native tool calling). Each turn reply with ONE JSON object:
- to call tools: {{"tool_calls": [{{"name": "...", "arguments": {{...}}}}]}}
- to finish: {{"answer": "...", "sources": ["..."]}}
Available tools (JSON schemas):
{specs}"""


@dataclass
class ModelTurn:
    text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)  # {"id", "name", "arguments": dict}


class ChatModel(ABC):
    @abstractmethod
    def step(self, messages: list[dict], specs: list[dict]) -> ModelTurn:
        """One model turn given the conversation and the tool specs."""


class GatewayChatModel(ChatModel):
    def __init__(self, model: str | None = None, sleep=time.sleep):  # noqa: ANN001
        from openai import OpenAI

        s = get_settings()
        if not s.api_key:
            raise LlmAuthError("API_KEY is not set in .env")
        self.model = model or s.llm_model_extract
        if not self.model.endswith("-dz-eu"):
            raise LlmError("agent requires an EU data-zone deployment (-dz-eu)")
        self._client = OpenAI(base_url=s.llm_base_url, api_key="unused",
                              default_headers={"api-key": s.api_key}, max_retries=0)
        self._sleep = sleep
        self.native_tools = True

    def step(self, messages: list[dict], specs: list[dict]) -> ModelTurn:
        import openai

        use_tools = self.native_tools
        for attempt in range(6):
            kwargs: dict[str, Any] = {"model": self.model, "messages": messages, "max_completion_tokens": 2000}
            if use_tools:
                kwargs["tools"] = [{"type": "function", "function": spec} for spec in specs]
            try:
                msg = self._client.chat.completions.create(**kwargs).choices[0].message
            except openai.RateLimitError:
                self._sleep(min(60.0, 2.0**attempt) + random.uniform(0, 1))
                continue
            except (openai.AuthenticationError, openai.PermissionDeniedError) as exc:
                raise LlmAuthError("gateway rejected the credentials") from exc
            except openai.BadRequestError as exc:
                if use_tools:
                    self.native_tools = use_tools = False
                    raise _ToolsUnsupported from exc
                raise LlmError(f"bad request to deployment {self.model}") from exc
            except (openai.APIConnectionError, openai.APITimeoutError, openai.InternalServerError):
                self._sleep(min(30.0, 2.0**attempt))
                continue
            calls = []
            for tc in msg.tool_calls or []:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                calls.append({"id": tc.id, "name": tc.function.name,
                              "arguments": args if isinstance(args, dict) else {}})
            return ModelTurn(text=msg.content or "", tool_calls=calls)
        raise LlmError("gateway unavailable or rate limited")


class _ToolsUnsupported(Exception):
    pass


class ChatResult(BaseModel):
    answer: str
    tools_called: list[dict[str, Any]]
    sources: list[str]
    refused: bool = False
    simulated: bool = True
    mode: str = "native"


def is_advice_request(question: str) -> bool:
    return bool(_ADVICE.search(question))


def _scope_arguments(name: str, args: dict[str, Any], case_id: str, patient_id: str) -> dict[str, Any]:
    """The agent works on one case: pin case and patient ids so the model cannot wander to other patients."""
    out = dict(args)
    if name == "case_overview":
        out["case_id"] = case_id
    if name in ("vector_search", "create_task_draft"):
        out["patient_id"] = patient_id
    if name == "create_task_draft":
        out["case_id"] = case_id
    return out


def _short_args(args: dict[str, Any]) -> dict[str, Any]:
    return {k: (v if len(json.dumps(v, default=str)) < 120 else "…") for k, v in args.items()}


def _parse_final(text: str) -> tuple[str, list[str]] | None:
    try:
        data = extract_json(text)
    except (json.JSONDecodeError, ValueError):
        return None
    if "answer" not in data:
        return None
    sources = data.get("sources") or []
    return str(data["answer"]), [str(s) for s in sources if isinstance(s, str | int)]


def run_chat(case_id: str, patient_id: str, question: str, model: ChatModel) -> ChatResult:
    if is_advice_request(question):
        return ChatResult(answer=REFUSAL, tools_called=[], sources=[], refused=True)

    specs = agent_tools.TOOL_SPECS
    system = SYSTEM_PROMPT.format(case_id=case_id, patient_id=patient_id)
    messages: list[dict] = [{"role": "system", "content": system}, {"role": "user", "content": question}]
    mode = "native"
    if getattr(model, "native_tools", True) is False:
        mode = "json-plan"
        messages[0] = {"role": "system", "content": system + JSON_PROTOCOL.format(specs=json.dumps(specs))}
    called: list[dict[str, Any]] = []
    available_sources: list[str] = []
    answer: tuple[str, list[str]] | None = None

    for _ in range(MAX_STEPS):
        try:
            turn = model.step(messages, specs)
        except _ToolsUnsupported:
            mode = "json-plan"
            messages[0] = {"role": "system", "content": system + JSON_PROTOCOL.format(specs=json.dumps(specs))}
            continue
        if mode == "json-plan" or getattr(model, "native_tools", True) is False:
            mode = "json-plan"
            parsed_calls = _json_calls(turn.text)
            if parsed_calls is not None:
                turn = ModelTurn(text="", tool_calls=parsed_calls)
        if turn.tool_calls:
            if mode == "native":
                messages.append({"role": "assistant", "content": turn.text or None, "tool_calls": [
                    {"id": c["id"], "type": "function",
                     "function": {"name": c["name"], "arguments": json.dumps(c["arguments"])}}
                    for c in turn.tool_calls]})
            else:
                messages.append({"role": "assistant", "content": turn.text or json.dumps({"tool_calls": [
                    {"name": c["name"], "arguments": c["arguments"]} for c in turn.tool_calls]})})
            results = []
            for call in turn.tool_calls:
                args = _scope_arguments(call["name"], call["arguments"], case_id, patient_id)
                result = agent_tools.call_tool(call["name"], args)
                called.append({"name": call["name"], "arguments": _short_args(args),
                               "ok": "error" not in result})
                available_sources += result.get("sources", [])
                results.append((call, json.dumps(result, ensure_ascii=False, default=str)[:MAX_TOOL_CHARS]))
            if mode == "native":
                messages += [{"role": "tool", "tool_call_id": c["id"], "content": r} for c, r in results]
            else:
                messages.append({"role": "user", "content": "Tool results:\n" + "\n".join(
                    f"{c['name']}: {r}" for c, r in results)})
            continue
        answer = _parse_final(turn.text) or (turn.text.strip(), [])
        break

    if answer is None:
        return ChatResult(answer="Na dotaz se nepodařilo odpovědět v limitu kroků.", tools_called=called,
                          sources=[], mode=mode)
    text, cited = answer
    pool = list(dict.fromkeys(available_sources))
    used = [s for s in cited if s in pool] or ([] if not called else pool[:10])
    return ChatResult(answer=text, tools_called=called, sources=used, mode=mode)


def _json_calls(text: str) -> list[dict[str, Any]] | None:
    try:
        data = extract_json(text)
    except (json.JSONDecodeError, ValueError):
        return None
    calls = data.get("tool_calls")
    if not isinstance(calls, list) or not calls:
        return None
    return [{"id": f"call{i}", "name": str(c.get("name", "")),
             "arguments": c.get("arguments") if isinstance(c.get("arguments"), dict) else {}}
            for i, c in enumerate(calls) if isinstance(c, dict)]
