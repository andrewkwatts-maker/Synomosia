# synomosia

Conspiracy theories, hidden histories, and suppressed knowledge — a curated encyclopedia and live scraper for Python.

## Features

- Curated database of theories, figures, organizations, events, and documents
- Full-text search with FTS5 fallback to LIKE
- Topic graph linking related theories and entities
- Live scraper for Reddit, 4chan boards, and RSS feeds (optional)
- LLM-powered categorization into 16 conspiracy taxonomy categories (optional)
- Daily rotating local databases with compression
- On-demand corpus checkout (downloaded once, cached locally)

## Installation

```bash
pip install synomosia
```

With scraping support:

```bash
pip install "synomosia[scrape]"   # adds feedparser, requests, beautifulsoup4, praw
```

## Quick start

```python
import synomosia

# Curated database queries
theory = synomosia.GetTheory("Illuminati")
figure = synomosia.GetFigure("John F. Kennedy")
org    = synomosia.GetOrganization("Bilderberg Group")

# Full-text search
results = synomosia.Search("shadow government")
orgs    = synomosia.ByCategory("secret-society")
all_    = synomosia.GetAll("theory")

# Topic graph
related = synomosia.GetRelated("New World Order")
topics  = synomosia.GetTopics("government")
tree    = synomosia.GetTopicTree("deep-state")

# Live scraper — configure sources
synomosia.AddFeed("https://conspiracyarchive.com/feed/")
synomosia.AddSubreddit("conspiracy")       # requires REDDIT_CLIENT_ID env var
sources = synomosia.ListSources()

# Scrape and categorize
synomosia.Scrape()                         # fetch from all sources
synomosia.Categorize(verbose=True)         # LLM categorization (requires LLM backend)
report = synomosia.DailyReport()           # generate today's summary report

# Corpus
synomosia.FetchCorpus("gutenberg-1984")
hits = synomosia.SearchCorpus("surveillance")
```

## LLM-powered categorization

When an LLM backend is available, articles are classified into 16 categories:

`government-surveillance`, `secret-societies`, `false-flag`, `extraterrestrial`, `financial-manipulation`, `medical-coverup`, `media-control`, `religion-occult`, `geopolitical`, `technology-control`, `weather-manipulation`, `historical-revision`, `assassination`, `mind-control`, `new-world-order`, `other`

Set `LLM_BACKEND`, `LLM_MODEL`, etc. — see [eyecore](https://github.com/andrewkwatts-maker/EyeCore#llm-configuration) for configuration.

## Reddit scraping setup

```bash
export REDDIT_CLIENT_ID=your_client_id
export REDDIT_CLIENT_SECRET=your_client_secret
```

Register a read-only script app at [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps).

## Part of the Eyes of Azrael suite

| Package | Description |
|---|---|
| [`eyecore`](https://github.com/andrewkwatts-maker/EyeCore) | Shared foundation (DB, graph, corpus, LLM) |
| [`azrael`](https://github.com/andrewkwatts-maker/Azrael) | Mythology encyclopedia |
| [`synomosia`](https://github.com/andrewkwatts-maker/Synomosia) | Conspiracy theories and hidden histories |
| [`mnema`](https://github.com/andrewkwatts-maker/Mnema) | Historical figures and events |

## License

MIT — see [LICENSE](LICENSE)
