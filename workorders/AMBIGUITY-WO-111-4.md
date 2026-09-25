AMBIGUITY REPORT   WO-111   src/forensics_core/power/atlas.py:PowerSpec, save_atlas (not in write list); INTERFACES.md

Question (one sentence):
Where does the library version that "every stored atlas records" go, given that PowerSpec and
save_atlas (atlas.py) do not record it and atlas.py is not in the write list?

What the spec says / does not say (quote):
"Every stored atlas records the library version, the estimator settings and the seed." and
"Freeze the atlas format". `PowerSpec` has method, alpha, n_replicates, seed, settings; no
version. `save_atlas` writes the spec as a JSON `_spec` column; `load_atlas` restores only those
fields. Write only: lookup.py, data/atlas/README.md, docs/power_atlas.md, tests/test_power_lookup.py.

Options considered (A/B/...), and why the spec does not decide:
A. Add `library_version` to PowerSpec (set from `forensics_core.__version__` in power_curve) and
   to save_atlas/load_atlas. Correct place, but atlas.py is outside the write list.
B. A new public `store_atlas`/`publish_atlas` in lookup.py that wraps save_atlas and adds the
   version (a new `_library_version` column, or a key inside `settings`). Adds unspecified public
   API and puts provenance into a field documented as estimator settings, or adds a column the
   loader does not know.
C. Leave the format as atlas.py writes it and document that the version is not yet recorded.
The card requires the version but its write list forbids the file that owns the format.

Impact if the wrong option is picked:
The format the other repositories cite would be frozen twice, or frozen without the version that
lets a reader tell which library release produced a number.

Also: INTERFACES.md has no entry for `forensics_core.power` at all (atlas, aggregation, or the new
lookup). The new public module needs one, e.g. under a heading
"`power/lookup.py` (changed during implementation: new module)", but INTERFACES.md is read-only
for this card.

Tests blocked:
None of the card's must-pass list. As built, lookup.py does not write atlases; it reads them
through atlas.load_atlas, and data/atlas/README.md / docs/power_atlas.md state that the version
field is pending this report. No INTERFACES.md edit was made.
