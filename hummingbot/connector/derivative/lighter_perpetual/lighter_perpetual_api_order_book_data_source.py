import asyncio
import time
from typing import Dict, List, Optional, Any

import lighter
from lighter.ws_client import WsClient
from hummingbot.connector.derivative.lighter_perpetual import lighter_perpetual_constants as CONSTANTS
from hummingbot.core.data_type.common import TradeType
from hummingbot.core.data_type.funding_info import FundingInfo
from hummingbot.core.data_type.order_book_message import OrderBookMessage, OrderBookMessageType
from hummingbot.core.data_type.perpetual_api_order_book_data_source import PerpetualAPIOrderBookDataSource
from hummingbot.logger import HummingbotLogger


class LighterPerpetualAPIOrderBookDataSource(PerpetualAPIOrderBookDataSource):
    _logger: Optional[HummingbotLogger] = None

    def __init__(
        self,
        trading_pairs: List[str],
        domain: str = CONSTANTS.EXCHANGE_NAME,
        api_factory=None,
        throttler=None,
    ):
        super().__init__(trading_pairs)
        self._domain = domain
        self._api_factory = api_factory
        self._throttler = throttler
        self._api_client = lighter.ApiClient()
        self._market_id_map: Dict[str, int] = {}
        self._id_market_map: Dict[int, str] = {}

        self._diff_messages_queue: Optional[asyncio.Queue] = None
        self._trade_messages_queue: Optional[asyncio.Queue] = None
        self._snapshot_messages_queue: Optional[asyncio.Queue] = None
        self._ws_client = None

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = HummingbotLogger(__name__)
        return cls._logger

    async def get_last_traded_prices(self, trading_pairs: List[str], domain: Optional[str] = None) -> Dict[str, float]:
        prices = {}
        if not self._market_id_map:
             await self._update_market_map()

        try:
             order_api = lighter.OrderApi(self._api_client)
             for pair in trading_pairs:
                 symbol = pair.split("-")[0]
                 market_id = self._market_id_map.get(symbol)
                 if market_id:
                     trades = await order_api.recent_trades(market_id=market_id, limit=1)
                     if trades:
                         prices[pair] = float(trades[0].price)
        except Exception as e:
             self.logger().error(f"Error fetching last traded prices: {e}")
        return prices

    async def get_funding_info(self, trading_pair: str) -> FundingInfo:
        return FundingInfo(
            trading_pair=trading_pair,
            index_price=0,
            mark_price=0,
            next_funding_utc_timestamp=0,
            rate=0,
        )

    async def _update_market_map(self):
        try:
            order_api = lighter.OrderApi(self._api_client)
            books = await order_api.order_books()
            for book in books:
                symbol = book.symbol
                market_id = book.market_id
                self._market_id_map[symbol] = market_id
                self._id_market_map[market_id] = symbol
        except Exception as e:
            self.logger().error(f"Error updating market map: {e}")

    async def _request_order_book_snapshot(self, trading_pair: str) -> Dict[str, Any]:
        if not self._market_id_map:
            await self._update_market_map()

        symbol = trading_pair.split("-")[0]
        market_id = self._market_id_map.get(symbol)
        if not market_id:
            return {}

        order_api = lighter.OrderApi(self._api_client)
        details = await order_api.order_book_details(market_id=market_id)

        return {
            "trading_pair": trading_pair,
            "bids": [[float(b.price), float(b.amount)] for b in details.bids],
            "asks": [[float(a.price), float(a.amount)] for a in details.asks],
            "nonce": int(time.time() * 1000)
        }

    async def listen_for_subscriptions(self):
        pass # Started lazily

    async def listen_for_order_book_diffs(self, ev_loop: asyncio.AbstractEventLoop, output: asyncio.Queue):
        self._diff_messages_queue = output
        if not self._ws_client:
            await self._start_ws_client()

    async def listen_for_trades(self, ev_loop: asyncio.AbstractEventLoop, output: asyncio.Queue):
        self._trade_messages_queue = output
        if not self._ws_client:
             await self._start_ws_client()

    async def listen_for_funding_info(self, output: asyncio.Queue):
        pass

    async def _start_ws_client(self):
        if self._ws_client: return

        await self._update_market_map()
        market_ids = [self._market_id_map.get(p.split("-")[0]) for p in self.trading_pairs]
        market_ids = [m for m in market_ids if m is not None]

        host = lighter.Configuration().host.replace("https://", "").replace("http://", "")

        def on_order_book_update(update):
            market_id = update.market_id
            symbol = self._id_market_map.get(market_id)
            if not symbol: return
            pair = f"{symbol}-USDC"

            # Assuming update contains nonce/timestamp
            ts = time.time()

            msg = OrderBookMessage(
                message_type=OrderBookMessageType.SNAPSHOT, # Lighter seems to send full snapshots? Or check if diff.
                content={
                    "trading_pair": pair,
                    "bids": [[float(b.price), float(b.amount)] for b in update.bids],
                    "asks": [[float(a.price), float(a.amount)] for a in update.asks],
                    "update_id": getattr(update, "nonce", int(ts * 1000)),
                },
                timestamp=ts
            )
            if self._diff_messages_queue:
                self._diff_messages_queue.put_nowait(msg)

            # If update contains trades?
            # If not, ignore trades queue for now.

        self._ws_client = WsClient(
            host=host,
            path='/stream',
            order_book_ids=market_ids,
            on_order_book_update=on_order_book_update
        )

        asyncio.create_task(self._ws_client.run_async())
