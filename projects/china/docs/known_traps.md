# Known traps - china

## 1. Part of the gap is methodological, not fraudulent

Cross-province economic activity is double-counted when both the producing and the
head-office province claim it; provinces and the centre use different deflators; the centre
applies adjustments for the informal economy that provinces do not. **Estimate the mechanical
component before attributing any residual to misreporting.** A reconciliation that treats the
whole gap as gross error is wrong by construction.

## 2. Boundary changes and rebasing create level shifts

Chongqing separated from Sichuan in 1997; Hainan from Guangdong in 1988; periodic economic
censuses (2004, 2008, 2013, 2018) trigger rebasing and back-revisions of national and
provincial series. Each creates a level shift that mimics manipulation. Build a break table
in `docs/data_dictionary.md` and test around, not across, breaks.

## 3. Revisions overwrite history

NBS and provincial portals serve the *current* vintage. A revised Liaoning series no longer
shows the padded figures; the anchor is only visible if the pre-revision vintage is preserved.
Keep every vintage fetched (content-addressed under `data/raw/`), and use yearbook editions as
frozen vintages.

## 4. Nominal vs real, and price indices

Provincial "GDP growth" is real growth at provincial deflators; the provincial-sum gap in
nominal levels and in real growth rates behave differently. Never mix.

## 5. Physical proxies have their own biases

Electricity consumption tracks heavy industry, not services; the proxy relationship shifts as
provinces move up the value chain (the Li Keqiang-index critique). Rail freight lost share to
road transport over the period. Nightlights saturate in dense cities (DMSP) and the
DMSP to VIIRS transition in 2012 and 2013 is itself a break; use a harmonised series and test across
the seam separately.

## 6. Growth targets create honest bunching too

Provinces set annual growth targets and manage real activity (credit, infrastructure) to hit
them. Bunching of reported growth at the target is consistent with both misreporting and
genuine target-hitting; the physical-proxy residual is what distinguishes them.

## 7. The reform is not a single instant

The unified accounting reform was announced, piloted and then applied; provinces revised
back-series at different times. Treat the effective year as verified in
`validation_anchors.md`, but test sensitivity to ±1 year.
