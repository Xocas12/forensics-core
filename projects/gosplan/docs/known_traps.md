# Known traps — gosplan

Populate before any analysis. Each of these produces a signal that a naive detector will read
as distortion.

## 1. The 1961 currency reform rescales monetary series

The rouble was redenominated 10:1 in 1961. Value series spanning the reform show a
discontinuity of exactly one order of magnitude; older tables sometimes restate pre-1961
figures in new roubles and sometimes do not. Every value series must carry a units column
(`old_roubles` / `new_roubles`) and the transcription schema must force the transcriber to
state which the printed table used.

## 2. Territorial changes 1939–40 break geographic comparability

The annexation of eastern Poland, the Baltic states, Bessarabia and parts of Finland changed
the territory to which "USSR" totals refer. Pre-war and post-war series are not comparable
without adjustment; Soviet yearbooks often present both "within pre-17 September 1939
boundaries" and "within present boundaries". Record the boundary basis per table.

## 3. The index-number problem (Gerschenkron effect)

Soviet growth rates swing enormously with base-year weights. Early-year (1926/27) prices weight
the goods that subsequently expanded most, producing spectacular growth; late-year weights
produce modest growth. **Any result must be shown robust across weighting schemes**, and any
comparison of official and Western growth rates must first align the weights.

## 4. Hidden inflation

Physical output series and value aggregates diverge because deflators were understated
(new "improved" products at higher prices booked as real growth). This divergence is the core
of the Khanin critique and is a **finding, not noise**. Do not "clean" it away by rescaling
value series to physical ones.

## 5. Periodic definitional revisions mid-series

Gross output vs net output vs "normative net output"; changes in what counts as "industry";
reclassification of enterprises between ministries; the 1988 shift toward net material
product presentations. Track definition changes per series in the data dictionary and never
splice across an unrecorded change.

## 6. Padding was semi-institutionalised and often known to superiors

Pripiski (padding) were pervasive and frequently anticipated by the ministries receiving the
reports. **If everyone distorts, there is no honest control group and absolute anomaly
detection has no baseline.** Design toward within-sector and within-year *relative*
comparison: which enterprises, regions or sectors distort more than their peers, not whether
any distorts at all.

## 7. Physical series were also targets

Physical output (tons of cotton, tons of steel) was itself plan-targeted and padded; the Uzbek
cotton affair was padding of a physical series. Physical proxies are only useful controls when
the falsifiers did not control them: hydrology, weather, downstream capacity, transport
capacity, foreign trade partners' mirror statistics.

## 8. Western estimates are not ground truth

CIA, Bergson and Khanin estimates disagree with each other and were built from the same
official inputs with different adjustments. Treat them as alternative reconstructions to be
reconciled, not as labels.

## 9. Transcription error mimics everything

Digit tests on OCR'd tables detect OCR. Double-transcribe a random sample, compute the
inter-transcription error rate per digit position, and only run digit tests on tables whose
error rate is documented and low. Store page images alongside every transcribed table.
