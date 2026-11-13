import cv2, time
cap = cv2.VideoCapture("http://localhost:8000/mjpeg")
n, t0, saved = 0, time.time(), False
while time.time() - t0 < 5:
    ok, frame = cap.read()
    if not ok:
        continue
    n += 1
    if not saved:
        print("resolución:", frame.shape[1], "x", frame.shape[0])
        cv2.imwrite("frame.jpg", frame)
        saved = True
print("frames en 5 s:", n, "→ ~", round(n / 5, 1), "fps")
cap.release()
