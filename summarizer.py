"""Generate social-media-ready summaries for collected news articles."""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Iterable, Optional

from openai import OpenAI

LOGGER = logging.getLogger(__name__)


@dataclass
class ArticleForSummary:
    """Minimal representation of an article for social summarization."""

    title: str
    summary: str
    link: Optional[str]


class SocialSummarizer:
    """Wrapper around the OpenAI API to build concise social media summaries."""

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
        """Mutate entries in-place by adding a `social_summary` key when possible."""

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
                social_summary = self._create_summary(article)
            except Exception as exc:  # pragma: no cover - defensive logging
                LOGGER.warning("Failed to summarize '%s': %s", article.title, exc)
                continue

            if not social_summary:
                continue

            entry["social_summary"] = social_summary
            generated += 1

        return generated

    def _create_summary(self, article: ArticleForSummary) -> str:
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
                                "你是一名專業的科技新聞編輯，擅長將 AI 新聞濃縮成適合 Threads 與 Twitter 的貼文。"
                                "請僅輸出摘要內容，不要加上標題、表情符號或 hashtag。"
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                )
            except Exception as exc:  # pragma: no cover - network failure
                if attempt == self._max_retries:
                    raise
                LOGGER.debug("OpenAI call failed (attempt %d/%d): %s", attempt, self._max_retries, exc)
                time.sleep(delay)
                delay *= 2
                continue

            message = response.choices[0].message.content if response.choices else ""
            return (message or "").strip()

        return ""

    def _build_prompt(self, article: ArticleForSummary) -> str:
        base = article.summary or ""
        link_segment = f"文章連結：{article.link}\n" if article.link else ""
        return (
            "請根據以下資訊撰寫約 150 字的繁體中文摘要，"
            "語氣專業、精準，著重新聞的核心重點與潛在影響，"
            "避免冗長鋪陳。不要加入網址，亦不要包含 emoji 或 hashtag。\n"
            f"新聞標題：{article.title}\n"
            f"原始摘要：{base}\n"
            f"{link_segment}"
        )


__all__ = ["SocialSummarizer"]
