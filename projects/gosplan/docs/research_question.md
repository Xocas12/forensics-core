# Research question — gosplan

**Bound the volume of reporting distortion in Soviet economic statistics, with a magnitude and
a sectoral distribution, using methods calibrated on the three projects with ground truth.**

This is the target project. It has almost no labels: one anchor event (the Uzbek cotton
affair), a literature of Western re-estimates (CIA, Bergson, Khanin) that disagree with each
other, and no possibility of confirming any individual figure against an archive from here.

## What this project is, and is not

**It is not primarily a coding problem.** Much of the source material exists only as scanned
Russian-language printed tables. A large share of the work is OCR, transcription, schema
design and reconciliation of definitions across yearbook editions. The pipeline is built for
that: transcription targets with fixed schemas, validation of transcribed tables against
arithmetic identities and against a second transcription, and provenance down to the page.

## Sub-questions

1. **Internal consistency.** Do the published series satisfy the accounting identities they
   claim to (sectoral sums, input-output balances, physical-to-value conversions)? Where they
   do not, `forensics_core.reconcile` locates the nodes needing the largest corrections.
2. **Physical vs value series.** Do value aggregates grow faster than the physical output
   series that should underpin them? This is the hidden-inflation question and the core of the
   Khanin critique; the gap is a finding, not noise.
3. **Notch bunching.** Do reported plan-fulfilment percentages bunch at 100 % (the bonus
   threshold), and does the excess mass vary by sector, year and republic?
4. **Underdispersion.** Are reported harvest and output series smoother than the physical
   drivers (weather, hydrology, freight) permit?
5. **Transfer.** Do detectors calibrated on `elections`, `aaer` and `china` rank the Uzbek
   cotton years and sector at the top when applied blind?

## What a result can and cannot claim

With a single anchor, any detector is fit and validated on the same event. The strongest
honest claim is a *bound* — "reported distortion is at least X in sector S over years Y, on
the assumption that the padding mechanism resembles the anchor" — with the assumption stated.
Point estimates of aggregate distortion are not supportable from this design.
