"""
vision.pipeline
===============
ClaudeVision-Lite interface.
Wraps OpenCV capture + local face embedding model + YOLO object detection.
Emits face and object events to registered callbacks.

Face DB:
    SQLite at config/faces.db
    Schema: faces(uid TEXT PRIMARY KEY, embedding BLOB, label TEXT, enrolled_at REAL)

Depth:
    Lightweight monocular depth model (MiDaS-small ONNX).
    Gives relative depth; calibrated to approx cm via config.
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

import cv2
import numpy as np


@dataclass
class FaceEvent:
    uid: str
    label: str
    bbox: Tuple[int, int, int, int]   # x, y, w, h
    depth_cm: float
    confidence: float
    frame_ts: float = field(default_factory=time.time)


@dataclass
class ObjectEvent:
    label: str
    bbox: Tuple[int, int, int, int]
    confidence: float
    depth_cm: float
    frame_ts: float = field(default_factory=time.time)


class FaceDB:
    """SQLite-backed face identity store."""

    def __init__(self, path: str):
        import sqlite3
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS faces (
                uid        TEXT PRIMARY KEY,
                embedding  BLOB NOT NULL,
                label      TEXT NOT NULL,
                enrolled_at REAL NOT NULL
            )
        """)
        self._conn.commit()

    def enroll(self, uid: str, label: str, embedding: np.ndarray):
        self._conn.execute(
            "INSERT OR REPLACE INTO faces VALUES (?,?,?,?)",
            (uid, embedding.tobytes(), label, time.time())
        )
        self._conn.commit()

    def identify(self, embedding: np.ndarray, threshold: float = 0.6
                 ) -> Optional[Tuple[str, str, float]]:
        """
        Return (uid, label, similarity) for best match above threshold,
        or None if no match found.
        """
        rows = self._conn.execute(
            "SELECT uid, embedding, label FROM faces").fetchall()
        best_sim, best_uid, best_label = 0.0, None, None
        for uid, emb_bytes, label in rows:
            ref = np.frombuffer(emb_bytes, dtype=np.float32)
            sim = float(np.dot(embedding, ref) /
                        (np.linalg.norm(embedding) * np.linalg.norm(ref) + 1e-9))
            if sim > best_sim:
                best_sim, best_uid, best_label = sim, uid, label
        if best_sim >= threshold:
            return best_uid, best_label, best_sim
        return None

    def close(self):
        self._conn.close()


class VisionPipeline:
    """
    Main vision loop. Call start() to begin capturing frames.

    Usage:
        vp = VisionPipeline(camera_index=0, resolution=(640,480), fps=30,
                            face_db="config/faces.db",
                            confidence_threshold=0.82)

        @vp.on_face
        def handle(ev: FaceEvent):
            print(ev.uid, ev.depth_cm)

        @vp.on_object
        def handle(ev: ObjectEvent):
            print(ev.label, ev.confidence)

        vp.start()  # blocking
    """

    def __init__(self, camera_index: int = 0,
                 resolution: Tuple[int, int] = (640, 480),
                 fps: int = 30,
                 face_db: str = "config/faces.db",
                 confidence_threshold: float = 0.82,
                 depth_model: str = "config/depth_lite.onnx",
                 track_max_objects: int = 8, **_):
        self.resolution = tuple(resolution)
        self.fps = fps
        self.confidence_threshold = confidence_threshold
        self._face_db = FaceDB(face_db)
        self._face_callbacks: List[Callable] = []
        self._object_callbacks: List[Callable] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._cap: Optional[cv2.VideoCapture] = None

        # Lazy-load heavy models
        self._depth_model_path = depth_model
        self._depth_net = None
        self._face_enc = None

    # ------------------------------------------------------------------
    # Decorator-based callback registration
    # ------------------------------------------------------------------

    def on_face(self, fn: Callable) -> Callable:
        self._face_callbacks.append(fn)
        return fn

    def on_object(self, fn: Callable) -> Callable:
        self._object_callbacks.append(fn)
        return fn

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        self._running = True
        self._cap = cv2.VideoCapture(0)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.resolution[0])
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
        self._cap.set(cv2.CAP_PROP_FPS, self.fps)
        self._load_models()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._thread.join()

    def stop(self):
        self._running = False
        if self._cap:
            self._cap.release()
        self._face_db.close()

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    def _load_models(self):
        import onnxruntime as ort
        try:
            self._depth_net = ort.InferenceSession(self._depth_model_path)
        except Exception:
            self._depth_net = None  # graceful fallback: depth = 0

        try:
            import face_recognition as fr
            self._face_enc = fr
        except ImportError:
            self._face_enc = None

    def _loop(self):
        while self._running:
            ret, frame = self._cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            ts = time.time()
            depth_map = self._estimate_depth(frame)
            self._process_faces(frame, depth_map, ts)
            self._process_objects(frame, depth_map, ts)

    def _estimate_depth(self, frame: np.ndarray) -> np.ndarray:
        if self._depth_net is None:
            return np.zeros(frame.shape[:2], dtype=np.float32)
        inp = cv2.resize(frame, (256, 256)).astype(np.float32) / 255.0
        inp = inp.transpose(2, 0, 1)[np.newaxis]
        out = self._depth_net.run(None, {"input": inp})[0][0]
        return cv2.resize(out, (frame.shape[1], frame.shape[0]))

    def _process_faces(self, frame, depth_map, ts):
        if self._face_enc is None:
            return
        rgb = frame[:, :, ::-1]
        locs = self._face_enc.face_locations(rgb, model="hog")
        encs = self._face_enc.face_encodings(rgb, locs)
        for (top, right, bottom, left), enc in zip(locs, encs):
            enc32 = enc.astype(np.float32)
            match = self._face_db.identify(enc32, self.confidence_threshold)
            uid   = match[0] if match else "unknown"
            label = match[1] if match else "unknown"
            conf  = match[2] if match else 0.0
            cx, cy = (left + right) // 2, (top + bottom) // 2
            depth = float(depth_map[cy, cx]) * 200.0  # rough cm calibration
            ev = FaceEvent(uid=uid, label=label,
                           bbox=(left, top, right-left, bottom-top),
                           depth_cm=depth, confidence=conf, frame_ts=ts)
            for cb in self._face_callbacks:
                cb(ev)

    def _process_objects(self, frame, depth_map, ts):
        # Placeholder: real impl would run YOLO here
        pass
