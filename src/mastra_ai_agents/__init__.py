"""ASI swarm orchestration for Hermes sub-agents.

The public surface is small on purpose: a graph engine, the swarm layer that plans and judges,
and the three stores it persists through.
"""

from .blackboard import Blackboard
from .consensus import merge, rank, vote
from .engine import Orchestrator
from .memory import Memory
from .policy import Policy
from .store import RunStore
from .swarm import Swarm, build_graph, choose_template, templates
from .types import Recall, Run, Step

__version__ = "2.0.0"

__all__ = [
    "Blackboard",
    "Memory",
    "Orchestrator",
    "Policy",
    "Recall",
    "Run",
    "RunStore",
    "Step",
    "Swarm",
    "build_graph",
    "choose_template",
    "merge",
    "rank",
    "templates",
    "vote",
    "__version__",
]
