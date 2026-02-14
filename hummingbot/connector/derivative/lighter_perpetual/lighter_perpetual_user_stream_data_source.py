import asyncio
from typing import Optional
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.logger import HummingbotLogger
import lighter
from lighter.ws_client import WsClient

class LighterPerpetualUserStreamDataSource(UserStreamTrackerDataSource):
    _logger: Optional[HummingbotLogger] = None

    def __init__(self,
                 lighter_api_key_private_key: str,
                 lighter_account_index: int = 0,
                 lighter_api_key_index: int = 0,
                 domain: str = "lighter"):
        super().__init__()
        self._lighter_api_key_private_key = lighter_api_key_private_key
        self._lighter_account_index = lighter_account_index
        self._lighter_api_key_index = lighter_api_key_index
        self._domain = domain
        self._ws_client = None

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = HummingbotLogger(__name__)
        return cls._logger

    @property
    def last_recv_time(self) -> float:
        return 0

    async def listen_for_user_stream(self, output: asyncio.Queue):
        try:
            host = lighter.Configuration().host.replace("https://", "").replace("http://", "")

            def on_account_update(update):
                output.put_nowait(update)

            self._ws_client = WsClient(
                host=host,
                path='/stream',
                account_ids=[self._lighter_account_index],
                on_account_update=on_account_update
            )

            await self._ws_client.run_async()

        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.logger().error(f"Error in user stream: {e}")
            await asyncio.sleep(5.0)  # Retry delay
