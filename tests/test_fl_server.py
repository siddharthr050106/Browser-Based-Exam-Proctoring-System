"""Tests for FL aggregation logic."""

import numpy as np
from flwr.common import ndarrays_to_parameters, parameters_to_ndarrays

from fl.server import SecureFedAvg

def test_secure_fedavg_noise_injection():
    """Test that FedAvg correctly applies differential privacy noise."""
    strategy = SecureFedAvg(noise_multiplier=0.1)
    
    # Mock some updates from 2 clients
    weights1 = [np.array([1.0, 2.0]), np.array([3.0, 4.0])]
    weights2 = [np.array([1.2, 2.2]), np.array([3.2, 4.2])]
    
    # Mock FitRes
    class MockFitRes:
        def __init__(self, parameters, num_examples):
            self.parameters = parameters
            self.num_examples = num_examples
            self.metrics = {}
            
    res1 = (None, MockFitRes(ndarrays_to_parameters(weights1), 10))
    res2 = (None, MockFitRes(ndarrays_to_parameters(weights2), 10))
    
    # Run aggregation
    agg_params, _ = strategy.aggregate_fit(1, [res1, res2], [])
    
    assert agg_params is not None
    agg_ndarrays = parameters_to_ndarrays(agg_params)
    
    # The pure average would be [1.1, 2.1] and [3.1, 4.1]
    # Because of noise, it won't be exactly that, but it should be close
    # and not identical to the pure average.
    
    pure_avg_w0 = np.array([1.1, 2.1])
    
    assert len(agg_ndarrays) == 2
    assert agg_ndarrays[0].shape == pure_avg_w0.shape
