import asyncio
import time
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Union, Any

import lighter
from lighter.ws_client import WsClient

from hummingbot.connector.derivative.lighter_perpetual import lighter_perpetual_constants as CONSTANTS, lighter_perpetual_utils
from hummingbot.connector.derivative.lighter_perpetual.lighter_perpetual_api_order_book_data_source import LighterPerpetualAPIOrderBookDataSource
from hummingbot.connector.derivative.lighter_perpetual.lighter_perpetual_user_stream_data_source import LighterPerpetualUserStreamDataSource
from hummingbot.connector.perpetual_derivative_py_base import PerpetualDerivativePyBase
from hummingbot.connector.derivative.position import Position
from hummingbot.core.data_type.common import OrderType, PositionAction, PositionMode, TradeType, PositionSide
from hummingbot.core.data_type.in_flight_order import PerpetualDerivativeInFlightOrder, OrderState
from hummingbot.core.data_type.trade_fee import TradeFeeBase, TokenAmount
from hummingbot.core.utils.async_utils import safe_ensure_future, safe_gather
from hummingbot.logger import HummingbotLogger
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.auth import AuthBase


class LighterPerpetualDerivative(PerpetualDerivativePyBase):
    _logger = None

    def __init__(
        self,
        lighter_api_key_private_key: str,
        lighter_account_index: int = 0,
        lighter_api_key_index: int = 0,
        trading_pairs: Optional[List[str]] = None,
        trading_required: bool = True,
        domain: str = CONSTANTS.EXCHANGE_NAME,
        **kwargs,
    ):
        self._lighter_api_key_private_key = lighter_api_key_private_key
        self._lighter_account_index = lighter_account_index
        self._lighter_api_key_index = lighter_api_key_index
        self._domain = domain
        self._trading_required = trading_required

        self._api_private_keys = {self._lighter_api_key_index: self._lighter_api_key_private_key}

        self._signer_client: Optional[lighter.SignerClient] = None
        self._api_client: Optional[lighter.ApiClient] = None

        self._market_id_map: Dict[str, int] = {}
        self._id_market_map: Dict[int, str] = {}

        self._trading_pairs = trading_pairs if trading_pairs else []

        super().__init__(kwargs.get("balance_asset_limit"), kwargs.get("rate_limits_share_pct"))

        if trading_pairs:
            for trading_pair in trading_pairs:
                self._perpetual_trading.add_trading_pair(trading_pair)

    @property
    def name(self) -> str:
        return CONSTANTS.EXCHANGE_NAME

    @property
    def auth_keys(self):
        return self._api_private_keys

    @property
    def funding_fee_poll_interval(self) -> int:
        return 120

    @property
    def client_order_id_max_length(self):
        return 32

    @property
    def client_order_id_prefix(self):
        return "HBOT"

    @property
    def trading_rules_request_path(self):
        return ""

    @property
    def trading_pairs_request_path(self):
        return ""

    @property
    def check_network_request_path(self):
        return ""

    @property
    def is_cancel_request_in_exchange_synchronous(self) -> bool:
        return True

    @property
    def is_trading_required(self) -> bool:
        return self._trading_required

    @property
    def authenticator(self):
        return None

    @property
    def rate_limits_rules(self):
        return CONSTANTS.RATE_LIMITS

    @property
    def domain(self):
        return self._domain

    @property
    def trading_pairs(self):
        return self._trading_pairs

    @property
    def supported_order_types(self):
        return [OrderType.LIMIT, OrderType.MARKET]

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = HummingbotLogger(__name__)
        return cls._logger

    def _create_web_assistants_factory(self) -> WebAssistantsFactory:
        return WebAssistantsFactory(throttler=self._throttler)

    def _create_user_stream_data_source(self) -> LighterPerpetualUserStreamDataSource:
        return LighterPerpetualUserStreamDataSource(
            lighter_api_key_private_key=self._lighter_api_key_private_key,
            lighter_account_index=self._lighter_account_index,
            lighter_api_key_index=self._lighter_api_key_index,
            domain=self._domain
        )

    def _user_stream_event_listener(self):
        return None

    def _is_request_exception_related_to_time_synchronizer(self, request_exception: Exception):
        return False

    def _is_order_not_found_during_status_update_error(self, status_update_exception: Exception) -> bool:
        return False

    def _is_order_not_found_during_cancelation_error(self, cancelation_exception: Exception) -> bool:
        return False

    async def _format_trading_rules(self, exchange_info_dict: Dict[str, Any]) -> List:
        return []

    async def _initialize_trading_pair_symbols_from_exchange_info(self, exchange_info: Dict[str, Any]):
        await self._update_market_map()

    async def _update_trading_fees(self):
        pass

    async def _all_trade_updates_for_order(self, order: PerpetualDerivativeInFlightOrder) -> List[TradeType]:
        return []

    async def _request_order_status(self, order: PerpetualDerivativeInFlightOrder) -> OrderState:
        return OrderState.OPEN

    async def _place_cancel(self, order_id: str, tracked_order: PerpetualDerivativeInFlightOrder):
        await self._cancel_order(order_id, tracked_order.trading_pair)
        return True

    async def start_network(self):
        await super().start_network()
        if not self._api_client:
            self._api_client = lighter.ApiClient()

        if self._trading_required and not self._signer_client:
             url = lighter.Configuration().host
             self._signer_client = lighter.SignerClient(
                 url=url,
                 account_index=self._lighter_account_index,
                 api_private_keys=self._api_private_keys
             )

        await self._update_market_map()

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
            self.logger().error(f"Error fetching market map: {e}")

    async def stop_network(self):
        await super().stop_network()
        if self._api_client:
            await self._api_client.close()
        if self._signer_client:
            await self._signer_client.close()

    async def check_network(self) -> str:
        try:
            if self._api_client:
                root_api = lighter.RootApi(self._api_client)
                await root_api.status()
        except Exception:
            return "Network status check failed"
        return "Network status check successful"

    def supported_position_modes(self) -> List[PositionMode]:
        return [PositionMode.ONEWAY]

    def get_buy_collateral_token(self, trading_pair: str) -> str:
        return "USDC"

    def get_sell_collateral_token(self, trading_pair: str) -> str:
        return "USDC"

    def _create_order_book_data_source(self) -> LighterPerpetualAPIOrderBookDataSource:
        return LighterPerpetualAPIOrderBookDataSource(
            trading_pairs=self.trading_pairs,
            domain=self._domain,
            api_factory=None,
            throttler=self._throttler,
        )

    async def _place_order(
        self,
        order_id: str,
        trading_pair: str,
        amount: Decimal,
        trade_type: TradeType,
        order_type: OrderType,
        price: Decimal,
        position_action: PositionAction = PositionAction.NIL,
        **kwargs,
    ) -> Tuple[str, float]:
        if not self._signer_client:
            raise RuntimeError("Signer client not initialized")

        symbol = self._trading_pair_to_symbol(trading_pair)
        market_id = self._market_id_map.get(symbol)
        if market_id is None:
            await self._update_market_map()
            market_id = self._market_id_map.get(symbol)
            if market_id is None:
                raise ValueError(f"Market ID not found for {trading_pair}")

        is_ask = (trade_type == TradeType.SELL)

        lighter_order_type = lighter.ORDER_TYPE_LIMIT
        if order_type == OrderType.MARKET:
            lighter_order_type = lighter.ORDER_TYPE_MARKET

        tif = lighter.ORDER_TIME_IN_FORCE_GOOD_TILL_TIME

        client_order_index = int(time.time() * 1000) % 2147483647

        try:
            result = await self._signer_client.create_order(
                market_index=market_id,
                client_order_index=client_order_index,
                base_amount=float(amount),
                price=float(price),
                is_ask=is_ask,
                order_type=lighter_order_type,
                time_in_force=tif,
                reduce_only=(position_action == PositionAction.CLOSE),
                api_key_index=self._lighter_api_key_index
            )
            created_order, resp, error = result

            if error:
                 self.logger().error(f"Error placing order: {error}")
                 raise RuntimeError(f"Lighter order placement failed: {error}")

            return order_id, self.current_timestamp

        except Exception as e:
            self.logger().error(f"Exception placing order: {e}")
            raise

    async def _cancel_order(self, order_id: str, trading_pair: str) -> bool:
        if not self._signer_client:
            return False

        in_flight_order = self._order_tracker.fetch_order(client_order_id=order_id)
        if in_flight_order and in_flight_order.exchange_order_id:
             try:
                 symbol = self._trading_pair_to_symbol(trading_pair)
                 market_id = self._market_id_map.get(symbol)
                 if market_id is None:
                     return False

                 await self._signer_client.cancel_order(
                     market_index=market_id,
                     order_index=int(in_flight_order.exchange_order_id),
                     api_key_index=self._lighter_api_key_index
                 )
                 return True
             except Exception as e:
                 self.logger().error(f"Error cancelling order: {e}")
        return False

    async def _update_balances(self):
        try:
            account_api = lighter.AccountApi(self._api_client)
            account_response = await account_api.account(by="index", value=str(self._lighter_account_index))
            if not account_response.accounts:
                return
            account = account_response.accounts[0]

            self._account_balances.clear()
            self._account_available_balances.clear()

            for asset in account.assets:
                symbol = asset.symbol
                balance = Decimal(str(asset.balance))
                locked = Decimal(str(asset.locked_balance))
                available = balance - locked

                self._account_balances[symbol] = balance
                self._account_available_balances[symbol] = available

        except Exception as e:
            self.logger().error(f"Error updating balances: {e}")

    async def _update_positions(self):
        try:
            account_api = lighter.AccountApi(self._api_client)
            account_response = await account_api.account(by="index", value=str(self._lighter_account_index))
            if not account_response.accounts:
                return
            account = account_response.accounts[0]

            for pos in account.positions:
                symbol = pos.symbol
                trading_pair = self._symbol_to_trading_pair(symbol)

                amount = Decimal(str(pos.position))
                if amount == 0:
                    continue

                entry_price = Decimal(str(pos.avg_entry_price))
                unrealized_pnl = Decimal(str(pos.unrealized_pnl))

                leverage = Decimal("1")
                imf = Decimal(str(pos.initial_margin_fraction))
                if imf > 0:
                    leverage = Decimal("1") / imf

                position = Position(
                    trading_pair=trading_pair,
                    position_side=PositionSide.LONG if amount > 0 else PositionSide.SHORT,
                    unrealized_pnl=unrealized_pnl,
                    entry_price=entry_price,
                    amount=abs(amount),
                    leverage=leverage
                )
                pos_key = self._perpetual_trading.position_key(trading_pair, position.position_side)
                self._perpetual_trading.set_position(pos_key, position)

        except Exception as e:
            self.logger().error(f"Error updating positions: {e}")

    async def _fetch_last_fee_payment(self, trading_pair: str) -> Tuple[float, Decimal, Decimal]:
        return 0, Decimal("0"), Decimal("0")

    def _get_fee(
        self,
        base_currency: str,
        quote_currency: str,
        order_type: OrderType,
        order_side: TradeType,
        position_action: PositionAction,
        amount: Decimal,
        price: Decimal = Decimal("NaN"),
        is_maker: Optional[bool] = None,
    ) -> TradeFeeBase:
        return lighter_perpetual_utils.DEFAULT_FEES

    async def _trading_pair_position_mode_set(self, mode: PositionMode, trading_pair: str) -> Tuple[bool, str]:
        if mode == PositionMode.ONEWAY:
            return True, ""
        return False, "Only ONEWAY position mode is supported"

    async def _set_trading_pair_leverage(self, trading_pair: str, leverage: int) -> Tuple[bool, str]:
        if self._signer_client:
             try:
                 symbol = self._trading_pair_to_symbol(trading_pair)
                 market_id = self._market_id_map.get(symbol)
                 if market_id:
                     await self._signer_client.update_leverage(
                         market_index=market_id,
                         leverage=leverage,
                         api_key_index=self._lighter_api_key_index
                     )
                     return True, ""
             except Exception as e:
                 return False, str(e)
        return False, "Signer client not initialized"

    def _trading_pair_to_symbol(self, trading_pair: str) -> str:
        return trading_pair.split("-")[0]

    def _symbol_to_trading_pair(self, symbol: str) -> str:
        return f"{symbol}-USDC"
