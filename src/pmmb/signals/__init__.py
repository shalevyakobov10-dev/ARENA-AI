"""מנועי סיגנלים. כל מנוע מממש את SignalEngine (Protocol ב-base.py)."""
from __future__ import annotations

from ..config import SignalConfig
from .meanrev import MeanReversionEngine
from .momentum import MomentumEngine

ENGINES = {"momentum": MomentumEngine, "meanrev": MeanReversionEngine}


def build_signal_engine(cfg: SignalConfig):
    """בונה את המנוע לפי signal.engine — נקודת ההחלפה היחידה בקוד."""
    cls = ENGINES.get(cfg.engine)
    if cls is None:
        raise ValueError(f"מנוע לא מוכר: {cfg.engine} (אפשרי: {sorted(ENGINES)})")
    return cls(cfg)
