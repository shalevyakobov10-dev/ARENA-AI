"""טעינת קונפיגורציה: YAML + משתני סביבה + אימות ערכים."""
from __future__ import annotations

import os
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

import yaml

try:  # dotenv אופציונלי
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "config.yaml"


class ConfigError(ValueError):
    pass


# --------------------------------------------------------------------------
#  סכימות (dataclasses)
# --------------------------------------------------------------------------
@dataclass
class ExecutionConfig:
    mode: str = "paper"
    starting_cash: float = 1000.0
    slippage_bps: float = 10.0
    taker_fee_bps: float = 0.0
    fee_mode: str = "model"        # model = נוסחת פולימרקט · off = עמלה שטוחה/אפס
    max_slippage_bps: float = 150.0
    order_type: str = "FAK"
    live_confirm_env: str = "PMMB_LIVE_CONFIRM"

    def validate(self) -> None:
        if self.fee_mode not in {"model", "off"}:
            raise ConfigError(f"execution.fee_mode לא חוקי: {self.fee_mode}")
        if self.mode not in {"paper", "live", "shadow"}:
            raise ConfigError(f"execution.mode לא חוקי: {self.mode}")
        if self.starting_cash <= 0:
            raise ConfigError("execution.starting_cash חייב להיות חיובי")


@dataclass
class UniverseConfig:
    max_markets: int = 120
    min_volume_24h: float = 5000
    min_liquidity: float = 2000
    max_spread: float = 0.04
    price_band: tuple[float, float] = (0.05, 0.95)
    min_hours_to_resolution: float = 6
    max_hours_to_resolution: float = 720
    exclude_tags: list[str] = field(default_factory=list)
    exclude_slug_contains: list[str] = field(default_factory=list)
    exclude_sectors: list[str] = field(default_factory=list)   # crypto / sports / politics ...
    require_order_book: bool = True


@dataclass
class ExitConfig:
    take_profit: float = 0.12
    stop_loss: float = 0.07
    time_stop_hours: float = 48
    exit_on_flip: bool = True


@dataclass
class MeanRevConfig:
    lookback_candles: int = 12       # חלון למדידת העודף
    z_entry: float = 1.5             # כמה סטיות תקן כדי להיחשב "עודף"
    z_max: float = 5.0               # מעל זה זו ידיעה חדשה, לא עודף — לא נוגעים
    reversion_ratio: float = 0.45    # איזה חלק מהעודף מתקן (נמדד אמפירית)
    max_room_pct: float = 0.6        # לא מהמרים על יותר מ-60% מהמקום עד הקצה
    allow_short: bool = False        # הצד העולה לא הראה היפוך אמין בדאטה
    horizon_hours: int = 24          # אופק האחזקה שנמדד (24 נרות שעתיים)
    trend_guard: bool = False        # מסנן הקשר-מגמה (מחקר: לא נמצא אמין עדיין)
    trend_window: int = 72           # חלון מדידת המגמה הארוכה
    trend_max_norm: float = 3.0      # צניחה בתוך מגמת עלייה חזקה מזה — מדלגים


@dataclass
class SignalConfig:
    engine: str = "meanrev"          # momentum | meanrev
    candle_fidelity_min: int = 5
    lookback_candles: int = 144
    ema_fast: int = 9
    ema_slow: int = 26
    breakout_window: int = 20
    momentum_window: int = 12
    vol_window: int = 30
    min_score: float = 0.55
    min_edge: float = 0.03
    confirm_candles: int = 2
    trend_filter: bool = True
    allow_short: bool = True
    meanrev: MeanRevConfig = field(default_factory=MeanRevConfig)
    exit: ExitConfig = field(default_factory=ExitConfig)

    def validate(self) -> None:
        if self.ema_fast >= self.ema_slow:
            raise ConfigError("signal.ema_fast חייב להיות קטן מ-ema_slow")
        need = max(self.ema_slow, self.breakout_window, self.vol_window, self.momentum_window)
        if self.lookback_candles < need + self.confirm_candles:
            raise ConfigError(
                f"signal.lookback_candles ({self.lookback_candles}) קטן מדי; "
                f"צריך לפחות {need + self.confirm_candles}"
            )
        if not 0 <= self.min_score <= 1:
            raise ConfigError("signal.min_score חייב להיות בין 0 ל-1")
        if self.engine not in ("momentum", "meanrev"):
            raise ConfigError(f"signal.engine לא מוכר: {self.engine}")


@dataclass
class RiskConfig:
    risk_per_trade_pct: float = 0.02
    kelly_fraction: float = 0.25
    max_position_pct: float = 0.10
    max_total_exposure_pct: float = 0.40
    max_open_positions: int = 5
    max_daily_loss_pct: float = 0.05
    max_drawdown_pct: float = 0.20
    cooldown_minutes: float = 30
    min_order_size: float = 5.0
    max_price_impact_pct: float = 0.02

    def validate(self) -> None:
        if self.max_position_pct > self.max_total_exposure_pct:
            raise ConfigError("max_position_pct לא יכול לעלות על max_total_exposure_pct")
        if self.risk_per_trade_pct <= 0 or self.risk_per_trade_pct > 0.25:
            raise ConfigError("risk_per_trade_pct צריך להיות בין 0 ל-0.25")


@dataclass
class DataConfig:
    gamma_base_url: str = "https://gamma-api.polymarket.com"
    clob_base_url: str = "https://clob.polymarket.com"
    http_timeout: float = 15.0
    max_retries: int = 3
    rate_limit_rps: float = 8.0
    history_cache_ttl_sec: float = 120.0
    db_path: str = "pmmb.db"
    record_books: bool = True      # אוסף snapshots של ספר הפקודות למחקר imbalance


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: str = "logs/pmmb.log"
    json_console: bool = False


@dataclass
class Config:
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    universe: UniverseConfig = field(default_factory=UniverseConfig)
    signal: SignalConfig = field(default_factory=SignalConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    data: DataConfig = field(default_factory=DataConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    # ---- טעינה ----
    @classmethod
    def load(cls, path: str | Path | None = None) -> "Config":
        p = Path(path) if path else DEFAULT_CONFIG
        raw: dict[str, Any] = {}
        if p.exists():
            with open(p, "r", encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or {}
        cfg = _build(cls, raw)
        cfg.apply_env()
        cfg.validate()
        return cfg

    def apply_env(self) -> None:
        """עקיפות מהירות מהסביבה, למשל PMMB_RISK_PER_TRADE_PCT=0.01"""
        overrides = {
            "PMMB_MODE": ("execution", "mode", str),
            "PMMB_STARTING_CASH": ("execution", "starting_cash", float),
            "PMMB_DB_PATH": ("data", "db_path", str),
            "PMMB_RISK_PER_TRADE_PCT": ("risk", "risk_per_trade_pct", float),
            "PMMB_MAX_OPEN_POSITIONS": ("risk", "max_open_positions", int),
            "PMMB_MIN_SCORE": ("signal", "min_score", float),
            "PMMB_MIN_EDGE": ("signal", "min_edge", float),
            "PMMB_LOG_LEVEL": ("logging", "level", str),
        }
        for env, (section, attr, caster) in overrides.items():
            val = os.getenv(env)
            if val not in (None, ""):
                try:
                    setattr(getattr(self, section), attr, caster(val))
                except (TypeError, ValueError) as exc:
                    raise ConfigError(f"ערך לא חוקי ל-{env}: {val}") from exc

    def validate(self) -> None:
        self.execution.validate()
        self.signal.validate()
        self.risk.validate()


# --------------------------------------------------------------------------
#  בניית dataclass מתוך dict (עם זיהוי שדות לא מוכרים)
# --------------------------------------------------------------------------
def _build(cls: type, data: dict[str, Any]):
    if not is_dataclass(cls):
        return data
    if not isinstance(data, dict):
        raise ConfigError(f"צריך mapping עבור {cls.__name__}, קיבלנו {type(data).__name__}")
    known = {f.name: f for f in fields(cls)}
    unknown = set(data) - set(known)
    if unknown:
        raise ConfigError(f"שדות לא מוכרים ב-{cls.__name__}: {sorted(unknown)}")

    kwargs: dict[str, Any] = {}
    for name, f in known.items():
        if name not in data:
            continue
        val = data[name]
        ftype = f.type if isinstance(f.type, str) else getattr(f.type, "__name__", str)

        nested = _nested_dataclass(f)
        if nested is not None and isinstance(val, dict):
            kwargs[name] = _build(nested, val)
        elif ftype in ("float", "int", "str", "bool"):
            kwargs[name] = {"float": float, "int": int, "str": str, "bool": bool}[ftype](val)
        elif ftype == "list" or isinstance(val, list):
            kwargs[name] = list(val)
        elif "tuple" in str(f.type):
            kwargs[name] = tuple(val)
        else:
            kwargs[name] = val
    return cls(**kwargs)


def _nested_dataclass(f) -> type | None:
    """מזהה שדה שהוא בעצמו dataclass (למשל Config.signal.exit)"""
    factory = getattr(f, "default_factory", None)
    if factory is not None:
        try:
            default = factory()
        except TypeError:
            return None
        if is_dataclass(default):
            return type(default)
    default = getattr(f, "default", None)
    if default is not None and is_dataclass(default):
        return type(default)
    return None
