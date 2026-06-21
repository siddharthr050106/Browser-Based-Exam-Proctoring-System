"""Audio Anomaly Detector — runs the ONNX CNN model and manages escalation logic.

The interface: detect(pcm_int16) -> AudioResult
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import structlog

# We use onnxruntime at runtime, not torch.
try:
    import onnxruntime as ort
except ImportError:
    ort = None

from detection.audio_cnn import preprocess_audio, CLASSES

logger = structlog.get_logger()


@dataclass
class AudioResult:
    """Result from audio detection."""
    predicted_class: str
    confidence: float
    is_speech: bool = False
    is_anomalous: bool = False
    sustained_windows: int = 0
    flags: list[str] = field(default_factory=list)


class AudioDetector:
    """Audio anomaly detection using CNN.
    
    Classifies 3-second audio chunks into:
    - silence
    - single_speaker
    - multi_speaker
    - background_noise
    """

    def __init__(self, model_path: str = None):
        if model_path is None:
            # Default path: detection/models/audio_cnn.onnx
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            model_path = os.path.join(base_dir, "detection", "models", "audio_cnn.onnx")
            
        self.model_path = model_path
        self._ort_session = None
        self._load_model()
        
        # Tracking consecutive windows
        self._single_speaker_count = 0
        self._multi_speaker_count = 0
        
        # To store stats for FL
        self._calibration_data: list[list[float]] = [] # list of output probabilities
        
    def _load_model(self):
        if ort is None:
            logger.warning("onnxruntime_not_installed")
            return
            
        try:
            if os.path.exists(self.model_path):
                self._ort_session = ort.InferenceSession(self.model_path)
                logger.info("audio_cnn_loaded", path=self.model_path)
            else:
                logger.warning("audio_cnn_not_found", path=self.model_path)
        except Exception as e:
            logger.error("audio_cnn_load_error", error=str(e))
            
    def detect(self, pcm_int16: np.ndarray) -> AudioResult:
        result = AudioResult(predicted_class="silence", confidence=1.0)
        
        if self._ort_session is None:
            return result
            
        try:
            # Preprocess: (1, 64, 94)
            mel_spec = preprocess_audio(pcm_int16)
            # Add batch dimension: (1, 1, 64, 94)
            mel_spec = np.expand_dims(mel_spec, axis=0)
            
            # Run inference
            ort_inputs = {self._ort_session.get_inputs()[0].name: mel_spec}
            ort_outs = self._ort_session.run(None, ort_inputs)
            
            # Softmax
            logits = ort_outs[0][0]
            exp_logits = np.exp(logits - np.max(logits))
            probs = exp_logits / exp_logits.sum()
            
            pred_idx = int(np.argmax(probs))
            result.predicted_class = CLASSES[pred_idx]
            result.confidence = float(probs[pred_idx])
            
            # Save stats for FL
            self._calibration_data.append(probs.tolist())
            
            # Escalation logic
            if result.predicted_class == "single_speaker":
                self._single_speaker_count += 1
                self._multi_speaker_count = max(0, self._multi_speaker_count - 1)
                result.is_speech = True
                
                if self._single_speaker_count >= 3:
                    result.is_anomalous = True
                    result.sustained_windows = self._single_speaker_count
                    result.flags.append("SINGLE_SPEAKER")
                    
            elif result.predicted_class == "multi_speaker":
                self._multi_speaker_count += 1
                self._single_speaker_count = max(0, self._single_speaker_count - 1)
                result.is_speech = True
                
                if self._multi_speaker_count >= 3:
                    result.is_anomalous = True
                    result.sustained_windows = self._multi_speaker_count
                    result.flags.append("MULTI_SPEAKER")
                    
            elif result.predicted_class == "background_noise":
                self._single_speaker_count = max(0, self._single_speaker_count - 1)
                self._multi_speaker_count = max(0, self._multi_speaker_count - 1)
                result.flags.append("BACKGROUND_NOISE")
                result.is_anomalous = True
                
            else: # silence
                self._single_speaker_count = max(0, self._single_speaker_count - 1)
                self._multi_speaker_count = max(0, self._multi_speaker_count - 1)
                
        except Exception as e:
            logger.error("audio_cnn_inference_error", error=str(e))
            
        return result
        
    def get_boundary_params(self) -> dict:
        """Export FL micro-payload (mean confidence per class)."""
        if len(self._calibration_data) < 10:
            return {}
            
        data = np.array(self._calibration_data) # shape: (N, 4)
        mean_probs = data.mean(axis=0)
        var_probs = data.var(axis=0)
        
        return {
            "mean_probs": mean_probs.tolist(),
            "var_probs": var_probs.tolist(),
            "sample_count": len(self._calibration_data)
        }
