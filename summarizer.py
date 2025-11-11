"""Generate long- and short-form content for collected news articles."""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Iterable, Optional

from openai import OpenAI

LOGGER = logging.getLogger(__name__)


@dataclass
class ArticleForSummary:
    """Minimal representation of an article for content generation."""

    title: str
    summary: str
    link: Optional[str]


@dataclass
class GeneratedContent:
    """Structured response from the language model."""

    social: str
    blog: str


class SummarizationError(RuntimeError):
    """Raised when summary generation fails for all attempted entries."""


class SocialSummarizer:
    """Wrapper around the OpenAI API to build both social and blog content."""

    def __init__(
        self,
        client: OpenAI,
        *,
        model: str = "gpt-4o-mini",
        temperature: float = 0.4,
        max_retries: int = 3,
        retry_delay: float = 2.0,
    ) -> None:
        self._client = client
        self._model = model
        self._temperature = temperature
        self._max_retries = max_retries
        self._retry_delay = retry_delay

    @classmethod
    def from_env(cls) -> Optional["SocialSummarizer"]:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return None
        client = OpenAI(api_key=api_key)
        return cls(client)

    def enrich_entries(self, entries: Iterable[dict]) -> int:
        """Mutate entries in-place by adding social and blog content when possible."""

        generated = 0
        failures: list[str] = []
        for entry in entries:
            article = ArticleForSummary(
                title=entry.get("title", ""),
                summary=entry.get("summary", ""),
                link=entry.get("link"),
            )
            if not article.title:
                continue

            try:
                content = self._create_content(article)
            except Exception as exc:  # pragma: no cover - defensive logging
                LOGGER.warning("Failed to generate content for '%s': %s", article.title, exc)
                failures.append(article.title or "(untitled)")
                continue

            if not content.social or not content.blog:
                continue

            entry["social_summary"] = content.social
            entry["blog_post"] = content.blog
            generated += 1

        if failures and generated == 0:
            unique_failures = sorted(set(failures))
            joined = ", ".join(unique_failures[:5])
            extra = "" if len(unique_failures) <= 5 else ", …"
            raise SummarizationError(
                "Unable to generate summaries for any article (attempted: "
                f"{joined}{extra})"
            )

        return generated

    def _create_content(self, article: ArticleForSummary) -> GeneratedContent:
        prompt = self._build_prompt(article)

        delay = self._retry_delay
        for attempt in range(1, self._max_retries + 1):
            try:
                response = self._create_response(prompt)
            except Exception as exc:  # pragma: no cover - network failure
                if attempt == self._max_retries:
                    raise
                LOGGER.debug(
                    "OpenAI call failed (attempt %d/%d): %s", attempt, self._max_retries, exc
                )
                time.sleep(delay)
                delay *= 2
                continue

            message = self._extract_response_text(response)
            if not message:
                continue

            parsed = self._parse_model_response(message)
            if not parsed:
                continue

            social = (parsed.get("social_post") or "").strip()
            blog = (parsed.get("blog_post") or "").strip()

            if not self._is_valid_social(social):
                LOGGER.debug("Social post failed validation; retrying")
                continue
            if not self._is_valid_blog(blog):
                LOGGER.debug("Blog post failed validation; retrying")
                continue

            return GeneratedContent(social=social, blog=blog)

        raise RuntimeError("Unable to generate content that satisfies constraints")

    def _create_response(self, prompt: str):
        """Issue a generation request using the most modern OpenAI API available."""

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an experienced technology journalist who writes natural, human-sounding "
                    "English prose without using emoji. Always follow length requirements precisely."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        if hasattr(self._client, "responses"):
            base_kwargs = {
                "model": self._model,
                "temperature": self._temperature,
            }
            response_format = {"type": "json_object"}

            # The OpenAI SDK has evolved quickly; try multiple permutations to
            # support both ``messages`` (legacy) and ``input`` (modern) payloads
            # as well as optional ``response_format`` support.
            attempts = [
                {"messages": messages, "response_format": response_format},
                {"messages": messages},
                {"input": self._messages_to_responses_input(messages), "response_format": response_format},
                {"input": self._messages_to_responses_input(messages)},
            ]

            last_error: Optional[Exception] = None
            for extra in attempts:
                try:
                    return self._client.responses.create(**base_kwargs, **extra)
                except TypeError as exc:
                    # Only continue when the error is caused by unsupported
                    # keyword arguments; re-raise other ``TypeError`` instances.
                    if not any(keyword in str(exc) for keyword in ("messages", "input", "response_format")):
                        raise
                    last_error = exc
                    continue

            if last_error:
                raise last_error

        # Fallback to the legacy Chat Completions API for older client versions.
        return self._client.chat.completions.create(
            model=self._model,
            temperature=self._temperature,
            response_format={"type": "json_object"},
            messages=messages,
        )

    @staticmethod
    def _extract_response_text(response: object) -> str:
        """Normalize text extraction across Responses and Chat Completions payloads."""

        if response is None:
            return ""

        text = getattr(response, "output_text", None)
        if isinstance(text, str) and text.strip():
            return text

        output = getattr(response, "output", None)
        if output:
            fragments: list[str] = []
            for item in output:
                for content in getattr(item, "content", []) or []:
                    piece = getattr(content, "text", None)
                    if piece:
                        fragments.append(piece)
            if fragments:
                return "".join(fragments)

        choices = getattr(response, "choices", None)
        if choices:
            first = choices[0]
            message = getattr(first, "message", None)
            if message and getattr(message, "content", None):
                content = message.content
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    return "".join(str(part) for part in content if part)
            text = getattr(first, "text", None)
            if isinstance(text, str):
                return text

        return ""

    @staticmethod
    def _parse_model_response(message: str) -> Optional[dict]:
        """Attempt to parse a JSON object from the model output."""

        if not message:
            return None

        try:
            return json.loads(message)
        except json.JSONDecodeError:
            LOGGER.debug("Received non-JSON response; attempting to extract JSON body")

        start = message.find("{")
        end = message.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None

        try:
            return json.loads(message[start : end + 1])
        except json.JSONDecodeError:
            LOGGER.debug("Unable to recover JSON payload from model response")
            return None

    def _build_prompt(self, article: ArticleForSummary) -> str:
        base = article.summary or ""
        link_segment = f"URL: {article.link}\n" if article.link else ""
        return (
            "Write two distinct English outputs based on the article below.\n"
            "1. Social media post: fewer than 150 words, concise yet vivid, avoiding bullet lists and emojis.\n"
            "2. Blog post: at least 400 words, structured with paragraphs and subheadings that feel naturally written by a human editor.\n"
            "Ensure both pieces avoid hashtags and marketing clichés.\n"
            "Respond in strict JSON format with keys 'social_post' and 'blog_post'.\n"
            f"Title: {article.title}\n"
            f"Summary: {base}\n"
            f"{link_segment}"
        )

    @staticmethod
    def _is_valid_social(content: str) -> bool:
        if not content:
            return False
        if any(ord(char) >= 0x1F300 for char in content):
            return False
        word_count = len(content.split())
        return word_count < 150

    @staticmethod
    def _is_valid_blog(content: str) -> bool:
        if not content:
            return False
        if any(ord(char) >= 0x1F300 for char in content):
            return False
        word_count = len(content.split())
        return word_count >= 400

    @staticmethod
    def _messages_to_responses_input(messages: list[dict]) -> list[dict]:
        """Convert chat-style messages to the Responses API ``input`` format."""

        converted: list[dict] = []
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            if isinstance(content, list):
                # Already in the structured format expected by the new API.
                converted.append({"role": role, "content": content})
            else:
                converted.append({"role": role, "content": str(content)})
        return converted


__all__ = ["SocialSummarizer", "SummarizationError"]
