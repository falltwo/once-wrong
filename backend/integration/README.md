# Frontend PR #1 integration handoff

These assets connect the existing frontend to the backend without copying the frontend into this backend PR or merging its branch. Target frontend commit: `8e2e787d8e892aa1c263f7b0f9a36d91bd6a4a8f` from [Draft PR #1](https://github.com/falltwo/once-wrong/pull/1).

## Apply in a separate frontend working copy

From PowerShell, adjust the two paths to your checkouts. Use a fresh disposable frontend copy so the original frontend author's work remains intact.

```powershell
$backendRepo = 'C:\work\once-wrong-backend'
$frontendCopy = 'C:\work\once-wrong-frontend'
git clone https://github.com/falltwo/once-wrong.git $frontendCopy
git -C $frontendCopy fetch origin refs/pull/1/head
git -C $frontendCopy switch --detach 8e2e787d8e892aa1c263f7b0f9a36d91bd6a4a8f

Copy-Item -LiteralPath "$backendRepo\backend\integration\reports.ts" -Destination "$frontendCopy\frontend\src\api\reports.ts"
git -C $frontendCopy apply --check "$backendRepo\backend\integration\frontend-pr1.patch"
git -C $frontendCopy apply "$backendRepo\backend\integration\frontend-pr1.patch"
```

Copy the adapter first, then apply the patch. The patch targets only types, workspace and report counts, suggestion rendering, status labels, and exported report metadata. It leaves the existing demo fixtures unchanged and makes no dependency or package-lock changes. If PR #1 changes, inspect any patch failure and rebase the handoff deliberately; do not force-apply it.

## Start the backend and frontend

Install the backend following [the backend README](../README.md). From the backend repository root, start the service. A separate smoke-test database is useful when you do not want browser checks to append versions to your usual demo database.

```powershell
$env:ONCE_WRONG_DB = "$backendRepo\backend\data\frontend-smoke.sqlite3"
$env:ONCE_WRONG_SEED_DEMO = 'true'
& "$backendRepo\backend\.venv\Scripts\python.exe" -m uvicorn once_wrong.main:app --app-dir "$backendRepo\backend" --host 127.0.0.1 --port 8000
```

In another PowerShell terminal:

```powershell
Set-Location -LiteralPath "$frontendCopy\frontend"
npm ci
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8000'
npm run build
npm run dev -- --port 5173 --strictPort
```

The adapter defaults to `http://127.0.0.1:8000`; `VITE_API_BASE_URL` overrides it. Vite reads this value at startup/build time. Restart or rebuild after changing it. The backend permits `http://127.0.0.1:5173` and `http://localhost:5173` by default. For a different frontend origin, set `ONCE_WRONG_ALLOWED_ORIGINS` to a comma-separated list before starting the backend.

Open `http://127.0.0.1:5173/reports`. Backend responses are the only data source. A stopped/unreachable backend produces a visible error; the adapter does not silently use localStorage or mock results.

## HTTP contract used by the adapter

| Method and path | Request | Response |
| --- | --- | --- |
| `GET /reports` | None | `200 Report[]` |
| `GET /reports/{reportId}` | URL-encoded report ID | `200 Report`, ascending versions |
| `POST /reports/{reportId}/versions` | `multipart/form-data`, field `file` | `201 Version`, synchronously parsed and checked |
| `GET /versions/{versionId}/issues/{issueId}/suggestion` | URL-encoded stored IDs | `200 Suggestion` |
| `POST /reports/{reportId}/submissions` | JSON `{ "versionId": "..." }` | `204`, internal confirmation only |

`Version` keeps the original `id`, `number`, `filename`, `createdAt`, `rows`, and `issues` fields. Backend responses also contain `schemaProfileId`, `ruleVersion`, `validationStatus: "completed"`, `validationRunId`, `sourceSha256`, and `summary: { totalChecks, passedChecks, failedChecks, notEvaluatedChecks }`. `Report.canSubmit` is the server's eligibility decision. The UI additionally ensures the selected version is the latest completed version and has not already been confirmed.

The additive TypeScript metadata fields are optional solely to allow the original, unused frontend mock module to type-check. The HTTP backend always returns them. Missing summaries display `—`; missing eligibility/status keeps confirmation disabled. Counts are never fabricated from the number of rows.

The adapter's existing function names remain `list`, `get`, `upload`, `suggestion`, `submit`, and `download`. The only argument change is `suggestion(issue, versionId)`, allowing the backend to look up the stored issue instead of trusting client-supplied `actual`/`expected` data. HTTP errors become `Error.message` values understood by the existing frontend error views; an empty successful `204` is handled without attempting JSON parsing.

Suggestion responses currently have `source: "demo"`, `verification: "unavailable"`, and no `value`. The UI labels the explanation as a fixed template rather than AI, and shows a verified value only when both `verification === "passed"` and a numeric value exist. No actual AI or candidate-revalidation pipeline is implemented. Confirmation is a backend record and never submits to an insurer or regulator.

## Manual acceptance flow

1. View the seeded `reserve-202609` report and its two original versions.
2. Upload [`sample-errors.csv`](../tests/fixtures/sample-errors.csv). Inspect `POL-003 / R-07` and `POL-004 / R-01` and the fixed explanation. No verified-candidate badge should appear.
3. Upload the same errors fixture again. Both findings should now be marked as repeated. The repeated-error filter should show two rows.
4. Upload [`sample-fixed.csv`](../tests/fixtures/sample-fixed.csv). The backend summary should show 12 passed checks, zero failures, and eligibility for internal confirmation.
5. Record internal confirmation. The response is `204`, the latest version is shown as confirmed, and the button is disabled.
6. Download the JSON report. It includes the source SHA-256, validation run ID, schema/rule versions, backend summary, and internal confirmation flag.
7. Select an older error version and reload. The URL restores it, history remains available, and confirmation stays disabled for the older version.
8. Restart the backend with the same database path. Uploaded versions and confirmation remain. Stop the backend and reload to check the explicit connection error rather than a mock fallback.

The two checks are team demonstration rules: product must be nonempty; opening must equal previous in the uploaded row. Both monetary columns come from the same CSV. This does not reconcile against a trusted prior-period source or establish official insurance-report correctness. Only UTF-8 CSV matching `demo_csv_v1` is supported; direct Excel parsing, actual AI, background jobs, accounts, external submission, and real benchmark results are outside this handoff.

## Optional automated browser smoke

`smoke.mjs` uses Playwright to exercise the same integration: report list, upload, server results, repeated errors, unavailable suggestions, corrected upload, internal confirmation, report download, historical version selection, and reload. It also checks that original versions remain unchanged and that no browser page errors occur.

Use an existing Playwright installation and Chromium browser. The script does not install either. Set `PLAYWRIGHT_MODULE` to the absolute Playwright package directory if it is not on Node's normal module search path; optionally set `BROWSER_PATH` to an existing Chromium/Chrome executable. The app and API must already be running.

```powershell
# Optional environment-specific paths:
# $env:PLAYWRIGHT_MODULE = 'C:\path\to\node_modules\playwright'
# $env:BROWSER_PATH = 'C:\path\to\chrome.exe'
$env:SMOKE_APP_URL = 'http://127.0.0.1:5173'
$env:SMOKE_API_BASE_URL = 'http://127.0.0.1:8000'
node "$backendRepo\backend\integration\smoke.mjs"
```

Each run appends **three synthetic versions** and records one internal confirmation. It preserves existing data. Screenshots and the downloaded JSON are written to the ignored `backend/integration/.smoke-artifacts/` directory, or to `SMOKE_ARTIFACT_DIR` if set. This script does not reset the database, merge either PR, or publish anything.
