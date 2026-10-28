# System Prompt Changelog

One entry per prompt version. A new version is a new file (`system_vN.md`); old files are never edited.
Every entry links to the eval run that was committed with it (see the README's prompt-change workflow).

| Version | Date | What changed | Why | Eval run |
|---|---|---|---|---|
| v1 | 2026-09-29 | First prompt: role, how to answer, claim breakdown with `source: null`, length (60–150 words, max 200, up to 5 bullets), exclusions with referral, off-domain redirect, format rule. | Initial version (AP §8). | _Pending: first baseline run (IP Phase 8)._ |
| v2 | 2026-10-26 | Grounded prompt (FAP §8.1): answer only from the numbered sources in the user turn; one source label per atomic claim; numbers copied exactly; per-document claims, never blended or ranked; population-level framing; `not_covered` when the sources don't answer; M1 exclusions plus "no daily calorie figures even when a source states one"; at most 8 claims under 40 words; `GroundedOutput` JSON only. Used with `RAG_ENABLED=true`. | Milestone 2: replace model memory with retrieved text (FPS §1). The calorie-figure line keeps WHO's "2000 calories per day" reference out of claims, which the M1 output guard (OUT-CAL-02) would otherwise decline. | _Pending: first grounded run against the real model (Phase 9)._ |
