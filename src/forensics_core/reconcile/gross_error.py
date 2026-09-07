"""Gross-error detection for reconciled flow data.

Reconciliation (see :mod:`forensics_core.reconcile.balance`) assumes every measurement carries
only random error. A *gross error* -- a mis-recorded, mis-transcribed or deliberately falsified
flow -- violates that assumption and shows up as an implausibly large adjustment. The classical
battery of tests is:

``global_test``
    Chi-square test on the reconciliation objective ``r' (A S A')^+ r`` (Almasy & Sztano 1975,
    *Probl. Control Inf. Theory* 4:57; Narasimhan & Jordache 2000, *Data Reconciliation and
    Gross Error Detection*, Gulf, ch. 7). Detects "something is wrong" without saying what.
``measurement_test``
    Per-measurement standardised adjustment ``z_i = a_i / sqrt(Var(a)_ii)`` (Mah & Tamhane 1982,
    *AIChE J.* 28:828), compared against a critical value for a family of ``n`` simultaneous
    tests using the Sidak (Sidak 1967, *JASA* 62:626) or Bonferroni level split recommended by
    Tamhane & Mah (1985, *Technometrics* 27:409).
``nodal_test``
    Per-constraint standardised imbalance ``z_j = r_j / sqrt((A S A')_jj)`` (Reilly & Carpani
    1963; Mah, Stanley & Downing 1976, *Ind. Eng. Chem. Process Des. Dev.* 15:175). Points at
    the *node* whose balance fails rather than at a single stream.
``serial_elimination``
    Ripps' deletion strategy (Ripps 1965, *Chem. Eng. Prog. Symp. Ser.* 61:8; Serth & Heenan
    1986, *AIChE J.* 32:733): drop the worst measurement, treat it as unmeasured, re-reconcile,
    repeat until the global test passes, ``max_removals`` is reached, or nothing testable is
    left. Returns the suspects in the order they were removed.

Deviation from the repo-wide convention (INTERFACES.md): as in
:mod:`forensics_core.reconcile.balance`, non-finite input is rejected rather than dropped, so
``details["n_dropped"]`` is always 0 here; dropping a measurement would silently change the
constraint system.

Provenance caveat: the chapter numbers for Narasimhan & Jordache (2000) and the volume and page
numbers above are taken from the secondary literature and from memory rather than checked
against the primary texts; confirm them before quoting. The formulae themselves are standard
and are reproduced in full in the docstrings below so they can be checked independently of the
citation.

Everything here is pure: no I/O, no global state, no plotting.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd
from numpy.typing import ArrayLike
from scipy import stats

from forensics_core._types import TestResult, jsonable
from forensics_core.reconcile.balance import (
    DEFAULT_RCOND,
    ReconciliationResult,
    _as_1d_float,
    _as_2d_float,
    _covariance,
    _require_finite,
    project_unmeasured,
    reconcile,
)

Correction = Literal["sidak", "bonferroni", "none"]
Elimination = Literal["project", "column"]

#: Relative tolerance below which a constraint's residual variance ``(A S A')_jj`` counts as
#: zero, so :func:`nodal_test` cannot standardise that constraint's imbalance (``z`` is
#: ``nan``). Scaled by the largest diagonal entry of ``A S A'``.
NODAL_VARIANCE_TOL = 1e-12

#: Relative tolerance below which a row of the column-deleted constraint matrix counts as
#: carrying no measured variable under ``elimination="column"`` (scaled by ``max(1, max|A|)``).
EMPTY_ROW_TOL = 1e-12

__all__ = [
    "EMPTY_ROW_TOL",
    "NODAL_VARIANCE_TOL",
    "Correction",
    "Elimination",
    "GrossErrorSuspect",
    "critical_z",
    "global_test",
    "measurement_test",
    "nodal_test",
    "serial_elimination",
]


# --------------------------------------------------------------------------------------------
# Critical values
# --------------------------------------------------------------------------------------------


def critical_z(alpha: float, n_tests: int, correction: Correction = "sidak") -> tuple[float, float]:
    """Two-sided critical value for ``n_tests`` simultaneous standard-normal tests.

    Tamhane & Mah (1985, *Technometrics* 27:409) run the measurement test at a per-test level
    ``beta`` chosen so that the family-wise type-I error is ``alpha``:

    - ``"sidak"``:      ``beta = 1 - (1 - alpha)**(1 / n_tests)`` (Sidak 1967, *JASA* 62:626;
      exact when the tests are independent, which the measurement tests are not, so it is an
      approximation here)
    - ``"bonferroni"``: ``beta = alpha / n_tests``
    - ``"none"``:       ``beta = alpha`` (no multiplicity adjustment)

    The critical value is ``Phi^-1(1 - beta / 2)``.

    Parameters
    ----------
    alpha : float
        Family-wise significance level, in ``(0, 1)``.
    n_tests : int
        Number of simultaneous tests, ``>= 1``.
    correction : {"sidak", "bonferroni", "none"}

    Returns
    -------
    critical : float
        Two-sided critical value on the ``z`` scale.
    beta : float
        The per-test significance level used.

    Raises
    ------
    ValueError
        If ``alpha`` is outside ``(0, 1)``, ``n_tests < 1``, or ``correction`` is unknown.
    """
    if not np.isfinite(alpha) or not (0.0 < alpha < 1.0):
        raise ValueError(f"alpha must lie strictly between 0 and 1; got {alpha!r}")
    n_tests = int(n_tests)
    if n_tests < 1:
        raise ValueError(f"n_tests must be at least 1; got {n_tests}")
    if correction == "sidak":
        beta = 1.0 - (1.0 - alpha) ** (1.0 / n_tests)
    elif correction == "bonferroni":
        beta = alpha / n_tests
    elif correction == "none":
        beta = alpha
    else:
        raise ValueError(f"correction must be 'sidak', 'bonferroni' or 'none'; got {correction!r}")
    return float(stats.norm.isf(beta / 2.0)), float(beta)


def _check_result(res: Any, name: str = "res") -> ReconciliationResult:
    if not isinstance(res, ReconciliationResult):
        raise ValueError(
            f"{name} must be a ReconciliationResult from forensics_core.reconcile.reconcile; "
            f"got {type(res).__name__}"
        )
    return res


# --------------------------------------------------------------------------------------------
# Global test
# --------------------------------------------------------------------------------------------


def global_test(res: ReconciliationResult, alpha: float = 0.05) -> TestResult:
    """Chi-square test on the reconciliation objective (Almasy & Sztano 1975).

    Under the null "no gross error, measurements unbiased with covariance ``S``" the constraint
    residual ``r = A y - b`` has mean zero and covariance ``V = A S A'``, so

    ``gamma = r' V^+ r  ~  chi2(rank V)``,

    and ``rank V = rank A`` whenever ``S`` is positive definite. Large ``gamma`` is evidence of
    a gross error somewhere in the system; the test says nothing about *where*. The alternative
    is one-sided (``"greater"``).

    Parameters
    ----------
    res : ReconciliationResult
        Output of :func:`forensics_core.reconcile.reconcile`.
    alpha : float
        Significance level in ``(0, 1)``, used only to report ``details["critical"]`` and
        ``details["reject"]``.

    Returns
    -------
    TestResult
        ``method="reconcile_global_test"``, ``statistic`` = the objective,
        ``pvalue`` = ``P(chi2(dof) > gamma)``, ``n`` = number of measurements. ``details`` holds
        ``dof``, ``critical``, ``reject``, ``alpha``, ``n_constraints`` and ``alternative``.

    Raises
    ------
    ValueError
        If ``res`` is not a :class:`ReconciliationResult` or ``alpha`` is out of range.

    Notes
    -----
    A system with no redundancy (``dof == 0``) cannot be tested: the objective is identically
    zero, so the p-value is reported as ``1.0`` and the critical value as ``inf``, making
    ``reject`` ``False``.
    """
    res = _check_result(res)
    if not np.isfinite(alpha) or not (0.0 < alpha < 1.0):
        raise ValueError(f"alpha must lie strictly between 0 and 1; got {alpha!r}")
    dof = int(res.dof)
    stat = float(res.objective)
    if dof <= 0:
        pvalue: float | None = 1.0
        critical = float("inf")
    else:
        pvalue = float(stats.chi2.sf(stat, dof))
        critical = float(stats.chi2.isf(alpha, dof))
    return TestResult(
        method="reconcile_global_test",
        statistic=stat,
        pvalue=pvalue,
        n=res.n,
        details={
            "alternative": "greater",
            "dof": dof,
            "critical": critical,
            "reject": bool(stat > critical),
            "alpha": float(alpha),
            "n_constraints": res.n_constraints,
            "n_dropped": 0,
        },
    )


# --------------------------------------------------------------------------------------------
# Measurement test
# --------------------------------------------------------------------------------------------


def measurement_test(
    res: ReconciliationResult,
    alpha: float = 0.05,
    correction: Correction = "sidak",
    *,
    n_tests: int | None = None,
) -> pd.DataFrame:
    """Per-measurement test on the standardised adjustment (Mah & Tamhane 1982).

    Under the no-gross-error null the adjustment vector ``a = x_hat - y`` has mean zero and
    covariance ``Var(a) = S A' (A S A')^+ A S``, so for a redundant measurement

    ``z_i = a_i / sqrt(Var(a)_ii)  ~  N(0, 1)``.

    A measurement is flagged when ``|z_i| > critical``, the two-sided critical value for the
    family of simultaneous tests (see :func:`critical_z`).

    Parameters
    ----------
    res : ReconciliationResult
    alpha : float
        Family-wise significance level in ``(0, 1)``.
    correction : {"sidak", "bonferroni", "none"}
        Multiplicity adjustment for the family of per-measurement tests.
    n_tests : int, optional
        Size of the test family. Default ``res.n``, the number of measurements: the level
        split fixed by the interface contract is ``beta = 1 - (1 - alpha)**(1 / n)`` over all
        ``n`` measurements. Pass ``n_tests=table.attrs["n_redundant"]`` for the less
        conservative convention of splitting ``alpha`` only over the tests actually performed
        (a non-redundant measurement has ``Var(a)_ii = 0``, cannot be moved by any constraint,
        and its ``z`` is ``nan``, so it carries no test); that lowers the critical value and
        flags more measurements.

    Returns
    -------
    pandas.DataFrame
        One row per measurement, in measurement order, with columns
        ``[index, name, adjustment, z, abs_z, critical, flag]``. ``abs_z = |z|`` is the
        "higher = more suspicious" score (INTERFACES.md); ``z`` keeps the sign, negative
        meaning the reported value was pulled *down* by reconciliation. ``z`` and ``abs_z`` are
        ``nan`` and ``flag`` is ``False`` for non-redundant measurements. Rows stay in
        measurement order -- sort by ``abs_z`` descending for a ranked shortlist. Settings are
        recorded in ``.attrs`` (``alpha``, ``beta``, ``correction``, ``critical``, ``n_tests``,
        ``n_redundant``, ``dof``).

    Raises
    ------
    ValueError
        If ``res`` is not a :class:`ReconciliationResult`, ``alpha`` is out of range,
        ``correction`` is unknown, or ``n_tests < 1``.
    """
    res = _check_result(res)
    z = np.asarray(res.standardized_adjustments, dtype=float)
    abs_z = np.abs(z)
    redundant = np.asarray(res.redundant, dtype=bool)
    n_redundant = int(redundant.sum())
    # The family size is the number of tests ACTUALLY performed. A non-redundant measurement
    # has an undefined (nan) standardized adjustment and is never tested, so counting it would
    # inflate the Sidak/Bonferroni critical value and cost power on the measurements that are
    # testable. This matches nodal_test, which counts only testable constraints.
    n_testable = int(np.isfinite(z).sum())
    n_tests_used = max(n_testable, 1) if n_tests is None else int(n_tests)
    critical, beta = critical_z(alpha, n_tests_used, correction)
    flag = np.isfinite(z) & (abs_z > critical)
    out = pd.DataFrame(
        {
            "index": np.arange(res.n, dtype=int),
            "name": res.measurement_names(),
            "adjustment": np.asarray(res.adjustments, dtype=float),
            "z": z,
            "abs_z": abs_z,
            "critical": np.full(res.n, critical),
            "flag": flag,
        }
    )
    out.attrs.update(
        {
            "alpha": float(alpha),
            "beta": float(beta),
            "correction": str(correction),
            "critical": float(critical),
            "n_tests": int(n_tests_used),
            "n_redundant": n_redundant,
            "dof": int(res.dof),
        }
    )
    return out


# --------------------------------------------------------------------------------------------
# Nodal test
# --------------------------------------------------------------------------------------------


def nodal_test(
    res: ReconciliationResult,
    alpha: float = 0.05,
    *,
    correction: Correction = "none",
) -> pd.DataFrame:
    """Per-constraint test on the standardised imbalance (Mah, Stanley & Downing 1976).

    The imbalance of constraint ``j`` is ``r_j = (A y - b)_j`` with variance ``V_jj`` where
    ``V = A S A'``, so under the no-gross-error null

    ``z_j = r_j / sqrt(V_jj)  ~  N(0, 1)``.

    A gross error on one stream inflates the imbalance of every node that stream touches, so
    the nodal test localises the problem to a node (or the pair of nodes joined by the faulty
    stream) rather than to a single measurement. It is the natural first screen when a whole
    reporting unit, rather than one number, is suspect.

    Parameters
    ----------
    res : ReconciliationResult
    alpha : float
        Family-wise significance level in ``(0, 1)``.
    correction : {"sidak", "bonferroni", "none"}
        Multiplicity adjustment over the constraints. The default ``"none"`` is the test as
        published (Mah, Stanley & Downing 1976) and as fixed by the interface contract: each
        node is tested at level ``alpha``, so on a clean network with many nodes some node is
        expected to be flagged about ``alpha`` of the time *per node*. Pass ``"sidak"`` or
        ``"bonferroni"`` (matching :func:`measurement_test`) to control the family-wise error
        over the whole network instead.

    Returns
    -------
    pandas.DataFrame
        One row per constraint with columns
        ``[index, name, residual, z, abs_z, critical, flag]``. ``abs_z = |z|`` is the
        "higher = more suspicious" score (INTERFACES.md); ``z`` keeps the sign of the
        imbalance. Both are ``nan`` for a constraint whose residual variance is zero (every
        variable in it is non-redundant). Rows stay in constraint order. Settings are recorded
        in ``.attrs``.

    Raises
    ------
    ValueError
        On an invalid ``res``, ``alpha`` or ``correction``.
    """
    res = _check_result(res)
    V = np.asarray(res.constraint_covariance, dtype=float)
    diag = np.diag(V).astype(float)
    r = np.asarray(res.constraint_residuals, dtype=float)
    m = int(r.size)
    scale = float(np.max(np.abs(diag))) if diag.size else 0.0
    testable = diag > (NODAL_VARIANCE_TOL * scale if scale > 0 else 0.0)
    z = np.full(m, np.nan)
    z[testable] = r[testable] / np.sqrt(diag[testable])
    abs_z = np.abs(z)
    n_tests = max(int(testable.sum()), 1)
    critical, beta = critical_z(alpha, n_tests, correction)
    flag = np.isfinite(z) & (abs_z > critical)
    out = pd.DataFrame(
        {
            "index": np.arange(m, dtype=int),
            "name": res.constraint_labels(),
            "residual": r,
            "z": z,
            "abs_z": abs_z,
            "critical": np.full(m, critical),
            "flag": flag,
        }
    )
    out.attrs.update(
        {
            "alpha": float(alpha),
            "beta": float(beta),
            "correction": str(correction),
            "critical": float(critical),
            "n_tests": n_tests,
        }
    )
    return out


# --------------------------------------------------------------------------------------------
# Serial elimination
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class GrossErrorSuspect:
    """One measurement removed by :func:`serial_elimination`.

    Attributes
    ----------
    index : int
        Position of the measurement in the *original* ``y`` (column of the original ``A``).
    name : str
        Label of the measurement (from ``names``, else ``"x<index>"``).
    z : float
        Standardised adjustment at the moment of removal, computed on the system that still
        contained every measurement not yet removed.
    order_removed : int
        1 for the first measurement removed, 2 for the second, and so on.
    critical : float
        Critical value that ``|z|`` exceeded.
    objective_before, objective_after : float
        Global-test statistic before and after this removal.
    pvalue_before, pvalue_after : float or None
        Global-test p-value before and after this removal.
    dof_before, dof_after : int
        Global-test degrees of freedom (``rank A``) before and after this removal; ``-1`` if
        not filled in.
    global_reject_after : bool
        Whether the global test still rejects after this removal. ``False`` on the last suspect
        means the elimination succeeded in explaining the imbalance.
    """

    index: int
    name: str
    z: float
    order_removed: int
    critical: float = float("nan")
    objective_before: float = float("nan")
    objective_after: float = float("nan")
    pvalue_before: float | None = None
    pvalue_after: float | None = None
    dof_before: int = -1
    dof_after: int = -1
    global_reject_after: bool = True

    def to_dict(self) -> dict[str, Any]:
        return jsonable(asdict(self))

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return f"#{self.order_removed} {self.name} (index {self.index}, z={self.z:.3g})"


def _reduce_system(
    A0: np.ndarray,
    b0: np.ndarray,
    removed: Sequence[int],
    elimination: Elimination,
    names: list[str],
    rcond: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Constraint system that remains after the ``removed`` measurements are taken out.

    ``elimination="project"`` applies Crowe's projection (see
    :func:`forensics_core.reconcile.balance.project_unmeasured`) so the removed variables are
    genuinely *unmeasured*: the constraint rows are recombined so the unknown flows cancel.
    ``elimination="column"`` merely deletes the columns, which asserts the removed flows are
    zero; see :func:`serial_elimination` for why that is usually wrong.
    """
    n = A0.shape[1]
    if elimination == "project":
        return project_unmeasured(A0, list(removed), b0, rcond=rcond)
    if elimination != "column":
        raise ValueError(f"elimination must be 'project' or 'column'; got {elimination!r}")
    mask = np.ones(n, dtype=bool)
    mask[list(removed)] = False
    measured = np.flatnonzero(mask)
    A_cur = A0[:, measured]
    scale = float(np.max(np.abs(A0))) if A0.size else 1.0
    empty = np.all(np.abs(A_cur) <= EMPTY_ROW_TOL * max(scale, 1.0), axis=1)
    if np.any(empty):
        rows = np.flatnonzero(empty).tolist()
        dropped = [names[i] for i in removed]
        raise ValueError(
            f"elimination='column': deleting {dropped} leaves constraint row(s) {rows} with no "
            "measured variable, so the reduced system is degenerate. Use the default "
            "elimination='project' (Crowe's projection), which recombines the constraints so "
            "the unmeasured flows cancel."
        )
    return A_cur, b0.copy(), measured


def serial_elimination(
    y: ArrayLike,
    A: np.ndarray,
    sigma: ArrayLike,
    b: ArrayLike | None = None,
    alpha: float = 0.05,
    max_removals: int | None = None,
    *,
    correction: Correction = "sidak",
    names: Sequence[str] | None = None,
    constraint_names: Sequence[str] | None = None,
    elimination: Elimination = "project",
    rcond: float = DEFAULT_RCOND,
) -> list[GrossErrorSuspect]:
    """Iteratively delete the worst measurement until the global test passes (Ripps 1965).

    The serial-elimination (deletion) strategy of Ripps (1965, *Chem. Eng. Prog. Symp. Ser.*
    61:8), refined by Serth & Heenan (1986, *AIChE J.* 32:733) and reviewed in Narasimhan &
    Jordache (2000, ch. 7):

    1. Reconcile; if :func:`global_test` does not reject, stop -- no gross error is detectable.
    2. Run :func:`measurement_test` and take the measurement with the largest ``|z|`` among
       those above the critical value. If none is above it, stop.
    3. Delete that measurement, so it becomes an *unmeasured* variable; reconcile the reduced
       system and go back to step 1, until the global test passes, ``max_removals`` removals
       have been made, or the removals have consumed every constraint row.

    Each removal also removes one measured variable, so the degrees of freedom fall as the
    procedure runs; the reported ``dof_before`` / ``dof_after`` make that visible.

    Parameters
    ----------
    y : array-like, shape (n,)
        Measured values; must be finite.
    A : array-like, shape (m, n)
        Constraint matrix, e.g. from :func:`forensics_core.reconcile.incidence_matrix`.
    sigma : array-like, shape (n,) or (n, n)
        Measurement standard deviations or covariance.
    b : array-like, shape (m,), optional
        Constraint constants; default zeros.
    alpha : float
        Family-wise significance level for both the global test and the measurement test.
    max_removals : int, optional
        Maximum number of measurements to remove. Default ``n - 1``.
    correction : {"sidak", "bonferroni", "none"}
        Multiplicity adjustment passed to :func:`measurement_test`.
    names, constraint_names : sequence of str, optional
        Labels; ``names`` supplies :attr:`GrossErrorSuspect.name`.
    elimination : {"project", "column"}
        How a removed measurement is taken out of the system.

        ``"project"`` (default, and the only correct reading of "treat it as unmeasured")
            eliminates the variable with Crowe's projection (Crowe, Garcia Campos & Hrymak
            1983, *AIChE J.* 29:881; Crowe 1996, *J. Process Control* 6:89): the constraint
            rows are recombined so the unknown flow cancels. On a flow network this merges the
            two nodes joined by the deleted stream.
        ``"column"``
            literally deletes the column and keeps every row. That asserts the removed flow is
            *zero*, not that it is unknown, and generally leaves the reduced system badly
            imbalanced, so the global test keeps rejecting after a removal that should have
            fixed it. Provided for comparison only; it raises :class:`ValueError` if a
            constraint row would be left with no measured variable.

        Neither variant assesses *observability* of the eliminated variables or the redundancy
        of the survivors: a stream removed here is simply no longer estimated. Serth &
        Heenan's refinements (variable classification, alternative test statistics) are not
        implemented.
    rcond : float
        Relative cutoff for the pseudo-inverses and for ``rank(A_u)`` in the projection.

    Returns
    -------
    list of GrossErrorSuspect
        In removal order; empty when the global test never rejects. Inspect
        ``suspects[-1].global_reject_after`` to see whether the elimination finally succeeded.

    Raises
    ------
    ValueError
        On invalid input or a negative ``max_removals``.

    Notes
    -----
    Running out of removable measurements is a *stopping condition*, not an error. On a small
    system a removal can consume the last constraint row (eliminating a variable with Crowe's
    projection costs one constraint), leaving nothing to reconcile or test: the measurement
    already identified is still returned, with ``dof_after = 0``, ``objective_after = nan``,
    ``pvalue_after = None`` and ``global_reject_after`` left ``True`` -- the imbalance was never
    shown to be explained. The two-stream system ``ENV -> N1 -> ENV`` is the extreme case: its
    single constraint disappears with the first removal.

    Serial elimination inherits the known weaknesses of the deletion strategy: gross-error
    *smearing* means the largest ``|z|`` need not sit on the faulty stream, and every deletion
    lowers the power of the tests that follow. Treat the returned list as a ranked shortlist
    for investigation, not as proof.
    """
    y0 = _as_1d_float(y, "y")
    _require_finite(y0, "y")
    A0 = _as_2d_float(A, "A")
    _require_finite(A0, "A")
    m, n = A0.shape
    if n != y0.size:
        raise ValueError(f"A has {n} columns but y has {y0.size} entries")
    if m == 0:
        raise ValueError("A must have at least one constraint row")
    S0 = _covariance(sigma, n)
    if b is None:
        b0 = np.zeros(m)
    else:
        b0 = _as_1d_float(b, "b")
        if b0.size != m:
            raise ValueError(f"b has {b0.size} entries but A has {m} rows")
        _require_finite(b0, "b")
    if names is not None:
        name_list = [str(v) for v in names]
        if len(name_list) != n:
            raise ValueError(f"names has {len(name_list)} entries but there are {n} measurements")
    else:
        name_list = [f"x{i}" for i in range(n)]
    if constraint_names is not None:
        cnames: list[str] | None = [str(v) for v in constraint_names]
        if len(cnames) != m:
            raise ValueError(
                f"constraint_names has {len(cnames)} entries but there are {m} constraints"
            )
    else:
        cnames = None
    if max_removals is None:
        max_removals_used = max(n - 1, 0)
    else:
        max_removals_used = int(max_removals)
        if max_removals_used < 0:
            raise ValueError(f"max_removals must be non-negative; got {max_removals}")
    # Validate alpha and correction up front, so a bad value fails before any work is done.
    critical_z(alpha, max(n, 1), correction)

    removed: list[int] = []
    records: list[dict[str, Any]] = []

    while True:
        A_cur, b_cur, measured = _reduce_system(A0, b0, removed, elimination, name_list, rcond)
        if A_cur.shape[0] == 0:
            # The previous removal consumed the last constraint row. That is a normal stopping
            # condition of the deletion strategy, not bad input: report the suspects found so
            # far, with the last one's "after" fields marking that nothing could be re-tested.
            if records:
                records[-1].update(
                    objective_after=float("nan"),
                    pvalue_after=None,
                    dof_after=0,
                    global_reject_after=True,
                )
            break
        sub_cnames = cnames if (cnames is not None and A_cur.shape[0] == m) else None
        res = reconcile(
            y0[measured],
            A_cur,
            S0[np.ix_(measured, measured)],
            b_cur,
            names=[name_list[i] for i in measured],
            constraint_names=sub_cnames,
            rcond=rcond,
        )
        gt = global_test(res, alpha)
        if records:
            records[-1].update(
                objective_after=float(res.objective),
                pvalue_after=gt.pvalue,
                dof_after=int(res.dof),
                global_reject_after=bool(gt.details["reject"]),
            )
        if not gt.details["reject"]:
            break
        if len(removed) >= max_removals_used:
            break
        table = measurement_test(res, alpha, correction)
        z_sub = table["z"].to_numpy(dtype=float)
        critical = float(table.attrs["critical"])
        abs_z = np.where(np.isfinite(z_sub), np.abs(z_sub), -np.inf)
        pos = int(np.argmax(abs_z))
        if not np.isfinite(abs_z[pos]) or abs_z[pos] <= critical:
            break
        original = int(measured[pos])
        records.append(
            {
                "index": original,
                "name": name_list[original],
                "z": float(z_sub[pos]),
                "order_removed": len(records) + 1,
                "critical": critical,
                "objective_before": float(res.objective),
                "pvalue_before": gt.pvalue,
                "dof_before": int(res.dof),
                "objective_after": float("nan"),
                "pvalue_after": None,
                "dof_after": -1,
                "global_reject_after": True,
            }
        )
        removed.append(original)

    return [GrossErrorSuspect(**rec) for rec in records]
