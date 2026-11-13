import cv2, time
d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
p = cv2.aruco.DetectorParameters()
p.adaptiveThreshWinSizeMax = 53
p.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
p.minMarkerPerimeterRate = 0.02
det = cv2.aruco.ArucoDetector(d, p)
clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
cap = cv2.VideoCapture("http://localhost:8000/mjpeg")
t0, n, hits, last = time.time(), 0, 0, None
while time.time() - t0 < 10:
    ok, frame = cap.read()
    if not ok:
        continue
    n += 1
    last = frame.copy()
    gray = clahe.apply(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
    corners, ids, _ = det.detectMarkers(gray)
    if ids is not None:
        hits += 1
        c = corners[0][0]
        side = ((c[0] - c[1]) ** 2).sum() ** 0.5
        cx = c[:, 0].mean() - frame.shape[1] / 2
        print(f"id {int(ids.ravel()[0])}  lado ~{side:.0f}px  desvío {cx:+.0f}px")
        cv2.aruco.drawDetectedMarkers(frame, corners, ids)
        cv2.imwrite("aruco_ok.jpg", frame)
if last is not None:
    cv2.imwrite("ultimo.jpg", last)
print(f"detectado en {hits} de {n} frames")
cap.release()
