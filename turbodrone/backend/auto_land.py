import asyncio, json, os, sys, threading, time
import cv2, websockets

FLY = "--fly" in sys.argv
URL, STREAM, HZ = "ws://localhost:8000/ws", "http://localhost:8000/mjpeg", 20
PITCH, YAW_GAIN, YAW_MAX, CENTER_TOL = 0.20, 0.35, 0.25, 0.35
LAND_SIDE, LAND_EY = 140, 0.55
START_WAIT, LOST_ARRIVED, LOST_ABORT, MAX_T, FRESH = 6.0, 0.8, 2.5, 30.0, 0.4

shared = {"t": 0.0, "side": 0.0, "ex": 0.0, "ey": 0.0}
stop = threading.Event()

def vision():
    d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    p = cv2.aruco.DetectorParameters()
    p.adaptiveThreshWinSizeMax = 53
    p.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    det = cv2.aruco.ArucoDetector(d, p)
    clahe = cv2.createCLAHE(2.0, (8, 8))
    cap = cv2.VideoCapture(STREAM)
    while not stop.is_set():
        ok, frame = cap.read()
        if not ok:
            continue
        h, w = frame.shape[:2]
        corners, ids, _ = det.detectMarkers(clahe.apply(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)))
        if ids is not None and 0 in ids.ravel():
            c = corners[list(ids.ravel()).index(0)][0]
            shared.update(t=time.time(),
                          side=float(((c[0] - c[1]) ** 2).sum() ** 0.5),
                          ex=float((c[:, 0].mean() - w / 2) / (w / 2)),
                          ey=float((c[:, 1].mean() - h / 2) / (h / 2)))
    cap.release()

def clamp(v, m):
    return max(-m, min(m, v))

def axes(yaw=0.0, pitch=0.0):
    return json.dumps({"type": "axes", "mode": "abs", "throttle": 0,
                       "yaw": yaw, "pitch": pitch, "roll": 0})

async def main():
    if FLY and input("¿El dron está EN EL AIRE y estable? (si/no): ").strip().lower() != "si":
        return
    threading.Thread(target=vision, daemon=True).start()
    ws = await websockets.connect(URL) if FLY else None
    st = {"landed": False}

    async def send(m):
        if ws:
            await ws.send(m)

    async def land(why):
        if st["landed"]:
            return
        st["landed"] = True
        print(f"\n>>> LAND ({why})" + ("" if FLY else "  [simulado]"))
        await send(json.dumps({"type": "land"}))

    t0, seen, close_n, last = time.time(), False, 0, (0, 0, 0)
    try:
        await send(json.dumps({"type": "set_speed_index", "speed_index": 0}))
        i = 0
        while True:
            now = time.time()
            if now - t0 > MAX_T:
                await land("tiempo máximo")
                break
            fresh = shared["t"] > t0 and now - shared["t"] < FRESH
            yaw = pitch = 0.0
            if fresh:
                seen = True
                last = (shared["t"], shared["side"], shared["ey"])
                ex = shared["ex"]
                yaw = clamp(YAW_GAIN * ex, YAW_MAX)
                pitch = PITCH if abs(ex) < CENTER_TOL else 0.0
                close_n = close_n + 1 if (shared["side"] >= LAND_SIDE or shared["ey"] >= LAND_EY) else 0
                if close_n >= 2:
                    await land(f"marcador cerca: lado={shared['side']:.0f}px ey={shared['ey']:+.2f}")
                    break
            else:
                close_n = 0
                if not seen:
                    if now - t0 > START_WAIT:
                        print("\nNo vi el marcador; salgo sin aterrizar (ejes en neutral).")
                        break
                else:
                    lost = now - last[0]
                    if lost > LOST_ARRIVED and (last[1] >= 100 or last[2] >= 0.4):
                        await land(f"salió del cuadro; último lado={last[1]:.0f}px ey={last[2]:+.2f}")
                        break
                    if lost > LOST_ABORT:
                        await land("perdí el marcador")
                        break
            await send(axes(yaw, pitch))
            if i % 5 == 0:
                print(f"visto={fresh!s:5}  yaw={yaw:+.2f}  pitch={pitch:+.2f}  ey={shared['ey']:+.2f}  ex={shared['ex']:+.2f}  lado={shared['side']:.0f}px", end="\r")
            i += 1
            await asyncio.sleep(1 / HZ)
    except (asyncio.CancelledError, KeyboardInterrupt):
        await land("Ctrl+C")
    finally:
        for _ in range(3 * HZ):
            await send(axes())
            await asyncio.sleep(1 / HZ)
        stop.set()
        if ws:
            await ws.close()

try:
    asyncio.run(main())
except KeyboardInterrupt:
    pass
sys.stdout.flush()
os._exit(0)
