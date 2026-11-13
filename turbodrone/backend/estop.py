import asyncio, json, websockets
async def f():
    async with websockets.connect("ws://localhost:8000/ws") as s:
        await s.send(json.dumps({"type": "estop"}))
asyncio.run(f())
