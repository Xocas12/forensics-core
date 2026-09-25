AMBIGUITY REPORT   WO-112   packages/forensics_core/tests/test_psephos_parity.py

Question (one sentence):
How should the psephos parity test obtain psephos in CI, given that psephos is not a
dependency of this workspace and neither `pyproject.toml` nor `.github/workflows/ci.yml` is
in the card's write list?

What the spec says / does not say (quote):
The card requires "A test asserting that, for one shared statistic on one synthetic dataset,
the two implementations agree to a stated tolerance, or a documented statement of why they
should not be expected to." Its write list is "docs/psephos_relationship.md and, only if the
decision requires it, the modules the decision names." It does not say where psephos comes
from when the test runs, and the option 1 versus 2 decision is Owner LEAD. The documented
statement alternative does not apply: on the same inputs the two implementations should
agree (the last-digit chi-square exactly), so a test is the right deliverable.

Options considered (A/B/...), and why the spec does not decide:
A. (implemented) The test imports psephos if installed, or from `PSEPHOS_SRC` pointing at a
   psephos checkout's `src/`, and otherwise skips with a reason saying drift is not being
   checked. Within the write list. Cost: skipped in CI today, so it catches drift only when
   someone runs it by hand. A test that is always skipped in CI is weak.
B. Add psephos as a git-sourced development dependency of the workspace, pinned to a commit
   (the test then runs everywhere with no change). Cost: edits `pyproject.toml` (outside the
   write list); `uv sync` needs network access to GitHub; the pin must be bumped by hand, so
   the test checks the pinned psephos, not psephos main.
C. Add a CI step that checks out psephos and sets `PSEPHOS_SRC`. Cost: edits
   `.github/workflows/ci.yml` (outside the write list); tracks psephos main unless pinned, so
   a psephos change can turn this repository's CI red.
D. Freeze psephos's outputs on the synthetic data as constants in the test. Cost: detects
   drift in this library only, never in psephos; puts numbers produced outside this
   repository into a test, a provenance question under CONTRACT rule 1.
E. Mirror image: a parity test in psephos that installs forensics-core. Cost: a change to
   psephos, forbidden from this repository; would need an issue there.
The spec does not decide because each of B to E requires writing outside the card's list or
making a decision that belongs to the lead (what psephos version this repository vouches
for).

Impact if the wrong option is picked:
With A alone, CI stays green while the two implementations drift, which is the failure the
card exists to prevent. With B or C unpinned, an unrelated psephos commit breaks this
repository's CI. With D, drift on the psephos side is invisible.

Tests blocked:
None fail. `test_last_digit_chi_square_agrees`, `test_integer_percentage_excess_agrees` and
`test_documented_psephos_defaults` are skipped wherever psephos is not importable, including
CI; all four tests pass with `PSEPHOS_SRC` set to a psephos checkout at commit 05626a6.
Recommendation for the lead: B, pinned, with the pin bumped deliberately; A's skip path then
remains as the fallback for environments without network access.
