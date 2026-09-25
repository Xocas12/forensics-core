AMBIGUITY REPORT   WO-403   projects/china/data/provinces.yaml (Chinese-name column), projects/china/tests/test_provinces.py:test_the_table_carries_no_chinese_name_beyond_the_attested_one
Question (one sentence):
Should data/provinces.yaml get the Chinese names and standard short forms of the other thirty provinces, which the card's acceptance criterion requires but a frozen test in the card's own write list forbids?
What the spec says / does not say (quote):
  Card, "Must pass": "Every canonical province resolves from its Chinese name, its English name and the common variants; an unknown name raises rather than silently dropping the row."
  Dispatch guidance for this session: the Chinese and English names of the provincial-level divisions are standard public facts and not sources in the CONTRACT rule-1 sense, so writing them is fine. Standard short forms such as the ones for Inner Mongolia, Guangxi and Beijing are allowed. It also says: "Don't edit existing tests."
  WO-403 was already committed in 711bbc0. Its commit message says: "The other thirty names were left out rather than supplied from memory, which is the correct outcome under the no-invented-facts rule even though it leaves the card's own acceptance criterion unmet ... #12 stays open for it."
  projects/china/tests/test_provinces.py (existing, frozen under CONTRACT rule 3) asserts:
    chinese = sorted(k for k in mapping if any("一" <= ch <= "鿿" for ch in k))
    assert chinese == ["辽宁省"], ("a Chinese name enters the table only with its source; typing the other thirty from memory would put unverified strings at the join with the panel")
  The provinces.yaml header and the pbc_reports.py module docstring both say the Chinese column is completed only "from a fetched year page's link text, one name at a time, each with its source, never from memory".
Options considered (A/B/...), and why the spec does not decide:
  A. Add the thirty Chinese names and the standard short forms, following the dispatch guidance. This fails the frozen test above. Editing that test is forbidden by CONTRACT rule 3 and by the guidance itself.
  B. Add the names and special-case the loader so the test still passes, for example by keeping them out of the mapping it returns. CONTRACT rule 3 names this as a violation ("do not special-case the implementation to satisfy it").
  C. Leave the table as committed in 711bbc0 (only the one Chinese name the registry attests) and report the conflict. I chose this option.
  The card and the dispatch guidance point one way. The frozen test and the recorded attestation policy (in the YAML header, the module docstring and 711bbc0) point the other. Only the lead can change the test or the policy (CONTRACT rules 3 and "Amending"), so the implementer cannot settle this.
Impact if the wrong option is picked:
  Picking A or B breaks a frozen test or evades it. Picking A also overturns, without saying so, a policy the lead reviewed and merged. Staying with C leaves 30 provinces that cannot be resolved from their Chinese names. The loader then raises on the first real central-bank year page, so provincial loans still cannot reach the panel. That failure is loud and safe; it does not silently shrink the panel.
Tests blocked:
  None fail. All 27 tests in test_provinces.py pass on the committed table. The card's own "Must pass" criterion (resolving by Chinese name) cannot be met without the lead doing one of two things:
    (i) change test_the_table_carries_no_chinese_name_beyond_the_attested_one and the attestation policy, saying in the commit message why standard administrative names do not need a registry source; or
    (ii) record the thirty names from a fetched year page (registry id pbc_regional_financial_operation_reports), with their source, as the README's one-off task already describes.
  Related points to check when this is resolved:
  - The dispatch guidance says the canonical list is in schema.py. It is actually in china.clean.provinces (PROVINCES, BOUNDARY_CHANGES, SUBPROVINCIAL_UNITS). schema.py and pbc_reports.py import it from there, and provinces.py is not on this card's whitelist.
  - The committed table's not_provinces list has three units (Binhai New Area/Tianjin, Baotou/Inner Mongolia, Shenzhen/Guangdong), and SUBPROVINCIAL_UNITS enforces them. The card says "the sub-provincial unit" (singular), and none of the whitelisted files says which one comes from an admitted episode. The table represents all three the same way: each maps to "<name> (sub-provincial unit of <parent>, not a province)".
