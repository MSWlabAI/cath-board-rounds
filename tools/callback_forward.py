#!/usr/bin/env python3
"""Forward 127.0.0.1:8081 -> the Switch server's collaboration callback listener.
Console-run servers bind that listener to a random loopback port, while the Mattermost
connection's Callback Base URL is fixed at connect time. Re-resolves the port per connection."""
import asyncio, re, subprocess
def target_port():
    for pid in subprocess.run(["pgrep", "-f", "switch_core.main"], capture_output=True, text=True).stdout.split():
        m = re.search(r"COLLABORATION_CALLBACK_PORT=(\d+)", subprocess.run(["ps", "eww", "-p", pid], capture_output=True, text=True).stdout)
        if m: return int(m.group(1))
async def pipe(r, w):
    try:
        while (b := await r.read(65536)): w.write(b); await w.drain()
    finally: w.close()
async def handle(r, w):
    p = target_port()
    if not p: w.close(); return
    try: ur, uw = await asyncio.open_connection("127.0.0.1", p)
    except OSError: w.close(); return
    await asyncio.gather(pipe(r, uw), pipe(ur, w))
async def main():
    s = await asyncio.start_server(handle, "127.0.0.1", 8081)
    async with s: await s.serve_forever()
asyncio.run(main())
