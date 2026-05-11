"""Tests for the face gate detector.

These tests mock MediaPipe since the solutions API may vary by version.
"""

import numpy as np
import pytest
from unittest.mock import patch, MagicMock
from detection.face_gate import FaceGate, FaceGateResult


@pytest.fixture
def mock_mediapipe():
    """Mock MediaPipe FaceMesh to avoid hardware dependency."""
    with patch("detection.face_gate.mp") as mock_mp:
        mock_mesh = MagicMock()
        mock_mp.solutions.face_mesh.FaceMesh.return_value = mock_mesh
        yield mock_mesh


class TestFaceGate:
    def test_no_face_flag_after_timeout(self, mock_mediapipe):
        gate = FaceGate(no_face_timeout=0.01)
        result = FaceGateResult(face_detected=False, face_count=0)

        import time
        gate._last_face_seen = time.time() - 10
        with patch.object(gate, '_process_frame', return_value=result):
            output = gate.process(np.zeros((480, 640, 3), dtype=np.uint8))
            assert "NO_FACE" in output.flags
            assert output.no_face_duration > 0

    def test_multiple_faces_flag(self, mock_mediapipe):
        gate = FaceGate()
        result = FaceGateResult(face_detected=True, face_count=2)

        with patch.object(gate, '_process_frame', return_value=result):
            output = gate.process(np.zeros((480, 640, 3), dtype=np.uint8))
            assert "MULTIPLE_PERSONS" in output.flags

    def test_identity_mismatch_flag(self, mock_mediapipe):
        gate = FaceGate(identity_threshold=0.9)
        gate._reference_embedding = np.ones(28, dtype=np.float32)
        landmarks = np.random.rand(478, 3).astype(np.float32)
        result = FaceGateResult(face_detected=True, face_count=1, landmarks=landmarks)

        with patch.object(gate, '_process_frame', return_value=result):
            output = gate.process(np.zeros((480, 640, 3), dtype=np.uint8))
            assert output.identity_match_score < 1.0

    def test_face_embedding_scale_invariance(self, mock_mediapipe):
        gate = FaceGate()
        landmarks = np.random.rand(478, 3).astype(np.float32)
        emb = gate._compute_face_embedding(landmarks)
        assert emb is not None
        assert len(emb) > 0


class TestFaceGateResult:
    def test_default_values(self):
        result = FaceGateResult()
        assert result.face_detected is False
        assert result.face_count == 0
        assert result.flags == []
        assert result.identity_match_score == 1.0


class TestCosine:
    def test_identical_vectors(self):
        a = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        assert abs(FaceGate._cosine_similarity(a, a) - 1.0) < 1e-5

    def test_orthogonal_vectors(self):
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([0.0, 1.0], dtype=np.float32)
        assert abs(FaceGate._cosine_similarity(a, b)) < 1e-5

    def test_zero_vector(self):
        a = np.array([1.0, 2.0], dtype=np.float32)
        b = np.zeros(2, dtype=np.float32)
        assert FaceGate._cosine_similarity(a, b) == 0.0
