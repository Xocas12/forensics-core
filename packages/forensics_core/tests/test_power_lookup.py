"""WO-111: the atlas lookup loads a stored atlas, answers, and refuses to extrapolate.

Every atlas here is synthetic: built by hand with obviously artificial power values, or
measured by ``power_curve`` on a generated normal population. Stored atlases go to
``tmp_path`` and never under any ``data/``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from forensics_core.power.atlas import (
    ATLAS_COLUMNS,
    AtlasError,
    PowerSpec,
    load_atlas,
    power_curve,
    save_atlas,
)
from forensics_core.power.lookup import detectable, minimum_detectable_effect

METHOD = "synthetic_method"

# power by (n, effect): rises in both, reaches 0.8 at effect 0.2 for n=100 and 0.1 for n=300
POWER = {
    50: {0.0: 0.05, 0.1: 0.10, 0.2: 0.40, 0.4: 0.85},
    100: {0.0: 0.05, 0.1: 0.30, 0.2: 0.80, 0.4: 0.99},
    300: {0.0: 0.05, 0.1: 0.90, 0.2: 1.00, 0.4: 1.00},
}


def _atlas(power=POWER, method=METHOD, fpr_override=None) -> pd.DataFrame:
    rows = []
    for n, curve in power.items():
        fpr = curve[0.0] if fpr_override is None else fpr_override
        for effect, p in curve.items():
            rows.append(
                {
                    "method": method,
                    "n": n,
                    "effect_size": effect,
                    "power": p,
                    "power_se": 0.0,
                    "n_replicates": 100,
                    "alpha": 0.05,
                    "false_positive_rate": fpr,
                }
            )
    frame = pd.DataFrame(rows, columns=ATLAS_COLUMNS)
    frame.attrs["spec"] = PowerSpec(
        method=method, alpha=0.05, n_replicates=100, seed=7, settings={"variant": "synthetic"}
    )
    return frame


@pytest.fixture
def stored(tmp_path):
    return save_atlas(_atlas(), tmp_path / "synthetic_atlas.parquet")


def test_stored_atlas_loads_with_its_spec(stored):
    frame = load_atlas(stored)
    assert list(frame.columns) == ATLAS_COLUMNS
    spec = frame.attrs["spec"]
    assert spec.seed == 7
    assert spec.settings == {"variant": "synthetic"}


def test_answers_a_minimum_detectable_effect_query_from_a_stored_atlas(stored):
    assert minimum_detectable_effect(METHOD, 100, atlas=stored) == pytest.approx(0.2)
    assert minimum_detectable_effect(METHOD, 300, atlas=stored) == pytest.approx(0.1)
    assert minimum_detectable_effect(METHOD, 50, atlas=stored) == pytest.approx(0.4)
    # a lower target is met by a smaller effect
    assert minimum_detectable_effect(METHOD, 100, power=0.3, atlas=stored) == pytest.approx(0.1)


def test_accepts_a_frame_as_well_as_a_path():
    assert minimum_detectable_effect(METHOD, 100, atlas=_atlas()) == pytest.approx(0.2)


@pytest.mark.parametrize("n", [12, 49, 301, 95000])
def test_refuses_a_sample_size_outside_the_measured_range(stored, n):
    with pytest.raises(AtlasError, match="does not cover"):
        minimum_detectable_effect(METHOD, n, atlas=stored)
    with pytest.raises(AtlasError, match="does not cover"):
        detectable(METHOD, n, 0.4, atlas=stored)


def test_unmeasured_sample_size_inside_the_range_is_an_open_question(stored):
    with pytest.raises(NotImplementedError, match="AMBIGUITY-WO-111-2"):
        minimum_detectable_effect(METHOD, 200, atlas=stored)


def test_no_atlas_and_non_unit_aggregation_are_open_questions(stored):
    with pytest.raises(NotImplementedError, match="AMBIGUITY-WO-111-1"):
        minimum_detectable_effect(METHOD, 100)
    with pytest.raises(NotImplementedError, match="AMBIGUITY-WO-111-3"):
        minimum_detectable_effect(METHOD, 100, aggregation="region", atlas=stored)


def test_unknown_method_is_refused(stored):
    with pytest.raises(AtlasError, match="no rows for method"):
        minimum_detectable_effect("other_method", 100, atlas=stored)


def test_no_measured_effect_reaching_power_is_refused_not_answered():
    weak = {50: {0.0: 0.05, 0.1: 0.1, 0.2: 0.2}, 100: {0.0: 0.05, 0.1: 0.2, 0.2: 0.5}}
    with pytest.raises(AtlasError, match="no measured effect reaches"):
        minimum_detectable_effect(METHOD, 100, atlas=_atlas(weak))


def test_miscalibrated_atlas_is_refused():
    bad = _atlas(fpr_override=0.5)
    with pytest.raises(AtlasError, match="false-positive rate"):
        minimum_detectable_effect(METHOD, 100, atlas=bad)
    with pytest.raises(AtlasError, match="false-positive rate"):
        detectable(METHOD, 100, 0.4, atlas=bad)


def test_detectable(stored):
    assert detectable(METHOD, 100, 0.2, atlas=stored)
    assert detectable(METHOD, 100, 0.3, atlas=stored)
    assert not detectable(METHOD, 100, 0.1, atlas=stored)
    assert detectable(METHOD, 300, 0.1, atlas=stored)


def test_detectable_does_not_extrapolate_beyond_the_measured_effects():
    weak = {50: {0.0: 0.05, 0.1: 0.1, 0.2: 0.2}, 100: {0.0: 0.05, 0.1: 0.2, 0.2: 0.5}}
    atlas = _atlas(weak)
    assert not detectable(METHOD, 100, 0.2, atlas=atlas)
    with pytest.raises(AtlasError, match="never measured"):
        detectable(METHOD, 100, 0.5, atlas=atlas)


def test_round_trip_of_a_measured_atlas(tmp_path):
    rng = np.random.default_rng(20260925)
    population = rng.normal(size=2_000)

    def ttest(sample):
        return stats.ttest_1samp(sample, 0.0).pvalue

    def shift(sample, effect, _rng):
        return sample + effect

    measured = power_curve(
        population,
        ttest,
        shift,
        method="synthetic_shift",
        effect_sizes=[0.5, 1.0],
        sample_sizes=[50, 100],
        n_replicates=40,
        seed=3,
    )
    path = save_atlas(measured, tmp_path / "synthetic_shift.parquet")
    assert minimum_detectable_effect("synthetic_shift", 100, atlas=path) == pytest.approx(0.5)
    with pytest.raises(AtlasError, match="does not cover"):
        minimum_detectable_effect("synthetic_shift", 12, atlas=path)
