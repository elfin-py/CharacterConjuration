#!/usr/bin/env python3
"""
Import PDF books into the markdown corpus used by the fallback retriever/indexer.

This script extracts text page-by-page and writes one markdown file per page into:
    backend/data/split_md/<Book_Name>/PAGE_###.md

It is intentionally simple and robust:
- uses PyPDF2, which is already present in the backend venv
- skips pages with no extractable text
- can skip books that already exist unless --force is provided
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from PyPDF2 import PdfReader


REPO_BACKEND = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_BACKEND / "data" / "split_md"


def sanitize_book_name(name: str) -> str:
    name = name.strip()
    name = re.sub(r"\.pdf$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[\\/]+", "_", name)
    name = re.sub(r"\s+", "_", name)
    return name


def clean_page_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def page_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"\s+", " ", line)
        return line[:120]
    return fallback


def import_pdf(pdf_path: Path, output_root: Path, force: bool = False) -> tuple[str, int]:
    book_dir = output_root / sanitize_book_name(pdf_path.name)
    if book_dir.exists() and any(book_dir.glob("*.md")) and not force:
        return book_dir.name, 0

    book_dir.mkdir(parents=True, exist_ok=True)
    if force:
        for old in book_dir.glob("*.md"):
            old.unlink()

    reader = PdfReader(str(pdf_path))
    written = 0
    for idx, page in enumerate(reader.pages, start=1):
        raw = page.extract_text() or ""
        text = clean_page_text(raw)
        if not text:
            continue

        title = page_title(text, f"{pdf_path.stem} Page {idx}")
        md = [
            f"# {title}",
            "",
            f"_Source: {pdf_path.name}, page {idx}_",
            "",
            text,
            "",
        ]
        out = book_dir / f"PAGE_{idx:03d}.md"
        out.write_text("\n".join(md), encoding="utf-8")
        written += 1

    return book_dir.name, written


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdfs", nargs="+", help="PDF files to import")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    for raw_pdf in args.pdfs:
        pdf_path = Path(raw_pdf).expanduser().resolve()
        if not pdf_path.exists():
            raise FileNotFoundError(f"Missing PDF: {pdf_path}")
        folder, written = import_pdf(pdf_path, output_root, force=args.force)
        if written == 0:
            print(f"SKIP {folder}: existing markdown retained")
        else:
            print(f"OK   {folder}: wrote {written} markdown files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
