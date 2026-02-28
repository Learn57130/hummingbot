from hummingbot.core.api_throttler.data_types import RateLimit

EXCHANGE_NAME = "lighter_perpetual"

# URLs - Not strictly used if SDK handles it, but good for reference
BASE_URL = "https://mainnet.zklighter.elliot.ai"
WS_URL = "wss://mainnet.zklighter.elliot.ai/ws"

# Timeouts
API_CALL_TIMEOUT = 10.0
WS_HEARTBEAT_TIME_INTERVAL = 30.0

# Rate Limits (Placeholder)
RATE_LIMITS = [
    RateLimit(limit_id="default", limit=100, time_interval=1),
]

# Order Types Mapping
ORDER_TYPE_MAP = {
    "LIMIT": "LIMIT",
    "MARKET": "MARKET",
}
