import cv2, time, numpy as np
cap = cv2.VideoCapture("http://localhost:8000/mjpeg")
t0, n, hits, saved = time.time(), 0, 0, False
while time.time() - t0 < 10:
    ok, frame = cap.read()
    if not ok:
        continue
    n += 1
    mask = cv2.inRange(cv2.cvtColor(frame, cv2.COLOR_BGR2HSV), (135, 70, 70), (170, 255, 255))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if cs:
        c = max(cs, key=cv2.contourArea)
        a = cv2.contourArea(c)
        if a > 150:
            hits += 1
            x, y, w, h = cv2.boundingRect(c)
            print(f"área {a:.0f}px²  centro x={x+w/2:.0f} y={y+h/2:.0f}")
            if not saved:
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.imwrite("blob.jpg", frame)
                saved = True
print(f"detectado en {hits} de {n} frames")
cap.release()
