# Vercel deployment

Production: https://clavius-space.vercel.app

Project `clavius` belongs to `aayushmw-3928s-projects` on the Hobby plan.
The connected repository is `aayush-mehrotra29/clavius`; `main` deploys to
production. Changes must be tested as a preview before promotion.

## Services and scientific inputs

`vercel.json` defines the Vite frontend and Python FastAPI simulation as two
services in the same deployment. `/api/*` reaches the actual Python API;
the other paths reach the frontend. Frontend `/app` deep links resolve to
`index.html`; missing assets retain their 404 responses.

The API uses Python 3.13 and Vercel's large-functions beta. The project sets
`VERCEL_SUPPORT_LARGE_FUNCTIONS=1`. The build runs
`scripts/setup_hosted_simulation.py`, which downloads the original terrain,
SPICE and Diviner inputs and checks every source hash before packaging.
It prepares site manifests, preserving the nominal origins and clone
registration checks. It keeps the existing public display derivatives and
site-specific historical Diviner clips unchanged. No NASA input is replaced
with synthetic terrain or reduced-resolution physical geometry.

The API explicitly includes its scientific input files, robot package,
contracts and public reference records in its function bundle. Vercel normally
separates public assets from Python functions; serving those assets from the
frontend does not make them readable by backend code.

## Durable state and execution

The private `clavius-simulation-state` Vercel Blob store is connected to this
project. Its credentials stay in Vercel-managed environment variables. The
Python SDK reads them server-side; never prefix them with `VITE_` or commit
them. Metadata records use unique immutable version paths so reading a just
completed job does not receive an older cached representation. Uploaded robot
packages, content-addressed artifacts and source snapshots persist privately
and restore into an instance's disposable `/tmp` runtime when needed.

Hosted numerical work finishes inside the creating HTTP request. Returning
first and leaving the existing thread pool running would allow Vercel to freeze
the job. The UI shows a calculating state while it waits. Completed jobs retain
the same result, replay and export contracts as local runs. Intermediate
progress remains request-local to reduce storage operations; terminal state
and evidence are written before returning. Cross-instance cancellation uses a
separate durable cancellation marker. Local launches keep their existing
asynchronous thread pool and SQLite storage.

A hosted calculation has a cooperative 270-second computation budget inside
Vercel's 300-second request maximum. Very long searches or simulations must be
reduced or run locally. Interrupted jobs have a stored deadline and are marked
failed when inspected or before accepting more work; they do not become
accepted completed results. A hard platform termination cannot guarantee a
partial evidence checkpoint. Uploads and buffered exports also inherit Vercel's
4.5 MB request/response limit; local robot imports retain their 30 MB limit.

## Engines and limits

Hosted native dynamics uses the deployed Linux MuJoCo library and records its
own implementation and library identities. It is distinct from MuJoCo on the
Mac and Gazebo Harmonic / DART in the local Colima VM. No Gazebo worker or
matching runtime benchmark is configured for the hosted service, so that engine
remains unavailable there. Recorded Chrono VIPER replays remain recorded rigid
contact evidence, separate from active hypothetical R1 mission assessments.

All existing scientific limits remain: declared hardware/power assumptions,
unresolved rover-scale hazards and regolith calibration, historical Diviner
context, and retained failed validation gates. Deployment does not establish
flight hardware support or lunar predictive accuracy.

The free plan has compute and storage quotas. Private Blob's included allowance
is 1 GB, 2,000 advanced operations and 10,000 simple operations per month;
exceeding an allowance can pause access. This deployment does not enable a paid
plan. Run history is shared by the public demo's API, as in the existing app;
private Blob protects the backing store, not per-user access to API records.

## Deployment and verification

Use an isolated checkout and authenticate with `vercel login`. Link it with
`vercel link --yes --project clavius --scope aayushmw-3928s-projects`.
Create a preview with `vercel deploy`, verify health, both sites, a real flight,
a rover traverse, saved-result reopening and evidence export, then promote the
verified deployment. Check that the production alias returns the Python health
JSON and that a fresh browser can complete the same workflow.

`.vercelignore` keeps local raw caches, kernels, credentials, native worker
runtimes and transient work out of CLI uploads. The scientific build downloads
are separate from those uploads. `.vercel/` and environment files stay ignored.
