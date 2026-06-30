"""OSINT Defensive Trigger Engine — self-protection perimeter for research agents."""

from osint_engine.engine import (
    TriggerDecision,
    TriggerEngine,
    evaluate_osint_trigger,
)
from osint_engine.config import EngineConfig, load_config

__all__ = [
    "TriggerDecision",
    "TriggerEngine",
    "evaluate_osint_trigger",
    "EngineConfig",
    "load_config",
]
