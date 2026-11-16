# Vercel deployment

The Vite frontend deploys to Vercel's Hobby plan with a free `vercel.app`
address. Vercel uses `npm ci`, `npm run build` and the `dist` output directory.
`vercel.json` serves `/app` and its nested routes through `index.html` while
missing assets retain their normal 404 responses.

## Hosted features

The landing page, lunar atlas, VIPER manual visualization and packaged native
Chrono replays run from the frontend's existing public assets. The dataset
manifests, source hashes and distinctions between visualization, recorded
replays and predictive hardware support remain unchanged.

There is no hosted simulation backend yet. `/api/*` returns HTTP 503 with an
explicit JSON explanation. New flight calculations, landing comparisons,
mission assessments, live sunlight calculations, robot imports and saved
simulation runs require the separate Python service. Packaged replay sunlight
remains recorded context, not a live forecast.

The current backend depends on native Python libraries, NASA input caches,
SQLite/filesystem persistence and a background thread pool. Its existing
architecture must run on a separate persistent service; uploading it as a
Vercel function does not provide those requirements. Gazebo additionally
requires its configured Linux worker and matching runtime benchmark.

## Deploy

Authenticate using `vercel login`, then link this repository to the intended
project with `vercel link --yes --project <project> --scope <team>`.
Run `vercel deploy --prod` for a production release. Use a clean checkout of
the intended commit so unfinished local work is not included. Git integration
can deploy future pushes to the production branch automatically.

`.vercelignore` allows only the frontend, public assets, the unavailable-backend
handler and web build configuration in CLI uploads. Raw caches, Python/native
runtimes, credentials and transient simulation work stay local. `.vercel/`
is ignored by Git.

## Connecting a backend later

Provision and validate the Python service with its pinned input data and
persistent runtime storage. Before exposing uploads and computation publicly,
add suitable authentication, request limits and job isolation. Replace the
`/api/:path*` rewrite with the trusted backend's HTTPS URL, preserving the
`/api/` path, for example `https://<backend-host>/api/:path*`. Remove the
unavailable-backend handler once the real service is connected. Same-origin
rewrites let the browser retain its existing API URLs.

Verify health, flight/landing jobs, saved runs, imports and applicable native
engine identities on that service before describing those hosted features as
operational. The local Vite development proxy continues to use the local
Python backend independently of these deployment routes.
