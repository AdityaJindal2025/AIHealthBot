"""Builds the chunk index: load → chunk → tag → embed → replace (FAP §6.3).

    python -m app.rag.build_index                 # always rebuild
    python -m app.rag.build_index --if-changed    # do nothing if the index is current
    python -m app.rag.build_index --write-report  # also regenerate corpus/build_report.md

`corpus_version` hashes everything that decides the index: the corpus files, the chunker
settings and the embedding model. Embedding happens **before** any write, and the old
chunks are replaced in one transaction, so a failed build never leaves a half-built or
empty index behind; the previous one stays in place.
"""

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Document, IndexedChunk, IndexMeta
from app.rag.chunker import ChunkSettings, chunk_corpus
from app.rag.corpus import CorpusError, corpus_digest, load_corpus
from app.rag.embedder import Embedder, get_embedder
from app.rag.tagger import tag_chunks

log = logging.getLogger("app.rag.index")


class BuildError(RuntimeError):
    pass


@dataclass(frozen=True)
class BuildResult:
    built: bool
    corpus_version: str
    chunk_count: int
    seconds: float


def compute_corpus_version(corpus_dir: str | Path, chunk_settings: ChunkSettings, embedder: Embedder) -> str:
    return expected_corpus_version(corpus_dir, chunk_settings, embedder.model_id, embedder.dims)


def expected_corpus_version(corpus_dir: str | Path, chunk_settings: ChunkSettings, model_id: str, dims: int) -> str:
    """The version an index built now would have; health compares it without loading the model."""
    return corpus_digest(corpus_dir, chunk_settings.fingerprint(), model_id, str(dims))


def build_index(
    db: Session,
    *,
    corpus_dir: str | Path,
    chunk_settings: ChunkSettings,
    embedder: Embedder,
    allow_unverified: bool,
    if_changed: bool = False,
) -> BuildResult:
    started = time.monotonic()
    version = compute_corpus_version(corpus_dir, chunk_settings, embedder)
    current = db.scalar(select(IndexMeta))
    if if_changed and current is not None and current.corpus_version == version:
        return BuildResult(False, version, current.chunk_count, time.monotonic() - started)

    corpus = load_corpus(corpus_dir, allow_unverified=allow_unverified)
    chunks = tag_chunks(chunk_corpus(corpus, chunk_settings).chunks)
    vectors = embedder.embed_documents([c.embed_text for c in chunks])
    if vectors.shape != (len(chunks), embedder.dims):
        raise BuildError(f"embedder returned shape {vectors.shape}, expected {(len(chunks), embedder.dims)}")

    try:
        db.execute(delete(IndexedChunk))
        db.execute(delete(IndexMeta))
        for doc in corpus.documents.values():
            db.merge(Document(
                document_id=doc.document_id, title=doc.title, publisher=doc.publisher,
                publisher_short=doc.publisher_short, year=doc.year, url=doc.url, aliases=list(doc.aliases),
                publisher_aliases=list(doc.publisher_aliases), verified_by=doc.verified_by,
                verified_on=doc.verified_on,
            ))
        db.execute(delete(Document).where(Document.document_id.not_in(list(corpus.documents))))
        db.add_all(
            IndexedChunk(
                chunk_id=c.chunk_id, document_id=c.document_id, section_path=list(c.section_path),
                section=c.section, page_start=c.page_start, page_end=c.page_end, ordinals=list(c.ordinals),
                kind=c.kind, text=c.text, embed_text=c.embed_text, token_count=c.token_count,
                restricted_category=c.restricted_category, restricted_rule_id=c.restricted_rule_id,
                embedding=vector, corpus_version=version,
            )
            for c, vector in zip(chunks, vectors, strict=True)
        )
        db.add(_index_meta(version, embedder, chunk_settings, len(chunks)))
        db.commit()
    except Exception:
        db.rollback()
        raise

    seconds = time.monotonic() - started
    log.info("index_built", extra={"corpus_version": version, "chunk_count": len(chunks),
                                   "embedding_model": embedder.model_id, "seconds": round(seconds, 2)})
    return BuildResult(True, version, len(chunks), seconds)


def _index_meta(version: str, embedder: Embedder, chunk_settings: ChunkSettings, count: int) -> IndexMeta:
    return IndexMeta(corpus_version=version, embedding_model=embedder.model_id, dims=embedder.dims,
                     chunker_settings=chunk_settings.as_dict(), chunk_count=count)


def main(argv: list[str] | None = None) -> int:
    from app.db.session import SessionLocal
    from app.logging_config import configure_logging

    parser = argparse.ArgumentParser(description="Build the chunk index")
    parser.add_argument("--if-changed", action="store_true", help="skip if the index is already current")
    parser.add_argument("--write-report", action="store_true", help="also regenerate corpus/build_report.md")
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    db = SessionLocal()
    try:
        result = build_index(
            db,
            corpus_dir=settings.CORPUS_DIR,
            chunk_settings=ChunkSettings.from_settings(settings),
            embedder=get_embedder(),
            allow_unverified=settings.ALLOW_UNVERIFIED_REGISTRY,
            if_changed=args.if_changed,
        )
    except (CorpusError, BuildError) as e:
        print(f"index build failed: {e}", file=sys.stderr)
        return 1
    finally:
        db.close()

    if result.built:
        print(f"built index {result.corpus_version}: {result.chunk_count} chunks in {result.seconds:.1f}s")
    else:
        print(f"index {result.corpus_version} is current ({result.chunk_count} chunks); nothing to do")
    if args.write_report:
        from app.rag import report

        report.main([])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
