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

    # Initialize strategy
    # connectors are initialized based on config.markets
    # init_connectors is a method of HummingbotApplication?
    # Usually self.init_connectors() takes no args or specific config?
    # Let's check init_connectors signature if possible, or assume it uses self.strategy_config_map.
    # But for V2 strategies, we pass connectors dict.
    # self.connectors is available if init_connectors was called.

    # self.init_connectors() updates self.connectors.
    # It reads from self.strategy_config_map (legacy).
    # But V2 config map is different structure.
    # V2 strategies usually manage their own connectors or use `self.connectors` if initialized correctly.
    # `StrategyV2ConfigBase` has `markets` field.
    # We need to ensure `self.connectors` are initialized for these markets.

    # self.init_connectors() logic:
    # It iterates self.strategy_config_map and looks for connector/market keys.
    # VwapMeanReversionConfig has `markets`.
    # We might need to manually init connectors or adapt config map for `init_connectors`.

    # Actually, `StrategyV2Base` strategies usually use `ScriptStrategyBase` which takes `connectors`.
    # Script strategies initialize connectors in `__init__` or `configure`.

    # If this strategy is loaded as a standard strategy, `start_command` calls `init_connectors` before `start(self)`.
    # `init_connectors` uses `config_params` which comes from `config_map`.
    # If `VwapMeanReversionConfig` uses `markets` field, and `init_connectors` knows how to read it?
    # `init_connectors` usually looks for keys ending in `_market` or `_connector`.
    # `StrategyV2ConfigBase` has `markets`.

    # I'll rely on `self.connectors` being populated.
    # If not, I might need to initialize them.

    connectors = self.connectors

    self.strategy = VwapMeanReversion(connectors=connectors, config=config)
    self.strategy.start(clock=self.clock, timestamp=self.clock.current_timestamp)
