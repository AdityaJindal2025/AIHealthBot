"""Retrieval eval: recall, MRR and score-floor calibration (FAP §7.4, §13.2, Phase 4).

    python evals/run_retrieval_eval.py [--embedding-model BAAI/bge-small-en-v1.5] [--no-write]

Run it with the backend's virtualenv, installed with the `embed` extra. No model calls and no
server: the index is built in-process into an in-memory SQLite database (MemoryStore), from
the committed corpus, with the configured embedder.

Writes evals/retrieval_runs/<UTC timestamp>/{results.jsonl, summary.md}. Exit codes: 0 ok,
1 document recall@k below evals/retrieval_baseline.json (a regression).
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))

# Settings are read at import time: an in-memory index, and the dev registry is allowed because
# this measures retrieval, not citations.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ.setdefault("ALLOW_UNVERIFIED_REGISTRY", "true")

QUESTIONS = ROOT / "retrieval_questions.yaml"
RUNS_DIR = ROOT / "retrieval_runs"
BASELINE = ROOT / "retrieval_baseline.json"
K_VALUES = (4, 6, 8)
CAP_VALUES = (2, 3)
FLOOR_KEEP = 0.95  # the floor keeps at least this share of answerable questions


def load_questions() -> list[dict]:
    data = yaml.safe_load(QUESTIONS.read_text())
    return [q for q in data["questions"] if not q.get("deprecated")]


def evaluate(db, questions: list[dict], k: int, cap: int) -> list[dict]:
    from app.rag.retriever import retrieve

    rows = []
    for q in questions:
        result = retrieve(db, q["question"], document_id=q.get("document_id"), k=k, max_per_doc=cap)
        docs = [h.document_id for h in result.hits]
        expected = q.get("expect_documents") or []
        row = {
            "id": q["id"],
            "group": q["group"],
            "question": q["question"],
            "top_score": result.top_score,
            "restricted_top": result.restricted_top,
            "hits": [{"label": h.label, "chunk_id": h.chunk_id, "score": h.score} for h in result.hits],
            "withheld": [w.chunk_id for w in result.withheld],
            "mode": result.mode,
            "filter_document_id": result.filter_document_id,
        }
        if expected:
            found = [d for d in expected if d in docs]
            row["doc_hit"] = bool(found)
            row["doc_recall"] = len(found) / len(expected)
            first = next((i for i, d in enumerate(docs, start=1) if d in expected), None)
            row["reciprocal_rank"] = 1 / first if first else 0.0
        if q.get("expect_ordinals"):
            ordinal_sets = {(h.document_id, o) for h in result.hits for o in _ordinals(db, h.chunk_id)}
            wanted = [tuple(x) for x in q["expect_ordinals"]]
            row["chunk_recall"] = sum(1 for w in wanted if w in ordinal_sets) / len(wanted)
        if q.get("document_id"):
            row["filter_respected"] = all(d == q["document_id"] for d in docs)
        if q.get("expect_restricted"):
            row["restricted_ok"] = result.restricted_top == q["expect_restricted"]
        rows.append(row)
    return rows


def _ordinals(db, chunk_id: str) -> list[int]:
    from app.db.models import IndexedChunk

    return db.get(IndexedChunk, chunk_id).ordinals


def metrics(rows: list[dict]) -> dict:
    def mean(values: list[float]) -> float | None:
        return round(statistics.fmean(values), 4) if values else None

    answerable = [r for r in rows if r["group"] in ("answerable", "filtered")]
    xdoc = [r for r in rows if r["group"] == "xdoc"]
    scored = answerable + xdoc
    return {
        "doc_hit_at_k": mean([float(r["doc_hit"]) for r in answerable]),
        "doc_recall_at_k": mean([r["doc_recall"] for r in scored]),
        "xdoc_recall_at_k": mean([r["doc_recall"] for r in xdoc]),
        "xdoc_all_found": mean([float(r["doc_recall"] == 1.0) for r in xdoc]),
        "chunk_recall_at_k": mean([r["chunk_recall"] for r in rows if "chunk_recall" in r]),
        "mrr": mean([r["reciprocal_rank"] for r in scored]),
        "filter_respected": mean([float(r["filter_respected"]) for r in rows if "filter_respected" in r]),
        "restricted_ok": mean([float(r["restricted_ok"]) for r in rows if "restricted_ok" in r]),
    }


def distribution(values: list[float]) -> dict:
    v = sorted(values)
    if not v:
        return {}

    def q(p: float) -> float:
        return round(v[min(len(v) - 1, int(p * len(v)))], 4)

    return {"n": len(v), "min": round(v[0], 4), "p05": q(0.05), "p25": q(0.25), "median": q(0.5),
            "p75": q(0.75), "max": round(v[-1], 4)}


def suggest_floor(rows: list[dict]) -> dict:
    """The highest floor that keeps ≥95% of answerable questions, and what it rejects.

    Calibrated on all-documents questions only: the floor is not applied to filtered requests,
    whose top score is limited to one document (the model's `not_covered` checks those).
    """
    answerable = sorted(r["top_score"] for r in rows if r["group"] in ("answerable", "xdoc"))
    nic = [r["top_score"] for r in rows if r["group"] == "not_in_corpus"]
    drop = int((1 - FLOOR_KEEP) * len(answerable))  # how many answerable questions may fall below
    floor = round(answerable[drop] - 1e-4, 4)
    return {
        "floor": floor,
        "answerable_kept": round(sum(s >= floor for s in answerable) / len(answerable), 4),
        "not_in_corpus_rejected": round(sum(s < floor for s in nic) / len(nic), 4) if nic else None,
        "not_in_corpus_above_floor": [
            r["id"] for r in rows if r["group"] == "not_in_corpus" and r["top_score"] >= floor
        ],
    }


def write_summary(path: Path, *, model: str, corpus_version: str, chunk_count: int, k: int, cap: int,
                  sweep: dict, rows: list[dict], floor: dict, baseline: dict | None) -> None:
    m = sweep[(k, cap)]
    groups = ", ".join(f"{g} {sum(r['group'] == g for r in rows)}" for g in sorted({r["group"] for r in rows}))
    lines = [
        f"# Retrieval Eval Run {path.parent.name}",
        "",
        f"- Embedding model: `{model}`",
        f"- Corpus version: `{corpus_version}` ({chunk_count} chunks)",
        f"- Questions: {len(rows)} ({groups})",
        f"- Reported configuration: k={k}, max per document={cap}",
        "",
        "## Metrics",
        "",
        "| Metric | Value | Baseline |",
        "|---|---|---|",
    ]
    for key, value in m.items():
        base = (baseline or {}).get(key)
        lines.append(f"| {key} | {value} | {base if base is not None else '–'} |")

    lines += ["", "## Sweep (k × per-document cap)", "",
              "| k | cap | doc hit@k | doc recall@k | xdoc all found | chunk recall@k | MRR |",
              "|---|---|---|---|---|---|---|"]
    for (kk, cc), mm in sorted(sweep.items()):
        lines.append(f"| {kk} | {cc} | {mm['doc_hit_at_k']} | {mm['doc_recall_at_k']} | {mm['xdoc_all_found']} | "
                     f"{mm['chunk_recall_at_k']} | {mm['mrr']} |")

    ans = [r["top_score"] for r in rows if r["group"] in ("answerable", "xdoc")]
    filtered = [r["top_score"] for r in rows if r["group"] == "filtered"]
    nic = [r["top_score"] for r in rows if r["group"] == "not_in_corpus"]
    lines += ["", "## Top-1 Score Distributions", "", "| Set | n | min | p05 | p25 | median | p75 | max |",
              "|---|---|---|---|---|---|---|---|"]
    for name, values in (("answerable (all documents)", ans), ("filtered (not floored)", filtered),
                         ("not in corpus", nic)):
        d = distribution(values)
        lines.append(f"| {name} | {d['n']} | {d['min']} | {d['p05']} | {d['p25']} | {d['median']} | {d['p75']} | "
                     f"{d['max']} |")
    lines += [
        "",
        "## Score Floor",
        "",
        f"Suggested `RETRIEVAL_MIN_SCORE`: **{floor['floor']}** (keeps {floor['answerable_kept']:.0%} of answerable "
        f"all-documents questions; rejects {floor['not_in_corpus_rejected']:.0%} of not-in-corpus questions). "
        "The floor applies in all-documents mode only.",
        "",
        "Not-in-corpus questions still above the floor (the model's `not_covered` is the second check): "
        + (", ".join(floor["not_in_corpus_above_floor"]) or "none"),
        "",
        "## Misses (reported configuration)",
        "",
        "| ID | Group | Question | Top score | Retrieved documents |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        missed = (("doc_recall" in r and r["doc_recall"] < 1.0 and r["group"] == "xdoc")
                  or ("doc_hit" in r and not r["doc_hit"])
                  or r.get("filter_respected") is False or r.get("restricted_ok") is False)
        if missed:
            docs = sorted({h["chunk_id"].split("#")[0] for h in r["hits"]})
            lines.append(f"| {r['id']} | {r['group']} | {r['question']} | {r['top_score']:.4f} | {', '.join(docs)} |")
    path.write_text("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--embedding-model", default=None, help="override EMBEDDING_MODEL")
    parser.add_argument("--no-write", action="store_true", help="print the metrics only")
    args = parser.parse_args(argv)
    if args.embedding_model:
        os.environ["EMBEDDING_MODEL"] = args.embedding_model

    from app.config import get_settings
    from app.db.models import Base
    from app.db.session import SessionLocal, engine
    from app.rag.build_index import build_index
    from app.rag.chunker import ChunkSettings
    from app.rag.embedder import get_embedder

    settings = get_settings()
    Base.metadata.create_all(engine)
    db = SessionLocal()
    embedder = get_embedder()
    built = build_index(db, corpus_dir=settings.CORPUS_DIR, chunk_settings=ChunkSettings.from_settings(settings),
                        embedder=embedder, allow_unverified=settings.ALLOW_UNVERIFIED_REGISTRY)

    questions = load_questions()
    sweep_rows = {(k, c): evaluate(db, questions, k, c) for k in K_VALUES for c in CAP_VALUES}
    sweep = {key: metrics(rows) for key, rows in sweep_rows.items()}
    k, cap = settings.RETRIEVAL_K, settings.RETRIEVAL_MAX_PER_DOC
    rows = sweep_rows.get((k, cap)) or evaluate(db, questions, k, cap)
    sweep.setdefault((k, cap), metrics(rows))
    floor = suggest_floor(rows)
    baseline = json.loads(BASELINE.read_text()) if BASELINE.exists() else None

    print(json.dumps({"k": k, "cap": cap, **sweep[(k, cap)], "suggested_floor": floor}, indent=2))
    if not args.no_write:
        run_dir = RUNS_DIR / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        run_dir.mkdir(parents=True)
        with (run_dir / "results.jsonl").open("w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        write_summary(run_dir / "summary.md", model=embedder.model_id, corpus_version=built.corpus_version,
                      chunk_count=built.chunk_count, k=k, cap=cap, sweep=sweep, rows=rows, floor=floor,
                      baseline=baseline)
        print(f"wrote {run_dir}")

    if baseline and baseline.get("embedding_model") == embedder.model_id:
        current = sweep[(k, cap)]["doc_recall_at_k"]
        if current is not None and current < baseline["doc_recall_at_k"]:
            print(f"REGRESSION: doc_recall_at_k {current} < baseline {baseline['doc_recall_at_k']}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
