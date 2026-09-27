"""
tests/unit/test_vision.py
Tests for the face database (no camera required).
"""

import pytest
import numpy as np
import tempfile

from vision.face_db import FaceDatabase


def random_enc():
    v = np.random.randn(128).astype(np.float32)
    return v / np.linalg.norm(v)


@pytest.fixture
def db(tmp_path):
    return FaceDatabase(str(tmp_path / "test_faces.db"))


class TestFaceDatabase:
    def test_identify_empty_db(self, db):
        enc = random_enc()
        uid, conf = db.identify(enc)
        assert uid == "unknown"
        assert conf == 0.0

    def test_enroll_and_identify(self, db):
        enc = random_enc()
        db.enroll("alice", enc)
        uid, conf = db.identify(enc)
        assert uid == "alice"
        assert conf > 0.9

    def test_distinct_faces_not_confused(self, db):
        enc_a = random_enc()
        enc_b = random_enc()
        db.enroll("alice", enc_a)
        db.enroll("bob", enc_b)
        uid_a, _ = db.identify(enc_a)
        uid_b, _ = db.identify(enc_b)
        assert uid_a == "alice"
        assert uid_b == "bob"

    def test_list_faces(self, db):
        db.enroll("alice", random_enc())
        db.enroll("bob", random_enc())
        faces = db.list_faces()
        assert "alice" in faces
        assert "bob" in faces

    def test_delete_face(self, db):
        enc = random_enc()
        db.enroll("temp_user", enc)
        db.delete("temp_user")
        assert "temp_user" not in db.list_faces()
