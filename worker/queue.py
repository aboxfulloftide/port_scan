import asyncio

# Shared asyncio queue between API trigger and worker loop (same process)
job_queue: asyncio.Queue = asyncio.Queue()
