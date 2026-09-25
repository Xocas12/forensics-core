"""Tests for :mod:`forensics_core.reconcile.gross_error`.

Synthetic data only: the four-node, six-edge toy network of ``test_reconcile_balance`` with
obviously artificial round-number flows, perturbed by a known number of standard deviations
(HARD RULE 3). No network access, no filesystem access.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy import stats

import forensics_core
from forensics_core.reconcile import (
    GrossErrorSuspect,
    critical_z,
    global_test,
    incidence_matrix,
    measurement_test,
    nodal_test,
    reconcile,
    serial_elimination,
)

# --------------------------------------------------------------------------------------------
# The same synthetic four-node, six-edge network as ``test_reconcile_balance`` (restated here so
# the two test modules stay independent):
#
#     ENV --e_in--> N1 --e12--> N2 --e24--> N4 --e_out--> ENV
#                     \                     ^
#                      --e13--> N3 --e34---/
# --------------------------------------------------------------------------------------------

EDGES: dict[str, tuple[str, str]] = {
    "e_in": ("ENV", "N1"),
    "e12": ("N1", "N2"),
    "e13": ("N1", "N3"),
    "e24": ("N2", "N4"),
    "e34": ("N3", "N4"),
    "e_out": ("N4", "ENV"),
}
EDGE_NAMES = ["e_in", "e12", "e13", "e24", "e34", "e_out"]
NODE_NAMES = ["N1", "N2", "N3", "N4"]

#: Exactly conserved synthetic flows: 10 in, splitting 6 / 4, 10 out.
TRUE_FLOWS = np.array([10.0, 6.0, 4.0, 6.0, 4.0, 10.0])

#: ``e13`` is the sloppiest stream, so a gross error on it barely smears onto its neighbours.
SIGMA = np.array([0.2, 0.2, 1.0, 0.2, 0.2, 0.2])

#: Equal-precision variant: a gross error then smears visibly over neighbouring streams.
EQUAL_SIGMA = np.array([0.5, 0.3, 0.3, 0.3, 0.3, 0.5])

BAD_EDGE = 2  # "e13"
ALPHA = 0.05


def build_network() -> tuple[np.ndarray, list[str], list[str]]:
    return incidence_matrix(EDGES)


def perturbed(k_sigma: float = 10.0, sigma: np.ndarray = SIGMA, edge: int = BAD_EDGE):
    """Synthetic reports with a single ``k_sigma`` gross error on ``edge``."""
    y = TRUE_FLOWS.copy()
    y[edge] += k_sigma * sigma[edge]
    return y


def clean_result(sigma: np.ndarray = SIGMA):
    A, nodes, edges = build_network()
    return reconcile(TRUE_FLOWS, A, sigma, names=edges, constraint_names=nodes)


def dirty_result(sigma: np.ndarray = SIGMA, k_sigma: float = 10.0):
    A, nodes, edges = build_network()
    return reconcile(perturbed(k_sigma, sigma), A, sigma, names=edges, constraint_names=nodes)


# --------------------------------------------------------------------------------------------
# critical_z
# --------------------------------------------------------------------------------------------


def test_critical_z_hand_computed_sidak():
    critical, beta = critical_z(0.05, 6, "sidak")
    assert beta == pytest.approx(1.0 - 0.95 ** (1.0 / 6))
    assert beta == pytest.approx(0.00851244, rel=1e-5)
    assert critical == pytest.approx(2.6310383, rel=1e-6)


def test_critical_z_hand_computed_bonferroni_and_none():
    critical_b, beta_b = critical_z(0.05, 6, "bonferroni")
    assert beta_b == pytest.approx(0.05 / 6)
    assert critical_b == pytest.approx(stats.norm.isf(0.05 / 12), rel=1e-12)

    critical_n, beta_n = critical_z(0.05, 6, "none")
    assert beta_n == pytest.approx(0.05)
    assert critical_n == pytest.approx(1.959964, rel=1e-6)


def test_critical_z_ordering():
    """Sidak splits alpha slightly less aggressively than Bonferroni, so it is less strict."""
    c_none = critical_z(0.05, 6, "none")[0]
    c_sidak = critical_z(0.05, 6, "sidak")[0]
    c_bonf = critical_z(0.05, 6, "bonferroni")[0]
    assert c_none < c_sidak < c_bonf
    # A bigger family means a stricter threshold.
    assert critical_z(0.05, 100, "sidak")[0] > c_sidak


@pytest.mark.parametrize(
    ("alpha", "n_tests", "correction", "message"),
    [
        (0.0, 6, "sidak", "alpha"),
        (1.0, 6, "sidak", "alpha"),
        (-0.1, 6, "sidak", "alpha"),
        (np.nan, 6, "sidak", "alpha"),
        (0.05, 0, "sidak", "at least 1"),
        (0.05, 6, "holm", "sidak"),
    ],
)
def test_critical_z_rejects_bad_input(alpha, n_tests, correction, message):
    with pytest.raises(ValueError, match=message):
        critical_z(alpha, n_tests, correction)


# --------------------------------------------------------------------------------------------
# global_test
# --------------------------------------------------------------------------------------------


def test_global_test_does_not_reject_an_exactly_conserved_network():
    res = global_test(clean_result(), alpha=ALPHA)
    assert isinstance(res, forensics_core.TestResult)
    assert res.method == "reconcile_global_test"
    assert res.statistic == pytest.approx(0.0, abs=1e-20)
    assert res.pvalue == pytest.approx(1.0)
    assert res.n == 6
    assert res.details["dof"] == 4  # rank(A), not the number of measurements
    assert res.details["critical"] == pytest.approx(stats.chi2.isf(0.05, 4))
    assert res.details["reject"] is False
    assert res.details["alternative"] == "greater"
    assert res.details["n_constraints"] == 4


def test_global_test_rejects_a_ten_sigma_gross_error():
    res = global_test(dirty_result(), alpha=ALPHA)
    assert res.details["reject"] is True
    assert res.pvalue < 1e-6
    assert res.statistic > res.details["critical"]


def test_global_test_hand_computed_two_edge_system():
    """``A = [1, -1]``, ``y = (10, 8)``, ``sigma = (1, 2)``: objective ``4 / 5 = 0.8`` on 1 dof."""
    res = reconcile([10.0, 8.0], np.array([[1.0, -1.0]]), [1.0, 2.0])
    gt = global_test(res)
    assert gt.statistic == pytest.approx(0.8)
    assert gt.details["dof"] == 1
    assert gt.pvalue == pytest.approx(float(stats.chi2.sf(0.8, 1)))
    assert gt.pvalue == pytest.approx(0.37109337, rel=1e-6)
    assert gt.details["reject"] is False


def test_global_test_statistic_scales_with_the_size_of_the_error():
    stats_by_k = [global_test(dirty_result(k_sigma=k)).statistic for k in (1.0, 3.0, 10.0)]
    assert stats_by_k[0] < stats_by_k[1] < stats_by_k[2]
    # The objective is quadratic in the injected error.
    assert stats_by_k[2] / stats_by_k[0] == pytest.approx(100.0, rel=1e-9)


def test_global_test_handles_a_system_with_no_redundancy():
    """Only non-redundant measurements: nothing is testable, so the test cannot reject."""
    res = reconcile([10.0, 8.0], np.zeros((1, 2)), [1.0, 1.0])
    gt = global_test(res)
    assert gt.details["dof"] == 0
    assert gt.pvalue == 1.0
    assert gt.details["reject"] is False


@pytest.mark.parametrize("alpha", [0.0, 1.0, -1.0])
def test_global_test_rejects_bad_alpha(alpha):
    with pytest.raises(ValueError, match="alpha"):
        global_test(clean_result(), alpha=alpha)


def test_global_test_rejects_a_non_result():
    with pytest.raises(ValueError, match="ReconciliationResult"):
        global_test({"objective": 1.0})


# --------------------------------------------------------------------------------------------
# measurement_test
# --------------------------------------------------------------------------------------------


def test_measurement_test_columns_and_clean_network():
    table = measurement_test(clean_result(), alpha=ALPHA)
    assert list(table.columns) == ["index", "name", "adjustment", "z", "abs_z", "critical", "flag"]
    assert table["name"].tolist() == EDGE_NAMES
    assert table["index"].tolist() == list(range(6))
    assert not table["flag"].any()
    np.testing.assert_allclose(table["z"].to_numpy(), np.zeros(6), atol=1e-12)
    assert table.attrs["correction"] == "sidak"
    assert table.attrs["n_tests"] == 6
    assert table.attrs["n_redundant"] == 6
    assert table.attrs["critical"] == pytest.approx(critical_z(ALPHA, 6, "sidak")[0])


def test_measurement_test_flags_exactly_the_perturbed_edge():
    table = measurement_test(dirty_result(), alpha=ALPHA)
    flagged = table.loc[table["flag"], "name"].tolist()
    assert flagged == ["e13"]
    assert int(table["z"].abs().idxmax()) == BAD_EDGE
    assert abs(table.loc[BAD_EDGE, "z"]) > 9.0
    # The error was reported too high, so the adjustment pulls the flow back down.
    assert table.loc[BAD_EDGE, "adjustment"] < 0.0


def test_measurement_test_largest_z_survives_smearing():
    """With equal precisions the gross error smears onto a neighbour (Narasimhan & Jordache
    ch. 7): more than one stream is flagged, but the culprit still has the largest |z|."""
    table = measurement_test(dirty_result(sigma=EQUAL_SIGMA), alpha=ALPHA)
    flagged = table.loc[table["flag"], "name"].tolist()
    assert "e13" in flagged
    assert len(flagged) > 1  # smearing is real; documented, not hidden
    assert int(table["z"].abs().idxmax()) == BAD_EDGE


def test_measurement_test_correction_changes_only_the_threshold():
    res = dirty_result()
    sidak = measurement_test(res, ALPHA, "sidak")
    bonf = measurement_test(res, ALPHA, "bonferroni")
    none = measurement_test(res, ALPHA, "none")
    np.testing.assert_allclose(sidak["z"].to_numpy(), bonf["z"].to_numpy())
    assert none.attrs["critical"] < sidak.attrs["critical"] < bonf.attrs["critical"]
    assert int(none["flag"].sum()) >= int(sidak["flag"].sum()) >= int(bonf["flag"].sum())


def test_measurement_test_explicit_family_size():
    res = dirty_result()
    default = measurement_test(res, ALPHA)
    wider = measurement_test(res, ALPHA, n_tests=1000)
    assert wider.attrs["n_tests"] == 1000
    assert wider.attrs["critical"] > default.attrs["critical"]


def test_measurement_test_leaves_non_redundant_measurements_untested():
    res = reconcile([10.0, 8.0, 5.0], np.array([[1.0, -1.0, 0.0]]), [1.0, 1.0, 1.0])
    table = measurement_test(res, ALPHA)
    assert np.isnan(table.loc[2, "z"])
    assert table.loc[2, "flag"] is np.False_ or not table.loc[2, "flag"]
    assert table.attrs["n_redundant"] == 2
    assert table.attrs["n_tests"] == 2  # the untestable measurement does not inflate the family


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"alpha": 0.0}, "alpha"),
        ({"correction": "holm"}, "sidak"),
        ({"n_tests": 0}, "at least 1"),
    ],
)
def test_measurement_test_rejects_bad_input(kwargs, message):
    with pytest.raises(ValueError, match=message):
        measurement_test(clean_result(), **kwargs)


# --------------------------------------------------------------------------------------------
# nodal_test
# --------------------------------------------------------------------------------------------


def test_nodal_test_clean_network_has_zero_imbalance():
    table = nodal_test(clean_result(), alpha=ALPHA)
    assert list(table.columns) == ["index", "name", "residual", "z", "abs_z", "critical", "flag"]
    assert table["name"].tolist() == NODE_NAMES
    np.testing.assert_allclose(table["residual"].to_numpy(), np.zeros(4), atol=1e-12)
    np.testing.assert_allclose(table["z"].to_numpy(), np.zeros(4), atol=1e-12)
    assert not table["flag"].any()


def test_nodal_test_flags_the_two_nodes_the_faulty_stream_touches():
    """``e13`` runs N1 -> N3, so exactly those two balances break, with opposite signs."""
    table = nodal_test(dirty_result(), alpha=ALPHA)
    flagged = table.loc[table["flag"], "name"].tolist()
    assert flagged == ["N1", "N3"]
    n1 = table.loc[table["name"] == "N1", "residual"].to_numpy()[0]
    n3 = table.loc[table["name"] == "N3", "residual"].to_numpy()[0]
    injected = 10 * SIGMA[BAD_EDGE]
    assert n1 == pytest.approx(-injected)
    assert n3 == pytest.approx(+injected)
    assert table.loc[table["name"] == "N2", "residual"].to_numpy()[0] == pytest.approx(0.0)


def test_nodal_test_hand_computed_z():
    """``z_j = r_j / sqrt((A S A')_jj)``. For N3, ``r = +10`` and ``V_33 = 1.0^2 + 0.2^2``."""
    table = nodal_test(dirty_result(), alpha=ALPHA)
    v33 = SIGMA[2] ** 2 + SIGMA[4] ** 2
    expected = (10 * SIGMA[BAD_EDGE]) / np.sqrt(v33)
    assert table.loc[table["name"] == "N3", "z"].to_numpy()[0] == pytest.approx(expected)


def test_nodal_test_correction_and_bad_input():
    res = dirty_result()
    assert (
        nodal_test(res, ALPHA, correction="none").attrs["critical"]
        < nodal_test(res, ALPHA, correction="sidak").attrs["critical"]
    )
    with pytest.raises(ValueError, match="alpha"):
        nodal_test(res, alpha=1.5)
    with pytest.raises(ValueError, match="ReconciliationResult"):
        nodal_test("not a result")


# --------------------------------------------------------------------------------------------
# serial_elimination
# --------------------------------------------------------------------------------------------


def test_serial_elimination_finds_nothing_in_a_clean_network():
    A, nodes, edges = build_network()
    suspects = serial_elimination(
        TRUE_FLOWS, A, SIGMA, alpha=ALPHA, names=edges, constraint_names=nodes
    )
    assert suspects == []


def test_serial_elimination_returns_the_perturbed_edge_first_and_then_passes():
    A, nodes, edges = build_network()
    y = perturbed()
    suspects = serial_elimination(y, A, SIGMA, alpha=ALPHA, names=edges, constraint_names=nodes)
    assert len(suspects) == 1
    first = suspects[0]
    assert isinstance(first, GrossErrorSuspect)
    assert first.name == "e13"
    assert first.index == BAD_EDGE
    assert first.order_removed == 1
    assert abs(first.z) > 9.0
    assert abs(first.z) > first.critical
    # Global test before: rejects. After eliminating e13 as unmeasured: passes.
    assert first.pvalue_before < 1e-6
    assert first.global_reject_after is False
    assert first.pvalue_after > ALPHA
    assert first.objective_after < first.objective_before
    assert first.objective_after == pytest.approx(0.0, abs=1e-18)
    # Removing a measured variable costs one degree of freedom.
    assert first.dof_before == 4
    assert first.dof_after == 3
    assert set(first.to_dict()) >= {"index", "name", "z", "order_removed"}


def test_serial_elimination_ranks_the_culprit_first_under_smearing():
    A, _, edges = build_network()
    suspects = serial_elimination(
        perturbed(sigma=EQUAL_SIGMA), A, EQUAL_SIGMA, alpha=ALPHA, names=edges
    )
    assert suspects[0].name == "e13"
    assert suspects[-1].global_reject_after is False


def test_serial_elimination_finds_two_independent_gross_errors():
    A, _, edges = build_network()
    sigma = np.array([1.0, 0.2, 1.0, 0.2, 0.2, 0.2])
    y = TRUE_FLOWS.copy()
    y[2] += 10 * sigma[2]  # e13 reported far too high
    y[0] -= 12 * sigma[0]  # e_in reported far too low, and by more
    suspects = serial_elimination(y, A, sigma, alpha=ALPHA, names=edges)
    assert [s.name for s in suspects] == ["e_in", "e13"]  # biggest |z| goes first
    assert [s.order_removed for s in suspects] == [1, 2]
    assert [s.index for s in suspects] == [0, 2]
    assert abs(suspects[0].z) > abs(suspects[1].z)
    assert suspects[0].global_reject_after is True  # one removal is not enough
    assert suspects[-1].global_reject_after is False
    assert suspects[0].dof_before == 4 and suspects[1].dof_after == 2


def test_serial_elimination_respects_max_removals():
    A, _, edges = build_network()
    suspects = serial_elimination(
        perturbed(sigma=EQUAL_SIGMA), A, EQUAL_SIGMA, alpha=ALPHA, max_removals=0, names=edges
    )
    assert suspects == []

    one = serial_elimination(
        perturbed(sigma=EQUAL_SIGMA), A, EQUAL_SIGMA, alpha=ALPHA, max_removals=1, names=edges
    )
    assert len(one) == 1


def test_serial_elimination_naive_column_deletion_does_not_restore_balance():
    """Deleting the column asserts the flow is *zero* rather than unknown, so the reduced
    system stays wildly imbalanced. Documented deviation: the default is Crowe's projection."""
    A, _, edges = build_network()
    y = perturbed()
    projected = serial_elimination(y, A, SIGMA, alpha=ALPHA, names=edges)
    naive = serial_elimination(
        y, A, SIGMA, alpha=ALPHA, max_removals=1, names=edges, elimination="column"
    )
    assert projected[0].name == naive[0].name == "e13"
    assert projected[0].global_reject_after is False
    assert naive[0].global_reject_after is True
    assert naive[0].objective_after > naive[0].objective_before


def test_serial_elimination_column_mode_raises_when_a_constraint_empties():
    """``A x = b`` with a row that constrains one variable alone: deleting its column would
    leave the row with no measured variable at all."""
    A = np.array([[1.0, -1.0, 0.0], [0.0, 0.0, 1.0]])
    y = np.array([10.0, 10.0, 20.0])
    sigma = np.array([1.0, 1.0, 1.0])
    b = np.array([0.0, 10.0])
    # The projection handles it: row 2 is consumed, row 1 survives, and the test then passes.
    suspects = serial_elimination(y, A, sigma, b, alpha=ALPHA, names=["a", "b", "c"])
    assert [s.name for s in suspects] == ["c"]
    assert suspects[0].z == pytest.approx(-10.0)
    assert suspects[0].global_reject_after is False

    with pytest.raises(ValueError, match="no measured variable"):
        serial_elimination(y, A, sigma, b, alpha=ALPHA, names=["a", "b", "c"], elimination="column")


def test_serial_elimination_accepts_a_covariance_matrix():
    A, _, edges = build_network()
    y = perturbed()
    from_sd = serial_elimination(y, A, SIGMA, alpha=ALPHA, names=edges)
    from_cov = serial_elimination(y, A, np.diag(SIGMA**2), alpha=ALPHA, names=edges)
    assert [s.name for s in from_sd] == [s.name for s in from_cov]
    assert from_sd[0].z == pytest.approx(from_cov[0].z)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"alpha": 0.0}, "alpha"),
        ({"correction": "holm"}, "sidak"),
        ({"max_removals": -1}, "non-negative"),
        ({"elimination": "magic"}, "project"),
        ({"names": ["too", "few"]}, "names has 2 entries"),
        ({"constraint_names": ["a"]}, "constraint_names has 1 entries"),
        ({"b": [0.0]}, "b has 1 entries"),
    ],
)
def test_serial_elimination_rejects_bad_input(kwargs, message):
    A, _, _ = build_network()
    with pytest.raises(ValueError, match=message):
        serial_elimination(perturbed(), A, SIGMA, **kwargs)


def test_serial_elimination_rejects_shape_mismatch_and_non_finite():
    A, _, _ = build_network()
    with pytest.raises(ValueError, match="columns but y has"):
        serial_elimination(TRUE_FLOWS[:5], A, SIGMA[:5])
    y = perturbed()
    y[0] = np.nan
    with pytest.raises(ValueError, match="y must be finite"):
        serial_elimination(y, A, SIGMA)
    with pytest.raises(ValueError, match="at least one constraint row"):
        serial_elimination(TRUE_FLOWS, np.zeros((0, 6)), SIGMA)
