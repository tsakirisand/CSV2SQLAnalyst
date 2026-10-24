# Verification

Streamlit migration validated locally on 2026-10-18 with Python 3.13.12 and Streamlit 1.66.0.

- `uv run pytest -q`: 28 tests passed (15 engine tests, 5 profiling/cleaning tests, and 8 Streamlit AppTest workflows).
- Streamlit started at http://127.0.0.1:8766; `/_stcore/health` returned `ok`.
- AppTest verified startup has no dataset, metrics, results, or chart, and that the first CSV import populates the workspace. Sample data requires an explicit button click.
- AppTest imported a three-row CSV into a custom table, checked schema/metrics, and grouped Books 30 and Coffee 25.
- AppTest checked chart reruns, axis changes, text-only/empty query results, row-cap notices, invalid queries, invalid/empty imports, sample reset, and separate session workspaces.
- Download payloads: parsed results CSV, checked self-contained Plotly HTML, and executed the deferred SQL export in a separate DuckDB connection.
- Verified five workspace tabs, column exploration, cleaning preview without mutation, apply/restore behavior, original snapshot replacement on a new import, full-dataset CSV, quality-report CSV, and SQL export of cleaned rows.
- Verified numeric fill validation, nullable-integer mean filling, combined cleaning order, empty-result rejection, and missing/distinct column profiles, and disabled apply actions for invalid or all-missing fill previews.

Visual layout and browser download clicks were not verified because no browser automation surface was available. The local launcher uses port 8766.

This verifies a local single-process app. Hosted deployment and public multi-user operation have not been tested.
