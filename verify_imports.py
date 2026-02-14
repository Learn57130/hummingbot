import sys
import os
import asyncio

# Adjust path
sys.path.append(os.getcwd())

async def main():
    print("Testing imports...")
    try:
        from hummingbot.connector.derivative.lighter_perpetual.lighter_perpetual_derivative import LighterPerpetualDerivative
        print("Connector imported successfully.")
    except Exception as e:
        print(f"Connector import failed: {e}")
        import traceback
        traceback.print_exc()

    try:
        from hummingbot.strategy.vwap_mean_reversion.vwap_mean_reversion import VwapMeanReversion
        from hummingbot.strategy.vwap_mean_reversion.vwap_mean_reversion_config_map import VwapMeanReversionConfig
        print("Strategy imported successfully.")

        # Test Config Instantiation
        config = VwapMeanReversionConfig(markets={"lighter_perpetual": {"ETH-USDC"}}, timeframe="1h")
        print("Config instantiated.")
        print(f"Candles config: {config.candles_config}")

    except Exception as e:
        print(f"Strategy import/config failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
