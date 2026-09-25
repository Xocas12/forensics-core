# workorders

The issues are card summaries; the cards themselves live in this
directory, in the tree, so a session can read one without network access, and so the
ambiguity route is a form rather than a suggestion.

The numbering ranges are fixed so areas cannot collide:

```
WO-000 to WO-099   programme spine and cross-cutting infrastructure   (root)
WO-100 to WO-199   shared method library                             packages/forensics_core
WO-200 to WO-299   elections                                         projects/elections
WO-300 to WO-399   aaer                                              projects/aaer
WO-400 to WO-499   china                                             projects/china
WO-500 to WO-599   gosplan                                           projects/gosplan
```

Cards WO-200 to WO-599 were filed as issues on the former `forensic-elections` and
`forensic-economy` repositories before they were merged into this one. Their paths
(`projects/...`, `packages/forensics_core/...`) are unchanged by the merge. Paths in the
library cards (WO-000 to WO-199) that begin `src/`, `tests/` or `docs/` are relative to
`packages/forensics_core/`, with one exception: `docs/PREREGISTRATION.md` (WO-003) is
programme-wide and lives in the root `docs/`, which is where the project cards look for it.

One card, one issue, one branch, one pull request. The issue body is the card.
