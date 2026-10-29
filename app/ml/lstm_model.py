"""LSTM Model for Regime Classification"""
import logging
from typing import Dict, Tuple

import torch
import torch.nn as nn

logger = logging.getLogger(__name__)


class RegimeLSTM(nn.Module):
    """LSTM classifier for market regime prediction."""

    def __init__(
        self,
        input_size: int,
        hidden_size: int = 64,
        num_layers: int = 2,
        num_classes: int = 3,
        dropout: float = 0.3,
    ):
        super().__init__()

        self.input_size = input_size
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.num_classes = num_classes

        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0,
        )

        self.fc = nn.Linear(hidden_size, num_classes)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass."""
        lstm_out, _ = self.lstm(x)
        last_hidden = lstm_out[:, -1, :]
        dropped = self.dropout(last_hidden)
        logits = self.fc(dropped)
        return logits

    def predict_proba(self, x: torch.Tensor) -> torch.Tensor:
        """Predict class probabilities."""
        self.eval()
        with torch.no_grad():
            logits = self.forward(x)
            probs = torch.softmax(logits, dim=1)
        return probs

    def predict(self, x: torch.Tensor) -> torch.Tensor:
        """Predict class labels."""
        probs = self.predict_proba(x)
        return torch.argmax(probs, dim=1)
