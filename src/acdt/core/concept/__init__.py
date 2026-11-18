"""Conceptual operations / architecture-trade primitives (deterministic, cited) for AI-driven concept studies.

The AI agent turns a free-text problem into a mission, requirements and alternatives; these modules only
*calculate* (mission geometry, search and detection, availability and fleet reliability, multi-criteria
comparison, study record). No module chooses an architecture. See docs/ai-concept-trade.md.
"""
from . import geo, ops, reliability, search, study, tradeoff  # noqa: F401
