import asyncio, json, websockets

URL = "ws://localhost:8000/ws"
HZ = 30

def axes(throttle=0, yaw=0, pitch=0, roll=0):
    return json.dumps({"type": "axes", "mode": "abs",
                       "throttle": throttle, "yaw": yaw,
                       "pitch": pitch, "roll": roll})

async def hold(ws, secs, **kw):
    msg = axes(**kw)
    for _ in range(int(secs * HZ)):
        await ws.send(msg)
        await asyncio.sleep(1 / HZ)

async def main():
    async with websockets.connect(URL) as ws:
        try:
            await hold(ws, 2)              # neutral
            await hold(ws, 1, pitch=0.3)   # pitch suave
            await hold(ws, 2)              # neutral
        finally:
            try:
                await hold(ws, 0.5)        # neutral antes de salir
            except Exception:
                pass

try:
    asyncio.run(main())
except KeyboardInterrupt:
    pass
