from hummingbot.strategy.vwap_mean_reversion.vwap_mean_reversion import VwapMeanReversion
from hummingbot.strategy.vwap_mean_reversion.vwap_mean_reversion_config_map import VwapMeanReversionConfig
from decimal import Decimal

def start(self):
    # self is HummingbotApplication instance

    # Convert config map to Pydantic model
    config_map = self.strategy_config_map

    try:
        config = VwapMeanReversionConfig(**config_map)
    except Exception as e:
        self.notify(f"Invalid configuration: {e}")
        return

    connectors = self.connectors

    self.strategy = VwapMeanReversion(connectors=connectors, config=config)
    self.strategy.start(clock=self.clock, timestamp=self.clock.current_timestamp)
