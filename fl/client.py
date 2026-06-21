"""Flower FL Client Adapter.

Runs at the end of an exam session to submit local model parameter
updates to the FL server.
"""

import flwr as fl
import numpy as np

class AudioCNNClient(fl.client.NumPyClient):
    """Flower NumPyClient for the Audio CNN model."""
    
    def __init__(self, model_weights: list[np.ndarray], sample_count: int):
        self.model_weights = model_weights
        self.sample_count = sample_count
        
    def get_parameters(self, config):
        return self.model_weights

    def fit(self, parameters, config):
        # In a full FL setup, we would run local training epochs here.
        # Since we use a micro-payload approach (sending calibration stats
        # or pre-computed weight deltas), we just return our weights.
        return self.model_weights, self.sample_count, {}

    def evaluate(self, parameters, config):
        # No local evaluation required
        return 0.0, self.sample_count, {"accuracy": 0.0}


def submit_contribution(weights: list[np.ndarray], sample_count: int, server_address="127.0.0.1:8080"):
    """Start the Flower client and submit the contribution."""
    client = AudioCNNClient(weights, sample_count)
    fl.client.start_numpy_client(server_address=server_address, client=client)
    print("[FL Client] Contribution submitted successfully.")
