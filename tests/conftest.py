"""Pytest configuration and shared fixtures."""

import sys
import os

# Add project root to sys.path so `detection` and `api` are importable
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)
