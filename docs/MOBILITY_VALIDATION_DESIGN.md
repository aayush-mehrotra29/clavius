# Mobility evidence dialog

Direct build uses the existing Clavius simulation design system. Refero style and screen searches on 15 November returned `NO_SUBSCRIPTION`, matching earlier checks. The existing product, the locked source/uncertainty dialogs and the bundled focus/forms guidance are the references for this bounded extension.

| Decision | Reference | Purpose |
| --- | --- | --- |
| Enter from Data & models, beside dynamics scope | Existing source and illumination evidence sections | Put physical validity beside the model it qualifies |
| Use the current dialog, Inter and numerical monospace, thin borders | Existing Clavius dialog and comparison table | Preserve hierarchy, keyboard behavior and narrow-screen scrolling |
| State that soil calibration is unresolved before the plot | User's accuracy priority and retained source-coverage rules | Prevent analytical engine checks from implying measured soil agreement |
| Keep a standard scientific plot, complete data table and source download | Existing published illumination evidence workflow | Let users inspect the discrepancies and reproduce the comparison |
| Show controls, time-step checks and physical agreement as separate fields | Numerical benchmark protocol | Avoid merging solver success with agreement to experiment |
| Preserve all published repeats and small negative points | Original author arrays | Do not hide measurement spread or replace values with zero |

The dialog must fit the existing desktop and 390 px mobile viewports, retain a readable table through its own horizontal scroller, and expose all report/download links. It does not alter rover mechanics, missions, engine selection or the landing page.

The CPU SCM extension uses the same locked dialog, metrics, chart, native details disclosure and table scroller. Its first comparison uses eight held-out observations against the rigid baseline on exactly those eight coordinates; it does not compare an eight-point score against the old eighteen-point score. Hollow/filled scientific markers preserve the training/holdout distinction. Separate time/grid rows expose failed numerical checks. The original rigid report remains visible below. An unavailable or hash-mismatched SCM report is stated explicitly. This is evidence review, with no new engine selector or implied mission activation.
