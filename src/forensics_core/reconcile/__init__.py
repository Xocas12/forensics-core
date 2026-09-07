"""Data reconciliation and gross-error detection, lifted from chemical process engineering
(Narasimhan & Jordache 2000; Crowe 1996). Reported flows on a graph must satisfy conservation
constraints A x = b; the minimum-variance perturbation restoring feasibility is the
reconciled estimate, and measurements needing large adjustments are gross-error suspects."""

from __future__ import annotations

from forensics_core.reconcile.balance import (
    CONSISTENCY_TOL,
    DEFAULT_RCOND,
    PROJECTION_ZERO_TOL,
    REDUNDANCY_TOL,
    ReconciliationResult,
    incidence_matrix,
    project_unmeasured,
    reconcile,
    reconcile_table,
)
from forensics_core.reconcile.gross_error import (
    EMPTY_ROW_TOL,
    NODAL_VARIANCE_TOL,
    Correction,
    Elimination,
    GrossErrorSuspect,
    critical_z,
    global_test,
    measurement_test,
    nodal_test,
    serial_elimination,
)

__all__ = [
    "CONSISTENCY_TOL",
    "DEFAULT_RCOND",
    "EMPTY_ROW_TOL",
    "NODAL_VARIANCE_TOL",
    "PROJECTION_ZERO_TOL",
    "REDUNDANCY_TOL",
    "Correction",
    "Elimination",
    "GrossErrorSuspect",
    "ReconciliationResult",
    "critical_z",
    "global_test",
    "incidence_matrix",
    "measurement_test",
    "nodal_test",
    "project_unmeasured",
    "reconcile",
    "reconcile_table",
    "serial_elimination",
]
