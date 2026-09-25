"""Analysis entry points for the gosplan project. **Every function here is a stub.**

Nothing in this package computes anything yet, and that is deliberate rather than unfinished.
Two reasons, in order of importance.

**There is no validated input.** The series these tests need do not exist in machine-readable
form. They have to be transcribed from printed pages, and until a table has passed
:mod:`gosplan.transcribe.validate` and had its transcription error rate measured by
:mod:`gosplan.transcribe.compare`, any number computed from it would be measuring the typing.
``docs/known_traps.md`` trap 9 is explicit: a digit test on a badly transcribed table detects
the transcription.

**There is one anchor.** The Uzbek cotton affair is the project's only labelled event, so a
detector fitted here is validated on the same event it was fitted to. Calibration has to come
from the three projects that have ground truth -- ``elections``, ``aaer`` and ``china`` -- and
arrive through :func:`forensics_core.eval.harness.transfer`. That is what
:mod:`gosplan.analysis.transfer` is for, and it is the reason the other four modules produce
*rankings and bounds* rather than probabilities.

The five modules map onto the five sub-questions in ``docs/research_question.md``:

=================================== ==========================================================
:mod:`~gosplan.analysis.plan_fulfilment`     bunching at the 100 percent bonus threshold
:mod:`~gosplan.analysis.hidden_inflation`    value series against the physical series beneath
:mod:`~gosplan.analysis.io_reconciliation`   accounting identities and where they fail
:mod:`~gosplan.analysis.harvest_dispersion`  reported series smoother than nature permits
:mod:`~gosplan.analysis.transfer`            detectors calibrated elsewhere, applied here
=================================== ==========================================================

Each signature is fixed so that callers, tests and notebooks can be written against it now.
Each docstring cites the method's source and states what remains to be done. Filling one in
is a piece of work that starts with data, not with code.
"""
