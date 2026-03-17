"""Curated prediction-market relationships monitored by Antilego.

The definitions remain in the recovered collector for historical provenance. This
module exposes them through the Antilego package so production imports do not
depend on the process's current working directory.
"""

from .recovered_collector.families import FAMILIES

__all__ = ["FAMILIES"]
