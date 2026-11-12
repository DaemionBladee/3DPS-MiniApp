
M06 adds a separately launched trusted analysis controller. Keep it outside the API
container; see [worker operations](../docs/WORKER_OPERATIONS.md) for image approval,
private staging, simulation execution and recovery. The pure profile definition is shared with the worker at image build time; API
startup requires no worker package or geometry imports. To include **real**
sandbox tests, build `worker/Dockerfile` and set `M06_TEST_WORKER_IMAGE` to its exact
`sha256:` image ID. Without that variable, those tests explicitly skip.
