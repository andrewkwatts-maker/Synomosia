#!/usr/bin/env python3
"""Augur scraper CLI.

Usage:
    python scripts/scrape.py run                    # scrape all sources
    python scripts/scrape.py add <url>              # add source (auto-detects feed)
    python scripts/scrape.py add <url> --name BBC --category world
    python scripts/scrape.py remove <url>           # remove source
    python scripts/scrape.py list                   # list configured sources
    python scripts/scrape.py compress               # compress old daily DBs
    python scripts/scrape.py days                   # list available day archives
    python scripts/scrape.py report [--date DATE] [--no-llm]   # generate topic reports
    python scripts/scrape.py reports [--date DATE]             # show existing reports
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))


def cmd_run(args) -> None:
    from augur._scraper import scrape_all
    print("Scraping all sources...")
    results = scrape_all(verbose=True)
    total = sum(v for v in results.values() if v >= 0)
    print(f"\nTotal new articles: {total}")


def cmd_add(args) -> None:
    from augur._scraper import add_source
    source = add_source(args.url, name=args.name or "", category=args.category)
    print(f"Added: {source['name']} -> {source['url']}")


def cmd_remove(args) -> None:
    from augur._scraper import remove_source
    if remove_source(args.url):
        print(f"Removed: {args.url}")
    else:
        print(f"Not found: {args.url}")
        sys.exit(1)


def cmd_list(args) -> None:
    from augur._scraper import load_sources
    sources = load_sources()
    if not sources:
        print("No sources configured.")
        return
    for s in sources:
        print(f"  [{s.get('category', 'general')}] {s.get('name', '')} -> {s['url']}")


def cmd_compress(args) -> None:
    from augur._store import compress_old_days
    compressed = compress_old_days(keep_uncompressed=args.keep)
    if compressed:
        print(f"Compressed: {', '.join(compressed)}")
    else:
        print("Nothing to compress.")


def cmd_days(args) -> None:
    from augur._store import available_days
    days = available_days()
    if not days:
        print("No data available.")
        return
    for d in days:
        print(f"  {d}")


def cmd_report(args) -> None:
    """Generate topic reports for a given date using LLM clustering."""
    from augur._report import generate_daily_reports
    target = args.date or None
    use_llm = not args.no_llm

    if target:
        print(f"Generating topic reports for {target}...")
    else:
        from datetime import date
        target = date.today().isoformat()
        print(f"Generating topic reports for today ({target})...")

    reports = generate_daily_reports(
        target_date=target,
        use_llm=use_llm,
        verbose=True,
    )

    if not reports:
        print("No articles found for that date.")
        return

    print(f"\nGenerated {len(reports)} topic report(s):\n")
    for r in reports:
        print(f"  [{r['article_count']} articles] {r['topic']}")
        # Print a brief excerpt of the summary (first 200 chars)
        summary = r.get("summary", "")
        if summary:
            excerpt = summary[:200].replace("\n", " ")
            if len(summary) > 200:
                excerpt += "..."
            print(f"    {excerpt}")
        print()


def cmd_reports(args) -> None:
    """Show existing topic reports for a given date."""
    from augur._query import GetReports
    target = args.date or None

    if target:
        print(f"Topic reports for {target}:\n")
    else:
        from datetime import date
        target = date.today().isoformat()
        print(f"Topic reports for today ({target}):\n")

    reports = GetReports(target)

    if not reports:
        print("No reports found. Run: python scripts/scrape.py report")
        return

    for r in reports:
        print(f"  [{r.get('article_count', 0)} articles] {r.get('topic', 'Unknown')}")
        summary = r.get("summary", "")
        if summary:
            excerpt = summary[:200].replace("\n", " ")
            if len(summary) > 200:
                excerpt += "..."
            print(f"    {excerpt}")
        links = r.get("links", [])
        if isinstance(links, list) and links:
            print(f"    Top links:")
            for link in links[:3]:
                title = link.get("title", "")
                url = link.get("url", "")
                if title and url:
                    print(f"      - {title}")
                    print(f"        {url}")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="augur news scraper")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("run", help="Scrape all configured sources")

    p_add = sub.add_parser("add", help="Add a news source")
    p_add.add_argument("url", help="RSS feed URL or website URL")
    p_add.add_argument("--name", default="", help="Display name")
    p_add.add_argument("--category", default="general", help="Category tag")

    p_rm = sub.add_parser("remove", help="Remove a source")
    p_rm.add_argument("url")

    sub.add_parser("list", help="List configured sources")

    p_comp = sub.add_parser("compress", help="Compress old daily DBs")
    p_comp.add_argument("--keep", type=int, default=2,
                        help="Keep N most recent days uncompressed (default: 2)")

    sub.add_parser("days", help="List available day archives")

    p_report = sub.add_parser("report", help="Generate topic reports for a date")
    p_report.add_argument("--date", default=None,
                          help="Date to generate reports for (YYYY-MM-DD, default: today)")
    p_report.add_argument("--no-llm", action="store_true",
                          help="Use keyword clustering instead of LLM")

    p_reports = sub.add_parser("reports", help="Show existing topic reports for a date")
    p_reports.add_argument("--date", default=None,
                           help="Date to show reports for (YYYY-MM-DD, default: today)")

    args = parser.parse_args()
    {
        "run": cmd_run,
        "add": cmd_add,
        "remove": cmd_remove,
        "list": cmd_list,
        "compress": cmd_compress,
        "days": cmd_days,
        "report": cmd_report,
        "reports": cmd_reports,
    }[args.command](args)


if __name__ == "__main__":
    main()
