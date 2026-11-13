"""
ArucoMonitorPlugin: observador. NO manda ningún comando al dron.

Detecta el ArUco (DICT_4X4_50, id 0) en cada frame, dibuja el cuadro en la web
(overlay) y muestra un letrero: NECESITA AJUSTE / PUEDE ATERRIZAR.
Guarda un CSV por frame, los últimos frames anotados y un resumen en
backend/logs/aruco_<fecha>/.
"""
import csv
import logging
import os
import threading
import time
from collections import deque
from datetime import datetime

import cv2
import numpy as np

from .base import Plugin

logger = logging.getLogger(__name__)

# Umbrales: los mismos de auto_land.py
LAND_SIDE = 140       # lado del marcador en px para considerarlo "cerca"
LAND_EY = 0.55        # posición vertical (-1 arriba .. +1 abajo) para "cerca"
CENTER_TOL = 0.35     # |ex| máximo para considerarlo centrado
CONFIRM_FRAMES = 2    # frames seguidos cumpliendo para decir "puede aterrizar"
HOLD_S = 0.6          # tiempo que se mantiene el último estado si se pierde un frame
KEEP_FRAMES = 30      # frames guardados antes de cada volcado
MARKER_ID = 0

CSV_COLS = [
    "t", "frame", "fase", "detectado", "variante", "lado_px", "cx", "cy",
    "ex", "ey", "toca_borde", "cerca_por_lado", "cerca_por_ey", "estado", "detalle",
]


class ArucoMonitorPlugin(Plugin):
    _current = None

    # ------------------------------------------------------------------ ciclo
    def _on_start(self):
        try:
            cv2.setNumThreads(1)
        except Exception:
            pass

        d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        p = cv2.aruco.DetectorParameters()
        p.adaptiveThreshWinSizeMin = 3
        p.adaptiveThreshWinSizeMax = 53
        p.adaptiveThreshWinSizeStep = 6
        p.minMarkerPerimeterRate = 0.02
        p.polygonalApproxAccuracyRate = 0.05
        p.errorCorrectionRate = 0.8
        self.detector = cv2.aruco.ArucoDetector(d, p)
        self.clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "logs"))
        self.session_dir = os.path.join(base, f"aruco_{ts}")
        os.makedirs(self.session_dir, exist_ok=True)

        self._lock = threading.Lock()
        self._csv_f = open(os.path.join(self.session_dir, "datos.csv"), "w", newline="", buffering=1)
        self._csv = csv.writer(self._csv_f)
        self._csv.writerow(CSV_COLS)

        self.t0 = time.time()
        self.phase = "monitoreo"      # monitoreo -> vuelo -> aterrizado (si se llama notify)
        self.ring = deque(maxlen=KEEP_FRAMES)
        self.n_frames = 0
        self.n_det = 0
        self.max_side = 0.0
        self.first_ready_t = None
        self.state = ("NECESITA AJUSTE", "no veo el marcador")
        self.ok_streak = 0
        self.last_seen = None
        self.ever_seen = False

        ArucoMonitorPlugin._current = self
        self.loop_thread = threading.Thread(target=self._loop, daemon=True)
        self.loop_thread.start()
        logger.info("[ArucoMonitor] Sesión en %s", self.session_dir)

    def _on_stop(self):
        if self.loop_thread:
            self.loop_thread.join(timeout=1.5)
        try:
            self._dump("final")
            self._write_summary()
        except Exception:
            logger.exception("[ArucoMonitor] Error al guardar el final")
        try:
            self._csv_f.close()
        except Exception:
            pass
        if ArucoMonitorPlugin._current is self:
            ArucoMonitorPlugin._current = None

    # Para engancharlo a los botones de la web: ArucoMonitorPlugin.notify("takeoff")
    @classmethod
    def notify(cls, event: str):
        inst = cls._current
        if inst and inst.running:
            inst._event(event)

    def _event(self, event: str):
        if event == "takeoff":
            self.phase = "vuelo"
        elif event == "land":
            self.phase = "aterrizado"
            threading.Timer(2.0, lambda: self._dump("land")).start()
        with self._lock:
            row = {c: "" for c in CSV_COLS}
            row.update(t=f"{time.time() - self.t0:.2f}", fase=self.phase, estado=f"EVENTO:{event}")
            self._csv.writerow([row[c] for c in CSV_COLS])

    # ---------------------------------------------------------------- detección
    def _decode(self, frame):
        if hasattr(frame, "format") and frame.format == "jpeg":
            raw = bytes(frame.data)
            img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
            return img, raw
        if isinstance(frame, np.ndarray):
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            return frame, (buf.tobytes() if ok else None)
        return None, None

    def _detect(self, img):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        variantes = (
            ("normal", lambda: gray),
            ("oscuro", lambda: cv2.convertScaleAbs(gray, alpha=0.45)),
            ("clahe", lambda: self.clahe.apply(gray)),
        )
        for nombre, make in variantes:
            corners, ids, _ = self.detector.detectMarkers(make())
            if ids is None:
                continue
            for c, i in zip(corners, ids.ravel()):
                if int(i) == MARKER_ID:
                    return nombre, np.asarray(c, dtype=np.float32).reshape(4, 2)
        return None, None

    # --------------------------------------------------------------------- loop
    def _loop(self):
        logger.info("[ArucoMonitor] Esperando frames...")
        last_log = time.time()
        for frame in self.frames:
            if not self.running:
                break
            img, raw = self._decode(frame)
            if img is None:
                continue

            now = time.time()
            t = now - self.t0
            h, w = img.shape[:2]
            self.n_frames += 1

            variante, pts = self._detect(img)
            overlay = []
            row = {c: "" for c in CSV_COLS}
            row.update(t=f"{t:.2f}", frame=self.n_frames, fase=self.phase, detectado=int(pts is not None))

            if pts is not None:
                self.n_det += 1
                self.ever_seen = True
                self.last_seen = now
                side = float(np.mean([np.linalg.norm(pts[i] - pts[(i + 1) % 4]) for i in range(4)]))
                cx, cy = pts.mean(axis=0)
                ex = float((cx - w / 2) / (w / 2))
                ey = float((cy - h / 2) / (h / 2))
                x1, y1 = pts.min(axis=0)
                x2, y2 = pts.max(axis=0)
                m = 0.02
                borde = bool(x1 <= w * m or y1 <= h * m or x2 >= w * (1 - m) or y2 >= h * (1 - m))
                cerca_lado = side >= LAND_SIDE
                cerca_ey = ey >= LAND_EY
                centrado = abs(ex) <= CENTER_TOL
                self.max_side = max(self.max_side, side)

                if (cerca_lado or cerca_ey) and centrado:
                    self.ok_streak += 1
                else:
                    self.ok_streak = 0

                if self.ok_streak >= CONFIRM_FRAMES:
                    self.state = ("PUEDE ATERRIZAR", f"lado {side:.0f} px")
                    if self.first_ready_t is None:
                        self.first_ready_t = t
                        self._snapshot(img, pts, "puede_aterrizar")
                else:
                    razones = []
                    if not centrado:
                        razones.append("marcador a la derecha" if ex > 0 else "marcador a la izquierda")
                    if not (cerca_lado or cerca_ey):
                        razones.append(f"muy lejos (lado {side:.0f} px, meta {LAND_SIDE})")
                    self.state = ("NECESITA AJUSTE", ", ".join(razones) or "confirmando")

                color = "lime" if self.state[0] == "PUEDE ATERRIZAR" else "orange"
                overlay.append({
                    "type": "rect",
                    "coords": [float(x1 / w), float(y1 / h), float(x2 / w), float(y2 / h)],
                    "color": color,
                })
                row.update(variante=variante, lado_px=f"{side:.1f}", cx=f"{cx:.0f}", cy=f"{cy:.0f}",
                           ex=f"{ex:+.2f}", ey=f"{ey:+.2f}", toca_borde=int(borde),
                           cerca_por_lado=int(cerca_lado), cerca_por_ey=int(cerca_ey))
            else:
                self.ok_streak = 0
                perdido_hace = (now - self.last_seen) if self.last_seen else None
                if perdido_hace is None:
                    self.state = ("NECESITA AJUSTE", "no veo el marcador")
                elif perdido_hace > HOLD_S:
                    self.state = ("NECESITA AJUSTE", "perdí el marcador")

            estado, detalle = self.state
            row.update(estado=estado, detalle=detalle)
            color_txt = "lime" if estado == "PUEDE ATERRIZAR" else "orange"
            overlay.append({"type": "text", "text": f"{estado}: {detalle}", "color": color_txt})
            self.send_overlay(overlay)

            with self._lock:
                self._csv.writerow([row[c] for c in CSV_COLS])
            if raw is not None:
                self.ring.append((t, raw, None if pts is None else pts.copy(), estado, detalle))

            if now - last_log >= 5.0:
                logger.info("[ArucoMonitor] detecciones %d/%d, lado máx %.0f px, estado: %s",
                            self.n_det, self.n_frames, self.max_side, estado)
                last_log = now

    # ------------------------------------------------------------------ salida
    def _annotate(self, img, pts, estado, detalle):
        color = (0, 255, 0) if estado == "PUEDE ATERRIZAR" else (0, 165, 255)
        if pts is not None:
            cv2.polylines(img, [pts.astype(np.int32).reshape(-1, 1, 2)], True, color, 3)
        cv2.putText(img, f"{estado}: {detalle}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
        return img

    def _snapshot(self, img, pts, nombre):
        try:
            out = self._annotate(img.copy(), pts, "PUEDE ATERRIZAR", "primer aviso")
            cv2.imwrite(os.path.join(self.session_dir, f"{nombre}.jpg"), out)
        except Exception:
            pass

    def _dump(self, tag: str):
        folder = os.path.join(self.session_dir, f"ultimos_{tag}")
        os.makedirs(folder, exist_ok=True)
        for k, (t, raw, pts, estado, detalle) in enumerate(list(self.ring)):
            img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                continue
            img = self._annotate(img, pts, estado, detalle)
            cv2.imwrite(os.path.join(folder, f"{k:02d}_t{t:.1f}.jpg"), img)
        logger.info("[ArucoMonitor] Últimos frames guardados en %s", folder)

    def _write_summary(self):
        pct = 100.0 * self.n_det / self.n_frames if self.n_frames else 0.0
        lines = [
            f"frames procesados: {self.n_frames}",
            f"detecciones: {self.n_det} ({pct:.1f}%)",
            f"lado máximo visto: {self.max_side:.0f} px",
            f"primer 'PUEDE ATERRIZAR' en t={self.first_ready_t if self.first_ready_t is not None else 'nunca'}",
            f"duración: {time.time() - self.t0:.1f} s",
            f"carpeta: {self.session_dir}",
        ]
        with open(os.path.join(self.session_dir, "resumen.txt"), "w") as f:
            f.write("\n".join(lines) + "\n")
        logger.info("[ArucoMonitor] Resumen:\n%s", "\n".join(lines))
