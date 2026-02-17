#!/usr/bin/env python3
"""
Readwise Reader → Markdown exporter.

Fetches documents from Readwise Reader API and exports them
as individual markdown files with YAML frontmatter, organized
into folders by reading status.

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


def slugify(text, max_len=80):
    """Create a filesystem-safe slug from text."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text).strip('-')
    return text[:max_len] if text else "untitled"


def format_date(date_str):
    """Format an ISO date string to YYYY-MM-DD."""
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        return date_str[:10] if date_str else None


def yaml_escape(val):
    """Escape a string for YAML frontmatter."""
    if val is None:
        return '""'
    val = str(val)
    if any(c in val for c in ':{}[]#&*!|>\'"@`,%'):
        return f'"{val.replace(chr(34), chr(92)+chr(34))}"'
    return val


def document_to_file(doc):
    """Convert a single document to a markdown string with YAML frontmatter."""
    title = doc.get("title", "Untitled") or "Untitled"
    author = doc.get("author") or ""
    source_url = doc.get("source_url", "") or ""
    reader_url = doc.get("url", "") or ""
    category = doc.get("category", "article")
    location = doc.get("location", "")
    word_count = doc.get("word_count") or 0
    reading_time = doc.get("reading_time") or ""
    reading_progress = doc.get("reading_progress") or 0
    summary = doc.get("summary") or ""
    tags = doc.get("tags", {})
    saved_at = format_date(doc.get("saved_at"))
    published = format_date(doc.get("published_date"))
    site_name = doc.get("site_name") or ""
    notes = doc.get("notes") or ""
    doc_id = doc.get("id", "")

    tag_list = sorted(tags.keys()) if isinstance(tags, dict) else (tags or [])

    # YAML frontmatter
    lines = ["---"]
    lines.append(f"id: {yaml_escape(doc_id)}")
    lines.append(f"title: {yaml_escape(title)}")
    lines.append(f"author: {yaml_escape(author)}")
    lines.append(f"url: {yaml_escape(source_url)}")
    lines.append(f"reader_url: {yaml_escape(reader_url)}")
    lines.append(f"site: {yaml_escape(site_name)}")
    lines.append(f"category: {category}")
    lines.append(f"location: {location}")
    lines.append(f"word_count: {word_count}")
    lines.append(f"reading_time: {yaml_escape(reading_time)}")
    lines.append(f"reading_progress: {reading_progress}")
    if saved_at:
        lines.append(f"saved_at: {saved_at}")
    if published:
        lines.append(f"published: {published}")
    if tag_list:
        lines.append(f"tags: [{', '.join(yaml_escape(t) for t in tag_list)}]")
    else:
        lines.append("tags: []")
    lines.append("---")
    lines.append("")

    # Title
    lines.append(f"# {title}")
    lines.append("")

    # Metadata
    meta = []
    if author:
        meta.append(f"**{author}**")
    if site_name:
        meta.append(f"_{site_name}_")
    if meta:
        lines.append(" · ".join(meta))
        lines.append("")

    if source_url:
        lines.append(f"🔗 [{source_url[:80]}{'...' if len(source_url) > 80 else ''}]({source_url})")
        lines.append("")

    # Summary
    if summary:
        lines.append("## Summary")
        lines.append("")
        lines.append(f"> {summary}")
        lines.append("")

    # Notes
    if notes:
        lines.append("## Notes")
        lines.append("")
        lines.append(notes)
        lines.append("")

    # Highlights
    highlights = doc.get("_highlights", [])
    if highlights:
        lines.append("## Highlights")
        lines.append("")
        for h in highlights:
            text = h.get("content", h.get("title", ""))
            if text:
                lines.append(f"> {text}")
                h_notes = h.get("notes", "")
                if h_notes:
                    lines.append(f">\n> — _{h_notes}_")
                lines.append("")

    return "\n".join(lines)


def generate_index(all_docs, output_dir):
    """Generate a top-level README index."""
    queue = [d for d in all_docs if d.get("location") in LOCATIONS["queue"]]
    archive = [d for d in all_docs if d.get("location") in LOCATIONS["archive"]]
    feed = [d for d in all_docs if d.get("location") in LOCATIONS["feed"]]

    total_words = sum(d.get("word_count", 0) or 0 for d in all_docs)
    categories = {}
    for d in all_docs:
        cat = d.get("category", "other")
        categories[cat] = categories.get(cat, 0) + 1

    lines = []
    lines.append("# 📚 Readwise Reader Library")
    lines.append("")
    lines.append(f"_Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_")
    lines.append("")
    lines.append("## Sections")
    lines.append("")
    lines.append(f"- [`queue/`](queue/) — 📋 Reading Queue ({len(queue)} items)")
    lines.append(f"- [`archive/`](archive/) — ✅ Archive ({len(archive)} items)")
    if feed:
        lines.append(f"- [`feed/`](feed/) — 📡 Feed ({len(feed)} items)")
    lines.append("")
    lines.append("## Stats")
    lines.append("")
    lines.append(f"- **Total items:** {len(all_docs)}")
    lines.append(f"- **Total words:** {total_words:,}")
    lines.append(f"- **Categories:** {', '.join(f'{k} ({v})' for k, v in sorted(categories.items(), key=lambda x: -x[1]))}")
    lines.append("")

    # Table of all items
    lines.append("## All Items")
    lines.append("")
    lines.append("| Status | Title | Author | Category | Words | Progress |")
    lines.append("|--------|-------|--------|----------|-------|----------|")
    for doc in sorted(all_docs, key=lambda d: d.get("saved_at", ""), reverse=True):
        title = doc.get("title", "Untitled") or "Untitled"
        short_title = title[:50] + "..." if len(title) > 50 else title
        author = doc.get("author", "") or ""
        short_author = author[:20] + "..." if len(author) > 20 else author
        cat = doc.get("category", "")
        wc = doc.get("word_count") or 0
        loc = doc.get("location", "")
        progress = doc.get("reading_progress") or 0
        pct = f"{int(progress * 100)}%" if progress else "-"

        # Link to individual file
        section = "queue" if loc in LOCATIONS["queue"] else ("archive" if loc in LOCATIONS["archive"] else "feed")
        slug = slugify(title)
        link = f"[{short_title}]({section}/{slug}.md)"

        status = "📋" if loc in LOCATIONS["queue"] else ("✅" if loc in LOCATIONS["archive"] else "📡")
        lines.append(f"| {status} | {link} | {short_author} | {cat} | {wc:,} | {pct} |")

    lines.append("")
    return "\n".join(lines)


def generate_section_index(docs, title, emoji, folder_name, description=""):
    """Generate an index for a section folder."""
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
        "article": "📄", "email": "📧", "rss": "📡", "pdf": "📑",
        "epub": "📖", "tweet": "🐦", "video": "🎬", "highlight": "💡", "note": "📝",
    }

    for cat in sorted(by_category.keys()):
        cat_docs = by_category[cat]
        cat_docs.sort(key=lambda d: d.get("saved_at", ""), reverse=True)
        emoji_cat = cat_emojis.get(cat, "📄")
        lines.append(f"## {emoji_cat} {cat.title()} ({len(cat_docs)})")
        lines.append("")
        for doc in cat_docs:
            title = doc.get("title", "Untitled") or "Untitled"
            slug = slugify(title)
            author = doc.get("author", "") or ""
            saved = format_date(doc.get("saved_at")) or ""
            lines.append(f"- [{title}]({slug}.md) — {author} ({saved})")
        lines.append("")

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

    print("🔄 Fetching documents from Readwise Reader...")
    all_docs = []

    for section, locations in LOCATIONS.items():
        for loc in locations:
            print(f"  📥 Fetching '{loc}' documents...")
            docs = fetch_all_documents(token, location=loc)
            if args.categories:
                docs = [d for d in docs if d.get("category") in args.categories]
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

    # Create folder structure
    print("\n📝 Generating markdown files...")

    sections = {
        "queue": {
            "docs": [d for d in all_docs if d.get("location") in LOCATIONS["queue"]],
            "title": "Reading Queue",
            "emoji": "📋",
            "desc": "Articles and documents waiting to be read.",
        },
        "archive": {
            "docs": [d for d in all_docs if d.get("location") in LOCATIONS["archive"]],
            "title": "Archive",
            "emoji": "✅",
            "desc": "Finished reading or archived for reference.",
        },
        "feed": {
            "docs": [d for d in all_docs if d.get("location") in LOCATIONS["feed"]],
            "title": "Feed",
            "emoji": "📡",
            "desc": "Items from RSS feeds and subscriptions.",
        },
    }

    # Track slugs to handle duplicates
    used_slugs = {}

    for section_name, section in sections.items():
        docs = section["docs"]
        if not docs:
            continue

        section_dir = output_dir / section_name
        section_dir.mkdir(parents=True, exist_ok=True)

        # Write individual files
        for doc in docs:
            title = doc.get("title", "Untitled") or "Untitled"
            slug = slugify(title)

            # Handle duplicate slugs
            key = f"{section_name}/{slug}"
            if key in used_slugs:
                used_slugs[key] += 1
                slug = f"{slug}-{used_slugs[key]}"
            else:
                used_slugs[key] = 0

            filepath = section_dir / f"{slug}.md"
            filepath.write_text(document_to_file(doc))

        # Section index
        index_md = generate_section_index(
            docs, section["title"], section["emoji"], section_name, section["desc"]
        )
        (section_dir / "README.md").write_text(index_md)
        print(f"  ✅ {section_name}/ ({len(docs)} files)")

    # Top-level index
    index_md = generate_index(all_docs, output_dir)
    (output_dir / "README.md").write_text(index_md)
    print(f"  ✅ README.md (index)")

    # Raw JSON backup
    json_path = output_dir / "data.json"
    with open(json_path, "w") as f:
        json.dump(all_docs, f, indent=2, default=str)
    print(f"  ✅ data.json (raw data backup)")

    print(f"\n🎉 Done! Output in: {output_dir.resolve()}")
    print(f"   {sum(len(s['docs']) for s in sections.values())} individual markdown files generated.")


if __name__ == "__main__":
    main()
