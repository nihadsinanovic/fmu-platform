"""CVode solver configuration for Assimulo."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SolverConfig:
    """Configuration for the Assimulo CVode solver."""

    solver: str = "CVode"
    rtol: float = 1e-6
    atol: float = 1e-8
    max_order: int = 5
    max_steps: int = 100000
    initial_step: float = 1e-4

    @classmethod
    def from_dict(cls, data: dict) -> SolverConfig:
        return cls(
            solver=data.get("solver", "CVode"),
            rtol=data.get("rtol", 1e-6),
            atol=data.get("atol", 1e-8),
            max_order=data.get("max_order", 5),
            max_steps=data.get("max_steps", 100000),
            initial_step=data.get("initial_step", 1e-4),
        )
