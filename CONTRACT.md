# CONTRACT - statistical forensics programme

These are the standards this programme is written to. They bind me, and anyone else
contributing to `forensics-core`, `forensic-elections` or `forensic-economy`. **Work that
breaks one of them does not count**, whatever else it achieved: a correct result reached by a
forbidden route is not usable, because the route is what its credibility rests on.

The same file is kept in all three repositories, and in the sibling
[`gosplan-env`](https://github.com/Xocas12/gosplan-env).

Each rule states **what a violation looks like concretely** and **what catches it**. A rule
nobody can test against is decoration, and is marked as such where no automated check exists
yet.

---

## 1. NO INVENTED SOURCES

A URL, DOI, dataset name, file path, repository, statistic, coefficient, sample size or citation
that has no entry in a `data/SOURCES.yaml` with real fetch evidence does not go into any file.

This is the rule the whole programme's credibility rests on. Everything else here is downstream
of it. A programme that detects fabricated numbers cannot itself contain fabricated numbers.

If you believe a resource exists but cannot confirm it, record it in `SOURCES.yaml` with
`status: unverified` and a note saying what you tried. That is a complete and correct outcome.

**A violation looks like:** writing a plausible-looking DOI into a docstring because the paper is
real and the pattern is right. Writing "roughly 95,000 precincts" when no file has been counted.
Citing a coefficient from memory of a paper you did not open. Adding a GitHub Action version tag
to a workflow because a lower one existed and versions increment.

**What catches it:** nothing automatic. Provenance is checked by review against `SOURCES.yaml`
and `data/fetch_log.jsonl`. Distinguish "not found" from "not free": a paywalled source is a
recorded fact about access, not a missing source.

## 2. STOP AND REPORT

When the plan, the data and this contract do not determine a choice, **stop and write the
question down** rather than picking the reasonable default. Recording an unresolved question
is a complete outcome, not a failure to deliver.

Fluent invention is the failure mode this rule exists to prevent, and it is fluent precisely
because the invented choice usually *is* reasonable.

**A violation looks like:** a plan that says "score the control corpus" when no control corpus
exists, answered by quietly building one and proceeding. Picking `alpha = 0.05` because it is
conventional, when the choice was never made explicitly and it changes the reported result.

**What catches it:** nothing automatic. The open questions are carried in the repository's
issues and in `docs/`; a result that depended on an undocumented choice is caught only in
review.

## 3. FROZEN TESTS

A test is not edited to make the code pass. If a test looks wrong, say why in writing before
touching it; do not skip it, do not `xfail` it, and do not special-case the implementation to
satisfy it.

A test may be changed when it is actually wrong, and the commit message must then say what the
old test asserted, why that was wrong, and what the new one asserts instead.

**A violation looks like:** adding `@pytest.mark.skip` with a comment saying the test is flaky.
Loosening `assert x < 0.2` to `assert x < 0.6` so a run passes. Deleting an assertion that fails
and keeping the ones that pass.

**What catches it:** `git diff` on `tests/` in any pull request.

## 4. NO ANALYSIS BEFORE ITS PHASE

Every function under any `analysis/` raises `NotImplementedError` until its phase opens. No
notebook, script or test computes an inferential result about real data before the gate that
authorises it.

Scaffolding is not analysis. Loading, cleaning, counting rows and describing coverage are
permitted at any phase. Fitting, testing, scoring and estimating are not.

**A violation looks like:** replacing the body of an `analysis/` function with a working
implementation while its phase is still closed. Computing a Benford p-value on a real precinct
file "just to check the loader works" — use a synthetic fixture.

**What catches it:** `test_analysis_stubs.py` in each project, which asserts every public callable
under `analysis/` raises `NotImplementedError`. There are 16 such modules across the two project
repositories.

## 5. THE HELD-OUT ANCHOR

The Uzbek cotton series 1976–1985, and anything that isolates it, must not be plotted, tested,
scored, summarised or looked at before gate G3 is signed.

This is the programme's one genuinely out-of-sample test. The Uzbek cotton affair is a documented
falsification of known direction and approximate magnitude. If a method is tuned, even
unconsciously, on the series it is later said to have detected, the detection is circular and the
project's only real claim collapses.

An aggregate is permitted. A breakdown that isolates the held-out unit is not.

**A violation looks like:** a groupby on region that puts Uzbek SSR in its own row for those
years. Plotting all-Union cotton output with a vertical line at 1976. Reading the seal constant
in order to exclude those years "so the model does not see them" — which reveals the answer to
the person writing the exclusion.

**What catches it:** `gosplan.seal`, which holds the anchor definition, and `check_grouping`,
which refuses a grouping that isolates it. `unseal()` must not be called from analysis code; a
caller is violating this rule by another route. See
`projects/gosplan/docs/HELD_OUT.md`.

## 6. RAW DATA NEVER ENTERS GIT

`data/raw/`, `data/interim/`, `data/processed/`, `data/.cache/` and `data/fetch_log.jsonl` are
gitignored in both project repositories. Reproducibility comes from `make data` plus
`SOURCES.yaml`, not from committed blobs.

Test fixtures are the exception and are not data: they live in `tests/fixtures/`, are prefixed
`synthetic_`, and never appear under any `data/`.

**A violation looks like:** `git add -f data/raw/precincts.csv` because the source went offline.
Writing a generated dataframe to `data/interim/` so a later step can read it.

**What catches it:** `.gitignore` in both project repositories, lines 2–10.

## 7. EVERY FETCH IS LOGGED

Every network fetch attempt appends to `data/fetch_log.jsonl`: URL, HTTP status, UTC timestamp,
bytes, SHA-256 of the body, and the tool used. Successful or not.

A failed fetch is evidence. It is how "not found" is distinguished from "not free" and from "not
tried", and those three are different facts about the world.

**A violation looks like:** a retry loop that logs only the attempt that succeeded. Fetching a URL
by hand to see whether it works before writing the fetcher.

**What catches it:** review against the fetcher modules; the log is append-only by convention.

## 8. BOUNDS AND FAILURES ARE RESULTS

A replication that misses its target is reported as a miss, with the number it got and the number
it aimed at. A bound that binds is reported as binding. Never retry until it passes and report
only the pass.

**A violation looks like:** running a replication under six random seeds and reporting the one
that matched the published AUC. Widening a confidence interval until it covers the target.
Describing a 0.71 against a published 0.79 as "broadly consistent" without printing both.

**What catches it:** gate reviews. G2 requires the replication number beside its target regardless
of whether they agree.

## 9. FALSE POSITIVES SHIP WITH EVERY CLAIM

No detection result is reported without the same detector's behaviour on data where nothing should
be found. Not a sibling of the detector, not a refit, not a similar model — the same fitted object
that produced the claim.

A detector that fires on 30% of clean units and 40% of suspect ones has found nothing, and the 40%
alone reads as a discovery.

**Status:** the machinery exists — `forensics_core.control` defines the corpus, the three
kinds of control and the calibration verdict. The real external control tables do not.
Poland 2010 and Spain 2011 come out of the Kobak, Shpilkin and Pshenichnikov supplement, and
extracting them is still outstanding. Until it is done, every corpus that can be built is
within-dataset or synthetic and `has_external_control()` returns `False` for all of them,
which is the honest state rather than a bug.

**A violation looks like:** reporting that a detector flagged 12 of 40 regions, without saying what
it flagged among regions with no reason for suspicion. Constructing a fresh detector of the same
class to score the control, which measures a different object's behaviour.

**What catches it:** `eval.harness.transfer(..., controls=[...])` returns `fitted_detector` and
`control_reports`, computed with the instance that scored the target. An empty `control_reports` is
the visible signal that the rule-9 claim has not been made. Nothing enforces that it be filled:
what counts as a control is a substantive claim about the world and cannot be checked in code.

## 10. RANK METRICS ONLY, WITH THE BASE RATE BESIDE THEM

Where the positive base rate is small — every project here — report precision@k, recall@k and
average precision, with the base rate printed next to them. Accuracy is forbidden. ROC AUC is
reported only alongside a precision-recall number.

At a 2% base rate a detector that flags nothing is 98% accurate, and an AUC of 0.85 can coexist
with a precision@100 of 0.03.

**A violation looks like:** "the model achieves 97% accuracy". An AUC quoted alone.

**What catches it:** `eval.metrics`, which does not implement accuracy, and whose report carries
the base rate as a field.

## 11. PRE-REGISTRATION

The analysis plan — hypotheses, methods, thresholds, multiple-testing correction, and what each
result would and would not establish — is committed before any project-level result is computed.
That is gate G1.

Changing the plan afterwards is permitted and is recorded as a change, with the date, the reason,
and what the original said.

**A violation looks like:** running three tests, finding one significant, and writing the plan
around it. Deciding the correction family after seeing which findings survive.

**What catches it:** the pre-registration document, and the G1 gate signature. `forensics_core.correction` fixes the
hypothesis family in code, so the family is a committed object rather than a choice made at
reporting time.

## 12. WHITELIST DISCIPLINE

One task, one branch, one pull request, touching only the files that task needs. A change set
whose scope is declared before the work starts is reviewable without re-reading the whole
repository; one that grows as it goes is not.

The rule bites hardest across projects. The calibration results must not be consulted while
deciding how to specify the target analysis, because that is how a held-out anchor stops being
held out (rule 5).

**A violation looks like:** a pull request that also fixes an unrelated typo in another module.
Reading the elections results to decide how to frame the gosplan analysis.

**What catches it:** the pull request diff against the scope stated in its description.

## 13. ACCESS POLICIES ARE OBSERVED

Every scraper sends a descriptive `User-Agent` carrying a real contact address, respects the host's
rate limit, and caches so that a source is never fetched twice.

SEC EDGAR specifically: a contact email in the `User-Agent` is required, and 10 requests/second is
a hard ceiling to stay well under.

**A violation looks like:** running a fetcher with the placeholder contact still in place. Removing
a `sleep` because a backfill was slow. Re-downloading a filing already in the cache.

**What catches it:** `forensics_core.config.require_contact`, which raises while
`config/forensics.toml` still carries the placeholder marker, and which network code must call
before any request.

---

## Amending this contract

If the contract and the code disagree, that is an ambiguity report, not a licence to relax the
code. A rule may be changed by the lead, in a commit that says what the rule used to say and why
it changed.

Rules are never silently renumbered. `gosplan/seal.py` cites rule 5 and
`forensics_core/eval/harness.py` cites rule 9 by number, and the frozen list in
`tests/test_contract.py` exists so that a later change cannot quietly drop, reorder or reword a
rule without saying so.
