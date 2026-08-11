"""
Multi-provider LLM client (Google Gemini + Groq). Every LLM call the agent
makes (PLAN structured output, judgment calls, REFLECT/LEARN synthesis) goes
through here - callers never touch httpx or either provider's wire format
directly. Model IDs are pulled from app/config.py, never hardcoded, so they
can be swapped per stage without a code change.

A model ID prefixed "groq/" (e.g. "groq/llama-3.3-70b-versatile") is routed
to Groq's OpenAI-compatible chat/completions endpoint; anything else is
treated as a Gemini model ID and goes to generateContent. AI_MODEL_FALLBACKS
can freely mix both - see _generate for the cross-provider fallback chain.
"""
from __future__ import annotations

import asyncio
import copy
import json
import logging
import re
from dataclasses import dataclass
from itertools import cycle
from typing import Any, Type

import httpx
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

# A transient network hiccup or slow response shouldn't fail an entire audit
# run - retry connection/timeout errors a couple of times with backoff before
# giving up. Non-2xx responses (bad request, refusal) are not retried here
# since the same request would just fail the same way again - 429 is the one
# exception, handled separately below since it comes with its own wait time.
_MAX_NETWORK_RETRIES = 2
_RETRY_BACKOFF_SECONDS = 2.0

# EXECUTE makes one LLM call per judgment-method plan step, so a single audit
# run can easily exceed a free-tier quota (e.g. Gemini's 20 requests/window)
# well before it exceeds any reasonable per-call timeout. A 429 body usually
# comes with its own suggested wait (Gemini: RetryInfo.retryDelay in the JSON
# body; Groq/most others: a standard Retry-After header) - honor that instead
# of guessing, capped so one stuck quota can't hang a run indefinitely.
_MAX_RATE_LIMIT_RETRIES = 4
_DEFAULT_RATE_LIMIT_BACKOFF_SECONDS = 30.0
_MAX_RATE_LIMIT_BACKOFF_SECONDS = 90.0
_RETRY_DELAY_RE = re.compile(r"([\d.]+)\s*s")

# 5xx (transient overload/outage on the provider's side, e.g. Gemini 503
# "high demand" - no retryDelay is provided for these, unlike 429) - short
# exponential backoff, since these usually clear within seconds rather than
# the ~30s+ a quota window needs.
_RETRYABLE_SERVER_ERROR_STATUSES = {500, 502, 503, 504}
_MAX_SERVER_ERROR_RETRIES = 3
_SERVER_ERROR_BACKOFF_SECONDS = 5.0


def _parse_retry_delay_seconds(resp: httpx.Response) -> float | None:
    """Gemini puts the suggested wait in the JSON error body
    (error.details[].retryDelay, e.g. "35.27s"); most other providers
    (including Groq) use the standard HTTP Retry-After header instead."""
    try:
        details = resp.json().get("error", {}).get("details", [])
    except (ValueError, AttributeError):
        details = []
    for detail in details:
        if not isinstance(detail, dict) or not str(detail.get("@type", "")).endswith("RetryInfo"):
            continue
        match = _RETRY_DELAY_RE.match(str(detail.get("retryDelay", "")))
        if match:
            return float(match.group(1))

    retry_after = resp.headers.get("retry-after")
    if retry_after:
        try:
            return float(retry_after)
        except ValueError:
            pass
    return None


# Schema keywords Gemini's responseSchema (an OpenAPI-schema subset) does not
# document support for. Left in place, these risk the whole request being
# rejected rather than just being ignored - safer to strip them and rely on
# Pydantic's own validation of the parsed response instead.
_UNSUPPORTED_SCHEMA_KEYWORDS = ("minLength", "maxLength", "pattern", "multipleOf", "default")

_FREEFORM_OBJECT_NOTE = (
    ' Return this as a single JSON-encoded object string, e.g. \'{"key": "value"}\' - not a nested JSON object.'
)


class AIProviderError(Exception):
    """The LLM provider returned an error (non-2xx, or a malformed body) -
    from every model in the fallback chain, not just the first one tried."""


class AIRefusalError(Exception):
    """The model declined/blocked the request (prompt-level blockReason, or
    a candidate finishReason of SAFETY/RECITATION/etc. on Gemini; a
    finish_reason of content_filter on Groq)."""

    def __init__(self, category: str | None) -> None:
        self.category = category
        super().__init__(f"Model blocked the request (reason={category!r})")


def _resolve_refs(node: Any, defs: dict) -> Any:
    """Inline every $ref against the schema's own $defs, recursively. Done
    up front rather than relying on the provider to resolve $ref itself -
    none of our schemas are recursive, so a plain inline is always safe and
    sidesteps any doubt about how much of $ref/$defs either provider honors."""
    if isinstance(node, dict):
        if "$ref" in node:
            ref_name = node["$ref"].rsplit("/", 1)[-1]
            return _resolve_refs(copy.deepcopy(defs[ref_name]), defs)
        return {k: _resolve_refs(v, defs) for k, v in node.items() if k != "$defs"}
    if isinstance(node, list):
        return [_resolve_refs(item, defs) for item in node]
    return node


def _simplify_optional(node: Any) -> Any:
    """Pydantic represents `X | None` as `{"anyOf": [<schema for X>, {"type": "null"}]}`.
    Gemini's documented schema subset doesn't confirm anyOf support, so
    collapse that pattern down to just <schema for X> - the field already
    isn't in `required` when it's genuinely optional, which is all the
    "nullability" the API call itself needs; Pydantic still enforces the
    real type (including None) when the response is validated afterward.

    Also strips `additionalProperties` - confirmed live against the real
    Gemini API (not just docs) to be rejected outright with a 400 ("Unknown
    name additionalProperties... Cannot find field"), despite public docs
    listing it as supported."""
    if isinstance(node, dict):
        any_of = node.get("anyOf")
        if isinstance(any_of, list) and len(any_of) == 2:
            non_null = [branch for branch in any_of if branch.get("type") != "null"]
            null_branch = [branch for branch in any_of if branch.get("type") == "null"]
            if len(non_null) == 1 and len(null_branch) == 1:
                merged = {**node, **non_null[0]}
                merged.pop("anyOf", None)
                return _simplify_optional(merged)
        return {
            k: _simplify_optional(v)
            for k, v in node.items()
            if k not in _UNSUPPORTED_SCHEMA_KEYWORDS and k != "additionalProperties"
        }
    if isinstance(node, list):
        return [_simplify_optional(item) for item in node]
    return node


def _stringify_freeform_objects(node: Any) -> Any:
    """Gemini's schema subset doesn't document support for an open-ended
    `object` type with no `properties` (i.e. an arbitrary JSON blob) - and
    that shape is exactly what our `dict[str, Any]` fields (PlanStep's
    target_element, StepResult's evidence) produce. Rather than gamble on
    whether that's accepted, turn any such node into a `string` schema and
    ask the model to return JSON-encoded text there instead; the matching
    _decode_freeform_strings() pass (run against the *pre-stringify*
    resolved schema) converts it back to a real dict afterward. Reused as-is
    for Groq - harmless there (Groq's models handle open object schemas
    fine), and keeping one wire_schema means callers build it once per
    Pydantic model regardless of which provider ends up answering."""
    if isinstance(node, dict):
        if node.get("type") == "object" and "properties" not in node:
            return {"type": "string", "description": (node.get("description") or "") + _FREEFORM_OBJECT_NOTE}
        return {k: _stringify_freeform_objects(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_stringify_freeform_objects(item) for item in node]
    return node


def _decode_freeform_strings(data: Any, resolved_schema: Any) -> Any:
    """Inverse of _stringify_freeform_objects, applied to the parsed
    response: wherever the schema originally called for a free-form object,
    parse the JSON-encoded string the model returned there back into a
    dict, so the result validates against the real Pydantic model."""
    if not isinstance(resolved_schema, dict):
        return data

    schema_type = resolved_schema.get("type")

    if schema_type == "object" and "properties" not in resolved_schema:
        if isinstance(data, dict):
            return data
        if isinstance(data, str) and data.strip():
            try:
                parsed = json.loads(data)
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}

    if schema_type == "object" and isinstance(data, dict):
        properties = resolved_schema.get("properties", {})
        return {
            key: (_decode_freeform_strings(value, properties[key]) if key in properties else value)
            for key, value in data.items()
        }

    if schema_type == "array" and isinstance(data, list):
        item_schema = resolved_schema.get("items", {})
        return [_decode_freeform_strings(item, item_schema) for item in data]

    return data


@dataclass
class StructuredSchema:
    """A Gemini-safe responseSchema plus the pre-stringify resolved schema
    needed to decode any free-form-object fields back out of the response.
    Shared across providers - see _stringify_freeform_objects."""

    wire_schema: dict
    resolved_schema: dict


def build_structured_schema(model_cls: Type[BaseModel]) -> StructuredSchema:
    """Pydantic model -> a provider-safe response schema: $ref/$defs inlined,
    Optional-field anyOf collapsed, and any open-ended `dict[str, Any]`
    field turned into a JSON-encoded string field (see
    _stringify_freeform_objects) - all things Gemini's schema subset
    doesn't document support for, and harmless for Groq."""
    raw = model_cls.model_json_schema()
    defs = raw.get("$defs", {})
    resolved = _simplify_optional(_resolve_refs(raw, defs))
    return StructuredSchema(wire_schema=_stringify_freeform_objects(resolved), resolved_schema=resolved)


# ── Provider routing ────────────────────────────────────────────────────
# "groq/<model>" routes to Groq; anything else is a bare Gemini model ID.
# Lets AI_MODEL_FALLBACKS mix providers in one ordered list without any
# other module needing to know which provider actually served a given call.

def _is_groq_model(model: str) -> bool:
    return model.startswith("groq/")


def _strip_provider_prefix(model: str) -> str:
    return model.split("/", 1)[1] if "/" in model else model


# ── Gemini wire format ──────────────────────────────────────────────────

# GEMINI_API_KEYS can hold several comma-separated keys (e.g. from separate
# free-tier accounts) - rotated round-robin on every call, same rationale as
# _next_groq_key below: spreads retries across quotas instead of hammering
# the one key that just got rate-limited.
_gemini_key_cycle: "cycle[str] | None" = None


def _next_gemini_key() -> str:
    global _gemini_key_cycle
    keys = settings.gemini_api_keys_list
    if not keys:
        raise AIProviderError("GEMINI_API_KEYS is not configured")
    if _gemini_key_cycle is None:
        _gemini_key_cycle = cycle(keys)
    return next(_gemini_key_cycle)


def _build_gemini_request(
    model: str, *, system_prompt: str, user_message: str, schema: StructuredSchema,
    max_tokens: int, thinking_budget: int | None,
) -> tuple[str, dict, dict]:
    generation_config: dict[str, Any] = {
        "maxOutputTokens": max_tokens,
        "responseMimeType": "application/json",
        "responseSchema": schema.wire_schema,
    }
    if thinking_budget is not None:
        generation_config["thinkingConfig"] = {"thinkingBudget": thinking_budget}

    url = f"{settings.GEMINI_BASE_URL}/models/{model}:generateContent"
    headers = {"x-goog-api-key": _next_gemini_key(), "content-type": "application/json"}
    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_message}]}],
        "generationConfig": generation_config,
    }
    return url, headers, payload


def _extract_text_gemini(data: dict) -> str:
    candidates = data.get("candidates") or []
    if not candidates:
        return ""
    parts = (candidates[0].get("content") or {}).get("parts") or []
    for part in parts:
        if "text" in part:
            return part["text"]
    return ""


def _check_for_block_gemini(data: dict) -> None:
    block_reason = (data.get("promptFeedback") or {}).get("blockReason")
    if block_reason:
        raise AIRefusalError(block_reason)

    candidates = data.get("candidates") or []
    if candidates:
        finish_reason = candidates[0].get("finishReason")
        if finish_reason in ("SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT"):
            raise AIRefusalError(finish_reason)


# ── Groq wire format (OpenAI-compatible chat/completions) ──────────────
# response_format is left at the broadly-supported {"type": "json_object"}
# rather than Groq's stricter json_schema mode - not every Groq-hosted model
# documents json_schema support, while json_object is universal across the
# catalog. The schema is embedded in the system prompt instead so the model
# still knows the exact shape to produce; parse_json_loose + Pydantic
# validation downstream catch anything that drifts.
#
# GROQ_API_KEYS can hold several comma-separated keys (e.g. from separate
# free-tier accounts) - rotated round-robin on every call, so retries within
# one _generate_with_model call naturally spread across keys rather than
# hammering the one that just got rate-limited.
_groq_key_cycle: "cycle[str] | None" = None

# Groq's free tier rate-limits by tokens-per-minute (prompt + reserved
# output counted together), not just requests-per-minute - confirmed live
# against this account: openai/gpt-oss-20b/120b cap at 8000 TPM,
# llama-3.1-8b-instant at 6000, llama-3.3-70b-versatile at 12000. Gemini's
# AI_MAX_OUTPUT_TOKENS (16000) is sized for a full ~50-criterion AuditPlan
# and alone exceeds every one of those budgets, so every Groq call would
# get rejected outright (413) before this cap existed. PLAN's real output
# still won't fit even this cap - that's fine, a truncated response (see
# _is_truncated) falls through to the next model in AI_MODEL_FALLBACKS
# instead of returning broken JSON; EXECUTE's small per-step judgments are
# what this cap is actually sized for.
_GROQ_MAX_COMPLETION_TOKENS = 2048


def _next_groq_key() -> str:
    global _groq_key_cycle
    keys = settings.groq_api_keys_list
    if not keys:
        raise AIProviderError("GROQ_API_KEYS is not configured")
    if _groq_key_cycle is None:
        _groq_key_cycle = cycle(keys)
    return next(_groq_key_cycle)


# Groq's "openai/gpt-oss-*" models are reasoning models: they spend output
# tokens on a hidden chain-of-thought before writing the actual answer.
# Confirmed live - with the default (unset) reasoning effort and our tight
# _GROQ_MAX_COMPLETION_TOKENS budget, gpt-oss-20b burned the entire budget
# "thinking" and returned a 400 with an empty failed_generation (no content
# left to write). reasoning_effort="low" fixes it. This param is Groq-model-
# specific though - sending it to a non-reasoning model (e.g. a Llama model)
# gets rejected outright with "reasoning_effort is not supported with this
# model", so it's only ever added for models that need it.
def _is_reasoning_model(model: str) -> bool:
    return "gpt-oss" in model


def _build_groq_request(
    model: str, *, system_prompt: str, user_message: str, schema: StructuredSchema, max_tokens: int,
) -> tuple[str, dict, dict]:
    schema_instructions = (
        "\n\nRespond with a single JSON object only - no markdown fences, no commentary - "
        f"that strictly matches this JSON Schema:\n{json.dumps(schema.wire_schema)}"
    )
    url = f"{settings.GROQ_BASE_URL}/chat/completions"
    headers = {"Authorization": f"Bearer {_next_groq_key()}", "content-type": "application/json"}
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt + schema_instructions},
            {"role": "user", "content": user_message},
        ],
        "response_format": {"type": "json_object"},
        "max_completion_tokens": min(max_tokens, _GROQ_MAX_COMPLETION_TOKENS),
    }
    if _is_reasoning_model(model):
        payload["reasoning_effort"] = "low"
    return url, headers, payload


def _extract_text_groq(data: dict) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""
    return (choices[0].get("message") or {}).get("content") or ""


def _check_for_block_groq(data: dict) -> None:
    choices = data.get("choices") or []
    if choices and choices[0].get("finish_reason") == "content_filter":
        raise AIRefusalError("content_filter")


def _is_truncated(model: str, data: dict) -> bool:
    """True if the model hit its output-token ceiling mid-response - a
    successful (200) call that still can't be used, since the JSON is cut
    off. Most likely on Groq given _GROQ_MAX_COMPLETION_TOKENS is sized for
    small judgment-call outputs, not a full PLAN-sized response."""
    if _is_groq_model(model):
        choices = data.get("choices") or []
        return bool(choices) and choices[0].get("finish_reason") == "length"
    candidates = data.get("candidates") or []
    return bool(candidates) and candidates[0].get("finishReason") == "MAX_TOKENS"


# Once a model's own retries (429/5xx above) are exhausted, these are the
# statuses worth switching models over - a different model (possibly a
# different provider entirely) has its own quota and its own capacity, so a
# fresh one can succeed where the original is stuck. A hard 4xx (bad
# request, auth) would fail identically on any model, so those are not
# fallback triggers - except 413: Groq's small models cap prompt+completion
# tokens together at 8000-12000 TPM (see _GROQ_MAX_COMPLETION_TOKENS), and a
# PLAN-sized prompt (a full page's accessibility tree, easily 10k+ tokens)
# blows straight through that regardless of max_completion_tokens. That's a
# per-model capacity ceiling, not a malformed request - Gemini's models
# further down the chain have a much larger context window and handle the
# same prompt fine, so 413 needs to fall over just like 429/5xx instead of
# failing the whole run on the first undersized model it hits.
_MODEL_FALLBACK_TRIGGER_STATUSES = {413, 429, *_RETRYABLE_SERVER_ERROR_STATUSES}


async def _generate_with_model(
    client: httpx.AsyncClient, model: str, *,
    system_prompt: str, user_message: str, schema: StructuredSchema,
    max_tokens: int, thinking_budget: int | None,
) -> httpx.Response:
    """Runs the network/429/5xx retry loop for one fixed model and returns
    whatever response it ends on (success, or the last failing attempt).

    The request is rebuilt on every attempt, not once up front - that's what
    makes key rotation actually happen per retry (see _next_gemini_key /
    _next_groq_key, both called from inside build_request())."""
    real_model = _strip_provider_prefix(model)
    is_groq = _is_groq_model(model)
    key_count = len(settings.groq_api_keys_list) if is_groq else len(settings.gemini_api_keys_list)
    has_multiple_keys = key_count > 1

    def build_request() -> tuple[str, dict, dict]:
        if is_groq:
            return _build_groq_request(
                real_model, system_prompt=system_prompt, user_message=user_message, schema=schema, max_tokens=max_tokens,
            )
        return _build_gemini_request(
            real_model, system_prompt=system_prompt, user_message=user_message, schema=schema,
            max_tokens=max_tokens, thinking_budget=thinking_budget,
        )

    max_attempts = max(_MAX_NETWORK_RETRIES, _MAX_RATE_LIMIT_RETRIES, _MAX_SERVER_ERROR_RETRIES) + 1

    for attempt in range(max_attempts):
        url, headers, payload = build_request()
        try:
            resp = await client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            if attempt >= _MAX_NETWORK_RETRIES:
                raise AIProviderError(f"Failed to reach the API for {model}: {exc}") from exc
            logger.warning(
                "Request to %s failed (attempt %d/%d): %r - retrying",
                model, attempt + 1, _MAX_NETWORK_RETRIES + 1, exc,
            )
            await asyncio.sleep(_RETRY_BACKOFF_SECONDS * (attempt + 1))
            continue

        if resp.status_code == 429 and attempt < _MAX_RATE_LIMIT_RETRIES:
            if has_multiple_keys:
                # The next attempt's build_request() call already rotates to
                # a fresh key with its own quota - no need to wait out this
                # key's backoff when another one is available immediately.
                logger.warning(
                    "Rate limit hit on %s (attempt %d/%d) - rotating to next %s key",
                    model, attempt + 1, _MAX_RATE_LIMIT_RETRIES + 1, "Groq" if is_groq else "Gemini",
                )
                continue
            delay = min(
                _parse_retry_delay_seconds(resp) or _DEFAULT_RATE_LIMIT_BACKOFF_SECONDS,
                _MAX_RATE_LIMIT_BACKOFF_SECONDS,
            )
            logger.warning(
                "Rate limit hit on %s (attempt %d/%d) - waiting %.1fs before retrying",
                model, attempt + 1, _MAX_RATE_LIMIT_RETRIES + 1, delay,
            )
            await asyncio.sleep(delay)
            continue

        if resp.status_code in _RETRYABLE_SERVER_ERROR_STATUSES and attempt < _MAX_SERVER_ERROR_RETRIES:
            if has_multiple_keys:
                # Rotate to a fresh key immediately - a different key may be
                # routed to a less-loaded server and succeed right away, so
                # there's no reason to wait out the backoff on the same key.
                logger.warning(
                    "Server error %d on %s (attempt %d/%d) - rotating to next %s key",
                    resp.status_code, model, attempt + 1, _MAX_SERVER_ERROR_RETRIES + 1,
                    "Groq" if is_groq else "Gemini",
                )
                continue
            delay = _SERVER_ERROR_BACKOFF_SECONDS * (attempt + 1)
            logger.warning(
                "Server error %d on %s (attempt %d/%d) - waiting %.1fs before retrying",
                resp.status_code, model, attempt + 1, _MAX_SERVER_ERROR_RETRIES + 1, delay,
            )
            await asyncio.sleep(delay)
            continue

        return resp

    return resp


async def _generate(
    *, model: str, system_prompt: str, user_message: str, schema: StructuredSchema,
    max_tokens: int, thinking_budget: int | None,
) -> str:
    models_to_try = [model] + [m for m in settings.AI_MODEL_FALLBACKS if m != model]

    async with httpx.AsyncClient(timeout=settings.AI_REQUEST_TIMEOUT_SECONDS) as client:
        for index, current_model in enumerate(models_to_try):
            is_last_model = index == len(models_to_try) - 1

            try:
                resp = await _generate_with_model(
                    client, current_model,
                    system_prompt=system_prompt, user_message=user_message, schema=schema,
                    max_tokens=max_tokens, thinking_budget=thinking_budget,
                )
            except AIProviderError as exc:
                # _generate_with_model only raises after exhausting its own
                # network-error retries (or a missing API key) for this one
                # model - unreachable is just as much "try the next model"
                # as a 429/5xx response.
                if is_last_model:
                    raise
                logger.warning("Model %s unavailable (%s) - falling back to %s", current_model, exc, models_to_try[index + 1])
                continue

            if resp.is_success:
                # A 200 doesn't guarantee a *usable* response - a model that
                # hit its output-token ceiling mid-JSON still returns 200,
                # just with truncated content parse_json_loose can't use.
                if not is_last_model and _is_truncated(current_model, resp.json()):
                    logger.warning(
                        "Model %s truncated its output - falling back to %s",
                        current_model, models_to_try[index + 1],
                    )
                    continue
                break

            if resp.status_code not in _MODEL_FALLBACK_TRIGGER_STATUSES or is_last_model:
                break

            logger.warning(
                "Model %s exhausted its retries (status %d) - falling back to %s",
                current_model, resp.status_code, models_to_try[index + 1],
            )

    if not resp.is_success:
        raise AIProviderError(f"{current_model} API error {resp.status_code}: {resp.text[:500]}")

    data = resp.json()
    if _is_groq_model(current_model):
        _check_for_block_groq(data)
        return _extract_text_groq(data)
    _check_for_block_gemini(data)
    return _extract_text_gemini(data)


async def complete_structured(
    *,
    model: str,
    system_prompt: str,
    user_message: str,
    schema: StructuredSchema,
    max_tokens: int | None = None,
    thinking_budget: int | None = None,
) -> dict:
    """Structured-output completion: the response is constrained (server-side
    on Gemini via responseSchema; via prompt + response_format on Groq) to
    `schema.wire_schema`. Any free-form-object field the model returned as a
    JSON-encoded string is decoded back into a dict before returning.

    `thinking_budget` only affects Gemini calls (generationConfig.
    thinkingConfig.thinkingBudget, in tokens; -1 lets the model size its own
    reasoning per task). Gemini's "thinking" tokens are drawn from the *same*
    maxOutputTokens budget as the visible response (confirmed live - a
    request with a low maxOutputTokens and no thinking cap spent its entire
    budget on internal reasoning and left nothing for the actual JSON,
    truncating it mid-string). Leave this unset only when `max_tokens` is
    generous enough to absorb an unbounded thinking pass; otherwise always
    set it explicitly."""
    text = await _generate(
        model=model,
        system_prompt=system_prompt,
        user_message=user_message,
        schema=schema,
        max_tokens=max_tokens or settings.AI_MAX_OUTPUT_TOKENS,
        thinking_budget=thinking_budget,
    )
    if not text:
        raise AIProviderError("LLM response had no structured output text part")

    parsed = parse_json_loose(text)
    return _decode_freeform_strings(parsed, schema.resolved_schema)


def parse_json_loose(text: str) -> dict:
    """Structured output should already be exact JSON, but strip any stray
    markdown fences defensively."""
    stripped = text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", stripped, re.DOTALL)
    if match:
        stripped = match.group(1).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise AIProviderError(f"Could not parse structured JSON response: {exc}") from exc
