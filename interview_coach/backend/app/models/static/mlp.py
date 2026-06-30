"""MLP for static alphabet and digit recognition."""

from typing import List

import torch.nn as nn


class StaticSignMLP(nn.Module):
    def __init__(
        self,
        input_dim: int = 63,
        hidden_dims: List[int] | None = None,
        num_classes: int = 34,
        dropout: float = 0.2,
    ):
        super().__init__()
        hidden_dims = hidden_dims or [128, 64]
        layers: list[nn.Module] = []
        prev = input_dim
        for hidden in hidden_dims:
            layers.extend([nn.Linear(prev, hidden), nn.ReLU(), nn.Dropout(dropout)])
            prev = hidden
        layers.append(nn.Linear(prev, num_classes))
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x)