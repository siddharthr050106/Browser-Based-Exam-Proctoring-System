"""Audio CNN Model Definition and Preprocessing.

This module defines the PyTorch model for training and the preprocessing
function used by both training and the ONNX runtime in the sidecar.
"""

from __future__ import annotations

import numpy as np
import logging

logger = logging.getLogger(__name__)

# The 4 classes
CLASSES = ["silence", "single_speaker", "multi_speaker", "background_noise"]

def preprocess_audio(pcm_int16: np.ndarray, sample_rate: int = 16000) -> np.ndarray:
    """Convert raw 16kHz PCM int16 audio to a normalized Mel spectrogram.
    
    Args:
        pcm_int16: 1D numpy array of int16 audio samples.
        sample_rate: The sample rate (default 16000).
        
    Returns:
        A numpy array of shape (1, 64, 94) containing the mel spectrogram.
    """
    import librosa
    
    # Convert int16 to float32 in range [-1.0, 1.0]
    audio_float = pcm_int16.astype(np.float32) / 32768.0
    
    # Ensure exactly 3 seconds (48000 samples)
    target_samples = sample_rate * 3
    if len(audio_float) < target_samples:
        pad_width = target_samples - len(audio_float)
        audio_float = np.pad(audio_float, (0, pad_width), mode='constant')
    elif len(audio_float) > target_samples:
        audio_float = audio_float[:target_samples]
        
    # Compute Mel spectrogram
    # n_fft=1024, hop_length=512 -> ~94 frames for 3 seconds
    mel_spec = librosa.feature.melspectrogram(
        y=audio_float, 
        sr=sample_rate, 
        n_mels=64,
        n_fft=1024,
        hop_length=512
    )
    
    # Convert to log scale (dB)
    log_mel = librosa.power_to_db(mel_spec, ref=np.max)
    
    # Normalize to roughly [-1, 1]
    # librosa.power_to_db puts max at 0, min around -80
    norm_mel = (log_mel + 40.0) / 40.0
    
    # Add channel dimension: (1, n_mels, n_frames) -> (1, 64, 94)
    return np.expand_dims(norm_mel, axis=0).astype(np.float32)


# Only import torch if available (the sidecar only needs onnxruntime)
try:
    import torch
    import torch.nn as nn
    
    class AudioCNN(nn.Module):
        """Tiny CNN for audio classification (4 classes)."""
        def __init__(self, num_classes=4):
            super().__init__()
            # Input: (batch, 1, 64, 94)
            self.features = nn.Sequential(
                nn.Conv2d(1, 16, kernel_size=3, padding=1),
                nn.BatchNorm2d(16),
                nn.ReLU(),
                nn.MaxPool2d(2, 2), # -> (16, 32, 47)
                
                nn.Conv2d(16, 32, kernel_size=3, padding=1),
                nn.BatchNorm2d(32),
                nn.ReLU(),
                nn.MaxPool2d(2, 2), # -> (32, 16, 23)
                
                nn.Conv2d(32, 64, kernel_size=3, padding=1),
                nn.BatchNorm2d(64),
                nn.ReLU(),
                nn.AdaptiveAvgPool2d((1, 1)) # -> (64, 1, 1)
            )
            
            self.classifier = nn.Sequential(
                nn.Linear(64, 32),
                nn.ReLU(),
                nn.Dropout(0.3),
                nn.Linear(32, num_classes)
            )
            
        def forward(self, x):
            x = self.features(x)
            x = x.view(x.size(0), -1)
            x = self.classifier(x)
            return x

except ImportError:
    logger.debug("PyTorch not available. AudioCNN class not defined (using ONNX for inference).")
