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
                continue

            if not content.social or not content.blog:
                continue

            entry["social_summary"] = content.social
            entry["blog_post"] = content.blog
            generated += 1

        return generated

    def _create_content(self, article: ArticleForSummary) -> GeneratedContent:
        prompt = self._build_prompt(article)

        delay = self._retry_delay
        for attempt in range(1, self._max_retries + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    temperature=self._temperature,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are an experienced technology journalist who writes natural, human-sounding "
                                "English prose without using emoji. Always follow length requirements precisely."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                )
            except Exception as exc:  # pragma: no cover - network failure
                if attempt == self._max_retries:
                    raise
                LOGGER.debug(
                    "OpenAI call failed (attempt %d/%d): %s", attempt, self._max_retries, exc
                )
                time.sleep(delay)
                delay *= 2
                continue

            message = response.choices[0].message.content if response.choices else ""
            if not message:
                continue

            try:
                parsed = json.loads(message)
            except json.JSONDecodeError:
                LOGGER.debug("Received non-JSON response; retrying")
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

    def _build_prompt(self, article: ArticleForSummary) -> str:
        base = article.summary or ""
        link_segment = f"URL: {article.link}\n" if article.link else ""
        return (
            "Write two distinct English outputs based on the article below.\n"
            "1. Social media post: fewer than 150 words, concise yet vivid, avoiding bullet lists and emojis.\n"
            "2. Blog post: at least 700 words, structured with paragraphs and subheadings that feel naturally written by a human editor.\n"
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
        return word_count >= 700


__all__ = ["SocialSummarizer"]
