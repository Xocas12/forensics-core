"""Tests for :mod:`forensics_core.reconcile.balance`.

All data here is synthetic and obviously artificial: a four-node, six-edge toy network whose
flows are small round numbers that balance exactly at every node (HARD RULE 3). Nothing touches
the network or the filesystem.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from forensics_core.reconcile import (
    ReconciliationResult,
    incidence_matrix,
    project_unmeasured,
    reconcile,
    reconcile_table,
)

# --------------------------------------------------------------------------------------------
# Synthetic network
#
#            e_in            e12            e24
#     ENV ---------> N1 ----------> N2 ----------> N4 ----------> ENV
#                     \                            ^      e_out
#                      \  e13              e34    /
#                       -----------> N3 ---------
#
# Four internal nodes, six edges, every flow measured. rank(A) = 4, so two degrees of
# redundancy remain.
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

#: Reported precisions. ``e13`` is the sloppiest stream, so a gross error on it is mostly
#: absorbed by its own adjustment rather than smeared over the network.
SIGMA = np.array([0.2, 0.2, 1.0, 0.2, 0.2, 0.2])


def build_network() -> tuple[np.ndarray, list[str], list[str]]:
    return incidence_matrix(EDGES)


# --------------------------------------------------------------------------------------------
# incidence_matrix
# --------------------------------------------------------------------------------------------


def test_incidence_matrix_signs_order_and_environment_row_dropped():
    A, nodes, edges = build_network()
    assert nodes == NODE_NAMES  # first-appearance order, ENV never appears
    assert edges == EDGE_NAMES
    assert A.shape == (4, 6)
    expected = np.array(
        [
            [1.0, -1.0, -1.0, 0.0, 0.0, 0.0],  # N1: e_in in; e12, e13 out
            [0.0, 1.0, 0.0, -1.0, 0.0, 0.0],  # N2: e12 in; e24 out
            [0.0, 0.0, 1.0, 0.0, -1.0, 0.0],  # N3: e13 in; e34 out
            [0.0, 0.0, 0.0, 1.0, 1.0, -1.0],  # N4: e24, e34 in; e_out out
        ]
    )
    np.testing.assert_array_equal(A, expected)
    assert np.linalg.matrix_rank(A) == 4


def test_incidence_matrix_conserves_the_true_flows_exactly():
    A, _, _ = build_network()
    np.testing.assert_allclose(A @ TRUE_FLOWS, np.zeros(4), atol=0.0)


def test_incidence_matrix_respects_given_node_order():
    A, nodes, _ = incidence_matrix(EDGES, nodes=["N4", "N3", "N2", "N1"])
    assert nodes == ["N4", "N3", "N2", "N1"]
    A_default, _, _ = build_network()
    np.testing.assert_array_equal(A, A_default[::-1])


def test_incidence_matrix_drops_the_environment_node_by_name():
    # Rename the environment: "ENV" then becomes an ordinary node with its own balance row.
    A, nodes, _ = incidence_matrix(EDGES, environment="NOWHERE")
    assert nodes == ["ENV", "N1", "N2", "N3", "N4"]
    assert A.shape == (5, 6)
    # ENV receives e_out and emits e_in.
    np.testing.assert_array_equal(A[0], np.array([-1.0, 0.0, 0.0, 0.0, 0.0, 1.0]))


def test_incidence_matrix_default_and_explicit_edge_names():
    A, nodes, edges = incidence_matrix([("ENV", "N1"), ("N1", "ENV"), ("N1", "ENV")])
    assert nodes == ["N1"]
    assert edges == ["ENV->N1", "N1->ENV", "N1->ENV#2"]
    np.testing.assert_array_equal(A, np.array([[1.0, -1.0, -1.0]]))

    _, _, named = incidence_matrix([("ENV", "N1"), ("N1", "ENV")], edge_names=["inflow", "outflow"])
    assert named == ["inflow", "outflow"]

    _, _, triples = incidence_matrix([("a", "ENV", "N1"), ("b", "N1", "ENV")])
    assert triples == ["a", "b"]


@pytest.mark.parametrize(
    ("edges", "kwargs", "message"),
    [
        ([("N1", "N1")], {}, "self-loop"),
        ([], {}, "at least one edge"),
        ([("N1", 3)], {}, "must be strings"),
        ([("N1", "")], {}, "non-empty"),
        ([("ENV", "N1"), ("N1", "ENV")], {"nodes": ["N1", "N2"]}, "no incident edge"),
        ([("ENV", "N1"), ("N1", "N2")], {"nodes": ["N1"]}, "missing from"),
        ([("ENV", "N1"), ("N1", "ENV")], {"nodes": ["N1", "N1"]}, "unique"),
        (
            [("ENV", "N1"), ("N1", "ENV")],
            {"edge_names": ["dup", "dup"]},
            "unique",
        ),
        ([("ENV", "N1"), ("N1", "ENV")], {"edge_names": ["only_one"]}, "entries but there are"),
        ([("ENV", "N1")], {"environment": ""}, "non-empty string"),
    ],
)
def test_incidence_matrix_rejects_bad_specifications(edges, kwargs, message):
    with pytest.raises(ValueError, match=message):
        incidence_matrix(edges, **kwargs)


# --------------------------------------------------------------------------------------------
# reconcile: hand-computed values
# --------------------------------------------------------------------------------------------


def test_reconcile_hand_computed_equal_sigma():
    """One stream in, one out, both sigma = 1: split the imbalance evenly.

    ``A = [1, -1]``, ``y = (10, 8)``, ``S = I``. Then ``r = 2``, ``V = A S A' = 2``,
    ``a = -S A' V^-1 r = (-1, +1)``, ``x_hat = (9, 9)``, ``Var(a) = [[.5, -.5], [-.5, .5]]``
    so ``z = (-sqrt(2), +sqrt(2))``, and the objective is ``r' V^-1 r = 4 / 2 = 2``.
    """
    A = np.array([[1.0, -1.0]])
    res = reconcile([10.0, 8.0], A, [1.0, 1.0])
    assert isinstance(res, ReconciliationResult)
    np.testing.assert_allclose(res.adjusted, [9.0, 9.0])
    np.testing.assert_allclose(res.adjustments, [-1.0, 1.0])
    np.testing.assert_allclose(res.constraint_residuals, [2.0])
    np.testing.assert_allclose(res.adjustment_covariance, np.array([[0.5, -0.5], [-0.5, 0.5]]))
    np.testing.assert_allclose(res.standardized_adjustments, [-np.sqrt(2.0), np.sqrt(2.0)])
    assert res.objective == pytest.approx(2.0)
    assert res.dof == 1
    assert res.n == 2 and res.n_constraints == 1 and res.rank == 1


def test_reconcile_hand_computed_unequal_sigma():
    """Sloppier measurements take more of the adjustment.

    ``A = [1, -1]``, ``y = (10, 8)``, ``sigma = (1, 2)`` so ``S = diag(1, 4)``.
    ``V = 1 + 4 = 5``, ``a = -(1, -4) * 2 / 5 = (-0.4, +1.6)``, ``x_hat = (9.6, 9.6)``,
    ``Var(a) = [[0.2, -0.8], [-0.8, 3.2]]``, ``z = (-0.4/sqrt(0.2), 1.6/sqrt(3.2))``,
    objective ``= 4 / 5 = 0.8``.
    """
    A = np.array([[1.0, -1.0]])
    res = reconcile([10.0, 8.0], A, [1.0, 2.0])
    np.testing.assert_allclose(res.adjustments, [-0.4, 1.6])
    np.testing.assert_allclose(res.adjusted, [9.6, 9.6])
    np.testing.assert_allclose(res.adjustment_covariance, np.array([[0.2, -0.8], [-0.8, 3.2]]))
    np.testing.assert_allclose(
        res.standardized_adjustments,
        [-0.4 / np.sqrt(0.2), 1.6 / np.sqrt(3.2)],
    )
    assert res.objective == pytest.approx(0.8)
    assert res.dof == 1


def test_reconcile_hand_computed_with_nonzero_b():
    """``b`` is an accumulation term: ``A x = b`` instead of ``A x = 0``."""
    A = np.array([[1.0, -1.0]])
    res = reconcile([10.0, 8.0], A, [1.0, 1.0], b=[2.0])
    np.testing.assert_allclose(res.constraint_residuals, [0.0])
    np.testing.assert_allclose(res.adjustments, [0.0, 0.0])
    assert res.objective == pytest.approx(0.0)


# --------------------------------------------------------------------------------------------
# reconcile on the synthetic network
# --------------------------------------------------------------------------------------------


def test_reconcile_leaves_an_exactly_conserved_network_alone():
    A, nodes, edges = build_network()
    res = reconcile(TRUE_FLOWS, A, SIGMA, names=edges, constraint_names=nodes)
    np.testing.assert_allclose(res.adjustments, np.zeros(6), atol=1e-12)
    np.testing.assert_allclose(res.adjusted, TRUE_FLOWS, atol=1e-12)
    np.testing.assert_allclose(res.standardized_adjustments, np.zeros(6), atol=1e-12)
    assert res.objective == pytest.approx(0.0, abs=1e-20)
    assert res.dof == 4
    assert res.redundant.all()
    assert res.measurement_names() == EDGE_NAMES
    assert res.constraint_labels() == NODE_NAMES


def test_reconcile_restores_feasibility_to_1e_minus_10():
    A, _, _ = build_network()
    y = TRUE_FLOWS.copy()
    y[2] += 10 * SIGMA[2]  # +10 sigma gross error on e13
    y[0] += 0.05  # small honest noise elsewhere
    res = reconcile(y, A, SIGMA)
    assert np.max(np.abs(A @ res.adjusted)) < 1e-10
    assert res.max_constraint_violation < 1e-10
    assert res.objective > 0.0


def test_reconcile_recovers_an_injected_gross_error():
    """The injected +10 sigma error on the sloppiest stream is largely undone."""
    A, _, edges = build_network()
    injected = 10 * SIGMA[2]
    y = TRUE_FLOWS.copy()
    y[2] += injected
    res = reconcile(y, A, SIGMA, names=edges)
    assert abs(y[2] - TRUE_FLOWS[2]) == pytest.approx(injected)
    # Reconciliation pulls e13 back to within 5% of the truth.
    assert abs(res.adjusted[2] - TRUE_FLOWS[2]) < 0.05 * injected
    # ... and the adjustment lands on e13, not on its neighbours.
    assert np.argmax(np.abs(res.adjustments)) == 2
    assert np.max(np.abs(np.delete(res.adjustments, 2))) < 0.05 * injected


def test_reconcile_two_dimensional_covariance_matches_one_dimensional():
    A, _, _ = build_network()
    y = TRUE_FLOWS + np.array([0.3, -0.1, 0.4, 0.2, -0.2, 0.1])
    res_1d = reconcile(y, A, SIGMA)
    res_2d = reconcile(y, A, np.diag(SIGMA**2))
    np.testing.assert_allclose(res_2d.adjusted, res_1d.adjusted, rtol=0, atol=1e-12)
    np.testing.assert_allclose(res_2d.adjustments, res_1d.adjustments, rtol=0, atol=1e-12)
    np.testing.assert_allclose(
        res_2d.standardized_adjustments, res_1d.standardized_adjustments, rtol=0, atol=1e-12
    )
    assert res_2d.objective == pytest.approx(res_1d.objective)
    assert res_2d.dof == res_1d.dof


def test_reconcile_correlated_covariance_changes_the_answer():
    """A genuinely non-diagonal covariance must not give the diagonal answer."""
    A, _, _ = build_network()
    y = TRUE_FLOWS + np.array([0.3, -0.1, 0.4, 0.2, -0.2, 0.1])
    S = np.diag(SIGMA**2)
    S[0, 5] = S[5, 0] = 0.5 * SIGMA[0] * SIGMA[5]  # inflow and outflow errors correlate
    res_corr = reconcile(y, A, S)
    res_diag = reconcile(y, A, SIGMA)
    assert np.max(np.abs(res_corr.adjusted - res_diag.adjusted)) > 1e-6
    assert np.max(np.abs(A @ res_corr.adjusted)) < 1e-10


def test_reconcile_marks_non_redundant_measurements_nan():
    """A measurement absent from every constraint cannot be adjusted or tested."""
    A = np.array([[1.0, -1.0, 0.0]])
    res = reconcile([10.0, 8.0, 5.0], A, [1.0, 1.0, 1.0])
    np.testing.assert_array_equal(res.redundant, [True, True, False])
    assert np.isnan(res.standardized_adjustments[2])
    assert res.adjustments[2] == pytest.approx(0.0)
    assert res.adjusted[2] == pytest.approx(5.0)
    assert np.isfinite(res.standardized_adjustments[:2]).all()


def test_reconcile_uses_the_pseudo_inverse_for_dependent_constraints():
    """A duplicated (scaled) constraint row must not double the degrees of freedom."""
    A = np.array([[1.0, -1.0], [2.0, -2.0]])
    res = reconcile([10.0, 8.0], A, [1.0, 1.0])
    assert res.n_constraints == 2
    assert res.dof == 1  # rank, not row count
    np.testing.assert_allclose(res.adjusted, [9.0, 9.0])
    assert res.objective == pytest.approx(2.0)


def test_reconcile_rejects_inconsistent_dependent_constraints():
    A = np.array([[1.0, -1.0], [1.0, -1.0]])
    with pytest.raises(ValueError, match="inconsistent"):
        reconcile([10.0, 8.0], A, [1.0, 1.0], b=[0.0, 5.0])


@pytest.mark.parametrize(
    ("y", "A", "sigma", "kwargs", "message"),
    [
        ([1.0, 2.0], np.array([[1.0, -1.0, 1.0]]), [1.0, 1.0], {}, "columns but y has"),
        ([1.0, np.nan], np.array([[1.0, -1.0]]), [1.0, 1.0], {}, "y must be finite"),
        ([1.0, 2.0], np.array([[1.0, np.inf]]), [1.0, 1.0], {}, "A must be finite"),
        ([1.0, 2.0], np.array([[1.0, -1.0]]), [1.0, 0.0], {}, "strictly positive"),
        ([1.0, 2.0], np.array([[1.0, -1.0]]), [-1.0, 1.0], {}, "strictly positive"),
        ([1.0, 2.0], np.array([[1.0, -1.0]]), [1.0], {}, "entries but y has"),
        ([1.0, 2.0], np.array([[1.0, -1.0]]), np.ones((2, 3)), {}, "must have shape"),
        (
            [1.0, 2.0],
            np.array([[1.0, -1.0]]),
            np.array([[1.0, 0.5], [0.2, 1.0]]),
            {},
            "symmetric",
        ),
        (
            [1.0, 2.0],
            np.array([[1.0, -1.0]]),
            np.array([[1.0, 2.0], [2.0, 1.0]]),
            {},
            "positive definite",
        ),
        ([1.0, 2.0], np.array([[1.0, -1.0]]), np.ones((1, 2, 2)), {}, "1-D .* or 2-D"),
        ([1.0, 2.0], np.array([[1.0, -1.0]]), [1.0, 1.0], {"b": [0.0, 0.0]}, "b has 2 entries"),
        (
            [1.0, 2.0],
            np.array([[1.0, -1.0]]),
            [1.0, 1.0],
            {"names": ["only_one"]},
            "names has 1 entries",
        ),
        (
            [1.0, 2.0],
            np.array([[1.0, -1.0]]),
            [1.0, 1.0],
            {"constraint_names": ["a", "b"]},
            "constraint_names has 2 entries",
        ),
        ([[1.0, 2.0]], np.array([[1.0, -1.0]]), [1.0, 1.0], {}, "y must be 1-D"),
        ([1.0, 2.0], np.array([1.0, -1.0]), [1.0, 1.0], {}, "A must be 2-D"),
        ([1.0, 2.0], np.zeros((0, 2)), [1.0, 1.0], {}, "at least one constraint row"),
        ([1.0, 2.0], np.array([[1.0, -1.0]]), [1.0, 1.0], {"rcond": 1.0}, "rcond"),
    ],
)
def test_reconcile_rejects_bad_input(y, A, sigma, kwargs, message):
    with pytest.raises(ValueError, match=message):
        reconcile(y, A, sigma, **kwargs)


def test_reconcile_result_to_dict_is_jsonable():
    A, nodes, edges = build_network()
    res = reconcile(TRUE_FLOWS, A, SIGMA, names=edges, constraint_names=nodes)
    d = res.to_dict()
    assert isinstance(d["adjusted"], list)
    assert isinstance(d["objective"], float)
    assert d["names"] == EDGE_NAMES


# --------------------------------------------------------------------------------------------
# reconcile_table
# --------------------------------------------------------------------------------------------


def _flow_table(values: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame({"edge": EDGE_NAMES, "value": values, "sigma": SIGMA})


def test_reconcile_table_matches_reconcile_and_reorders_rows():
    A, _, edges = build_network()
    y = TRUE_FLOWS + np.array([0.3, -0.1, 0.4, 0.2, -0.2, 0.1])
    shuffled = _flow_table(y).iloc[[3, 0, 5, 2, 4, 1]].reset_index(drop=True)

    out = reconcile_table(shuffled, EDGES)
    assert list(out.columns) == [
        "edge",
        "source",
        "target",
        "value",
        "sigma",
        "adjusted",
        "adjustment",
        "standardized_adjustment",
        "redundant",
    ]
    assert out["edge"].tolist() == EDGE_NAMES  # network order, not table order
    assert out["source"].tolist() == [s for s, _ in EDGES.values()]
    assert out["target"].tolist() == [t for _, t in EDGES.values()]

    res = reconcile(y, A, SIGMA, names=edges)
    np.testing.assert_allclose(out["adjusted"].to_numpy(), res.adjusted)
    np.testing.assert_allclose(out["adjustment"].to_numpy(), res.adjustments)
    np.testing.assert_allclose(
        out["standardized_adjustment"].to_numpy(), res.standardized_adjustments
    )
    assert out.attrs["dof"] == 4
    assert out.attrs["objective"] == pytest.approx(res.objective)
    assert out.attrs["node_names"] == NODE_NAMES
    assert out.attrs["max_constraint_violation"] < 1e-10


def test_reconcile_table_on_exact_flows_makes_no_adjustment():
    out = reconcile_table(_flow_table(TRUE_FLOWS), EDGES)
    np.testing.assert_allclose(out["adjustment"].to_numpy(), np.zeros(6), atol=1e-12)
    assert out.attrs["objective"] == pytest.approx(0.0, abs=1e-20)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda t: t.drop(index=[0]), "missing edges"),
        (lambda t: pd.concat([t, t.iloc[[0]]], ignore_index=True), "more than once"),
        (lambda t: t.rename(columns={"sigma": "sd"}), "lacks required column"),
        (
            lambda t: pd.concat(
                [t, pd.DataFrame({"edge": ["ghost"], "value": [1.0], "sigma": [1.0]})],
                ignore_index=True,
            ),
            "not in the network",
        ),
    ],
)
def test_reconcile_table_rejects_bad_tables(mutate, message):
    with pytest.raises(ValueError, match=message):
        reconcile_table(mutate(_flow_table(TRUE_FLOWS)), EDGES)


def test_reconcile_table_rejects_non_dataframe():
    with pytest.raises(ValueError, match="pandas DataFrame"):
        reconcile_table({"edge": EDGE_NAMES}, EDGES)


# --------------------------------------------------------------------------------------------
# project_unmeasured
# --------------------------------------------------------------------------------------------


def test_project_unmeasured_keeps_the_true_flows_feasible():
    """Removing e13 as *unmeasured* merges nodes N1 and N3; the truth still satisfies the
    reduced constraints, which the naive column deletion would not."""
    A, _, _ = build_network()
    A_red, b_red, measured = project_unmeasured(A, [2])
    np.testing.assert_array_equal(measured, [0, 1, 3, 4, 5])
    assert A_red.shape[1] == 5
    assert A_red.shape[0] == 3  # one constraint is consumed by the eliminated variable
    np.testing.assert_allclose(A_red @ TRUE_FLOWS[measured] - b_red, 0.0, atol=1e-12)

    # Naive column deletion is *not* feasible: it asserts that e13 is zero.
    naive = A[:, measured]
    assert np.max(np.abs(naive @ TRUE_FLOWS[measured])) == pytest.approx(TRUE_FLOWS[2])


def test_project_unmeasured_is_a_no_op_with_nothing_to_remove():
    A, _, _ = build_network()
    A_red, b_red, measured = project_unmeasured(A, [])
    np.testing.assert_array_equal(A_red, A)
    np.testing.assert_array_equal(b_red, np.zeros(4))
    np.testing.assert_array_equal(measured, np.arange(6))


def test_project_unmeasured_detects_inconsistent_constants():
    # x2 alone appears in row 1, so eliminating it leaves "0 = 10".
    A = np.array([[1.0, -1.0, 0.0], [0.0, 0.0, 0.0]])
    with pytest.raises(ValueError, match="inconsistent"):
        project_unmeasured(A, [2], b=[0.0, 10.0])


@pytest.mark.parametrize(
    ("idx", "message"),
    [([9], "must lie in"), ([-1], "must lie in"), ([1, 1], "unique")],
)
def test_project_unmeasured_rejects_bad_indices(idx, message):
    A, _, _ = build_network()
    with pytest.raises(ValueError, match=message):
        project_unmeasured(A, idx)
