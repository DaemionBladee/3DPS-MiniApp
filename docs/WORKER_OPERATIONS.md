# M06 isolated worker operations and recovery

Status: simulation only. The API never starts a worker automatically. Run the
trusted orchestrator on a dedicated Linux test host with private PostgreSQL,
private model storage and access to a local Docker daemon. The API container
has no Docker socket. Never mount that socket, the database, a bot token, session
secrets or the whole model store into the slicer container.

## Build and explicitly approve a simulation profile revision

From the repository root (Python dependencies installed in `backend/.venv`):

```sh
docker build -f worker/Dockerfile -t 3dps-slicer:m06 .
M06_IMAGE=$(docker image inspect --format '{{.Id}}' 3dps-slicer:m06)
cd backend
export PYTHONPATH=.
# Supply trusted server settings through the private environment, as for FastAPI.
.venv/bin/alembic upgrade head
.venv/bin/python scripts/process_tasks.py --seed-image "$M06_IMAGE" --profile-revision 1
.venv/bin/python scripts/process_tasks.py --once --staging-root .local/analysis_jobs
# Omit --once for a foreground polling loop; SIGINT/SIGTERM stops between jobs.
```

Approval is an explicit administrative CLI action. There is no public profile
editor or worker command endpoint. Use an immutable local `sha256:` image ID;
job execution never pulls mutable tags. Rebuilding code or changing dependencies
requires a new approved profile revision. Keep images referenced by retained
runs. Do not delete existing profile/history records to reuse a revision number.

Managed Cloud: use the configured local Docker socket and inherited network
proxy/CA for **builds only**. With a session CA, append
`--secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt` to the build. The
controller clears Docker host/context/TLS overrides and selects
`unix:///var/run/docker.sock`. Runtime workers have `--network=none`; their
entrypoint clears all inherited environment variables before Python starts.

## Enforced boundary and budgets

- Nonroot UID/GID 10001; read-only image and single input directory; all Linux
  capabilities dropped; no-new-privileges; Docker default seccomp required.
- Only `/input/model.bin` and a bounded secret-free JSON manifest cross the
  boundary. Customer filenames, descriptions, special-requirement text, bot and
  database configuration do not cross it. The worker repeats structural checks
  and checksum verification. Normalized geometry goes to the native CLI; raw
  3MF settings never reach PrusaSlicer.
- Hard POSIX limits, applied before parsing and inherited by native children:
  768 MiB address space **per process**, 60 CPU seconds **per process**, 32
  processes per UID, 64 open descriptors, 64 MiB per file, no core files.
- Writable scratch: `/work` 128 MiB tmpfs and `/tmp` 32 MiB tmpfs; noexec,
  nosuid, nodev. No writable host output mount. Container has no printer network.
- Worker alarm 85 seconds; trusted execution wall limit 90 seconds; each native
  command also has a bounded timeout. Output JSON is at most 32 KiB. Native logs
  remain in bounded scratch, are rejected above 1 MiB, and are never returned;
  per-file limits bound writes before that final validation. Docker logs rotate
  at 128 KiB. G-code must be complete and at most 64 MiB; record hashes then
  discard it with the container. There is no G-code download endpoint.
- Docker is also requested to enforce 768 MiB memory/no extra swap, one CPU and
  32 PIDs. **Cloud's rootless daemon exposed its parent cgroup limits rather
  than these requested limits. Aggregate cgroup enforcement is unverified here.**
  Real tests verify POSIX memory/CPU/process limits and tmpfs exhaustion. These
  are not evidence of an aggregate container RAM/CPU ceiling. Verify cgroup
  delegation and actual aggregate resource attacks on the intended worker host
  before public execution. A dedicated VM/microVM boundary remains preferable
  for hostile public workloads; M06 does not deploy one.

The worker checks UID, capabilities, seccomp, no-new-privileges, read-only mounts,
network device isolation and scratch size before processing. Failing a check
returns an error; there is no host slicing fallback. Probe modes are image CLI
checks, unavailable through HTTP. Actual sandbox tests need an explicitly built
`M06_TEST_WORKER_IMAGE`; omitted-image skips must not be reported as passing.

## Claims, retries and recovery

`pending -> leased -> succeeded/failed`, with `superseded` invalidation. A short
PostgreSQL advisory lock enforces at most two unexpired leases per database;
request/task row locks and `SKIP LOCKED` avoid duplicate claims. Each claim gets a
new UUID fence and a 180-second lease. Claiming alone leaves the request submitted.
Only after Docker confirms actual container startup does the request enter
`analyzing`. Uncalibrated completed work finishes at `manual_review`; M06 never
advances to quotation eligibility.

Timeout, crash, engine availability and publication failures retry with 10/20
second exponential backoff, capped at 300 seconds. A task has three automatic
attempts. Deterministic geometry, unsafe profile, missing input and output
verification failures do not automatically retry. The Owner may reason about and
idempotently reschedule current terminal simulation work, choose only a compatible
approved profile, and extend the budget one attempt at a time up to six total.
Repeated clicks cannot extend it twice. Active or superseded work cannot be retried.

Before start and publication, recheck lease expiry/token, exact request revision,
specification hash, file status/current item relationship, checksum and profile
provenance. SQL triggers independently fence result insertion/completion and freeze
result/task provenance. Publication atomically inserts analysis/run, updates the
current result pointer and task/request, and writes **system-attributed** immutable
audit plus notification-outbox records. A DB failure rolls everything back; an
expired worker cannot publish later. Outbox delivery remains a later milestone.

Recovery scans expired leases in bounded batches; repeated scans are idempotent.
Each polling loop removes only named/labeled M06 containers and matching staging
directories older than five minutes (longer than any valid lease/wall budget).
It never scans/deletes ready private uploads. A normal error/timeout removes the
container and staged copy in `finally`. A host crash can leave private staged
copies until the next loop; retain disk monitoring and run the controller after
restart. Stop containers before retiring a host. Unexpected controller/database
errors exit visibly for the supervisor to restart; no errors count as success.

## Test commands

```sh
# Disposable loopback PostgreSQL only, database name beginning 3dps_test.
export TEST_DATABASE_URL='postgresql+asyncpg://TEST_USER:TEST_PASSWORD@127.0.0.1:TEST_PORT/3dps_test_analysis'
export M06_TEST_WORKER_IMAGE="$M06_IMAGE"
.venv/bin/pytest -q
.venv/bin/ruff check app alembic tests scripts ../worker ../telegram_bot
.venv/bin/mypy app scripts ../worker ../telegram_bot
DATABASE_URL="$TEST_DATABASE_URL" .venv/bin/alembic check
PYTHONPATH=. .venv/bin/python scripts/export_openapi.py
npm --prefix ../tools/api-types run generate
```

See `M06_IMPLEMENTATION_REPORT.md` for actual Cloud results and external checks.
