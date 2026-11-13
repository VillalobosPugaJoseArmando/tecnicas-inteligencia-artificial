import cv2, time
d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
det = cv2.aruco.ArucoDetector(d, cv2.aruco.DetectorParameters())
cap = cv2.VideoCapture("http://localhost:8000/mjpeg")
t0, n, hits, saved = time.time(), 0, 0, False
while time.time() - t0 < 10:
    ok, frame = cap.read()
    if not ok:
        continue
    n += 1
    corners, ids, _ = det.detectMarkers(frame)
    if ids is not None:
        hits += 1
        c = corners[0][0]
        side = ((c[0] - c[1]) ** 2).sum() ** 0.5
        cx = c[:, 0].mean() - frame.shape[1] / 2
        print(f"id {int(ids.ravel()[0])}  lado ~{side:.0f}px  desvío horizontal {cx:+.0f}px")
        if not saved:
            cv2.aruco.drawDetectedMarkers(frame, corners, ids)
            cv2.imwrite("aruco.jpg", frame)
            saved = True
print(f"detectado en {hits} de {n} frames")
cap.release()
