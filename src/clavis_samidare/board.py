from typing import Any

from clavis.boards.base import AcquisitionBoard
from clavis.clients.base import RegisterClient
from clavis.core.errors import BoardAlreadyConnectedError, BoardNotConnectedError
from clavis.schemas import BoardMetadata, BoardStatus


class SamidareBoard(AcquisitionBoard):
    def __init__(self, metadata: BoardMetadata, client: RegisterClient) -> None:
        self.metadata = metadata
        self.client = client
        self.connected = False
        self.powered = False
        self.global_options: dict[str, Any] = {}
        self.group_options: dict[str, dict[str, Any]] = {}
        self.channel_options: dict[str, dict[str, Any]] = {}

    def connect(self) -> None:
        if self.connected:
            raise BoardAlreadyConnectedError(f"Board already connected: {self.get_id()}")
        self.client.open()
        self.connected = True

    def disconnect(self) -> None:
        if not self.connected:
            raise BoardNotConnectedError(f"Board not connected: {self.get_id()}")
        self.client.close()
        self.connected = False
        self.powered = False

    def power_on(self) -> None:
        self._require_connected()
        self.powered = True

    def power_off(self) -> None:
        self._require_connected()
        self.powered = False

    def set_channel(self, channel_id: str, options: dict[str, Any]) -> None:
        self._require_connected()
        self.channel_options.setdefault(channel_id, {}).update(options)

    def set_group(self, group_id: str, options: dict[str, Any]) -> None:
        self._require_connected()
        self.group_options.setdefault(group_id, {}).update(options)

    def set_global(self, options: dict[str, Any]) -> None:
        self._require_connected()
        self.global_options.update(options)

    def get_id(self) -> str:
        return self.metadata.board_id

    def get_status(self) -> BoardStatus:
        return BoardStatus(
            board_id=self.get_id(),
            connected=self.connected,
            powered=self.powered,
            global_options=self.global_options,
            group_options=self.group_options,
            channel_options=self.channel_options,
        )

    def _require_connected(self) -> None:
        if not self.connected:
            raise BoardNotConnectedError(f"Board not connected: {self.get_id()}")
