# Research question - china

**Measure the gap between summed provincial GDP and reported national GDP, and test whether
provincial series track physical proxies.**

Provincial statistics bureaus historically reported growth that, summed, exceeded the national
figure the National Bureau of Statistics (NBS) published. Part of that gap is methodological
(cross-province double counting, different deflators, rebasing); part has been admitted to be
fabrication (Liaoning 2011 to 2014). The NBS's unified accounting reform, under which the centre
took over provincial GDP calculation, is a natural experiment: if the gap is partly
misreporting, it should contract discontinuously at the reform.

Sub-questions:

1. What is the provincial-sum minus national gap, by year, in levels and in growth rates, and
   how much of it is mechanically explained (double counting, deflators, boundary changes)?
2. Does the residual gap contract at the unified-accounting reform, and by how much? (The
   exact effective year is verified from NBS sources in `validation_anchors.md`.)
3. Do provincial GDP series track provincial electricity consumption, rail freight, bank
   credit and nightlights, and do the residuals from those relationships concentrate in
   provinces and years that were later revised?
4. Do the flagged provinces show underdispersion (growth too smooth) and bunching at the
   provincial growth target - the two signals that carry to the Soviet case?

This project calibrates `forensics_core.reconcile` (flow conservation between provincial and
national accounts) and `forensics_core.dispersion` against partial ground truth.
