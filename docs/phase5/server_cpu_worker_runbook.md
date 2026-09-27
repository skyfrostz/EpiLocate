# Phase 5 Server CPU Worker startup contract

This is a deployment preparation record, not an ECS deployment. The existing `worker` package remains the only inference implementation. Backend v2, PostgreSQL, private MinIO, an HTTPS Worker API origin, and one independently running sweeper are prerequisites.

## Provision and start

1. Verify the FrozenBaseline checkpoint SHA-256 is `548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734`. Mount the frozen root read-only. Keep Worker data in a separate writable private directory.
2. With the Backend database configured, run `python -m backend_v2.workers.provision` as described in [Backend v2 README](../../backend_v2/README.md). Use the Worker-reachable **HTTPS** Backend origin and private absolute output path. The generated mode-0600 environment file contains `WORKER_ID`, `TOKEN`, `BACKEND_URL`, `MODEL_VERSION`, `MODEL_HASH`, `EPILOCATE_FROZEN_ROOT`, and `WORKER_DATA_ROOT`.
3. Install the repository and FrozenBaseline dependencies in the selected Python environment. Run the independent process with:

   ```sh
   deploy/run_server_cpu_worker.sh /private/path/worker.env /path/to/python
   ```

   The launcher sets `WORKER_DEVICE=CPU` and executes `python -m worker`. For a private test CA, set `WORKER_CA_CERT=/path/to/ca.pem` in the process environment. On a production certificate chain, leave it unset. Use the service manager to restart on failure and preserve stdout/stderr in restricted logs. Do not put credentials in process arguments, Frontend files, or access logs.
4. Run `python -m backend_v2.workers.sweeper` as a separate process. It moves CREATED jobs to QUEUED and recovers expired leases. Keep only one sweeper and initially one CPU Worker process until the target host is measured.

The Worker registers, heartbeats, claims with capacity one, downloads a signed private DICOM object, verifies its hash, runs FrozenBaseline, and submits the existing result/asset protocol. Its CPU device selection does not remove the unchanged `CUDA` or `AUTO` options for a future AI Node. No Backend request process runs inference.

## Observed local behavior and release gate

The Stage 2 [E2E report](stage2_cpu_worker_e2e_report.md) records the macOS ARM CPU run, model hash, two-user queue, 90-second lease expiration, retry, and failure result. These timings do **not** establish ECS capacity. Before deploying, the owner must approve an ECS read-only resource audit, then review CPU, memory, task duration, disk, backups, TLS routing, process supervision, and rollback separately. The local HTTPS QA proxy in `qa/phase5_local_https.py` is loopback-only and not a production reverse proxy.
