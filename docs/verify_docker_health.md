# Subtask 10.1 — local Docker verification (pre-deployment)

This machine has no `gcloud` CLI and no authenticated GCP account/billing
access (see `/docs/BLOCKERS.md`), so the actual `gcloud run deploy` in
`docs/deploy_cloud_run.sh` has not been run. Everything short of that has
been built and verified for real:

## What was verified

1. **`docker build -t exam-scanner-backend:local backend/`** — succeeds
   cleanly (editable install picks up every runtime dependency including
   `pyzbar`/`opencv-python-headless`/`PyMuPDF`; `libzbar0`/`libglib2.0-0`
   installed as apt packages so `pyzbar` doesn't fail at import/decode
   time, not just at pip-install time).
2. **`docker run -p 8081:8080 ... exam-scanner-backend:local`**, pointed at
   the real local Supabase stack via `DATABASE_URL`/`SUPABASE_URL` env
   vars — the container starts and `uvicorn` binds `0.0.0.0:${PORT}`
   (Cloud Run's exact contract).
3. **`GET http://127.0.0.1:8081/health` from the host** (i.e. from outside
   the container, over the mapped port — not `docker exec`) returned
   `200 {"status": "ok"}`.
4. **`GET http://127.0.0.1:8081/quizzes` (no auth) from the host** returned
   `422`, not a routing 404 — confirms the whole FastAPI app (not just the
   trivial `/health` route) is wired up correctly inside the container.
5. **The Phase-9-style smoke test itself** (`backend/scripts/e2e_smoke_test.py`)
   was run against a locally-running instance of this exact application
   (via `uvicorn`, not the Docker container — see below for why) pointed at
   the real local Supabase stack, and passed: health check, disposable-user
   auth, quiz creation, Excel upload, version generation, real PDF
   download+render, and `/scan` all round-tripped over real HTTP and
   finalized with the exact expected score (`3.0/3`).

## Why the smoke test ran against `uvicorn` directly, not the container

Docker Desktop for Windows exposes `host.docker.internal` for
*containers to reach the host*; it does not make that hostname resolvable
*from the host itself* (confirmed: `nslookup host.docker.internal` fails
on this host, and the LAN IP it does resolve to on the container side is
firewalled from host-to-self traffic). Since Supabase Storage's signed
PDF URLs are built from whatever `SUPABASE_URL` the backend process used,
a URL built with `host.docker.internal` inside the container isn't
fetchable by a script running on the host afterward. This is a Windows
Docker Desktop networking artifact specific to this dev machine, not
something that will exist in real Cloud Run (where both the deployed
service and the operator's machine reach the same public HTTPS Supabase
URL). Splitting the verification this way — container correctness
(build/run/route/`$PORT`/`/health`) proven via the container, full
E2E-with-real-scoring correctness proven via the identical application
code running outside the container's networking quirk — covers everything
that's actually meaningful to verify pre-deployment without either gap.

## What's still blocked

Actually deploying (`gcloud run deploy`) and re-running
`e2e_smoke_test.py` with `BACKEND_URL` pointed at the real
`https://*.a.run.app` service URL requires GCP credentials this session
doesn't have. See `/docs/BLOCKERS.md`.
