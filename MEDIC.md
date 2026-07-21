# Medic loop — self-healing runbook (Pivot Itinerary Automation)

> A scheduled Claude session ("the medic") that turns a manual-review flag into a
> reviewed **pull request**, so the tedious diagnose→fix→test cycle runs on its
> own while a human keeps the final gate before anything reaches a client
> document. This file is the medic's standing instructions — a fresh session
> reads it and CLAUDE.md, then follows the steps below.

## Why a human still merges
Extractor fixes must be diagnosed against the **real PDF/body** (CLAUDE.md §9),
and a subtly-wrong regex could ship a **factually incorrect travel document** —
the exact failure §7 forbids. So the medic **proposes** (opens a PR); it never
auto-merges to `main`, and the cloud runner only picks up a fix after a human
merges it. Not every flag is even a code bug — a genuinely ambiguous email, a
missing PNR, or a non-confirmation must **stay flagged for a human**.

## What counts as an unresolved flag
`flagged_ids.json` lists every `message_id` the poll has flagged. A flag is
**unresolved** and the medic should work it when its `message_id` is:
- in `flagged_ids.json`, AND
- NOT in `processed_ids.json` (a later poll didn't already succeed on it), AND
- NOT in `medic_ids.json` (the medic hasn't already opened a PR/issue for it).

## Steps (per run)
1. `git fetch origin main && git checkout -B claude/medic origin/main` for a clean base.
2. Read `flagged_ids.json`, `processed_ids.json`, `medic_ids.json`. Compute the
   unresolved set (above). If empty → **end silently** (no email, no PR).
3. For each unresolved `message_id`:
   a. **Diagnose (redacted, never local):** dispatch `medic-diagnose.yml` with the
      id (`gh`/MCP `actions_run_trigger`, ref `main`), wait, read the job log.
      The log is PII-redacted by `tools/medic_diagnose.py`; the actual PDF/body
      never leaves CI. Read the `VERDICT:` line.
   b. **Classify from the verdict:**
      - `resolved` → a later poll will reprocess it cleanly; just record the id in
        `medic_ids.json` (worked, no action needed) and move on.
      - `needs-human` (no portal matched) → open a short GitHub **issue** (title
        `Manual review: <redacted subject>`), record the id, move on. Do NOT
        attempt a code fix.
      - `parser-bug` / `parser-error` → go to (c).
   c. **Fix it:** using the redacted source + the per-field "missing:" breakdown,
      patch the matching `extract_*` in `extractors.py`. Follow the §9 rules
      (handle all three IATA designator shapes via `_IATA_DESIG`; never fabricate;
      accuracy first). Add a **zero-PII** regression fixture under `tests/fixtures/`
      mirroring the real (redacted) layout, wire it into `tests/test_extractors.py`
      `CASES`, and `UPDATE_GOLDEN=1 python -m pytest tests/ -q` to snapshot it.
   d. **Verify:** `python -m pytest tests/ -q` must be green. If the fix can't be
      made confidently (layout too ambiguous, would risk a wrong document), STOP
      — open a needs-human issue instead.
   e. **Propose:** commit, push the branch, open a PR to `main` describing the
      root cause, the fix, and the new test. Record the id in `medic_ids.json`.
4. Commit `medic_ids.json` (and any issue/PR refs) so the next run doesn't repeat
   work. One PR per flag; never auto-merge.

## Guardrails
- **Never** print un-redacted PII (names, tickets, PNRs) into any public log,
  commit, issue, or PR. Diagnosis happens only through `medic-diagnose.yml`.
- **Never** auto-merge or push to `main`. Human review is the gate.
- **Never** widen a regex so far it matches noise — prefer a precise, layout-
  anchored pattern plus a regression test, exactly as CLAUDE.md §8/§9 do.
- If a flag has already been worked (`medic_ids.json`) but the human rejected the
  PR, leave it for the human — do not reopen automatically.
- Recording an id in `medic_ids.json` means "the medic has handled this once",
  covering all three outcomes (resolved / needs-human / PR opened).

## Files
| File | Role |
|---|---|
| `tools/medic_diagnose.py` | Redacted any-portal diagnosis (run in CI only). |
| `.github/workflows/medic-diagnose.yml` | Dispatchable CI job that runs the above. |
| `medic_ids.json` | Dedup log (message_id only) of flags the medic has handled. |
| `flagged_ids.json` | Flags raised by the poll (message_id only). |
| `MEDIC.md` | This runbook. |
