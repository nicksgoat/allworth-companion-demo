"""Vendor-agnostic LLM provider layer.

Swap providers by setting LLM_PROVIDER env var: "anthropic" (default) or "openai".
Also requires the relevant API key: ANTHROPIC_API_KEY or OPENAI_API_KEY.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from allworth_api import config as _config  # noqa: F401  (loads .env first)

# ── Unified types ────────────────────────────────────────────────────────


@dataclass
class ToolCall:
    """A tool invocation request from the model."""
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class StreamEvent:
    """Unified streaming event emitted by all providers."""
    type: str  # "text" | "tool_use_start" | "tool_use_end" | "done"
    data: dict[str, Any]


@dataclass
class CompletionResult:
    """Non-streaming completion result."""
    text: str
    stop_reason: str


# ── Abstract base ────────────────────────────────────────────────────────


class LLMProvider(ABC):
    """Interface every LLM provider must implement."""

    @abstractmethod
    async def stream_with_tools(
        self,
        *,
        model: str,
        system: list[dict] | str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 2048,
    ) -> AsyncIterator[StreamEvent]:
        """Stream a response that may include tool use.

        Yields StreamEvent objects. When the model requests tool use,
        it yields tool_use_start events. After the stream completes,
        yields a "done" event with stop_reason and tool_calls list.
        """
        ...

    @abstractmethod
    async def complete(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict],
        max_tokens: int = 1024,
    ) -> CompletionResult:
        """Non-streaming completion (used for fact extraction, etc.)."""
        ...


# ── Anthropic provider ───────────────────────────────────────────────────


class AnthropicProvider(LLMProvider):
    def __init__(self):
        from anthropic import AsyncAnthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        self._client = AsyncAnthropic(api_key=api_key)

    async def stream_with_tools(
        self,
        *,
        model: str,
        system: list[dict] | str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 2048,
    ) -> AsyncIterator[StreamEvent]:
        async with self._client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            system=system,
            tools=tools,
            messages=messages,
        ) as stream:
            async for event in stream:
                if event.type == "content_block_start" and event.content_block.type == "tool_use":
                    yield StreamEvent("tool_use_start", {"name": event.content_block.name})
                elif event.type == "text":
                    yield StreamEvent("text", {"delta": event.text})
            response = await stream.get_final_message()

        # Collect tool calls from the response
        tool_calls = []
        for block in response.content:
            if block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, input=block.input))

        yield StreamEvent("done", {
            "stop_reason": response.stop_reason,
            "tool_calls": tool_calls,
            "raw_content": response.content,
        })

    def format_tool_results(self, tool_calls: list[ToolCall], results: list[str]) -> dict:
        """Format tool results as an Anthropic user message."""
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": result,
                }
                for tc, result in zip(tool_calls, results, strict=True)
            ],
        }

    async def complete(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict],
        max_tokens: int = 1024,
    ) -> CompletionResult:
        response = await self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        return CompletionResult(text=text, stop_reason=response.stop_reason)


# ── OpenAI provider ──────────────────────────────────────────────────────


def _to_openai_tools(anthropic_tools: list[dict]) -> list[dict]:
    """Convert Anthropic-format tool schemas to OpenAI function-calling format."""
    openai_tools = []
    for t in anthropic_tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        })
    return openai_tools


def _to_openai_messages(system: list[dict] | str, messages: list[dict]) -> list[dict]:
    """Convert system + messages to OpenAI format.

    Anthropic system can be a list of content blocks or a string.
    OpenAI uses a system message at the start.
    Also converts tool_result messages to OpenAI's function role format.
    """
    oai_messages = []

    # System message
    if isinstance(system, str):
        oai_messages.append({"role": "system", "content": system})
    elif isinstance(system, list):
        sys_text = "\n\n".join(
            block["text"] for block in system if isinstance(block, dict) and "text" in block
        )
        oai_messages.append({"role": "system", "content": sys_text})

    # Convert conversation messages
    for msg in messages:
        role = msg["role"]
        content = msg.get("content")

        # Pass through pre-formatted OpenAI messages (assistant with tool_calls, tool messages)
        if role == "assistant" and "tool_calls" in msg and not isinstance(content, list):
            oai_messages.append(msg)
            continue
        if role == "tool":
            oai_messages.append(msg)
            continue

        if role == "user" and isinstance(content, list):
            # Check if this is tool results
            if content and isinstance(content[0], dict) and content[0].get("type") == "tool_result":
                for block in content:
                    oai_messages.append({
                        "role": "tool",
                        "tool_call_id": block["tool_use_id"],
                        "content": block["content"],
                    })
            else:
                # Regular content blocks
                text = " ".join(
                    b["text"] for b in content if isinstance(b, dict) and b.get("type") == "text"
                )
                oai_messages.append({"role": "user", "content": text})
        elif role == "assistant" and isinstance(content, list):
            # Assistant message with potential tool_use blocks
            text_parts = []
            tool_calls = []
            for block in content:
                if hasattr(block, "type"):
                    # Anthropic response object
                    if block.type == "text":
                        text_parts.append(block.text)
                    elif block.type == "tool_use":
                        tool_calls.append({
                            "id": block.id,
                            "type": "function",
                            "function": {
                                "name": block.name,
                                "arguments": json.dumps(block.input),
                            },
                        })
                elif isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        tool_calls.append({
                            "id": block["id"],
                            "type": "function",
                            "function": {
                                "name": block["name"],
                                "arguments": json.dumps(block.get("input", {})),
                            },
                        })
            assistant_msg: dict[str, Any] = {"role": "assistant"}
            if text_parts:
                assistant_msg["content"] = " ".join(text_parts)
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            oai_messages.append(assistant_msg)
        else:
            oai_messages.append({"role": role, "content": content})

    return oai_messages


class OpenAIProvider(LLMProvider):
    def __init__(self):
        from openai import AsyncOpenAI

        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")
        self._client = AsyncOpenAI(api_key=api_key)

    async def stream_with_tools(
        self,
        *,
        model: str,
        system: list[dict] | str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 2048,
    ) -> AsyncIterator[StreamEvent]:
        oai_tools = _to_openai_tools(tools)
        oai_messages = _to_openai_messages(system, messages)

        stream = await self._client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=oai_messages,
            tools=oai_tools,
            stream=True,
        )

        full_text = ""
        tool_calls_acc: dict[int, dict] = {}  # index -> {id, name, arguments}
        finish_reason = None

        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if not delta:
                continue

            if chunk.choices[0].finish_reason:
                finish_reason = chunk.choices[0].finish_reason

            # Text content
            if delta.content:
                full_text += delta.content
                yield StreamEvent("text", {"delta": delta.content})

            # Tool calls (streamed incrementally)
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls_acc:
                        tool_calls_acc[idx] = {"id": "", "name": "", "arguments": ""}
                    if tc_delta.id:
                        tool_calls_acc[idx]["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            tool_calls_acc[idx]["name"] = tc_delta.function.name
                            yield StreamEvent("tool_use_start", {"name": tc_delta.function.name})
                        if tc_delta.function.arguments:
                            tool_calls_acc[idx]["arguments"] += tc_delta.function.arguments

        # Build final tool calls
        final_tool_calls = []
        for idx in sorted(tool_calls_acc):
            tc = tool_calls_acc[idx]
            try:
                args = json.loads(tc["arguments"]) if tc["arguments"] else {}
            except json.JSONDecodeError:
                args = {}
            final_tool_calls.append(ToolCall(id=tc["id"], name=tc["name"], input=args))

        # Map OpenAI finish reasons to our stop_reason
        stop_reason = "tool_use" if finish_reason == "tool_calls" else "end_turn"

        yield StreamEvent("done", {
            "stop_reason": stop_reason,
            "tool_calls": final_tool_calls,
            "raw_content": None,
        })

    def format_tool_results(self, tool_calls: list[ToolCall], results: list[str]) -> dict:
        """Format tool results as OpenAI tool messages (one per call)."""
        # OpenAI expects multiple messages, one per tool call
        # We return a list here; chat_service handles the difference
        return [
            {
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            }
            for tc, result in zip(tool_calls, results, strict=True)
        ]

    async def complete(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict],
        max_tokens: int = 1024,
    ) -> CompletionResult:
        oai_messages = [{"role": "system", "content": system}]
        for msg in messages:
            oai_messages.append({"role": msg["role"], "content": msg["content"]})

        response = await self._client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=oai_messages,
        )
        text = response.choices[0].message.content or ""
        return CompletionResult(text=text, stop_reason=response.choices[0].finish_reason or "stop")


# ── Azure OpenAI provider ────────────────────────────────────────────────


class AzureOpenAIProvider(LLMProvider):
    """Uses Azure OpenAI Service. Requires AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY."""

    def __init__(self):
        from openai import AsyncAzureOpenAI

        api_key = os.environ.get("AZURE_OPENAI_API_KEY", "")
        endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
        api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
        if not api_key:
            raise ValueError("AZURE_OPENAI_API_KEY not set")
        if not endpoint:
            raise ValueError("AZURE_OPENAI_ENDPOINT not set")
        self._client = AsyncAzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
        )

    async def stream_with_tools(
        self,
        *,
        model: str,
        system: list[dict] | str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 2048,
    ) -> AsyncIterator[StreamEvent]:
        oai_tools = _to_openai_tools(tools)
        oai_messages = _to_openai_messages(system, messages)

        stream = await self._client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=oai_messages,
            tools=oai_tools,
            stream=True,
        )

        full_text = ""
        tool_calls_acc: dict[int, dict] = {}
        finish_reason = None

        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if not delta:
                continue

            if chunk.choices[0].finish_reason:
                finish_reason = chunk.choices[0].finish_reason

            if delta.content:
                full_text += delta.content
                yield StreamEvent("text", {"delta": delta.content})

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls_acc:
                        tool_calls_acc[idx] = {"id": "", "name": "", "arguments": ""}
                    if tc_delta.id:
                        tool_calls_acc[idx]["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            tool_calls_acc[idx]["name"] = tc_delta.function.name
                            yield StreamEvent("tool_use_start", {"name": tc_delta.function.name})
                        if tc_delta.function.arguments:
                            tool_calls_acc[idx]["arguments"] += tc_delta.function.arguments

        final_tool_calls = []
        for idx in sorted(tool_calls_acc):
            tc = tool_calls_acc[idx]
            try:
                args = json.loads(tc["arguments"]) if tc["arguments"] else {}
            except json.JSONDecodeError:
                args = {}
            final_tool_calls.append(ToolCall(id=tc["id"], name=tc["name"], input=args))

        stop_reason = "tool_use" if finish_reason == "tool_calls" else "end_turn"

        yield StreamEvent("done", {
            "stop_reason": stop_reason,
            "tool_calls": final_tool_calls,
            "raw_content": None,
        })

    def format_tool_results(self, tool_calls: list[ToolCall], results: list[str]) -> dict:
        return [
            {
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            }
            for tc, result in zip(tool_calls, results, strict=True)
        ]

    async def complete(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict],
        max_tokens: int = 1024,
    ) -> CompletionResult:
        oai_messages = [{"role": "system", "content": system}]
        for msg in messages:
            oai_messages.append({"role": msg["role"], "content": msg["content"]})

        response = await self._client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=oai_messages,
        )
        text = response.choices[0].message.content or ""
        return CompletionResult(text=text, stop_reason=response.choices[0].finish_reason or "stop")


# ── Factory ──────────────────────────────────────────────────────────────

# Model defaults per provider
PROVIDER_DEFAULTS = {
    "anthropic": {
        "chat_model": "claude-opus-4-7",
        "extract_model": "claude-haiku-4-5",
    },
    "openai": {
        "chat_model": "gpt-4o",
        "extract_model": "gpt-4o-mini",
    },
    "azure_openai": {
        "chat_model": "gpt-4o",
        "extract_model": "gpt-4o-mini",
    },
}

_PROVIDER_NAME = os.environ.get("LLM_PROVIDER", "anthropic").lower()


def get_provider() -> LLMProvider | None:
    """Create the configured LLM provider, or None if no API key is set."""
    if _PROVIDER_NAME == "azure_openai":
        if not os.environ.get("AZURE_OPENAI_API_KEY"):
            return None
        return AzureOpenAIProvider()
    elif _PROVIDER_NAME == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            return None
        return OpenAIProvider()
    else:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return None
        return AnthropicProvider()


def get_chat_model() -> str:
    return os.environ.get("LLM_CHAT_MODEL", PROVIDER_DEFAULTS.get(_PROVIDER_NAME, {}).get("chat_model", ""))


def get_extract_model() -> str:
    default = PROVIDER_DEFAULTS.get(_PROVIDER_NAME, {}).get("extract_model", "")
    return os.environ.get("LLM_EXTRACT_MODEL", default)


# Singleton
provider = get_provider()
CHAT_MODEL = get_chat_model()
EXTRACT_MODEL = get_extract_model()
