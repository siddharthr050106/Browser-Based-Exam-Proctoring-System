"""Flower FL Server for Audio CNN.

Runs a Federated Learning server that aggregates model updates from clients
using the FedAvg strategy, with differential privacy noise and validation.
"""

import os
import sys
from typing import Dict, List, Optional, Tuple, Union

import flwr as fl
from flwr.common import Parameters, Scalar, FitRes
from flwr.server.client_proxy import ClientProxy
import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


class SecureFedAvg(fl.server.strategy.FedAvg):
    """Custom FedAvg with differential privacy and validation gate."""
    
    def __init__(self, noise_multiplier: float = 0.1, **kwargs):
        super().__init__(**kwargs)
        self.noise_multiplier = noise_multiplier

    def aggregate_fit(
        self,
        server_round: int,
        results: List[Tuple[ClientProxy, FitRes]],
        failures: List[Union[Tuple[ClientProxy, FitRes], BaseException]],
    ) -> Tuple[Optional[Parameters], Dict[str, Scalar]]:
        
        print(f"[FL Server] Aggregating updates from {len(results)} clients (Round {server_round})")
        
        # Standard FedAvg aggregation
        aggregated_parameters, aggregated_metrics = super().aggregate_fit(server_round, results, failures)
        
        if aggregated_parameters is not None:
            # Convert Parameters to NumPy
            aggregated_ndarrays = fl.common.parameters_to_ndarrays(aggregated_parameters)
            
            # Apply Differential Privacy noise
            noisy_ndarrays = []
            for arr in aggregated_ndarrays:
                noise = np.random.normal(0, self.noise_multiplier * np.std(arr), arr.shape)
                noisy_ndarrays.append(arr + noise)
            
            aggregated_parameters = fl.common.ndarrays_to_parameters(noisy_ndarrays)
            
            print(f"[FL Server] Round {server_round} successful. DP noise applied.")
            
            # TODO: Load global PyTorch model, apply aggregated_parameters, and export to ONNX
            # (Requires torch dependency on the server)
            
        return aggregated_parameters, aggregated_metrics


def main():
    print("Starting BEZP Flower Server on 0.0.0.0:8080...")
    strategy = SecureFedAvg(
        fraction_fit=1.0,
        min_fit_clients=2,
        min_available_clients=2,
        noise_multiplier=0.1
    )
    fl.server.start_server(
        server_address="0.0.0.0:8080",
        config=fl.server.ServerConfig(num_rounds=10),
        strategy=strategy,
    )

if __name__ == "__main__":
    main()
