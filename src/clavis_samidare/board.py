from typing import Any

from clavis.boards.base import AcquisitionBoard
from clavis.clients.base import RegisterClient
from clavis.core.errors import BoardAlreadyAcquiringError, BoardAlreadyConnectedError, BoardNotAcquiringError, BoardNotConnectedError, BoardNotPoweredError, InvalidParameterError
from clavis.schemas import BoardMetadata, BoardStatus
from clavis_samidare.controls import SamidareControlState, decode_pon, encode_pon, update_state
from clavis_samidare.registers import DELAY_ADJUST_INIT_REGISTER, LEGACY_START_REGISTER, LEGACY_START_VALUE, PON_REGISTER, TRIGGER_ENABLE_REGISTER


class SamidareBoard(AcquisitionBoard):
    def __init__(self, metadata: BoardMetadata, client: RegisterClient) -> None:
        self.metadata = metadata
        self.client = client
        self.connected = False
        self.acquiring = False
        self.state = SamidareControlState()
        self.group_options: dict[str, dict[str, Any]] = {}
        self.channel_options: dict[str, dict[str, Any]] = {}

    def connect(self) -> None:
        if self.connected:
            raise BoardAlreadyConnectedError(f"Board already connected: {self.get_id()}")
        self.client.open()
        self.state = decode_pon(self.client.read_register(PON_REGISTER))
        self.connected = True

    def disconnect(self) -> None:
        if not self.connected:
            raise BoardNotConnectedError(f"Board not connected: {self.get_id()}")
        self.client.close()
        self.connected = False
        self.acquiring = False
        self.state = SamidareControlState()

    def power_on(self) -> None:
        self._require_connected()
        self.state = SamidareControlState(**{**self.state.__dict__, "powered": True})
        self._write_pon()

    def power_off(self) -> None:
        self._require_connected()
        self.acquiring = False
        self.state = SamidareControlState(**{**self.state.__dict__, "powered": False})
        self._write_pon()

    def start_acquisition(self) -> None:
        self._require_connected()
        if not self.state.powered:
            raise BoardNotPoweredError(f"SAMIDARE board is not powered: {self.get_id()}")
        if self.acquiring:
            raise BoardAlreadyAcquiringError(f"SAMIDARE board is already acquiring: {self.get_id()}")
        self.client.write_register(DELAY_ADJUST_INIT_REGISTER, 1)
        self.client.write_register(TRIGGER_ENABLE_REGISTER, 1)
        self.client.write_register(LEGACY_START_REGISTER, LEGACY_START_VALUE)
        self.acquiring = True

    def stop_acquisition(self) -> None:
        self._require_connected()
        if not self.acquiring:
            raise BoardNotAcquiringError(f"SAMIDARE board is not acquiring: {self.get_id()}")
        self.client.write_register(DELAY_ADJUST_INIT_REGISTER, 0)
        self.client.write_register(TRIGGER_ENABLE_REGISTER, 0)
        self.acquiring = False

    def set_channel(self, channel_id: str, options: dict[str, Any]) -> None:
        self._require_connected()
        self.channel_options.setdefault(channel_id, {}).update(options)

    def set_group(self, group_id: str, options: dict[str, Any]) -> None:
        self._require_connected()
        self.group_options.setdefault(group_id, {}).update(options)

    def set_global(self, options: dict[str, Any]) -> None:
        self._require_connected()
        try:
            self.state = update_state(self.state, options)
        except ValueError as exc:
            raise InvalidParameterError(str(exc)) from exc
        self._write_pon()

    def get_id(self) -> str:
        return self.metadata.board_id

    def get_status(self) -> BoardStatus:
        return BoardStatus(
            board_id=self.get_id(),
            connected=self.connected,
            powered=self.state.powered,
            acquiring=self.acquiring,
            global_options=self.state.as_options(),
            group_options=self.group_options,
            channel_options=self.channel_options,
        )

    def _require_connected(self) -> None:
        if not self.connected:
            raise BoardNotConnectedError(f"Board not connected: {self.get_id()}")

    def _write_pon(self) -> None:
        self.client.write_register(PON_REGISTER, encode_pon(self.state))
