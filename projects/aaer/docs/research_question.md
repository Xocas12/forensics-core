# Research question — aaer

**Reproduce the Beneish M-score baseline and the published machine-learning benchmark for
detecting accounting misstatement, using SEC enforcement actions as labels.**

Labels are SEC Accounting and Auditing Enforcement Releases (AAERs). The published benchmark
is Bao, Ke, Li, Yu & Zhang (2020, *Journal of Accounting Research*), whose reported
out-of-sample performance is the target to match and then beat; the exact numbers and the
correction to that paper are recorded in `validation_anchors.md` once verified.

Sub-questions:

1. Does the eight-variable Beneish M-score, computed from the free SEC Financial Statement
   Data Sets, reproduce the published sensitivity/specificity on the overlapping years?
2. What does the Bao et al. approach achieve on the same free inputs, and what is lost by
   substituting SEC structured data for Compustat?
3. Does a positive-unlabeled formulation (`forensics_core.labels.pu`) beat the
   treat-unflagged-as-clean formulation on rank metrics? Enforcement is selected, so the PU
   framing is more honest; the question is whether it is also more powerful.
4. Which of the eight Beneish components and which of the bunching-at-the-notch features
   (earnings just meeting analyst consensus, just above zero, just above last year) carry the
   signal? These are the features that have analogues in the Soviet data.

## The coverage problem (design decision required)

Free structured financials from the SEC begin with XBRL in 2009. Most AAER research, including
the Bao et al. training period, covers violations from the 1990s and 2000s. **The free path
and the labelled period do not fully overlap.** Options, each with a cost:

- Restrict to fiscal years ≥ 2009: free data, but far fewer positives and a different
  enforcement regime.
- Obtain Compustat (paywalled; CMU has WRDS access for affiliates): full overlap, not
  reproducible by outsiders.
- Obtain the curated Dechow et al. AAER dataset (registration): better labels, same
  financials problem.

This is a real constraint on the project, not a scaffolding bug. The user must choose.
