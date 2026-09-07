"""Linear data reconciliation on a flow network.

Given measurements ``y`` of flows that must satisfy linear conservation constraints
``A x = b``, the reconciled estimate is the minimum-variance perturbation of ``y`` that
restores feasibility (weighted least squares with equality constraints). The closed form,
for measurement covariance ``S``::

    x_hat = y - S A' (A S A')^+ (A y - b)

is the classical solution of Kuehn & Davidson (1961, *Chem. Eng. Prog.* 57:31) as presented
in Narasimhan & Jordache (2000, *Data Reconciliation and Gross Error Detection*, Gulf,
ch. 3), and the adjustment covariance ``Var(a) = S A' (A S A')^+ A S`` underlies the
measurement test of Mah & Tamhane (1982, *AIChE J.* 28:828). Unmeasured variables are removed
with Crowe's projection matrix (Crowe, Garcia Campos & Hrymak 1983, *AIChE J.* 29:881;
Crowe 1986, *AIChE J.* 32:616; Crowe 1996, *J. Process Control* 6:89).

Deviation from the repo-wide convention (INTERFACES.md): non-finite values are **rejected**
here, not dropped with a count in ``details["n_dropped"]``. Dropping a measurement silently
turns it into an *unmeasured* variable, which changes the constraint system and the degrees of
freedom of every test that follows; the caller must ask for that explicitly with
:func:`project_unmeasured`. Every entry point in this module and in
:mod:`forensics_core.reconcile.gross_error` therefore raises ``ValueError`` on ``nan``/``inf``.

Provenance caveat: the chapter, volume and page numbers cited here and below are taken from the
secondary literature and from memory rather than checked against the primary texts; confirm
them before quoting. The formulae themselves are standard and are written out in full in the
docstrings so they can be verified independently of the citation.

Everything here is pure: no I/O, no global state.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import ArrayLike

from forensics_core._types import jsonable

#: Relative eigenvalue cutoff (fraction of the largest eigenvalue) below which an eigenvalue of
#: ``A S A'`` is treated as zero when forming its pseudo-inverse and counting its rank.
DEFAULT_RCOND = 1e-12

#: Relative tolerance below which a column of ``A S`` counts as zero. A measurement whose
#: column of ``A S`` vanishes is *non-redundant*: no constraint can adjust it and
#: ``Var(a)_ii = 0`` exactly, so its standardized adjustment is undefined (``nan``).
REDUNDANCY_TOL = 1e-10

#: Relative tolerance for the two consistency checks on the constraint constants: that ``b``
#: lies in the range of a rank-deficient ``A`` (:func:`reconcile`), and that a constraint left
#: with no measured variable by :func:`project_unmeasured` has a zero right-hand side. Scaled by
#: ``max(1, max|b|)``.
CONSISTENCY_TOL = 1e-8

#: Relative tolerance below which an entry of the projected matrix ``P A_m`` is treated as
#: numerical dust from the SVD and set to zero, and below which a whole projected row counts as
#: carrying no measured variable (:func:`project_unmeasured`). Scaled by a *single* global
#: ``max(1, max|A_m|)``, so ``A`` is assumed to have coefficients of comparable magnitude.
PROJECTION_ZERO_TOL = 1e-10

__all__ = [
    "CONSISTENCY_TOL",
    "DEFAULT_RCOND",
    "PROJECTION_ZERO_TOL",
    "REDUNDANCY_TOL",
    "ReconciliationResult",
    "incidence_matrix",
    "project_unmeasured",
    "reconcile",
    "reconcile_table",
]


# --------------------------------------------------------------------------------------------
# Input coercion helpers (private)
# --------------------------------------------------------------------------------------------


def _as_1d_float(x: ArrayLike, name: str) -> np.ndarray:
    """Coerce to a 1-D float64 array; raise ``ValueError`` on non-numeric or non-1-D input."""
    if hasattr(x, "to_numpy"):  # pandas Series / Index, incl. nullable dtypes
        try:
            arr = x.to_numpy(dtype=float, na_value=np.nan)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be numeric; got {type(x).__name__}") from exc
    else:
        arr = np.asarray(x)
        if arr.dtype.kind == "b":
            raise ValueError(f"{name} must be numeric, not boolean")
        if arr.dtype.kind not in "iuf":
            try:
                arr = arr.astype(float)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be numeric; got dtype {arr.dtype}") from exc
    arr = np.asarray(arr, dtype=float)
    if arr.ndim != 1:
        raise ValueError(f"{name} must be 1-D; got shape {arr.shape}")
    return arr


def _as_2d_float(x: ArrayLike, name: str) -> np.ndarray:
    """Coerce to a 2-D float64 array; raise ``ValueError`` on non-numeric or non-2-D input."""
    if hasattr(x, "to_numpy"):
        try:
            arr = x.to_numpy(dtype=float)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be numeric; got {type(x).__name__}") from exc
    else:
        arr = np.asarray(x)
        if arr.dtype.kind == "b":
            raise ValueError(f"{name} must be numeric, not boolean")
        if arr.dtype.kind not in "iuf":
            try:
                arr = arr.astype(float)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be numeric; got dtype {arr.dtype}") from exc
    arr = np.asarray(arr, dtype=float)
    if arr.ndim != 2:
        raise ValueError(f"{name} must be 2-D; got shape {arr.shape}")
    return arr


def _require_finite(arr: np.ndarray, name: str) -> None:
    if not np.all(np.isfinite(arr)):
        raise ValueError(
            f"{name} must be finite. Reconciliation cannot drop a non-finite measurement "
            "without changing the constraint system; remove the variable's column from A "
            "(see project_unmeasured) instead of passing nan/inf."
        )


def _covariance(sigma: ArrayLike, n: int) -> np.ndarray:
    """Turn ``sigma`` (1-D std devs or 2-D covariance) into a validated ``(n, n)`` covariance.

    1-D input must be strictly positive; 2-D input must be symmetric and positive definite
    (checked with a Cholesky factorisation). A zero variance is rejected rather than treated as
    an infinitely precise measurement: move such a quantity into ``b`` instead. Both branches
    go through the same coercion helpers as ``y``, so a boolean array is rejected rather than
    silently read as standard deviations of 1.
    """
    try:
        ndim = int(np.ndim(sigma))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "sigma must be a numeric 1-D array of standard deviations or a 2-D covariance "
            "matrix; got a ragged or non-array-like object"
        ) from exc
    if ndim == 1:
        arr = _as_1d_float(sigma, "sigma")
        if arr.size != n:
            raise ValueError(f"sigma has {arr.size} entries but y has {n}")
        _require_finite(arr, "sigma")
        if np.any(arr <= 0):
            raise ValueError(
                "sigma (standard deviations) must be strictly positive; a zero-variance "
                "measurement should be moved into the constraint constant b"
            )
        return np.diag(arr * arr)
    if ndim == 2:
        arr = _as_2d_float(sigma, "sigma")
        if arr.shape != (n, n):
            raise ValueError(f"sigma as a covariance must have shape ({n}, {n}); got {arr.shape}")
        _require_finite(arr, "sigma")
        scale = float(np.max(np.abs(arr))) if arr.size else 0.0
        if not np.allclose(arr, arr.T, rtol=1e-8, atol=1e-12 * max(scale, 1.0)):
            raise ValueError("sigma as a covariance must be symmetric")
        try:
            np.linalg.cholesky(arr)
        except np.linalg.LinAlgError as exc:
            raise ValueError("sigma as a covariance must be positive definite") from exc
        return (arr + arr.T) / 2.0
    raise ValueError(f"sigma must be 1-D (standard deviations) or 2-D (covariance); got {ndim}-D")


def _pinv_psd(V: np.ndarray, rcond: float) -> tuple[np.ndarray, int]:
    """Pseudo-inverse and rank of a symmetric positive semi-definite matrix via ``eigh``.

    Eigenvalues at or below ``rcond * max(eigenvalue)`` (or non-positive) are treated as zero;
    the number retained is the rank, which for positive definite ``S`` equals ``rank(A)``.
    """
    if V.shape[0] == 0:
        return np.zeros_like(V), 0
    w, Q = np.linalg.eigh(V)
    w_max = float(w.max())
    if w_max <= 0.0:
        return np.zeros_like(V), 0
    keep = w > rcond * w_max
    Qk = Q[:, keep]
    pinv = (Qk / w[keep]) @ Qk.T
    return (pinv + pinv.T) / 2.0, int(keep.sum())


# --------------------------------------------------------------------------------------------
# Incidence matrix
# --------------------------------------------------------------------------------------------


def _normalise_edges(
    edges: Sequence[tuple[str, str]]
    | Sequence[tuple[str, str, str]]
    | Mapping[str, tuple[str, str]],
    edge_names: Sequence[str] | None,
) -> list[tuple[str, str, str]]:
    """Return ``[(name, source, target), ...]`` from any accepted edge specification."""
    from_mapping = isinstance(edges, Mapping)
    if from_mapping:
        if edge_names is not None:
            raise ValueError("edge_names cannot be combined with a mapping of edges")
        names = [str(k) for k in edges]
        pairs = list(edges.values())
    else:
        pairs = list(edges)
        names = None if edge_names is None else [str(x) for x in edge_names]
    if len(pairs) == 0:
        raise ValueError("edges must contain at least one edge")

    lengths = {len(p) if isinstance(p, tuple | list) else -1 for p in pairs}
    if lengths == {3}:
        if from_mapping:
            raise ValueError(
                "a mapping of edges must map a name to a (source, target) pair, not to a "
                "(name, source, target) triple"
            )
        if names is not None:
            raise ValueError("edge_names cannot be combined with (name, source, target) edges")
        names = [str(p[0]) for p in pairs]
        pairs = [(p[1], p[2]) for p in pairs]
    elif lengths != {2}:
        raise ValueError(
            "every edge must be a (source, target) pair or a (name, source, target) triple"
        )

    if names is not None and len(names) != len(pairs):
        raise ValueError(f"edge_names has {len(names)} entries but there are {len(pairs)} edges")

    out: list[tuple[str, str, str]] = []
    seen: dict[str, int] = {}
    for k, (src, dst) in enumerate(pairs):
        if not isinstance(src, str) or not isinstance(dst, str):
            raise ValueError(f"edge {k}: node names must be strings; got ({src!r}, {dst!r})")
        if not src or not dst:
            raise ValueError(f"edge {k}: node names must be non-empty strings")
        if src == dst:
            raise ValueError(f"edge {k}: self-loop {src!r}->{dst!r} contributes nothing")
        if names is None:
            base = f"{src}->{dst}"
            count = seen.get(base, 0) + 1
            seen[base] = count
            name = base if count == 1 else f"{base}#{count}"
        else:
            name = names[k]
        out.append((name, src, dst))

    explicit = [n for n, _, _ in out]
    if len(set(explicit)) != len(explicit):
        dup = sorted({n for n in explicit if explicit.count(n) > 1})
        raise ValueError(f"edge names must be unique; duplicated: {dup}")
    return out


def _incidence(
    edges: Sequence[tuple[str, str]] | Mapping[str, tuple[str, str]],
    nodes: Sequence[str] | None,
    environment: str,
    edge_names: Sequence[str] | None,
) -> tuple[np.ndarray, list[str], list[str], list[str], list[str]]:
    """Build the incidence matrix; also return per-edge sources and targets."""
    if not isinstance(environment, str) or not environment:
        raise ValueError("environment must be a non-empty string")
    triples = _normalise_edges(edges, edge_names)

    if nodes is None:
        node_names: list[str] = []
        for _, src, dst in triples:
            for v in (src, dst):
                if v != environment and v not in node_names:
                    node_names.append(v)
    else:
        given = list(nodes)
        if any(not isinstance(v, str) for v in given):
            raise ValueError("nodes must be strings")
        if len(set(given)) != len(given):
            raise ValueError("nodes must be unique")
        node_names = [v for v in given if v != environment]
        touched = {v for _, src, dst in triples for v in (src, dst) if v != environment}
        unknown = sorted(touched - set(node_names))
        if unknown:
            raise ValueError(f"edges reference nodes missing from `nodes`: {unknown}")
        isolated = [v for v in node_names if v not in touched]
        if isolated:
            raise ValueError(f"nodes with no incident edge (empty constraint): {isolated}")

    if not node_names:
        raise ValueError("no internal node: every edge touches only the environment")

    index = {v: i for i, v in enumerate(node_names)}
    A = np.zeros((len(node_names), len(triples)), dtype=float)
    for k, (_, src, dst) in enumerate(triples):
        if dst != environment:
            A[index[dst], k] += 1.0
        if src != environment:
            A[index[src], k] -= 1.0
    edge_labels = [n for n, _, _ in triples]
    sources = [s for _, s, _ in triples]
    targets = [t for _, _, t in triples]
    return A, node_names, edge_labels, sources, targets


def incidence_matrix(
    edges: Sequence[tuple[str, str]] | Mapping[str, tuple[str, str]],
    nodes: Sequence[str] | None = None,
    environment: str = "ENV",
    *,
    edge_names: Sequence[str] | None = None,
) -> tuple[np.ndarray, list[str], list[str]]:
    """Node-edge incidence matrix of a directed flow network (Narasimhan & Jordache 2000, §3.2).

    Parameters
    ----------
    edges : sequence of (source, target) pairs, (name, source, target) triples, or a mapping
        ``{name: (source, target)}``
        One entry per measured flow; the flow leaves ``source`` and enters ``target``. The
        default name of an unnamed edge is ``"source->target"``; parallel unnamed edges get a
        ``#2``, ``#3``... suffix in order of appearance.
    nodes : sequence of str, optional
        Row order. Must list every non-environment node touched by ``edges`` (an isolated node
        is an error: its row would be an empty constraint). Default: first-appearance order,
        scanning each edge's source then target.
    environment : str
        Name of the environment (external source/sink) node. Its row is dropped because
        exchanges with the outside world are not conserved.
    edge_names : sequence of str, optional
        Explicit names for ``(source, target)`` edges; must be unique.

    Returns
    -------
    A : numpy.ndarray, shape (n_nodes, n_edges)
        ``A[node, edge] = +1`` if the edge flows into the node, ``-1`` if it flows out.
    node_names : list of str
    edge_names : list of str

    Raises
    ------
    ValueError
        On self-loops, non-string node names, duplicate names, unknown or isolated nodes, or
        a network with no internal node.
    """
    A, node_names, edge_labels, _, _ = _incidence(edges, nodes, environment, edge_names)
    return A, node_names, edge_labels


# --------------------------------------------------------------------------------------------
# Reconciliation
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class ReconciliationResult:
    """Outcome of :func:`reconcile`.

    Attributes
    ----------
    adjusted : numpy.ndarray, shape (n,)
        Reconciled estimates ``x_hat``.
    adjustments : numpy.ndarray, shape (n,)
        ``a = x_hat - y``.
    constraint_residuals : numpy.ndarray, shape (m,)
        ``r = A y - b`` (imbalance of the *measured* values).
    standardized_adjustments : numpy.ndarray, shape (n,)
        ``a_i / sqrt(Var(a)_ii)``; ``nan`` for non-redundant measurements (``redundant`` is
        False), whose adjustment variance is exactly zero.
    objective : float
        ``r' (A S A')^+ r``, the minimised weighted sum of squared adjustments.
    dof : int
        Degrees of freedom of the reconciliation, ``rank(A S A')`` (equal to ``rank(A)`` for a
        positive definite ``S``); the chi-square degrees of freedom of the global test.
    A : numpy.ndarray, shape (m, n)
        Constraint matrix as used.
    sigma : numpy.ndarray, shape (n, n)
        Measurement covariance ``S`` actually used (``diag(sigma**2)`` when std devs were
        given).
    b : numpy.ndarray, shape (m,)
        Constraint constants.
    adjustment_covariance : numpy.ndarray, shape (n, n)
        ``Var(a) = S A' (A S A')^+ A S``.
    constraint_covariance : numpy.ndarray, shape (m, m)
        ``V = A S A'``.
    constraint_covariance_pinv : numpy.ndarray, shape (m, m)
        ``V^+``.
    redundant : numpy.ndarray of bool, shape (n,)
        True where the measurement participates in at least one constraint (after weighting
        by ``S``) and can therefore be adjusted and tested.
    max_constraint_violation : float
        ``max |A x_hat - b|`` (a numerical diagnostic; zero up to rounding).
    names, constraint_names : tuple of str, optional
        Labels for measurements and constraints.
    """

    adjusted: np.ndarray
    adjustments: np.ndarray
    constraint_residuals: np.ndarray
    standardized_adjustments: np.ndarray
    objective: float
    dof: int
    A: np.ndarray
    sigma: np.ndarray
    b: np.ndarray
    adjustment_covariance: np.ndarray
    constraint_covariance: np.ndarray
    constraint_covariance_pinv: np.ndarray
    redundant: np.ndarray
    max_constraint_violation: float
    names: tuple[str, ...] | None = None
    constraint_names: tuple[str, ...] | None = None

    @property
    def n(self) -> int:
        """Number of measurements."""
        return int(self.adjusted.size)

    @property
    def n_constraints(self) -> int:
        """Number of constraint rows (may exceed ``dof`` when rows are dependent)."""
        return int(self.A.shape[0])

    @property
    def rank(self) -> int:
        """Alias of :attr:`dof`."""
        return self.dof

    def measurement_names(self) -> list[str]:
        """Measurement labels, defaulting to ``x0, x1, ...``."""
        if self.names is None:
            return [f"x{i}" for i in range(self.n)]
        return list(self.names)

    def constraint_labels(self) -> list[str]:
        """Constraint labels, defaulting to ``c0, c1, ...``."""
        if self.constraint_names is None:
            return [f"c{j}" for j in range(self.n_constraints)]
        return list(self.constraint_names)

    def to_dict(self) -> dict[str, Any]:
        return jsonable({f.name: getattr(self, f.name) for f in fields(self)})


def reconcile(
    y: ArrayLike,
    A: np.ndarray,
    sigma: ArrayLike,
    b: ArrayLike | None = None,
    *,
    names: Sequence[str] | None = None,
    constraint_names: Sequence[str] | None = None,
    rcond: float = DEFAULT_RCOND,
    redundancy_tol: float = REDUNDANCY_TOL,
) -> ReconciliationResult:
    """Weighted least-squares reconciliation of measurements to linear constraints.

    Solves ``min (x - y)' S^-1 (x - y)  s.t.  A x = b`` in closed form (Kuehn & Davidson 1961;
    Narasimhan & Jordache 2000, eq. 3.4 ff.)::

        r     = A y - b
        x_hat = y - S A' (A S A')^+ r
        a     = x_hat - y,   Var(a) = S A' (A S A')^+ A S
        objective = r' (A S A')^+ r     (~ chi2(rank) under the no-gross-error null)

    The Moore-Penrose pseudo-inverse replaces the inverse when ``A S A'`` is singular
    (linearly dependent constraint rows); the constraints are then still satisfied exactly
    provided ``b`` is consistent (lies in the range of ``A``), which is checked.

    Parameters
    ----------
    y : array-like, shape (n,)
        Measured values. Must be finite.
    A : array-like, shape (m, n)
        Constraint matrix (e.g. from :func:`incidence_matrix`). Must be finite, ``m >= 1``.
    sigma : array-like, shape (n,) or (n, n)
        Measurement standard deviations (strictly positive) or a symmetric positive definite
        covariance matrix.
    b : array-like, shape (m,), optional
        Constraint constants; default zeros (pure conservation).
    names, constraint_names : sequence of str, optional
        Labels carried into the result and into the tables of ``gross_error``.
    rcond : float
        Relative eigenvalue cutoff for the pseudo-inverse of ``A S A'``.
    redundancy_tol : float
        Relative tolerance below which a column of ``A S`` is treated as zero, marking the
        measurement as non-redundant (``standardized_adjustments`` is ``nan`` there).

    Returns
    -------
    ReconciliationResult

    Raises
    ------
    ValueError
        On shape mismatch, non-finite input, non-positive or non-definite ``sigma``, or an
        inconsistent ``b`` (no ``x`` satisfies ``A x = b``).

    Notes
    -----
    Non-finite measurements are rejected rather than dropped: dropping one silently turns it
    into an unmeasured variable and changes the constraint system. Use
    :func:`project_unmeasured` to do that explicitly.
    """
    y_arr = _as_1d_float(y, "y")
    _require_finite(y_arr, "y")
    A_arr = _as_2d_float(A, "A")
    _require_finite(A_arr, "A")
    m, n = A_arr.shape
    if n != y_arr.size:
        raise ValueError(f"A has {n} columns but y has {y_arr.size} entries")
    if m == 0:
        raise ValueError("A must have at least one constraint row")
    if not (0.0 <= rcond < 1.0):
        raise ValueError("rcond must lie in [0, 1)")
    if not (0.0 <= redundancy_tol < 1.0):
        raise ValueError("redundancy_tol must lie in [0, 1)")
    S = _covariance(sigma, n)
    if b is None:
        b_arr = np.zeros(m)
    else:
        b_arr = _as_1d_float(b, "b")
        if b_arr.size != m:
            raise ValueError(f"b has {b_arr.size} entries but A has {m} rows")
        _require_finite(b_arr, "b")
    if names is not None:
        names_t = tuple(str(v) for v in names)
        if len(names_t) != n:
            raise ValueError(f"names has {len(names_t)} entries but there are {n} measurements")
    else:
        names_t = None
    if constraint_names is not None:
        cnames_t = tuple(str(v) for v in constraint_names)
        if len(cnames_t) != m:
            raise ValueError(
                f"constraint_names has {len(cnames_t)} entries but there are {m} constraints"
            )
    else:
        cnames_t = None

    SAt = S @ A_arr.T  # (n, m)
    V = A_arr @ SAt  # (m, m)
    V = (V + V.T) / 2.0
    V_pinv, rank = _pinv_psd(V, rcond)

    if rank < m and np.any(b_arr != 0.0):
        # range(V) == range(A) for positive definite S, so b must be invariant under V V^+.
        b_perp = b_arr - V @ (V_pinv @ b_arr)
        scale = max(1.0, float(np.max(np.abs(b_arr))))
        if np.max(np.abs(b_perp)) > CONSISTENCY_TOL * scale:
            raise ValueError(
                "constraints are inconsistent: b does not lie in the range of A, so no x "
                "satisfies A x = b (dependent constraint rows with conflicting constants)"
            )

    r = A_arr @ y_arr - b_arr
    a = -SAt @ (V_pinv @ r)
    x_hat = y_arr + a
    var_a = SAt @ V_pinv @ SAt.T
    var_a = (var_a + var_a.T) / 2.0
    var_diag = np.diag(var_a).copy()

    AS = SAt.T  # (m, n): column i is A S e_i
    col_scale = np.max(np.abs(A_arr)) * np.max(np.abs(S), axis=0)  # per-column scale
    col_max = np.max(np.abs(AS), axis=0)
    redundant = col_max > redundancy_tol * np.where(col_scale > 0, col_scale, 1.0)
    redundant &= var_diag > 0.0

    z = np.full(n, np.nan)
    z[redundant] = a[redundant] / np.sqrt(var_diag[redundant])

    objective = float(r @ (V_pinv @ r))
    violation = float(np.max(np.abs(A_arr @ x_hat - b_arr))) if m else 0.0

    return ReconciliationResult(
        adjusted=x_hat,
        adjustments=a,
        constraint_residuals=r,
        standardized_adjustments=z,
        objective=objective,
        dof=int(rank),
        A=A_arr,
        sigma=S,
        b=b_arr,
        adjustment_covariance=var_a,
        constraint_covariance=V,
        constraint_covariance_pinv=V_pinv,
        redundant=redundant,
        max_constraint_violation=violation,
        names=names_t,
        constraint_names=cnames_t,
    )


def reconcile_table(
    flows: pd.DataFrame,
    edges: Sequence[tuple[str, str]] | Mapping[str, tuple[str, str]],
    sigma_col: str = "sigma",
    value_col: str = "value",
    *,
    edge_col: str = "edge",
    nodes: Sequence[str] | None = None,
    environment: str = "ENV",
    b: ArrayLike | None = None,
    edge_names: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Reconcile a tidy flow table ``[edge, value, sigma]`` on the network given by ``edges``.

    Convenience wrapper around :func:`incidence_matrix` and :func:`reconcile`.

    Parameters
    ----------
    flows : pandas.DataFrame
        One row per measured edge with columns ``edge_col``, ``value_col`` and ``sigma_col``.
        Every edge of the network must appear exactly once; extra rows are an error.
    edges : as for :func:`incidence_matrix`
        The network. Edge labels in ``flows[edge_col]`` must match the edge names produced by
        :func:`incidence_matrix` (``"source->target"`` for unnamed pairs, the mapping keys or
        triple names otherwise).
    sigma_col, value_col, edge_col : str
        Column names.
    nodes, environment, edge_names
        Passed to :func:`incidence_matrix`.
    b : array-like, optional
        Constraint constants in node order (default zeros).

    Returns
    -------
    pandas.DataFrame
        Rows in network edge order with columns ``[edge, source, target, value, sigma,
        adjusted, adjustment, standardized_adjustment, redundant]``. Scalar diagnostics
        (``objective``, ``dof``, ``n_constraints``, ``node_names``,
        ``max_constraint_violation``) are stored in ``DataFrame.attrs``.
    """
    if not isinstance(flows, pd.DataFrame):
        raise ValueError("flows must be a pandas DataFrame")
    for col in (edge_col, value_col, sigma_col):
        if col not in flows.columns:
            raise ValueError(f"flows lacks required column {col!r}")

    A, node_names, edge_labels, sources, targets = _incidence(edges, nodes, environment, edge_names)
    labels = flows[edge_col].astype(str).tolist()
    if len(set(labels)) != len(labels):
        dup = sorted({v for v in labels if labels.count(v) > 1})
        raise ValueError(f"flows lists some edges more than once: {dup}")
    missing = [e for e in edge_labels if e not in labels]
    if missing:
        raise ValueError(f"flows is missing edges: {missing}")
    unknown = sorted(set(labels) - set(edge_labels))
    if unknown:
        raise ValueError(f"flows contains edges not in the network: {unknown}")

    ordered = flows.set_index(flows[edge_col].astype(str)).loc[edge_labels]
    y = _as_1d_float(ordered[value_col], value_col)
    sigma = _as_1d_float(ordered[sigma_col], sigma_col)
    res = reconcile(y, A, sigma, b, names=edge_labels, constraint_names=node_names)

    out = pd.DataFrame(
        {
            "edge": edge_labels,
            "source": sources,
            "target": targets,
            "value": y,
            "sigma": sigma,
            "adjusted": res.adjusted,
            "adjustment": res.adjustments,
            "standardized_adjustment": res.standardized_adjustments,
            "redundant": res.redundant,
        }
    )
    out.attrs.update(
        {
            "objective": res.objective,
            "dof": res.dof,
            "n_constraints": res.n_constraints,
            "node_names": list(node_names),
            "max_constraint_violation": res.max_constraint_violation,
        }
    )
    return out


# --------------------------------------------------------------------------------------------
# Unmeasured variables: Crowe's projection
# --------------------------------------------------------------------------------------------


def project_unmeasured(
    A: np.ndarray,
    unmeasured: Sequence[int],
    b: ArrayLike | None = None,
    *,
    rcond: float = DEFAULT_RCOND,
    zero_tol: float = PROJECTION_ZERO_TOL,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Eliminate unmeasured variables from ``A x = b`` with Crowe's projection matrix.

    Partition ``A = [A_m A_u]`` into measured and unmeasured columns. The constraints on the
    measured variables alone are ``P A_m x_m = P b`` where the rows of ``P`` span the left
    null space of ``A_u`` (Crowe, Garcia Campos & Hrymak 1983, *AIChE J.* 29:881; Crowe
    1986, *AIChE J.* 32:616). ``P`` is taken from the full SVD of ``A_u`` (orthonormal rows).
    Constraint combinations that involve only unmeasured variables vanish and are dropped.

    This is the correct meaning of "treat a measurement as unmeasured": simply deleting its
    column while keeping the row would assert that the flow is zero. Observability of the
    eliminated variables is *not* assessed here and their values are not estimated.

    Parameters
    ----------
    A : array-like, shape (m, n)
    unmeasured : sequence of int
        Column indices of ``A`` to eliminate (may be empty).
    b : array-like, shape (m,), optional
        Constraint constants; default zeros.
    rcond : float
        Relative singular-value cutoff when computing ``rank(A_u)``.
    zero_tol : float
        Relative tolerance below which an entry of the projected matrix ``P A_m`` is treated as
        numerical dust and set to zero, and below which a whole projected row counts as
        carrying no measured variable and is dropped (default :data:`PROJECTION_ZERO_TOL`).
        It is scaled by one *global* ``max(1, max|A_m|)``, so ``A`` is assumed to have
        coefficients of comparable magnitude: with a unit-conversion coefficient of, say,
        ``1e-11`` next to coefficients of order 1, rescale that column (and its measurement)
        before calling, or pass a smaller ``zero_tol``.

    Returns
    -------
    A_reduced : numpy.ndarray, shape (k, n - len(unmeasured))
        Projected constraints on the measured variables (``k`` may be zero).
    b_reduced : numpy.ndarray, shape (k,)
    measured : numpy.ndarray of int, shape (n - len(unmeasured),)
        Column indices of ``A`` that remain, in increasing order.

    Raises
    ------
    ValueError
        On invalid indices, or if the projection reveals inconsistent constants (a vanished
        constraint with a non-zero right-hand side).
    """
    A_arr = _as_2d_float(A, "A")
    _require_finite(A_arr, "A")
    m, n = A_arr.shape
    if b is None:
        b_arr = np.zeros(m)
    else:
        b_arr = _as_1d_float(b, "b")
        if b_arr.size != m:
            raise ValueError(f"b has {b_arr.size} entries but A has {m} rows")
        _require_finite(b_arr, "b")
    if not (0.0 <= zero_tol < 1.0):
        raise ValueError("zero_tol must lie in [0, 1)")
    idx = [int(i) for i in unmeasured]
    if any(i < 0 or i >= n for i in idx):
        raise ValueError(f"unmeasured indices must lie in [0, {n}); got {idx}")
    if len(set(idx)) != len(idx):
        raise ValueError(f"unmeasured indices must be unique; got {idx}")
    mask = np.ones(n, dtype=bool)
    mask[idx] = False
    measured = np.flatnonzero(mask)
    A_m = A_arr[:, measured]
    if not idx:
        return A_m, b_arr.copy(), measured

    A_u = A_arr[:, idx]
    U, s, _ = np.linalg.svd(A_u, full_matrices=True)
    rank_u = int(np.sum(s > rcond * s.max())) if s.size and s.max() > 0 else 0
    P = U[:, rank_u:].T  # (m - rank_u, m)
    A_red = P @ A_m
    b_red = P @ b_arr

    scale_A = max(1.0, float(np.max(np.abs(A_m))) if A_m.size else 1.0)
    scale_b = max(1.0, float(np.max(np.abs(b_arr))))
    zero_rows = np.all(np.abs(A_red) <= zero_tol * scale_A, axis=1)
    if np.any(np.abs(b_red[zero_rows]) > CONSISTENCY_TOL * scale_b):
        raise ValueError(
            "constraints are inconsistent after eliminating the unmeasured variables: a "
            "constraint with no measured variable has a non-zero right-hand side"
        )
    A_red = A_red[~zero_rows]
    b_red = b_red[~zero_rows]
    A_red[np.abs(A_red) <= zero_tol * scale_A] = 0.0
    return A_red, b_red, measured
