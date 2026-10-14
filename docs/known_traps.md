# Known traps: forensics-core

The four project documents (`elections`, `china`, `gosplan`, `aaer`) list the confounds of
their own sources. This one lists confounds that belong to a method rather than to one
project's data: they apply wherever the method runs. `forensics_core.redteam.TRAPS` registers
each section here as `core-<section number>`, and `docs/redteam.md` records what each detector
did on it.

## 1. Honest series are persistent

Output levels, shares, rates and growth rates carry over from one period to the next. A
stationary series is not an exchangeable one. `dispersion.too_smooth_test` takes
exchangeability of the analysed values as its null, so under `detrend="none"` or `"linear"` it
rejects ordinary persistence, and under `detrend="diff"` it rejects a persistent growth rate.
A rejection is then a statement about the process, not about whether anyone wrote the numbers.

The same trap hides in a power atlas. `power.atlas.power_curve` with its default
`sampling="units"` returns each sample in random order, so an order-dependent test looks
calibrated on a persistent population it would reject window after window. Measure such a test
with `sampling="contiguous"`, on a population as persistent as the honest series it will meet.

Generator: `redteam.persistent_series` (a stationary AR(1) level, or a log level whose growth
rate is a stationary AR(1)).
