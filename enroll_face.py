#!/usr/bin/env python3
"""
enroll_face.py
==============
Enroll a new face into config/faces.db.
Captures N sample frames and averages embeddings for robustness.

Usage:
    python3 scripts/enroll_face.py --name "Ada" --samples 30
    python3 scripts/enroll_face.py --name "Max" --samples 30 --uid user_max
"""

import argparse
import uuid

import cv2
import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name",    required=True, help="Human-readable label")
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--uid",     default=None, help="Override generated UID")
    parser.add_argument("--camera",  type=int, default=0)
    parser.add_argument("--db",      default="config/faces.db")
    args = parser.parse_args()

    try:
        import face_recognition as fr
    except ImportError:
        print("ERROR: face_recognition not installed. Run: pip install face-recognition")
        return

    from ruby.vision.pipeline import FaceDB
    db = FaceDB(args.db)
    uid = args.uid or f"user_{uuid.uuid4().hex[:8]}"

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print(f"ERROR: cannot open camera {args.camera}")
        return

    print(f"Enrolling: {args.name!r} (uid={uid})")
    print(f"Collecting {args.samples} samples. Look at the camera.")
    embeddings = []

    while len(embeddings) < args.samples:
        ret, frame = cap.read()
        if not ret:
            continue
        rgb = frame[:, :, ::-1]
        locs = fr.face_locations(rgb, model="hog")
        encs = fr.face_encodings(rgb, locs)
        if encs:
            embeddings.append(encs[0].astype(np.float32))
            print(f"  sample {len(embeddings)}/{args.samples}", end="\r")

        cv2.imshow("Enrollment -- press Q to cancel", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()

    if len(embeddings) < 5:
        print("ERROR: not enough samples captured")
        return

    avg_embedding = np.mean(embeddings, axis=0)
    avg_embedding /= np.linalg.norm(avg_embedding) + 1e-9
    db.enroll(uid, args.name, avg_embedding)
    db.close()
    print(f"\nEnrolled {args.name!r} with {len(embeddings)} samples -> uid={uid}")


if __name__ == "__main__":
    main()
