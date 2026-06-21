"""Training script for the Audio CNN.

Downloads LibriSpeech (dev-clean subset for faster testing) and trains
the AudioCNN model by synthetically generating the 4 classes:
- 0: silence
- 1: single_speaker
- 2: multi_speaker
- 3: background_noise

Finally, exports the trained model to ONNX format.
"""

import os
import sys
import argparse
import random
import numpy as np

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader

# Add project root to path so we can import detection
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from detection.audio_cnn import AudioCNN, preprocess_audio

class SyntheticAudioDataset(Dataset):
    """Dynamically generates 3-second audio samples for the 4 classes."""
    def __init__(self, librispeech_path, length=1000):
        self.length = length
        self.sample_rate = 16000
        self.chunk_samples = self.sample_rate * 3  # 3 seconds
        
        print("Loading LibriSpeech dataset (this may take a while if downloading)...")
        try:
            import torchaudio
            self.librispeech = torchaudio.datasets.LIBRISPEECH(
                root=librispeech_path, url="dev-clean", download=True
            )
            # Try to load one sample to verify the audio codec works on Windows
            _ = self.librispeech[0]
            print(f"Loaded {len(self.librispeech)} speech samples.")
        except Exception as e:
            print(f"Warning: Failed to load LibriSpeech ({e}). Using fully synthetic 'speech' data.")
            self.librispeech = None

    def __len__(self):
        return self.length

    def _get_random_speech_chunk(self):
        """Extract a random 3-second chunk from LibriSpeech or generate synthetic speech."""
        if self.librispeech is not None:
            import torchaudio
            idx = random.randint(0, len(self.librispeech) - 1)
            waveform, sample_rate, _, _, _, _ = self.librispeech[idx]
            
            # Resample if needed
            if sample_rate != self.sample_rate:
                resampler = torchaudio.transforms.Resample(orig_freq=sample_rate, new_freq=self.sample_rate)
                waveform = resampler(waveform)
                
            waveform = waveform.squeeze().numpy()
        else:
            # Generate synthetic "speech-like" signals (modulated formants with pauses)
            t = np.linspace(0, 3, self.chunk_samples, endpoint=False)
            f1 = 500 + 100 * np.sin(2 * np.pi * 2 * t)
            f2 = 1500 + 200 * np.sin(2 * np.pi * 3 * t)
            waveform = 0.5 * np.sin(2 * np.pi * f1 * t) + 0.3 * np.sin(2 * np.pi * f2 * t)
            envelope = np.clip(np.sin(2 * np.pi * random.uniform(1, 4) * t), 0, 1)
            waveform = (waveform * envelope).astype(np.float32)
        
        if len(waveform) > self.chunk_samples:
            start = random.randint(0, len(waveform) - self.chunk_samples)
            return waveform[start : start + self.chunk_samples]
        else:
            # Pad if too short
            pad_width = self.chunk_samples - len(waveform)
            return np.pad(waveform, (0, pad_width), mode='constant')

    def __getitem__(self, idx):
        # Evenly distribute the 4 classes
        label = idx % 4
        
        if label == 0:
            # Silence: very low amplitude white noise
            audio = np.random.normal(0, 0.001, self.chunk_samples).astype(np.float32)
            
        elif label == 1:
            # Single speaker
            audio = self._get_random_speech_chunk()
            
        elif label == 2:
            # Multi speaker: mix two different speech chunks
            audio1 = self._get_random_speech_chunk()
            audio2 = self._get_random_speech_chunk()
            # Random mixing ratio
            ratio = random.uniform(0.3, 0.7)
            audio = ratio * audio1 + (1.0 - ratio) * audio2
            
        elif label == 3:
            # Background noise: synthetic colored noise or hum to simulate TV/AC
            # A mix of low frequency sine waves and pink noise
            t = np.linspace(0, 3, self.chunk_samples, endpoint=False)
            hum = 0.05 * np.sin(2 * np.pi * 50 * t) + 0.02 * np.sin(2 * np.pi * 120 * t)
            noise = np.random.normal(0, 0.02, self.chunk_samples)
            # Apply a simple low-pass effect via rolling average
            noise = np.convolve(noise, np.ones(10)/10, mode='same')
            audio = (hum + noise).astype(np.float32)

        # Apply random gain
        gain = random.uniform(0.5, 1.5)
        audio = audio * gain
        
        # Convert to int16 (as expected by the sidecar)
        audio_int16 = np.clip(audio * 32768.0, -32768, 32767).astype(np.int16)
        
        # Preprocess using the exact same function the sidecar uses
        mel_spec = preprocess_audio(audio_int16, self.sample_rate)
        
        return torch.tensor(mel_spec), torch.tensor(label, dtype=torch.long)


def train(epochs=10, batch_size=32):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Training on device: {device}")
    
    data_path = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_path, exist_ok=True)
    
    # 2000 samples for train, 400 for val
    train_dataset = SyntheticAudioDataset(data_path, length=2000)
    val_dataset = SyntheticAudioDataset(data_path, length=400)
    
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)
    
    model = AudioCNN(num_classes=4).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    
    print("Starting training...")
    for epoch in range(epochs):
        model.train()
        running_loss = 0.0
        correct = 0
        total = 0
        
        for inputs, labels in train_loader:
            inputs, labels = inputs.to(device), labels.to(device)
            
            optimizer.zero_grad()
            outputs = model(inputs)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            
            running_loss += loss.item()
            _, predicted = torch.max(outputs.data, 1)
            total += labels.size(0)
            correct += (predicted == labels).sum().item()
            
        train_acc = 100 * correct / total
        
        # Validation
        model.eval()
        val_loss = 0.0
        val_correct = 0
        val_total = 0
        with torch.no_grad():
            for inputs, labels in val_loader:
                inputs, labels = inputs.to(device), labels.to(device)
                outputs = model(inputs)
                loss = criterion(outputs, labels)
                val_loss += loss.item()
                _, predicted = torch.max(outputs.data, 1)
                val_total += labels.size(0)
                val_correct += (predicted == labels).sum().item()
                
        val_acc = 100 * val_correct / val_total
        print(f"Epoch [{epoch+1}/{epochs}] "
              f"Loss: {running_loss/len(train_loader):.4f} Acc: {train_acc:.2f}% | "
              f"Val Loss: {val_loss/len(val_loader):.4f} Val Acc: {val_acc:.2f}%")
              
    return model

def export_onnx(model, output_path):
    """Export the trained model to ONNX format."""
    model.eval()
    # Dummy input: (batch_size=1, channels=1, n_mels=64, n_frames=94)
    dummy_input = torch.randn(1, 1, 64, 94, device=next(model.parameters()).device)
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    torch.onnx.export(
        model,
        dummy_input,
        output_path,
        export_params=True,
        opset_version=14,
        do_constant_folding=True,
        input_names=['input'],
        output_names=['output'],
        dynamic_axes={'input': {0: 'batch_size'}, 'output': {0: 'batch_size'}}
    )
    print(f"Model successfully exported to {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=10)
    args = parser.parse_args()
    
    model = train(epochs=args.epochs)
    
    model_dir = os.path.join(PROJECT_ROOT, "detection", "models")
    export_path = os.path.join(model_dir, "audio_cnn.onnx")
    export_onnx(model, export_path)
