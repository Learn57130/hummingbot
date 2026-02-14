from decimal import Decimal
from typing import Dict, List, Optional, Set, Any

from pydantic import Field, field_validator

from hummingbot.client.config.config_data_types import BaseClientModel
from hummingbot.strategy.strategy_v2_base import StrategyV2ConfigBase
from hummingbot.data_feed.candles_feed.data_types import CandlesConfig


class VwapMeanReversionConfig(StrategyV2ConfigBase):
    strategy_name: str = "vwap_mean_reversion"

    timeframe: str = Field(
        default="1h",
        json_schema_extra={
            "prompt": "Enter candles timeframe (5m, 30m, 1h, 4h):",
            "prompt_on_new": True,
        }
    )
    risk_per_trade: Decimal = Field(
        default=Decimal("0.02"),
        json_schema_extra={
            "prompt": "Enter risk per trade (e.g. 0.02 for 2%):",
            "prompt_on_new": True,
        }
    )
    max_active_positions: int = Field(
        default=2,
        json_schema_extra={
            "prompt": "Enter max active positions:",
            "prompt_on_new": True,
        }
    )
    atr_length: int = Field(
        default=14,
        json_schema_extra={
            "prompt": "Enter ATR length (default 14):",
            "prompt_on_new": True,
        }
    )
    stop_loss_multiplier: Decimal = Field(
        default=Decimal("1.5"),
        json_schema_extra={
            "prompt": "Enter Stop Loss Multiplier (x ATR) (default 1.5):",
            "prompt_on_new": True,
        }
    )
    sma_length: int = Field(
        default=100,
        json_schema_extra={
            "prompt": "Enter SMA Length (default 100):",
            "prompt_on_new": True,
        }
    )

    entry_z_score: Decimal = Field(default=Decimal("-2.5"), description="Z-score entry threshold")
    exit_z_score: Decimal = Field(default=Decimal("0.0"), description="Z-score exit threshold")
    fallback_sl_z_score: Decimal = Field(default=Decimal("-3.0"), description="Fallback SL Z-score")

    candles_config: List[CandlesConfig] = Field(
        default=[],
        json_schema_extra={
            "prompt": "Enter candles config (optional, usually auto-generated):",
            "prompt_on_new": False,
        }
    )

    @field_validator("timeframe")
    @classmethod
    def validate_timeframe(cls, v: str) -> str:
        if v not in ["5m", "30m", "1h", "4h"]:
            raise ValueError("Timeframe must be one of: 5m, 30m, 1h, 4h")
        return v
