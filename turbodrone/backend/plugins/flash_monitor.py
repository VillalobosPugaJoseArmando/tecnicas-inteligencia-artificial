"""
FlashMonitorPlugin: observador que detecta el celular por el PARPADEO de su pantalla.
NO manda ningún comando al dron.

La pantalla alterna blanco/negro (~3 Hz). Se buscan las zonas donde los pixeles
cambian mucho dentro de una ventana corta de frames, se descartan las líneas
delgadas (movimiento de la cámara) y se exige que el brillo dentro de la zona
suba y baje de verdad. Funciona aunque la cámara queme el color y sin resolver
detalles finos, así que alcanza más lejos que el ArUco.

Reutiliza de ArucoMonitorPlugin: CSV, eventos takeoff/land, últimos frames y resumen.
Columnas del CSV: lado_px = lado equivalente del cuadro detectado (raíz del área).
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

from .aruco_monitor import ArucoMonitorPlugin, CSV_COLS, KEEP_FRAMES

logger = logging.getLogger(__name__)

SCALE = 4            # se procesa a 1/4 del tamaño
HIST = 8             # frames en la ventana de análisis
RANGE_T = 70         # diferencia mínima (más claro - más oscuro) por pixel
MIN_AMP = 60         # amplitud mínima del parpadeo dentro de la zona
MIN_SIDE = 30        # lado equivalente mínimo (px reales) para aceptar
MIN_SOLIDITY = 0.55  # qué tan "rectangular" debe ser la zona
LAND_SIDE = 200      # PROVISIONAL: lado equivalente (px) para "cerca". Se ajusta con datos
CENTER_TOL = 0.35
CONFIRM_FRAMES = 3
HOLD_S = 0.8


class FlashMonitorPlugin(ArucoMonitorPlugin):

    def _on_start(self):
        try:
            cv2.setNumThreads(1)
        except Exception:
            pass

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "logs"))
        self.session_dir = os.path.join(base, f"flash_{ts}")
        os.makedirs(self.session_dir, exist_ok=True)

        self._lock = threading.Lock()
        self._csv_f = open(os.path.join(self.session_dir, "datos.csv"), "w", newline="", buffering=1)
        self._csv = csv.writer(self._csv_f)
        self._csv.writerow(CSV_COLS)

        self.t0 = time.time()
        self.phase = "monitoreo"
        self.ring = deque(maxlen=KEEP_FRAMES)
        self.n_frames = 0
        self.n_det = 0
        self.max_side = 0.0
        self.first_ready_t = None
        self.state = ("NECESITA AJUSTE", "no veo el celular parpadeando")
        self.ok_streak = 0
        self.last_seen = None
        self.ever_seen = False

        ArucoMonitorPlugin._current = self
        self.loop_thread = threading.Thread(target=self._loop, daemon=True)
        self.loop_thread.start()
        logger.info("[FlashMonitor] Sesión en %s", self.session_dir)

    # ---------------------------------------------------------------- detección
    def _find_blob(self, hist, k_open, k_close):
        stack = np.stack(hist)
        rng = stack.max(axis=0) - stack.min(axis=0)
        mask = (rng > RANGE_T).astype(np.uint8) * 255
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k_open)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k_close)
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            return None, 0.0
        c = max(cnts, key=cv2.contourArea)
        area = cv2.contourArea(c)
        if area < (MIN_SIDE / SCALE) ** 2:
            return None, 0.0
        x, y, bw, bh = cv2.boundingRect(c)
        if area / float(bw * bh) < MIN_SOLIDITY:
            return None, 0.0
        serie = stack[:, y:y + bh, x:x + bw].reshape(len(hist), -1).mean(axis=1)
        amp = float(serie.max() - serie.min())
        d = np.diff(serie)
        signos = np.sign(d[np.abs(d) > 8])
        cambios = int(np.sum(signos[1:] != signos[:-1])) if len(signos) > 1 else 0
        if amp < MIN_AMP or cambios < 2:
            return None, amp
        box = cv2.boxPoints(cv2.minAreaRect(c)) * SCALE
        return box.astype(np.float32), amp

    # --------------------------------------------------------------------- loop
    def _loop(self):
        logger.info("[FlashMonitor] Esperando frames...")
        hist = deque(maxlen=HIST)
        k_open = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        k_close = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
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

            small = cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY),
                               (w // SCALE, h // SCALE), interpolation=cv2.INTER_AREA)
            hist.append(small)

            pts, amp = (None, 0.0)
            if len(hist) == HIST:
                pts, amp = self._find_blob(hist, k_open, k_close)

            overlay = []
            row = {c: "" for c in CSV_COLS}
            row.update(t=f"{t:.2f}", frame=self.n_frames, fase=self.phase, detectado=int(pts is not None))

            if pts is not None:
                self.n_det += 1
                self.ever_seen = True
                self.last_seen = now
                lado_a = float(np.linalg.norm(pts[0] - pts[1]))
                lado_b = float(np.linalg.norm(pts[1] - pts[2]))
                side = float(np.sqrt(lado_a * lado_b))
                cx, cy = pts.mean(axis=0)
                ex = float((cx - w / 2) / (w / 2))
                ey = float((cy - h / 2) / (h / 2))
                x1, y1 = np.clip(pts.min(axis=0), 0, [w, h])
                x2, y2 = np.clip(pts.max(axis=0), 0, [w, h])
                cerca = side >= LAND_SIDE
                centrado = abs(ex) <= CENTER_TOL
                self.max_side = max(self.max_side, side)

                if cerca and centrado:
                    self.ok_streak += 1
                else:
                    self.ok_streak = 0

                if self.ok_streak >= CONFIRM_FRAMES:
                    self.state = ("PUEDE ATERRIZAR", f"tamaño {side:.0f} px")
                    if self.first_ready_t is None:
                        self.first_ready_t = t
                        self._snapshot(img, pts, "puede_aterrizar")
                else:
                    razones = []
                    if not centrado:
                        razones.append("celular a la derecha" if ex > 0 else "celular a la izquierda")
                    if not cerca:
                        razones.append(f"muy lejos (tamaño {side:.0f} px, meta {LAND_SIDE})")
                    self.state = ("NECESITA AJUSTE", ", ".join(razones) or "confirmando")

                color = "lime" if self.state[0] == "PUEDE ATERRIZAR" else "orange"
                overlay.append({
                    "type": "rect",
                    "coords": [float(x1 / w), float(y1 / h), float(x2 / w), float(y2 / h)],
                    "color": color,
                })
                row.update(variante=f"flash amp={amp:.0f}", lado_px=f"{side:.1f}", cx=f"{cx:.0f}",
                           cy=f"{cy:.0f}", ex=f"{ex:+.2f}", ey=f"{ey:+.2f}",
                           cerca_por_lado=int(cerca))
            else:
                self.ok_streak = 0
                perdido_hace = (now - self.last_seen) if self.last_seen else None
                if perdido_hace is None:
                    self.state = ("NECESITA AJUSTE", "no veo el celular parpadeando")
                elif perdido_hace > HOLD_S:
                    self.state = ("NECESITA AJUSTE", "perdí el celular")
                row.update(variante=f"flash amp={amp:.0f}")

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
                logger.info("[FlashMonitor] detecciones %d/%d, tamaño máx %.0f px, estado: %s",
                            self.n_det, self.n_frames, self.max_side, estado)
                last_log = now
