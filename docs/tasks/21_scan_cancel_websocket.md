# Task 21: Scan Cancellation & WebSocket Endpoint

## Status: COMPLETE ✅

**Deviations from plan:**
- `running_jobs` moved to module level in `worker/main.py` (plan showed it as a local variable inside `worker_loop`).
- Hard cancellation also kills active nmap subprocesses via `kill_job_scanners()` in `worker/pipeline.py` — each tier registers/deregisters its `PortScanner` instance and we call `nm._nm_proc.kill()` on cancel. The plan did not cover this.
- WebSocket endpoint was already implemented in Task 14 (DB-poll approach). The pub/sub approach from this task doc was not used.

**Depends on:** Task 11, Task 14  
**Complexity:** Medium  
**Description:** Implement scan job cancellation (via asyncio task cancellation) and the WebSocket endpoint that streams live scan progress events to the browser.

---

## Files to Modify / Create

- `scans/router.py` — add cancel endpoint + WebSocket endpoint
- `worker/main.py` — expose running task registry
- `worker/progress.py` — already created in Task 14

---

## `worker/main.py` additions

Expose the running jobs dict so the cancel endpoint can reach it:

```python
# At module level (add to existing worker/main.py)
running_jobs: dict[int, asyncio.Task] = {}

async def worker_loop():
    logger.info("Scan worker started")
    while True:
        job_id = await job_queue.get()
        if job_id is None:
            break
        task = asyncio.create_task(run_job(job_id))
        running_jobs[job_id] = task
        task.add_done_callback(lambda t, jid=job_id: running_jobs.pop(jid, None))
```

---

## `scans/router.py` — Cancel Endpoint

```python
from worker.main import running_jobs

@router.post("/{job_id}/cancel", status_code=200)
async def cancel_scan(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_operator)
):
    job = await db.get(ScanJob, job_id)
    if not job:
        raise HTTPException(404, "Scan job not found")
    if job.status not in ("queued", "running"):
        raise HTTPException(400, f"Cannot cancel a job with status '{job.status}'")

    # Cancel the asyncio task if running
    task = running_jobs.get(job_id)
    if task and not task.done():
        task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=3.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

    # If still queued (not yet picked up by worker), mark directly
    job.status = "cancelled"
    job.finished_at = datetime.now(timezone.utc)
    await db.commit()

    return {"status": "cancelled", "job_id": job_id}
```

---

## `scans/router.py` — WebSocket Endpoint

```python
from fastapi import WebSocket, WebSocketDisconnect
from worker.progress import subscribe, unsubscribe
import asyncio, json

@router.websocket("/ws/{job_id}")
async def scan_progress_ws(websocket: WebSocket, job_id: int):
    """
    Stream live scan progress events for a given job.
    Client connects, receives events as JSON, connection closes when job finishes.
    """
    await websocket.accept()
    q = subscribe(job_id)
    try:
        # Check if job already finished before client connected
        async with AsyncSessionLocal() as db:
            job = await db.get(ScanJob, job_id)
            if not job:
                await websocket.send_json({"type": "error", "message": "Job not found"})
                return
            if job.status in ("completed", "failed", "cancelled"):
                await websocket.send_json({
                    "type": "job_done",
                    "job_id": job_id,
                    "status": job.status
                })
                return

        # Stream events
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=30.0)
                await websocket.send_json(event)
                if event.get("type") == "job_done":
                    break
            except asyncio.TimeoutError:
                # Send keepalive ping
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        unsubscribe(job_id, q)
        try:
            await websocket.close()
        except Exception:
            pass
```

---

## WebSocket Registration in `api/main.py`

The WebSocket route must be registered on the **app** directly (not under an APIRouter prefix), or the router prefix must be `/ws`:

```python
# Option A: Register the scans router with a /ws prefix for WS routes
# The router already has prefix="/api/scans", so the WS path becomes:
# ws://host/api/scans/ws/{job_id}

# Option B: Separate WS router
from fastapi import APIRouter as WSRouter
ws_router = WSRouter()

@ws_router.websocket("/ws/scans/{job_id}")
async def scan_ws_proxy(websocket: WebSocket, job_id: int):
    # delegate to the same handler
    from scans.router import scan_progress_ws
    await scan_progress_ws(websocket, job_id)

app.include_router(ws_router)
```

> **Recommended:** Use Option A. The frontend connects to `ws://host/api/scans/ws/{job_id}`.  
> Update `ScanProgressModal.jsx` accordingly:
> ```js
> const ws = new WebSocket(`ws://${location.host}/api/scans/ws/${jobId}`)
> ```

---

## Frontend `ScanProgressModal.jsx` Update

Update the WebSocket URL in `src/components/ScanProgressModal.jsx`:

```js
// Replace:
const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/scans/${jobId}`)
// With:
const proto = location.protocol === 'https:' ? 'wss' : 'ws'
const ws = new WebSocket(`${proto}://${location.host}/api/scans/ws/${jobId}`)
```

---

## Testing

```bash
# Trigger a scan
curl -X POST http://localhost/api/scans/ \
  -H "Content-Type: application/json" \
  -b "access_token=<jwt>" \
  -d '{"subnet_id": 1, "profile_id": 1}'

# Connect to WebSocket (using websocat)
websocat "ws://localhost/api/scans/ws/1"

# Cancel the scan
curl -X POST http://localhost/api/scans/1/cancel \
  -b "access_token=<jwt>"
```
