"""Measurement harness: BER and simple round-trip reports (grows with each milestone)."""
from __future__ import annotations

import numpy as np


def ber(tx: np.ndarray, rx: np.ndarray) -> float:
    tx = tx.astype(np.uint8)
    rx = rx.astype(np.uint8)
    assert tx.shape == rx.shape, (tx.shape, rx.shape)
    return float(np.mean(tx != rx))
