"""Pure authoritative gameplay simulation. Standard library only.

Public seam for Alan's adapter:

    from simulation import Simulation, Assignment, LegsCommand, Vec2

Run the synthetic runner from the repo root:

    PYTHONPATH=backend python -m simulation.synthetic
"""

from .engine import Simulation
from .types import (
    ArmsCommand,
    Assignment,
    BallDTO,
    CharacterDTO,
    InputRejected,
    LegsCommand,
    PhaseChanged,
    ResultDTO,
    RolesChanged,
    Score,
    SimEvent,
    SimulationError,
    StateDTO,
    Vec2,
)

__all__ = [
    "ArmsCommand",
    "Assignment",
    "BallDTO",
    "CharacterDTO",
    "InputRejected",
    "LegsCommand",
    "PhaseChanged",
    "ResultDTO",
    "RolesChanged",
    "Score",
    "SimEvent",
    "Simulation",
    "SimulationError",
    "StateDTO",
    "Vec2",
]
