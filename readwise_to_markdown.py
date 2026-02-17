#!/usr/bin/env python3
"""
Readwise Reader → Markdown exporter.

Fetches documents from Readwise Reader API and exports them
as clean markdown files organized by reading status.

Usage:
    export READWISE_TOKEN="your_token_here"
    python3 readwise_to_markdown.py [--output-dir ./output]

Get your token at: https://readwise.io/access_token
"""

import os
import sys
import json
import argparse
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError


API_BASE = "https://readwise.io/api/v3"
LOCATIONS = {
    "queue": ["new", "later", "shortlist"],
    "archive": ["archive"],
    "feed": ["feed"],
}


def get_token():
    token = os.environ.get("READWISE_TOKEN")
    if not token:
        print("Error: READWISE_TOKEN environment variable not set.")
        print("Get your token at: https://readwise.io/access_token")
        sys.exit(1)
    return token


def api_request(endpoint, token, params=None):
    """Make a GET request to the Readwise API."""
    url = f"{API_BASE}/{endpoint}/"
    if params:
        url += "?" + urlencode(params, doseq=True)
    req = Request(url, headers={"Authorization": f"Token {token}"})
    try:
        with urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        print(f"API error {e.code}: {e.read().decode()}")
        sys.exit(1)


def fetch_all_documents(token, location=None, category=None):
    """Fetch all documents, handling pagination."""
    documents = []
    params = {}
    if location:
        params["location"] = location
    if category:
        params["category"] = category

    cursor = None
    while True:
        if cursor:
            params["pageCursor"] = cursor
        data = api_request("list", token, params)
        documents.extend(data.get("results", []))
        cursor = data.get("nextPageCursor")
        if not cursor:
            break
        print(f"  Fetched {len(documents)} documents so far...")

    return documents


def fetch_highlights(token, doc_id):
    """Fetch highlights (child documents) for a given document."""
    params = {"parent_id": doc_id, "category": "highlight"}
    data = api_request("list", token, params)
    return data.get("results", [])


def slugify(text, max_len=60):
    """Create a filesystem-safe slug from text."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text).strip('-')
    return text[:max_len]


def format_date(date_str):
    """Format an ISO date string to a readable format."""
    if not date_str:
        return "Unknown"
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        return date_str[:10] if date_str else "Unknown"


def progress_bar(progress):
    """Create a simple text progress bar."""
    if progress is None or progress == 0:
        return "not started"
    pct = int(progress * 100)
    filled = int(progress * 10)
    bar = "█" * filled + "░" * (10 - filled)
    return f"{bar} {pct}%"


def document_to_markdown(doc, include_highlights=False):
    """Convert a single document to a markdown entry."""
    title = doc.get("title", "Untitled")
    author = doc.get("author", "Unknown")
    source_url = doc.get("source_url", "")
    category = doc.get("category", "article")
    word_count = doc.get("word_count", 0)
    reading_time = doc.get("reading_time", "")
    reading_progress = doc.get("reading_progress", 0)
    summary = doc.get("summary", "")
    tags = doc.get("tags", {})
    saved_at = format_date(doc.get("saved_at"))
    published = format_date(doc.get("published_date"))
    site_name = doc.get("site_name", "")
    notes = doc.get("notes", "")

    # Tags as list
    tag_list = list(tags.keys()) if isinstance(tags, dict) else tags
    tag_str = ", ".join(f"`{t}`" for t in tag_list) if tag_list else ""

    lines = []
    lines.append(f"### [{title}]({source_url})")
    lines.append("")

    # Metadata line
    meta = []
    if author and author != "Unknown":
        meta.append(f"**{author}**")
    if site_name:
        meta.append(f"_{site_name}_")
    if meta:
        lines.append(" · ".join(meta))
        lines.append("")

    # Details
    details = []
    if category:
        details.append(f"📂 {category}")
    if word_count:
        details.append(f"📝 {word_count:,} words")
    if reading_time:
        details.append(f"⏱️ {reading_time}")
    if details:
        lines.append(" | ".join(details))

    if reading_progress is not None and reading_progress > 0:
        lines.append(f"📖 Progress: {progress_bar(reading_progress)}")

    if saved_at != "Unknown":
        lines.append(f"📅 Saved: {saved_at}")
    if published and published != "Unknown":
        lines.append(f"📰 Published: {published}")
    if tag_str:
        lines.append(f"🏷️ Tags: {tag_str}")

    lines.append("")

    if summary:
        lines.append(f"> {summary}")
        lines.append("")

    if notes:
        lines.append(f"**Notes:** {notes}")
        lines.append("")

    # Highlights
    highlights = doc.get("_highlights", [])
    if highlights:
        lines.append("#### Highlights")
        lines.append("")
        for h in highlights:
            text = h.get("content", h.get("title", ""))
            if text:
                lines.append(f"> {text}")
                h_notes = h.get("notes", "")
                if h_notes:
                    lines.append(f">\n> — _{h_notes}_")
                lines.append("")

    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def generate_index(all_docs, output_dir):
    """Generate a top-level index/README."""
    queue = [d for d in all_docs if d.get("location") in LOCATIONS["queue"]]
    archive = [d for d in all_docs if d.get("location") in LOCATIONS["archive"]]
    feed = [d for d in all_docs if d.get("location") in LOCATIONS["feed"]]

    lines = []
    lines.append("# 📚 Readwise Reader Library")
    lines.append("")
    lines.append(f"_Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_")
    lines.append("")
    lines.append("| Section | Count |")
    lines.append("|---------|-------|")
    lines.append(f"| [📋 Reading Queue](queue.md) | {len(queue)} |")
    lines.append(f"| [✅ Archive](archive.md) | {len(archive)} |")
    if feed:
        lines.append(f"| [📡 Feed](feed.md) | {len(feed)} |")
    lines.append("")

    # Stats
    total_words = sum(d.get("word_count", 0) or 0 for d in all_docs)
    categories = {}
    for d in all_docs:
        cat = d.get("category", "other")
        categories[cat] = categories.get(cat, 0) + 1

    lines.append("## Stats")
    lines.append("")
    lines.append(f"- **Total items:** {len(all_docs)}")
    lines.append(f"- **Total words:** {total_words:,}")
    lines.append(f"- **Categories:** {', '.join(f'{k} ({v})' for k, v in sorted(categories.items(), key=lambda x: -x[1]))}")
    lines.append("")

    return "\n".join(lines)


def generate_section(docs, title, emoji, description=""):
    """Generate a markdown file for a section (queue/archive/feed)."""
    lines = []
    lines.append(f"# {emoji} {title}")
    lines.append("")
    if description:
        lines.append(f"_{description}_")
        lines.append("")
    lines.append(f"**{len(docs)} items**")
    lines.append("")

    if not docs:
        lines.append("_Nothing here yet!_")
        return "\n".join(lines)

    # Group by category
    by_category = {}
    for doc in docs:
        cat = doc.get("category", "article")
        by_category.setdefault(cat, []).append(doc)

    cat_emojis = {
        "article": "📄",
        "email": "📧",
        "rss": "📡",
        "pdf": "📑",
        "epub": "📖",
        "tweet": "🐦",
        "video": "🎬",
        "highlight": "💡",
        "note": "📝",
    }

    for cat in sorted(by_category.keys()):
        cat_docs = by_category[cat]
        # Sort by saved date, newest first
        cat_docs.sort(key=lambda d: d.get("saved_at", ""), reverse=True)
        emoji_cat = cat_emojis.get(cat, "📄")
        lines.append(f"## {emoji_cat} {cat.title()} ({len(cat_docs)})")
        lines.append("")
        for doc in cat_docs:
            lines.append(document_to_markdown(doc))

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Export Readwise Reader to Markdown")
    parser.add_argument(
        "--output-dir", "-o",
        default="./output",
        help="Output directory for markdown files (default: ./output)"
    )
    parser.add_argument(
        "--with-highlights",
        action="store_true",
        help="Also fetch highlights for each document (slower, more API calls)"
    )
    parser.add_argument(
        "--categories",
        nargs="*",
        default=None,
        help="Filter by categories (e.g., article pdf epub)"
    )
    args = parser.parse_args()

    token = get_token()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("🔄 Fetching documents from Readwise Reader...")
    all_docs = []

    for section, locations in LOCATIONS.items():
        for loc in locations:
            print(f"  📥 Fetching '{loc}' documents...")
            docs = fetch_all_documents(token, location=loc)
            # Filter by category if specified
            if args.categories:
                docs = [d for d in docs if d.get("category") in args.categories]
            # Skip highlights/notes as top-level docs
            docs = [d for d in docs if d.get("parent_id") is None]
            all_docs.extend(docs)
            print(f"    Found {len(docs)} items")

    print(f"\n📊 Total: {len(all_docs)} documents")

    # Optionally fetch highlights
    if args.with_highlights:
        print("\n💡 Fetching highlights...")
        for i, doc in enumerate(all_docs):
            highlights = fetch_highlights(token, doc["id"])
            doc["_highlights"] = highlights
            if (i + 1) % 10 == 0:
                print(f"  Processed {i + 1}/{len(all_docs)}")

    # Generate files
    print("\n📝 Generating markdown files...")

    # Queue
    queue_docs = [d for d in all_docs if d.get("location") in LOCATIONS["queue"]]
    queue_md = generate_section(queue_docs, "Reading Queue", "📋", "Articles and documents waiting to be read.")
    (output_dir / "queue.md").write_text(queue_md)
    print(f"  ✅ queue.md ({len(queue_docs)} items)")

    # Archive
    archive_docs = [d for d in all_docs if d.get("location") in LOCATIONS["archive"]]
    archive_md = generate_section(archive_docs, "Archive", "✅", "Finished reading or archived for reference.")
    (output_dir / "archive.md").write_text(archive_md)
    print(f"  ✅ archive.md ({len(archive_docs)} items)")

    # Feed
    feed_docs = [d for d in all_docs if d.get("location") in LOCATIONS["feed"]]
    if feed_docs:
        feed_md = generate_section(feed_docs, "Feed", "📡", "Items from RSS feeds and subscriptions.")
        (output_dir / "feed.md").write_text(feed_md)
        print(f"  ✅ feed.md ({len(feed_docs)} items)")

    # Index
    index_md = generate_index(all_docs, output_dir)
    (output_dir / "README.md").write_text(index_md)
    print(f"  ✅ README.md (index)")

    # Also dump raw JSON for potential future use
    json_path = output_dir / "data.json"
    with open(json_path, "w") as f:
        json.dump(all_docs, f, indent=2, default=str)
    print(f"  ✅ data.json (raw data backup)")

    print(f"\n🎉 Done! Output in: {output_dir.resolve()}")
    print(f"   Open {output_dir / 'README.md'} to see the index.")


if __name__ == "__main__":
    main()
