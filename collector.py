"""Collect AI-related news from configured RSS feeds and store them as Markdown."""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import logging
import pathlib
import re
from dataclasses import dataclass
from html import unescape
from typing import Iterable, List, Optional

import feedparser
import requests
import yaml
from zoneinfo import ZoneInfo

LOGGER = logging.getLogger(__name__)

USER_AGENT = "AICollector/1.0 (+https://github.com/)"


@dataclass
class FeedConfig:
    name: str
    url: str
    keywords: Optional[List[str]]


@dataclass
class Config:
    timezone: ZoneInfo
    keywords: List[str]
    feeds: List[FeedConfig]

    @classmethod
    def load(cls, path: pathlib.Path) -> "Config":
        with path.open("r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)

        if not raw:
            raise ValueError("Configuration file is empty")

        tz_name = raw.get("timezone", "UTC")
        try:
            timezone = ZoneInfo(tz_name)
        except Exception as exc:  # pragma: no cover - defensive logging
            raise ValueError(f"Invalid timezone '{tz_name}': {exc}") from exc

        keywords = [kw.lower() for kw in raw.get("keywords", [])]
        feeds: List[FeedConfig] = []
        for feed in raw.get("sources", []):
            feeds.append(
                FeedConfig(
                    name=feed["name"],
                    url=feed["url"],
                    keywords=[kw.lower() for kw in feed.get("keywords", [])] if feed.get("keywords") is not None else None,
                )
            )

        if not feeds:
            raise ValueError("No feeds configured.")

        return cls(timezone=timezone, keywords=keywords, feeds=feeds)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Target date in YYYY-MM-DD format. Defaults to yesterday in the configured timezone.",
    )
    parser.add_argument(
        "--feeds-file",
        type=pathlib.Path,
        default=pathlib.Path("config/feeds.yaml"),
        help="Path to the feeds configuration file.",
    )
    parser.add_argument(
        "--output-dir",
        type=pathlib.Path,
        default=pathlib.Path("data"),
        help="Directory where the Markdown files will be written.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level.",
    )
    parser.add_argument(
        "--require-summaries",
        action="store_true",
        help=(
            "Fail the run when the language model content generation step cannot be completed."
        ),
    )
    return parser.parse_args()


def determine_target_date(config: Config, date_str: Optional[str]) -> dt.date:
    now = dt.datetime.now(tz=config.timezone)
    if date_str:
        return dt.datetime.strptime(date_str, "%Y-%m-%d").date()
    yesterday = now - dt.timedelta(days=1)
    return yesterday.date()


def fetch_feed(url: str) -> feedparser.FeedParserDict:
    LOGGER.debug("Fetching feed: %s", url)
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()
    return feedparser.parse(response.content)


def entry_datetime(entry: feedparser.FeedParserDict, timezone: ZoneInfo) -> Optional[dt.datetime]:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        if key in entry and entry[key]:
            timestamp = calendar.timegm(entry[key])
            return dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc).astimezone(timezone)
    return None


def entry_matches_keywords(entry: feedparser.FeedParserDict, keywords: Iterable[str]) -> bool:
    lowered = " ".join(
        part for attr in ("title", "summary") for part in [entry.get(attr, "")]
    ).lower()
    return any(keyword in lowered for keyword in keywords)


def collect_entries(config: Config, target_date: dt.date) -> List[dict]:
    collected = []
    seen_keys = set()

    for feed in config.feeds:
        try:
            parsed = fetch_feed(feed.url)
        except Exception as exc:
            LOGGER.warning("Failed to fetch %s: %s", feed.name, exc)
            continue

        keywords = (
            []
            if feed.keywords == []
            else feed.keywords if feed.keywords else config.keywords
        )

        for entry in parsed.entries:
            published = entry_datetime(entry, config.timezone)
            if not published:
                continue
            if published.date() != target_date:
                continue

            if keywords:  # empty list disables keyword filtering
                if not entry_matches_keywords(entry, keywords):
                    continue

            key = (entry.get("title", ""), entry.get("link", ""))
            if key in seen_keys:
                continue
            seen_keys.add(key)

            collected.append(
                {
                    "title": entry.get("title", "(untitled)"),
                    "link": entry.get("link"),
                    "source": feed.name,
                    "published": published,
                    "summary": clean_summary(entry.get("summary", "")),
                }
            )
    collected.sort(key=lambda item: item["published"], reverse=True)
    return collected


def format_markdown(entries: List[dict], target_date: dt.date, timezone: ZoneInfo) -> str:
    header = [
        f"# AI News for {target_date.isoformat()} ({timezone.key})",
        "",
        f"Collected {len(entries)} article(s).",
        "",
    ]
    body = []
    for entry in entries:
        time_str = entry["published"].strftime("%H:%M")
        summary = entry["summary"].strip()
        summary_line = f"\n  > {summary}" if summary else ""
        body.append(
            f"- [{entry['title']}]({entry['link']}) — {time_str} · {entry['source']}{summary_line}"
        )
    if not body:
        body.append("No articles found for the selected date.")
    return "\n".join(header + body) + "\n"


def format_social_posts(entries: List[dict], target_date: dt.date) -> str:
    header = [
        f"# AI News Social Summaries for {target_date.isoformat()}",
        "",
        f"Collected {len(entries)} article(s).",
        "",
    ]
    body = []
    for idx, entry in enumerate(entries, start=1):
        social = entry.get("social_summary", "").strip()
        if not social:
            continue
        body.append(f"{idx}. {entry['title']}")
        body.append(f"   {social}")
        link = entry.get("link")
        if link:
            body.append(f"   {link}")
        body.append("")
    if not body:
        body.append("No social summaries were generated.")
    return "\n".join(header + body).rstrip() + "\n"


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "article"


def write_entry_content(
    entries: List[dict],
    target_date: dt.date,
    output_dir: pathlib.Path,
) -> tuple[int, int]:
    base_dir = (
        output_dir
        / str(target_date.year)
        / f"{target_date.month:02d}"
        / target_date.isoformat()
    )
    base_dir.mkdir(parents=True, exist_ok=True)

    slug_counts: dict[str, int] = {}
    social_files = 0
    blog_files = 0

    for entry in entries:
        social = (entry.get("social_summary") or "").strip()
        blog = (entry.get("blog_post") or "").strip()
        if not social or not blog:
            continue

        slug = slugify(entry.get("title", ""))
        count = slug_counts.get(slug, 0)
        slug_counts[slug] = count + 1
        if count:
            slug = f"{slug}-{count + 1}"

        source = entry.get("link") or entry.get("source") or "Unknown source"
        source_line = f"Source: {source}"

        if social:
            social_path = base_dir / f"{slug}-social.txt"
            social_path.write_text(f"{social}\n\n{source_line}\n", encoding="utf-8")
            social_files += 1

        if blog:
            blog_path = base_dir / f"{slug}-blog.md"
            blog_path.write_text(f"{blog}\n\n{source_line}\n", encoding="utf-8")
            blog_files += 1

    return social_files, blog_files


def write_output(markdown: str, target_date: dt.date, output_dir: pathlib.Path) -> pathlib.Path:
    subdir = output_dir / str(target_date.year) / f"{target_date.month:02d}"
    subdir.mkdir(parents=True, exist_ok=True)
    file_path = subdir / f"{target_date.isoformat()}-ai-news.md"
    file_path.write_text(markdown, encoding="utf-8")
    return file_path


def write_social_output(content: str, target_date: dt.date, output_dir: pathlib.Path) -> pathlib.Path:
    subdir = output_dir / str(target_date.year) / f"{target_date.month:02d}"
    subdir.mkdir(parents=True, exist_ok=True)
    file_path = subdir / f"{target_date.isoformat()}-ai-news-social.txt"
    file_path.write_text(content, encoding="utf-8")
    return file_path


def clean_summary(summary: str) -> str:
    if not summary:
        return ""
    text = unescape(summary)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level))

    config = Config.load(args.feeds_file)
    target_date = determine_target_date(config, args.date)

    entries = collect_entries(config, target_date)
    markdown = format_markdown(entries, target_date, config.timezone)
    output_path = write_output(markdown, target_date, args.output_dir)

    LOGGER.info("Wrote %d entries to %s", len(entries), output_path)

    try:
        from summarizer import SocialSummarizer, SummarizationError
    except ImportError:  # pragma: no cover - optional dependency
        LOGGER.debug("summarizer module is unavailable; skipping social summaries")
        return

    summarizer = SocialSummarizer.from_env()
    if not summarizer:
        message = "OPENAI_API_KEY not set; skipping social summary generation"
        if args.require_summaries:
            LOGGER.error("%s (required for this run)", message)
            raise SystemExit(1)
        LOGGER.info(message)
        return

    try:
        generated = summarizer.enrich_entries(entries)
    except SummarizationError as exc:
        if args.require_summaries:
            LOGGER.error("Social summary generation failed: %s", exc)
            raise SystemExit(1)
        LOGGER.warning("Social summary generation failed: %s", exc)
        return
    except Exception as exc:  # pragma: no cover - defensive logging
        if args.require_summaries:
            LOGGER.error("Unexpected error during social summary generation: %s", exc)
            raise SystemExit(1)
        LOGGER.warning(
            "Unexpected error encountered during social summary generation; skipping: %s",
            exc,
        )
        return

    if not generated:
        LOGGER.warning("Social summary generation was requested but no summaries were produced")
        if args.require_summaries:
            raise SystemExit(1)
        return

    social_content = format_social_posts(entries, target_date)
    social_path = write_social_output(social_content, target_date, args.output_dir)
    LOGGER.info("Wrote %d social summaries to %s", generated, social_path)

    social_files, blog_files = write_entry_content(entries, target_date, args.output_dir)
    LOGGER.info(
        "Wrote %d social post file(s) and %d blog post file(s) for individual articles",
        social_files,
        blog_files,
    )


if __name__ == "__main__":
    main()
