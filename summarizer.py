"""Generate long- and short-form content for collected news articles."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Iterable, Optional

from openai import APIError, OpenAI

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


class GenerationFailure(RuntimeError):
    """Base exception that carries structured failure details for logging."""

    def __init__(self, message: str, *, details: Optional[dict] = None) -> None:
        super().__init__(message)
        self.details = details or {}


class ValidationFailure(GenerationFailure):
    """Raised when model output does not satisfy validation requirements."""

    def __init__(self, kind: str, reason: str, content: str) -> None:
        preview_lines = content.strip().splitlines() if content else []
        preview_text = " ".join(line.strip() for line in preview_lines[:3] if line.strip())
        if len(preview_text) > 240:
            preview_text = preview_text[:237] + "..."
        word_count = len(content.split()) if content else 0
        details = {
            "kind": kind,
            "reason": reason,
            "word_count": word_count,
            "preview": preview_text or "<empty>",
        }
        super().__init__(f"{kind} failed validation: {reason}", details=details)


class APIRequestFailure(GenerationFailure):
    """Raised when the OpenAI API request itself fails."""

    def __init__(self, title: str, details: dict) -> None:
        status = details.get("status_code")
        error_type = details.get("error_type")
        message = "OpenAI API request failed"
        if status is not None or error_type:
            message += (
                f" (status={status if status is not None else 'unknown'},"
                f" type={error_type or 'unknown'})"
            )
        merged_details = dict(details)
        merged_details.setdefault("title", title)
        super().__init__(message, details=merged_details)


class EmptyResponseFailure(GenerationFailure):
    """Raised when the model returns no text content."""

    def __init__(self, title: str) -> None:
        super().__init__("Model returned an empty response", details={"title": title})


class ParseFailure(GenerationFailure):
    """Raised when the model response cannot be parsed as JSON."""

    def __init__(self, title: str, raw_message: str) -> None:
        snippet = raw_message.strip().replace("\n", " ")
        if len(snippet) > 500:
            snippet = snippet[:497] + "..."
        details = {"title": title, "snippet": snippet or "<empty>"}
        super().__init__("Model response was not valid JSON", details=details)


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
    ) -> None:
        self._client = client
        self._model = model
        self._temperature = temperature

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
                LOGGER.warning(
                    "Failed to generate content for '%s': %s | details=%s",
                    article.title,
                    exc,
                    self._format_failure_details(exc),
                )
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
        parsed = self._request_structured_response(prompt, article.title)

        social = (parsed.get("social_post") or "").strip()
        blog = (parsed.get("blog_post") or "").strip()

        social_ok, social_reason = self._validate_social(social)
        if not social_ok:
            failure = ValidationFailure("social_post", social_reason, social)
            self._log_validation_failure(failure)
            raise failure

        blog_ok, blog_reason = self._validate_blog(blog)
        if not blog_ok:
            failure = ValidationFailure("blog_post", blog_reason, blog)
            self._log_validation_failure(failure)
            raise failure

        return GeneratedContent(social=social, blog=blog)

    def _request_structured_response(self, prompt: str, article_title: str) -> dict:
        try:
            response = self._create_response(prompt)
        except APIError as exc:
            details = self._build_api_error_details(exc)
            self._log_api_error(article_title, details)
            raise APIRequestFailure(article_title, details) from exc

        message = self._extract_response_text(response)
        if not message:
            failure = EmptyResponseFailure(article_title)
            self._log_empty_response(failure)
            raise failure

        parsed = self._parse_model_response(message)
        if not parsed:
            failure = ParseFailure(article_title, message)
            self._log_parse_failure(failure)
            raise failure

        return parsed

    def _create_response(self, prompt: str):
        """Issue a generation request using the most modern OpenAI API available."""

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an experienced technology journalist who writes natural, human-sounding "
                    "English prose without using emoji. Follow the caller's length guidance while "
                    "delivering thorough, well-structured coverage without sounding repetitive."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        if hasattr(self._client, "responses"):
            base_kwargs = {
                "model": self._model,
                "temperature": self._temperature,
                "input": self._messages_to_responses_input(messages),
                "max_output_tokens": 2048,
            }

            try:
                return self._client.responses.create(
                    **base_kwargs, response_format={"type": "json_object"}
                )
            except TypeError as exc:
                message = str(exc)

                if "max_output_tokens" in message:
                    fallback_kwargs = {
                        key: value
                        for key, value in base_kwargs.items()
                        if key != "max_output_tokens"
                    }
                    try:
                        return self._client.responses.create(
                            **fallback_kwargs, response_format={"type": "json_object"}
                        )
                    except TypeError as inner_exc:
                        if "response_format" not in str(inner_exc):
                            raise
                        return self._client.responses.create(**fallback_kwargs)

                if "response_format" in message:
                    try:
                        return self._client.responses.create(**base_kwargs)
                    except TypeError as inner_exc:
                        if "max_output_tokens" not in str(inner_exc):
                            raise
                        fallback_kwargs = {
                            key: value
                            for key, value in base_kwargs.items()
                            if key != "max_output_tokens"
                        }
                        return self._client.responses.create(**fallback_kwargs)

                raise

        # Fallback to the legacy Chat Completions API for older client versions.
        return self._client.chat.completions.create(
            model=self._model,
            temperature=self._temperature,
            response_format={"type": "json_object"},
            messages=messages,
            max_tokens=2048,
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
            "2. Blog post: aim for roughly 600-750 words so it reads like a full article, with an engaging introduction, "
            "multiple body sections framed by Markdown subheadings, and a reflective conclusion. Add specific context, "
            "analysis, and implications drawn from the summary so the piece feels comprehensive.\n"
            "Ensure both pieces avoid hashtags and marketing clichés.\n"
            "Respond in strict JSON format with keys 'social_post' and 'blog_post'.\n"
            f"Title: {article.title}\n"
            f"Summary: {base}\n"
            f"{link_segment}"
        )

    @staticmethod
    def _validate_social(content: str) -> tuple[bool, str]:
        if not content:
            return False, "empty"
        if any(ord(char) >= 0x1F300 for char in content):
            return False, "contains_emoji"
        word_count = SocialSummarizer._word_count(content)
        if word_count >= 150:
            return False, f"word_count={word_count} >= max=150"
        return True, f"word_count={word_count}"

    @staticmethod
    def _validate_blog(content: str) -> tuple[bool, str]:
        if not content:
            return False, "empty"
        if any(ord(char) >= 0x1F300 for char in content):
            return False, "contains_emoji"
        word_count = SocialSummarizer._word_count(content)
        if word_count < 280:
            return False, f"word_count={word_count} < min=280"

        return True, f"word_count={word_count}"

    @staticmethod
    def _word_count(content: str) -> int:
        return len(content.split())

    @staticmethod
    def _log_validation_failure(failure: ValidationFailure) -> None:
        details = failure.details
        LOGGER.warning(
            "%s failed validation (%s). Preview: %s",
            details.get("kind", "<unknown>"),
            details.get("reason", "<unknown>"),
            details.get("preview", "<empty>"),
        )

    @staticmethod
    def _log_parse_failure(failure: ParseFailure) -> None:
        """Surface unparseable model responses for easier debugging."""

        details = failure.details
        LOGGER.error(
            "Model response for '%s' was not valid JSON. Snippet: %s",
            details.get("title", "<unknown>"),
            details.get("snippet", "<empty>"),
        )

    @staticmethod
    def _log_api_error(title: str, details: dict) -> None:
        LOGGER.error(
            "OpenAI API request failed for '%s' (status=%s, type=%s, message=%s, body=%s)",
            title,
            details.get("status_code", "unknown"),
            details.get("error_type", "unknown"),
            details.get("error_message", "<empty>"),
            details.get("response_body", "<empty>"),
        )

    @staticmethod
    def _log_empty_response(failure: EmptyResponseFailure) -> None:
        LOGGER.error(
            "Model returned an empty response for '%s'", failure.details.get("title", "<unknown>")
        )

    @staticmethod
    def _build_api_error_details(exc: APIError) -> dict:
        status_code = getattr(exc, "status_code", None)
        response = getattr(exc, "response", None)
        body: str = ""
        if response is not None:
            try:
                body = response.text
            except Exception:  # pragma: no cover - defensive logging
                body = repr(response)

        return {
            "status_code": status_code,
            "error_type": getattr(exc, "type", None) or exc.__class__.__name__,
            "error_message": str(exc),
            "response_body": (body.strip() or "<empty>"),
        }

    @staticmethod
    def _format_failure_details(exc: Exception) -> str:
        details = getattr(exc, "details", None)
        if not details:
            return "<none>"
        try:
            return json.dumps(details, ensure_ascii=False, sort_keys=True)
        except Exception:  # pragma: no cover - defensive
            return repr(details)

    @staticmethod
    def _messages_to_responses_input(messages: list[dict]) -> list[dict]:
        """Convert chat-style messages to the Responses API ``input`` format."""

        converted: list[dict] = []

        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")

            default_type = "output_text" if role == "assistant" else "input_text"

            segments: list[dict] = []
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and "type" in part:
                        # Older calling code may still provide the deprecated
                        # ``text`` type. Normalize it to ``input_text`` so the
                        # Responses API accepts the payload.
                        if part.get("type") == "text":
                            normalized = dict(part)
                            normalized["type"] = "input_text"
                            segments.append(normalized)
                        else:
                            segments.append(part)
                    elif part:
                        segments.append({"type": default_type, "text": str(part)})
            elif content:
                segments.append({"type": default_type, "text": str(content)})
            else:
                segments.append({"type": default_type, "text": ""})

            converted.append({"role": role, "content": segments})
        return converted


__all__ = ["SocialSummarizer", "SummarizationError"]
