# readwise-to-markdown

Export your [Readwise Reader](https://read.readwise.io) library to clean markdown files.

## Setup

1. Get your Readwise access token from [readwise.io/access_token](https://readwise.io/access_token)
2. Set it as an environment variable:
   ```bash
   export READWISE_TOKEN="your_token_here"
   ```

## Usage

```bash
# Basic export
python3 readwise_to_markdown.py

# Custom output directory
python3 readwise_to_markdown.py --output-dir ./my-reading-list

# Include highlights (slower — extra API calls per document)
python3 readwise_to_markdown.py --with-highlights

# Filter by category
python3 readwise_to_markdown.py --categories article pdf epub
```

## Output

```
output/
├── README.md      # Index with stats
├── queue.md       # 📋 Reading queue (new/later/shortlist)
├── archive.md     # ✅ Archived/read items
├── feed.md        # 📡 RSS feed items (if any)
└── data.json      # Raw JSON backup
```

Each document includes:
- Title (linked to source)
- Author & site
- Category, word count, reading time
- Reading progress bar
- Tags, saved/published dates
- Summary
- Highlights (with `--with-highlights`)

## Requirements

- Python 3.7+
- No external dependencies (uses only stdlib)

## License

MIT
