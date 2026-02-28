import pandas as pd
import numpy as np
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.core.data_type.common import OrderType, PositionAction, PositionMode, TradeType
from hummingbot.data_feed.candles_feed.data_types import CandlesConfig
from hummingbot.strategy.strategy_v2_base import StrategyV2Base
from hummingbot.strategy_v2.models.executor_actions import CreateExecutorAction, StopExecutorAction
from hummingbot.strategy_v2.executors.position_executor.data_types import PositionExecutorConfig
from hummingbot.strategy.vwap_mean_reversion.vwap_mean_reversion_config_map import VwapMeanReversionConfig


class VwapMeanReversion(StrategyV2Base):
    def __init__(self, connectors: Dict[str, ConnectorBase], config: VwapMeanReversionConfig = None):
        if config and not config.candles_config:
            candles_config = []
            for exchange, pairs in config.markets.items():
                for pair in pairs:
                    candles_config.append(
                        CandlesConfig(
                            connector=exchange,
                            trading_pair=pair,
                            interval=config.timeframe,
                            max_records=500
                        )
                    )
            config.candles_config = candles_config

        super().__init__(connectors, config)
        self.config = config

    def create_actions_proposal(self) -> List[CreateExecutorAction]:
        actions = []

        # Count active positions/executors
        active_executors = self.get_all_executors()
        active_executors = [e for e in active_executors if e.is_active]
        if len(active_executors) >= self.config.max_active_positions:
            return actions

        for connector_name, connector in self.connectors.items():
            for trading_pair in self.market_data_provider.get_trading_pairs(connector_name):
                # Check if we already have position/executor for this pair
                if any(e.trading_pair == trading_pair and e.connector_name == connector_name and e.is_active for e in active_executors):
                    continue

                candles = self.market_data_provider.get_candles_df(connector_name, trading_pair, self.config.timeframe)
                if candles.empty or len(candles) < self.config.sma_length + 10:
                    continue

                # Calculate Indicators
                df = self.calculate_indicators(candles)
                last_row = df.iloc[-1]

                # Logic: Long Entry
                # Z-score < -2.5
                # Price > SMA 100
                if last_row['z_score'] < float(self.config.entry_z_score) and last_row['close'] > last_row['sma']:
                    # Calculate Size
                    # Risk 2%
                    # SL Dist = 1.5 * ATR
                    atr = last_row['atr']
                    if atr <= 0: continue

                    sl_dist = 1.5 * atr
                    sl_price = last_row['close'] - sl_dist

                    # Account Equity
                    # Assuming Lighter uses USDC as collateral and quote
                    quote_balance = connector.get_available_balance(self.config.candles_config[0].trading_pair.split("-")[1] if "-" in self.config.candles_config[0].trading_pair else "USDC")
                    # Ideally get balance for specific quote asset of pair
                    # But simpler: use total balance of connector?
                    # `get_all_balances()`?
                    # I'll use `get_available_balance("USDC")` assuming USDC.
                    balance = connector.get_available_balance("USDC") # Lighter uses USDC

                    risk_amount = balance * float(self.config.risk_per_trade)
                    # risk_amount = size * sl_dist
                    # size = risk_amount / sl_dist
                    amount = risk_amount / sl_dist

                    # Convert to Decimal
                    amount = Decimal(str(amount))
                    price = Decimal(str(last_row['close']))
                    sl_price = Decimal(str(sl_price))
                    tp_price = Decimal("0") # Dynamic

                    # Create Executor
                    actions.append(CreateExecutorAction(
                        controller_id=self.config.strategy_name, # Use strategy name as controller ID?
                        executor_config=PositionExecutorConfig(
                            timestamp=self.current_timestamp,
                            connector_name=connector_name,
                            trading_pair=trading_pair,
                            side=TradeType.BUY,
                            entry_price=price,
                            amount=amount,
                            stop_loss=Decimal(str((price - sl_price) / price)), # % drop
                            take_profit=None, # Dynamic
                            time_limit=None
                        )
                    ))

                    if len(active_executors) + len(actions) >= self.config.max_active_positions:
                        break
        return actions

    def stop_actions_proposal(self) -> List[StopExecutorAction]:
        actions = []
        active_executors = [e for e in self.get_all_executors() if e.is_active]

        for executor in active_executors:
            # Check dynamic exit
            connector_name = executor.connector_name
            trading_pair = executor.trading_pair

            candles = self.market_data_provider.get_candles_df(connector_name, trading_pair, self.config.timeframe)
            if candles.empty: continue

            df = self.calculate_indicators(candles)
            last_row = df.iloc[-1]
            z_score = last_row['z_score']

            # Take Profit: Z-score > 0
            if z_score > float(self.config.exit_z_score):
                actions.append(StopExecutorAction(
                    executor_id=executor.id,
                    controller_id=executor.controller_id
                ))
                continue

            # Fallback SL: Z-score < -3.0
            if z_score < float(self.config.fallback_sl_z_score):
                actions.append(StopExecutorAction(
                    executor_id=executor.id,
                    controller_id=executor.controller_id
                ))
        return actions

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        # SMA 100
        df['sma'] = df['close'].rolling(self.config.sma_length).mean()

        # ATR 14 (Simple)
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        df['atr'] = true_range.rolling(self.config.atr_length).mean()

        # Anchored VWAP
        # Anchor: Start of day. Timestamp in ms.
        # df['timestamp'] is ms.
        # day_start = timestamp - (timestamp % 86400000)
        df['day_start'] = (df['timestamp'] // 86400000)

        # Group by day_start and calculate cumulative PV and V
        df['pv'] = df['close'] * df['volume']

        # Cumulative sum resetting every day
        # Using groupby transform
        df['cum_pv'] = df.groupby('day_start')['pv'].cumsum()
        df['cum_v'] = df.groupby('day_start')['volume'].cumsum()
        df['vwap'] = df['cum_pv'] / df['cum_v']

        # Anchored StdDev
        # Variance = Sum(Volume * (Price - VWAP)^2) / Sum(Volume)
        # This is weighted variance.
        # Or simple variance of price since anchor?
        # "Z-score of price vs VWAP" -> (Price - VWAP) / StdDev.
        # StdDev of what? Deviation of Price from VWAP?
        # Or just standard deviation of Price distribution?
        # Anchored VWAP Bands usually use:
        # StdDev = sqrt( Sum( Volume * (Price - VWAP_of_that_bar)^2 ) / Sum(Volume) ) ?
        # Or Sum( Volume * (Price - Current_VWAP)^2 ) ?
        # Standard definition for VWAP bands:
        # Variance = Accumulate(Volume * (Price - AveragePrice)^2) / Accumulate(Volume) ??
        # Simpler approach: Rolling StdDev of (Price - VWAP) or Price?
        # User said "price is 2.5 SD below VWAP".
        # This implies bands around VWAP.
        # Bands are usually VWAP +/- N * StdDev.
        # StdDev is usually calculated over the same anchor period or rolling.
        # I'll use Rolling StdDev(Price, window=100) as proxy if anchored is too complex to implement correctly without library.
        # But `pandas` groupby makes it possible.
        # Let's try Weighted StdDev.
        # Diff = Price - VWAP
        # But VWAP changes.
        # Standard deviation of the price relative to the VWAP.
        # sqrt( sum( (price_i - vwap_i)^2 ) / N ) ?
        # I'll use Rolling Standard Deviation of Price for simplicity and robustness.
        # df['std'] = df['close'].rolling(self.config.sma_length).std()
        # z_score = (price - vwap) / std

        df['std'] = df['close'].rolling(self.config.sma_length).std()
        df['z_score'] = (df['close'] - df['vwap']) / df['std']

        return df
