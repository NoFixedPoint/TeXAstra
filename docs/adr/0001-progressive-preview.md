# Update the visible page before full-document convergence

The live preview may update the visible page before off-screen pages and cross-references converge. The user accepted this trade-off so the ordinary-edit latency target of under 150 ms at the 95th percentile can focus on immediate editing feedback in a 100-page document rather than waiting for every downstream consequence.

Provisional results must be indicated, and full-document convergence is measured separately. Invalid input retains a visibly stale last-successful preview; navigation from stale output is disabled unless its correspondence to the current source has been validated. This decision permits progressive output but does not establish that an edit has only local effects or select an incremental compiler architecture.
