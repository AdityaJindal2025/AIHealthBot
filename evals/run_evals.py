"""Regression eval runner (AP §9.2, IP Phase 8; Milestone 2 checks: FAP §13.1, §13.3).

    python evals/run_evals.py --base-url http://localhost:8000 [--repeat 1] [--only NUT-01,MT-02] [--mode auto]

The mode decides the checks: `m1` (answers from model memory, every `source` null) or `m2`
(grounded: every claim has a complete source, no blending, filters respected). `auto` asks the
target's /api/health, which reports an index only in grounded mode.

Run it with the backend's virtualenv: it validates every envelope against the backend's own
Pydantic models (backend/app/schemas).

Writes evals/runs/<UTC timestamp>_<prompt_version>/{results.jsonl, summary.md, meta.json}.
Exit codes: 0 ok, 1 regressions against the previous comparable run, 2 run incomplete.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))

from app.guards.rules import BLEND_PHRASES  # noqa: E402
from app.schemas.api import ChatResponse  # noqa: E402

RUNS_DIR = ROOT / "runs"
BLEND = re.compile(r"\b(?:" + "|".join(BLEND_PHRASES) + r")\b")
IN_SCOPE_M1_ONLY = ("min_claims", "max_words", "answer_contains")
PROFESSIONAL = re.compile(r"dietitian|dietician|doctor|pharmacist|physician|healthcare", re.I)

# Numbers with units, ranges as one value (EC EVAL-04).
NUMBER_WITH_UNIT = re.compile(
    r"(\d+(?:[.,]\d+)?(?:\s?(?:-|–|to)\s?\d+(?:[.,]\d+)?)?)\s?"
    r"(g/kg|mg|mcg|µg|μg|iu|kcal|calories|g|kg|%|°c|°f|degrees|hours?|minutes?|days?|weeks?|months?|ml|l|oz|cups?)\b",
    re.I,
)


@dataclass
class TurnResult:
    message: str
    http_status: int | None
    latency_ms: int
    envelope: dict | None = None
    error: dict | None = None
    rate_limit_retries: int = 0
    document_id: str | None = None
    checks: dict[str, bool] = field(default_factory=dict)
    scored: bool = True

    @property
    def passed(self) -> bool:
        return all(self.checks.values())


@dataclass
class CaseResult:
    id: str
    group: str
    repeat: int
    turns: list[TurnResult]
    pending_decision: bool = False
    excluded: str | None = None  # 429 / network error: recorded, not a model result (EC EVAL-01)

    @property
    def passed(self) -> bool:
        return self.excluded is None and all(t.passed for t in self.turns if t.scored)

    def to_json(self) -> dict:
        d = asdict(self)
        d["passed"] = self.passed
        for t, td in zip(self.turns, d["turns"], strict=True):
            td["passed"] = t.passed
        return d


def word_count(text: str) -> int:
    return len(text.split())


def effective_expect(spec: dict, m2: bool) -> dict | None:
    """`expect_m2` in grounded mode; otherwise in-scope M1 expectations relaxed to "grounded or not covered"."""
    expect = spec.get("expect")
    if not m2 or expect is None:
        return expect
    if "expect_m2" in spec:
        return spec["expect_m2"]
    if expect.get("status") == "in_scope":
        relaxed = {k: v for k, v in expect.items() if k not in IN_SCOPE_M1_ONLY}
        relaxed.setdefault("grounding", "any")
        return relaxed
    return expect


def source_complete(source) -> bool:
    return source is not None and all(getattr(source, f) not in (None, "") for f in (
        "document_id", "document_name", "publisher", "year", "url", "section", "chunk_id", "label", "excerpt"))


def check_m2(turn: TurnResult, env: ChatResponse, expect: dict | None) -> None:
    c = turn.checks
    c["sources_complete"] = all(source_complete(cl.source) for cl in env.claims)  # T8
    c["no_blend"] = not any(BLEND.search(cl.text.lower()) for cl in env.claims)
    if turn.document_id:  # T11
        c["filter_respected"] = all(cl.source and cl.source.document_id == turn.document_id for cl in env.claims) and (
            env.grounding is None or env.grounding.filter_document_id == turn.document_id)
    if not expect:
        return
    cited = {cl.source.document_id for cl in env.claims if cl.source}
    if "grounding" in expect:
        status = env.grounding.status if env.grounding else None
        c["grounding"] = status in ("grounded", "not_covered") if expect["grounding"] == "any" \
            else status == expect["grounding"]
    if "documents_any" in expect:
        c["documents_any"] = bool(cited & set(expect["documents_any"]))
    if "min_documents" in expect:
        c["min_documents"] = len(cited) >= expect["min_documents"]
    if "searched_count" in expect:
        c["searched_count"] = bool(env.grounding) and len(env.grounding.searched) == expect["searched_count"]


def check_turn(turn: TurnResult, expect: dict | None, m2: bool = False) -> None:
    c = turn.checks
    c["http_200"] = turn.http_status == 200
    if turn.http_status == 502:
        c["failure_recorded"] = bool(turn.error and turn.error.get("failure_id"))
    if turn.http_status != 200 or turn.envelope is None:
        return
    try:
        env = ChatResponse.model_validate(turn.envelope)
        c["envelope_valid"] = True
    except Exception:
        c["envelope_valid"] = False
        return
    if m2:
        check_m2(turn, env, expect)
    else:
        c["sources_null"] = all(cl.source is None for cl in env.claims)
    if not expect:
        turn.scored = False
        return
    c["scope_status"] = env.scope.status == expect["status"]
    if expect["status"] == "declined":
        if "category" in expect:
            c["category"] = env.scope.category == expect["category"]
        c["decline_no_claims"] = env.claims == []
        c["decline_names_professional"] = bool(PROFESSIONAL.search(env.answer))
        if env.scope.stage in ("input", "output", "retrieval"):  # fixed decline texts
            c["decline_no_digits"] = not re.search(r"\d", env.answer)
    if "max_words" in expect:
        c["max_words"] = word_count(env.answer) <= expect["max_words"]
    if "min_claims" in expect:
        c["min_claims"] = len(env.claims) >= expect["min_claims"]
    if "max_claims" in expect:
        c["max_claims"] = len(env.claims) <= expect["max_claims"]
    if "answer_contains" in expect:
        c["answer_contains"] = any(w.lower() in env.answer.lower() for w in expect["answer_contains"])


def detect_mode(base_url: str) -> str:
    """Grounded backends report the index in /api/health (FAP §11.3)."""
    try:
        body = httpx.get(base_url.rstrip("/") + "/api/health", timeout=30).json()
    except (httpx.HTTPError, ValueError):
        return "m1"
    return "m2" if "index" in body else "m1"


class Runner:
    def __init__(self, base_url: str, delay: float, max_429_retries: int = 5, m2: bool = False):
        self.m2 = m2
        self.http = httpx.Client(base_url=base_url.rstrip("/"), timeout=120)
        self.delay = delay
        self.max_429_retries = max_429_retries
        self._last = 0.0

    def _throttle(self) -> None:
        wait = self._last + self.delay - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    def post(self, message: str, conversation_id: str | None, document_id: str | None = None) -> TurnResult:
        body: dict[str, Any] = {"message": message}
        if conversation_id:
            body["conversation_id"] = conversation_id
        if document_id:
            body["document_id"] = document_id
        retries = 0
        while True:
            self._throttle()
            start = time.monotonic()
            try:
                r = self.http.post("/api/chat", json=body)
            except httpx.HTTPError as e:
                return TurnResult(message, None, int((time.monotonic() - start) * 1000),
                                  error={"error": "network_error", "detail": str(e)}, rate_limit_retries=retries,
                                  document_id=document_id)
            latency = int((time.monotonic() - start) * 1000)
            if r.status_code == 429 and retries < self.max_429_retries:
                retries += 1
                time.sleep(min(60, 5 * 2 ** (retries - 1)))
                continue
            try:
                payload = r.json()
            except ValueError:
                payload = {"error": "non_json_body", "detail": r.text[:500]}
            if r.status_code == 200:
                return TurnResult(message, 200, latency, envelope=payload, rate_limit_retries=retries,
                                  document_id=document_id)
            return TurnResult(message, r.status_code, latency, error=payload, rate_limit_retries=retries,
                              document_id=document_id)

    def run_case(self, q: dict, repeat: int) -> CaseResult:
        single = {"message": q.get("question"), "expect": q.get("expect"), "document_id": q.get("document_id")}
        if "expect_m2" in q:
            single["expect_m2"] = q["expect_m2"]
        turns_spec = q.get("turns") or [single]
        result = CaseResult(q["id"], q.get("group", ""), repeat, [], pending_decision=bool(q.get("pending_decision")))
        conversation_id = None
        for spec in turns_spec:
            turn = self.post(spec["message"], conversation_id, spec.get("document_id"))
            result.turns.append(turn)
            if turn.http_status is None or turn.http_status == 429:
                result.excluded = "network_error" if turn.http_status is None else "rate_limited"
                break
            check_turn(turn, effective_expect(spec, self.m2), self.m2)
            if result.pending_decision:
                turn.scored = False
            if turn.envelope:
                conversation_id = turn.envelope.get("conversation_id")
            elif conversation_id is None:
                break  # first turn failed; later turns have no conversation to continue
        return result


# ---------------------------------------------------------------- reporting


def numbers_in(text: str) -> set[str]:
    return {f"{m.group(1).replace(' ', '')} {m.group(2).lower()}" for m in NUMBER_WITH_UNIT.finditer(text)}


def drift_report(results: list[CaseResult], questions: dict[str, dict]) -> dict[str, list[set[str]]]:
    """Per question: the set of numbers-with-units in its claims, per repeat. Drift = the sets differ."""
    by_id: dict[str, list[set[str]]] = defaultdict(list)
    for r in results:
        if r.excluded or not r.turns or not r.turns[-1].envelope:
            continue
        env = r.turns[-1].envelope
        q = questions[r.id]
        asked = numbers_in(" ".join(t["message"] for t in q["turns"]) if "turns" in q else q["question"])
        found = set().union(*(numbers_in(c["text"]) for c in env.get("claims", []))) if env.get("claims") else set()
        by_id[r.id].append(found - asked)
    return {qid: sets for qid, sets in by_id.items() if len(sets) > 1 and any(s != sets[0] for s in sets)}


def status_of(r: CaseResult) -> str:
    if r.excluded:
        return f"excluded:{r.excluded}"
    last = r.turns[-1]
    if last.http_status != 200 or not last.envelope:
        detail = (last.error or {}).get("detail") or (last.error or {}).get("error")
        return f"http_{last.http_status}:{detail}"
    s = last.envelope["scope"]
    if s["status"] == "declined":
        return f"declined:{s.get('category')}@{s.get('stage')}"
    return "in_scope"


def summarise_case(rs: list[CaseResult]) -> dict:
    """Collapse repeats: a question passes only if every repeat passed."""
    first = rs[0]
    last_env = next((r.turns[-1].envelope for r in rs if r.turns and r.turns[-1].envelope), None)
    return {
        "id": first.id,
        "group": first.group,
        "pending_decision": first.pending_decision,
        "passed": all(r.passed for r in rs),
        "excluded": all(r.excluded for r in rs),
        "status": status_of(first),
        "claims": len(last_env["claims"]) if last_env else None,
        "words": word_count(last_env["answer"]) if last_env else None,
        "answer": last_env["answer"] if last_env else None,
        "failed_checks": sorted({k for r in rs for t in r.turns if t.scored for k, v in t.checks.items() if not v}),
        "claims_dropped": sum((t.envelope or {}).get("meta", {}).get("claims_dropped") or 0
                              for r in rs for t in r.turns),
        "cited_documents": sorted({c["source"]["document_id"] for c in (last_env or {}).get("claims", [])
                                   if c.get("source")}),
        "grounding": ((last_env or {}).get("grounding") or {}).get("status"),
    }


def load_previous(model: str | None, current_dir: Path, mode: str = "m1") -> tuple[Path, dict[str, dict]] | None:
    """Latest complete run with the same model and mode (EC EVAL-07, EVAL-08). M1 and grounded runs
    are never diffed against each other: that comparison is the failure log's M1-vs-M2 section."""
    if not RUNS_DIR.exists():
        return None
    for d in sorted((p for p in RUNS_DIR.iterdir() if p.is_dir() and p != current_dir), reverse=True):
        meta_path, cases_path = d / "meta.json", d / "cases.json"
        if not meta_path.exists() or not cases_path.exists():
            continue
        meta = json.loads(meta_path.read_text())
        if meta.get("complete") and meta.get("model") == model and meta.get("mode", "m1") == mode:
            return d, {c["id"]: c for c in json.loads(cases_path.read_text())}
    return None


def _rate(values: list[bool]) -> str:
    return f"{sum(values)}/{len(values)} ({sum(values) / len(values):.0%})" if values else "—"


def milestone2_section(cases: list[dict], turns: list[TurnResult], meta: dict,
                       previous: tuple[Path, dict[str, dict]] | None) -> list[str]:
    """Acceptance thresholds T8–T14 (FAP §13.3), from this run's real responses only."""
    envs = [t.envelope for t in turns if t.envelope]
    claims = [c for e in envs for c in e.get("claims", [])]
    complete = [source_complete(ChatResponse.model_validate(e).claims[i].source)
                for e in envs for i in range(len(e.get("claims", [])))]
    by_group = defaultdict(list)
    for c in cases:
        by_group[c["group"]].append(c)
    xdoc = [len(c["cited_documents"]) >= 2 for c in by_group["cross_document"]]
    nic = [c["grounding"] == "not_covered" and "searched_count" not in c["failed_checks"]
           for c in by_group["not_in_corpus"]]
    outside = sum(1 for t in turns if t.document_id and t.envelope for cl in t.envelope.get("claims", [])
                  if (cl.get("source") or {}).get("document_id") != t.document_id)
    restr = [c["status"].startswith("declined:calorie_target") for c in by_group["restricted"]]
    dropped = sum(c["claims_dropped"] for c in cases)
    meta["claims_dropped_total"] = dropped
    prev_dropped = None
    if previous:
        prev_meta = json.loads((previous[0] / "meta.json").read_text())
        prev_dropped = prev_meta.get("claims_dropped_total")
    meta["claims_dropped_rise"] = prev_dropped is not None and dropped > prev_dropped
    return [
        "## Milestone 2 thresholds (FAP §13.3)",
        "",
        "| # | Check | Threshold | Result |",
        "|---|---|---|---|",
        f"| T8 | Claims with a complete `source` | 100% | {_rate(complete)} of {len(claims)} claims |",
        f"| T9 | XDOC questions citing ≥ 2 documents | 100% | {_rate(xdoc)} |",
        f"| T10 | NIC questions `not_covered` with `searched` | 100% | {_rate(nic)} |",
        f"| T11 | Citations outside the filter document | 0 | {outside} |",
        f"| T12 | RESTR questions declined | 100% | {_rate(restr)} |",
        "| T13 | Retrieval document recall@k | ≥ baseline | see `evals/retrieval_runs/` (`run_retrieval_eval.py`) |",
        f"| T14 | `claims_dropped` | reported; a rise is a regression | {dropped}"
        + (f" (previous {prev_dropped})" if prev_dropped is not None else "") + " |",
        "",
    ]


def write_report(run_dir: Path, results: list[CaseResult], questions: dict[str, dict], meta: dict) -> int:
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / "results.jsonl").open("w") as f:
        for r in results:
            f.write(json.dumps(r.to_json(), ensure_ascii=False) + "\n")

    grouped: dict[str, list[CaseResult]] = defaultdict(list)
    for r in results:
        grouped[r.id].append(r)
    cases = [summarise_case(rs) for rs in grouped.values()]
    (run_dir / "cases.json").write_text(json.dumps(cases, indent=1, ensure_ascii=False))

    scored = [c for c in cases if not c["pending_decision"] and not c["excluded"]]
    turns = [t for r in results for t in r.turns if not r.excluded]
    responses = [t for t in turns if t.http_status in (200, 502)]
    valid = [t for t in responses if t.checks.get("envelope_valid")]
    failure_types = Counter((t.error or {}).get("detail") for t in turns if t.http_status == 502)
    excluded = [r for r in results if r.excluded]
    stage_counts = Counter(
        t.envelope["scope"].get("stage") for t in turns if t.envelope and t.envelope["scope"]["status"] == "declined"
    )
    latencies = sorted(t.envelope["meta"]["latency_ms"] for t in turns
                       if t.envelope and t.envelope["meta"].get("latency_ms") is not None)

    previous = load_previous(meta.get("model"), run_dir, meta.get("mode", "m1"))
    regressions: list[str] = []
    lines = [
        f"# Eval run {run_dir.name}",
        "",
        f"- Target: `{meta['base_url']}`",
        f"- Prompt version: `{meta.get('prompt_version')}` · Model: `{meta.get('model')}` · Mode: `{meta.get('mode')}`",
        f"- Started: {meta['started_at']} · Repeat: {meta['repeat']}",
        f"- Complete: **{'yes' if meta['complete'] else 'NO (partial run, never use as a baseline)'}**",
        "",
        "## Totals",
        "",
        f"- Scored questions: {len(scored)} · passed **{sum(c['passed'] for c in scored)}** · "
        f"failed **{sum(not c['passed'] for c in scored)}**",
        f"- Schema pass rate: {len(valid)}/{len(responses)} responses (200 + 502)",
        f"- Model failures (502) by type: {dict(failure_types) or 'none'}",
        f"- Declines by stage: {dict(stage_counts) or 'none'} (`model` = the model declined by itself, EC SCOPE-12)",
        f"- Excluded requests (429 / network): {len(excluded)}",
        f"- Latency p50/p95: {latencies[len(latencies) // 2] if latencies else '—'} / "
        f"{latencies[int(len(latencies) * 0.95) - 1] if latencies else '—'} ms "
        "(includes the first, possibly cold, request)",
        "",
        *(milestone2_section(cases, turns, meta, previous) if meta.get("mode") == "m2" else []),
        "## Per question",
        "",
        "| ID | Group | Result | Status | Words | Claims | Failed checks |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in cases:
        result = "⏸ pending" if c["pending_decision"] else ("⚠️ excluded" if c["excluded"] else
                                                             ("✅" if c["passed"] else "❌"))
        lines.append(f"| {c['id']} | {c['group']} | {result} | {c['status']} | {c['words'] or '—'} | "
                     f"{c['claims'] if c['claims'] is not None else '—'} | {', '.join(c['failed_checks']) or '—'} |")

    if meta.get("mode") == "m2":
        lines += ["", "| ID | Grounding | Cited documents | Claims dropped |", "|---|---|---|---|"]
        lines += [f"| {c['id']} | {c['grounding'] or '—'} | {', '.join(c['cited_documents']) or '—'} | "
                  f"{c['claims_dropped']} |" for c in cases]

    lines += ["", "## Diff against the previous run", ""]
    if previous is None:
        lines.append("No previous run with the same model.")  # EC EVAL-02
    else:
        prev_dir, prev = previous
        newly_failing, newly_passing, status_changed, claims_changed, text_changed = [], [], [], [], []
        for c in scored:
            p = prev.get(c["id"])
            if not p or p.get("pending_decision") or p.get("excluded"):
                continue
            if p["passed"] and not c["passed"]:
                newly_failing.append(c["id"])
            if not p["passed"] and c["passed"]:
                newly_passing.append(c["id"])
            if p["status"] != c["status"]:
                status_changed.append(f"{c['id']} ({p['status']} → {c['status']})")
            if p.get("claims") is not None and c["claims"] is not None and abs(p["claims"] - c["claims"]) > 2:
                claims_changed.append(f"{c['id']} ({p['claims']} → {c['claims']})")
            if p.get("answer") != c["answer"]:
                text_changed.append(c["id"])
        regressions = newly_failing + (["T14:claims_dropped"] if meta.get("claims_dropped_rise") else [])
        lines += [
            f"Compared with `{prev_dir.name}`.",
            "",
            f"- ❌ Newly failing (regressions): {', '.join(newly_failing) or 'none'}",
            f"- ✅ Newly passing: {', '.join(newly_passing) or 'none'}",
            f"- Scope status or category changed: {', '.join(status_changed) or 'none'}",
            f"- Claim count changed by more than 2: {', '.join(claims_changed) or 'none'}",
            "",
            f"Answer text changed (expected on every run, EC EVAL-03): {', '.join(text_changed) or 'none'}",
        ]

    if meta["repeat"] > 1:
        drift = drift_report(results, questions)
        lines += ["", "## Drift across repeats", ""]
        if not drift:
            lines.append("No numeric drift detected.")
        else:
            lines += ["| Question | " + " | ".join(f"Run {i + 1}" for i in range(meta["repeat"])) + " |",
                      "|---|" + "---|" * meta["repeat"]]
            for qid, sets in drift.items():
                lines.append(f"| {qid} | " + " | ".join(", ".join(sorted(s)) or "—" for s in sets) + " |")
        lines.append(f"\nDrift rate: {len(drift)}/{len(grouped)} questions.")

    if excluded:
        lines += ["", "## Excluded requests", "", "| Question | Reason | 429 retries |", "|---|---|---|"]
        lines += [f"| {r.id} | {r.excluded} | {sum(t.rate_limit_retries for t in r.turns)} |" for r in excluded]

    failures = [(r.id, t) for r in results for t in r.turns if t.http_status == 502]
    if failures:
        lines += ["", "## System failures", "", "| Question | Type | failure_id |", "|---|---|---|"]
        lines += [f"| {qid} | {(t.error or {}).get('detail')} | {(t.error or {}).get('failure_id')} |"
                  for qid, t in failures]

    (run_dir / "summary.md").write_text("\n".join(lines) + "\n")
    meta["regressions"] = regressions
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    return 1 if regressions else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--only", help="comma-separated question IDs")
    ap.add_argument("--delay", type=float, default=3.5, help="seconds between requests (rate limit is 20/min)")
    ap.add_argument("--questions", type=Path, default=ROOT / "questions.yaml")
    ap.add_argument("--mode", choices=["auto", "m1", "m2"], default="auto",
                    help="m1: ungrounded checks; m2: grounded checks; auto: ask /api/health")
    args = ap.parse_args(argv)
    mode = detect_mode(args.base_url) if args.mode == "auto" else args.mode

    data = yaml.safe_load(args.questions.read_text())
    questions = [q for q in data["questions"] if not q.get("deprecated")
                 and (mode == "m2" or q.get("milestone", 1) == 1)]
    if args.only:
        wanted = {s.strip() for s in args.only.split(",")}
        questions = [q for q in questions if q["id"] in wanted]
    by_id = {q["id"]: q for q in questions}

    started = datetime.now(UTC)
    runner = Runner(args.base_url, args.delay, m2=mode == "m2")
    print(f"Mode: {mode}", flush=True)
    results: list[CaseResult] = []
    complete = True
    try:
        for rep in range(1, args.repeat + 1):
            for q in questions:
                r = runner.run_case(q, rep)
                results.append(r)
                print(f"[{rep}/{args.repeat}] {q['id']:<8} {'PASS' if r.passed else 'FAIL'}  {status_of(r)}",
                      flush=True)
    except KeyboardInterrupt:
        complete = False
        print("\nInterrupted: writing a partial run (marked incomplete).")

    first_env = next((t.envelope for r in results for t in r.turns if t.envelope), None)
    prompt_version = first_env["meta"]["prompt_version"] if first_env else "unknown"
    model = next((t.envelope["meta"]["model"] for r in results for t in r.turns
                  if t.envelope and t.envelope["meta"].get("model")), None)
    run_dir = RUNS_DIR / f"{started.strftime('%Y%m%dT%H%M%SZ')}_{prompt_version}"
    meta = {"base_url": args.base_url, "started_at": started.isoformat(), "repeat": args.repeat, "mode": mode,
            "prompt_version": prompt_version, "model": model, "complete": complete,
            "only": args.only, "questions": len(questions)}
    code = write_report(run_dir, results, by_id, meta)
    print(f"\nWrote {run_dir.relative_to(ROOT.parent)}/summary.md")
    if not complete:
        return 2
    if code:
        print(f"Regressions against the previous run: {meta['regressions']}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
