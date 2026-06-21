"""Tests for the audio detector."""

from unittest.mock import patch, MagicMock
import numpy as np

from detection.audio_detector import AudioDetector


@patch("detection.audio_detector.preprocess_audio")
@patch("detection.audio_detector.ort")
@patch("os.path.exists")
def test_audio_detector_escalation(mock_exists, mock_ort, mock_preprocess):
    """Test consecutive window escalation logic for AudioDetector."""
    mock_exists.return_value = True
    mock_preprocess.return_value = np.zeros((1, 64, 94), dtype=np.float32)
    
    # Mock ONNX Inference Session
    mock_session = MagicMock()
    mock_session.get_inputs.return_value = [MagicMock(name="input")]
    mock_ort.InferenceSession.return_value = mock_session
    
    detector = AudioDetector()
    
    # Fake audio input
    fake_audio = np.zeros(48000, dtype=np.int16)
    
    # Helper to mock output probabilities
    def set_mock_probs(probs_list):
        # probs_list corresponds to: silence, single_speaker, multi_speaker, background_noise
        # Pre-softmax logits
        logits = np.log(probs_list)
        mock_session.run.return_value = [[logits]]
        
    # Test silence
    set_mock_probs([0.9, 0.05, 0.02, 0.03])
    res = detector.detect(fake_audio)
    assert res.predicted_class == "silence"
    assert res.is_speech is False
    assert not res.flags
    
    # Test background noise
    set_mock_probs([0.1, 0.1, 0.1, 0.7])
    res = detector.detect(fake_audio)
    assert res.predicted_class == "background_noise"
    assert "BACKGROUND_NOISE" in res.flags
    
    # Test single speaker escalation
    set_mock_probs([0.05, 0.8, 0.1, 0.05])
    # Window 1
    res = detector.detect(fake_audio)
    assert res.predicted_class == "single_speaker"
    assert not res.flags
    # Window 2
    res = detector.detect(fake_audio)
    assert not res.flags
    # Window 3 -> Anomaly
    res = detector.detect(fake_audio)
    assert "SINGLE_SPEAKER" in res.flags
    assert res.sustained_windows == 3
    
    # Test FL boundary export
    params = detector.get_boundary_params()
    # Should be empty if < 10 samples
    assert not params
    
    # Add more samples to test FL export
    for _ in range(7):
        detector.detect(fake_audio)
        
    params = detector.get_boundary_params()
    assert "mean_probs" in params
    assert params["sample_count"] == 12
