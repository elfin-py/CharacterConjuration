"""
Rebuild the vector index for Character Conjuration.

Reads all Markdown files under data/split_md (and data/md if present),
chunks them, embeds with a small HF model, and pickles the index to
backend/character_index.pkl.

Requirements:
- HF_TOKEN in environment or backend/.env
- Internet access to download the embedding model on first run
"""

import os
import glob
import pickle
from pathlib import Path

from dotenv import load_dotenv
from llama_index.core import (
    SimpleDirectoryReader,
    VectorStoreIndex,
    ServiceContext,
)
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
import logging

from index_stubs import NullIndex


def collect_markdown(paths):
    files = []
    for p in paths:
        files.extend(glob.glob(os.path.join(p, "**", "*.md"), recursive=True))
    return files


def build_stub_index(out_path: Path):
    """Write a minimal stub index to avoid runtime load errors when offline."""
    with open(out_path, "wb") as f:
        pickle.dump(NullIndex(), f)
    print(f"Saved stub index to {out_path} (offline mode).")


def main():
    # Load env for HF_TOKEN
    # Ensure .env values override any empty existing env vars.
    load_dotenv(Path(__file__).parent / ".env", override=True)
    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        raise RuntimeError("HF_TOKEN not set; add it to backend/.env")

    base = Path(__file__).parent
    candidates = [base / "data" / "split_md", base / "data" / "md"]
    md_paths = [str(p) for p in candidates if p.exists()]
    if not md_paths:
        raise RuntimeError("No markdown source folders found (looked in data/split_md and data/md)")

    md_files = collect_markdown(md_paths)
    if not md_files:
        raise RuntimeError("No markdown files found in source folders.")

    print(f"Found {len(md_files)} markdown files; loading...")
    reader = SimpleDirectoryReader(input_files=md_files)
    docs = reader.load_data()

    # Chunk documents for better retrieval
    splitter = SentenceSplitter(chunk_size=800, chunk_overlap=100)
    out_path = base / "character_index.pkl"

    try:
        service_ctx = ServiceContext.from_defaults(
            embed_model=HuggingFaceEmbedding(model_name="BAAI/bge-small-en-v1.5", token=hf_token),
            node_parser=splitter,
        )
        print("Building index (this may take a few minutes on first run)...")
        index = VectorStoreIndex.from_documents(docs, service_context=service_ctx)
        with open(out_path, "wb") as f:
            pickle.dump(index, f)
        print(f"Saved index to {out_path}")
    except Exception as exc:
        logging.exception("Index build failed; writing stub index instead: %s", exc)
        build_stub_index(out_path)


if __name__ == "__main__":
    main()
