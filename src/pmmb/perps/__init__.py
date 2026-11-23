"""
חבילת PERPS של PMMB — מנוע מסחר מקצועי בחוזים תמידיים (Perpetual Futures) עד מינוף ×50.

מאפיינים עיקריים:
  - מתאם רב-בורסות: OKX (עד 50x-100x) + Hyperliquid DEX (40x / 235 נכסים) + Binance Futures
  - מנוע סיגנל רב-מצבי (Multi-Regime): ADX+ER Trend Pullback + Mean-Reversion + Funding/OI + Macro News
  - ניהול סיכונים של סוחר עלית: Isolated Margin, Dynamic Leverage עד ×50, Liquidation Buffer Guard, ATR Trailing Stop
  - סימולציית Paper חיה על L2 + Backtest + 3-Fold Walk-Forward + Self-Learning
"""
from .models import (
    PerpBook,
    PerpCandle,
    PerpFill,
    PerpInstrument,
    PerpOrder,
    PerpPosition,
    PerpSignal,
)

__all__ = [
    "PerpBook",
    "PerpCandle",
    "PerpFill",
    "PerpInstrument",
    "PerpOrder",
    "PerpPosition",
    "PerpSignal",
]
