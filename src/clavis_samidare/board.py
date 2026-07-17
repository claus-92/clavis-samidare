import time
from typing import Any

from clavis.boards.base import AcquisitionBoard
from clavis.clients.base import RegisterClient
from clavis.core.errors import BoardAlreadyAcquiringError, BoardAlreadyConnectedError, BoardConnectionError, BoardNotAcquiringError, BoardNotConnectedError, BoardNotPoweredError, InvalidParameterError
from clavis.schemas import BoardMetadata, BoardStatus
from clavis_samidare.controls import SamidareControlState, decode_pon, encode_pon, update_state
from clavis_samidare.registers import CALIBRATION_FAILED, CALIBRATION_READY, CALIBRATION_STATUS_REGISTER, DELAY_ADJUST_INIT_REGISTER, LEGACY_START_REGISTER, LEGACY_START_VALUE, PON_REGISTER, SAMPA_RESET_REGISTER, SAMPA_RESET_REQUEST, TRIGGER_ENABLE_REGISTER


class SamidareBoard(AcquisitionBoard):
    def __init__(
        self,
        metadata: BoardMetadata,
        client: RegisterClient,
        *,
        power_settle_time: float = 2.2,
        reset_settle_time: float = 0.01,
        calibration_timeout: float = 15.0,
        calibration_poll_interval: float = 0.05,
    ) -> None:
        self.metadata = metadata
        self.client = client
        self.connected = False
        self.acquiring = False
        self.calibration_ready = False
        self.power_settle_time = power_settle_time
        self.reset_settle_time = reset_settle_time
        self.calibration_timeout = calibration_timeout
        self.calibration_poll_interval = calibration_poll_interval
        self.state = SamidareControlState()
        self.group_options: dict[str, dict[str, Any]] = {}
        self.channel_options: dict[str, dict[str, Any]] = {}

    def connect(self) -> None:
        if self.connected:
            raise BoardAlreadyConnectedError(f"Board already connected: {self.get_id()}")
        try:
            self.client.open()
            self.state = decode_pon(self.client.read_register(PON_REGISTER))
        except Exception as exc:
            self.connected = False
            self.acquiring = False
            self.calibration_ready = False
            self.state = SamidareControlState()
            try:
                self.client.close()
            except Exception:
                pass
            raise BoardConnectionError(f"Failed to connect SAMIDARE board {self.get_id()}: {exc}") from exc
        self.connected = True

    def disconnect(self) -> None:
        if not self.connected:
            raise BoardNotConnectedError(f"Board not connected: {self.get_id()}")
        close_error: Exception | None = None
        try:
            self.client.close()
        except Exception as exc:
            close_error = exc
        finally:
            self.connected = False
            self.acquiring = False
            self.calibration_ready = False
            self.state = SamidareControlState()
        if close_error is not None:
            raise BoardConnectionError(f"Failed to disconnect SAMIDARE board {self.get_id()}: {close_error}") from close_error

    def power_on(self) -> None:
        self._require_connected()
        self.client.write_register(TRIGGER_ENABLE_REGISTER, 0)
        self.client.write_register(DELAY_ADJUST_INIT_REGISTER, 0)
        self.calibration_ready = False
        self.state = SamidareControlState(**{**self.state.__dict__, "powered": True})
        self._write_pon()
        time.sleep(self.power_settle_time)
        self.client.write_register(SAMPA_RESET_REGISTER, SAMPA_RESET_REQUEST)
        time.sleep(self.reset_settle_time)
        self.client.write_register(DELAY_ADJUST_INIT_REGISTER, 1)
        self._wait_for_calibration()

    def power_off(self) -> None:
        self._require_connected()
        self.client.write_register(TRIGGER_ENABLE_REGISTER, 0)
        self.client.write_register(DELAY_ADJUST_INIT_REGISTER, 0)
        self.acquiring = False
        self.calibration_ready = False
        self.state = SamidareControlState(**{**self.state.__dict__, "powered": False})
        self._write_pon()

    def start_acquisition(self) -> None:
        self._require_connected()
        if not self.state.powered:
            raise BoardNotPoweredError(f"SAMIDARE board is not powered: {self.get_id()}")
        if self.acquiring:
            raise BoardAlreadyAcquiringError(f"SAMIDARE board is already acquiring: {self.get_id()}")
        status = self.client.read_register(CALIBRATION_STATUS_REGISTER)
        if not status & CALIBRATION_READY or status & CALIBRATION_FAILED:
            self.calibration_ready = False
            raise BoardConnectionError(f"SAMIDARE board is not calibration-ready: status=0x{status:08x}")
        self.client.write_register(LEGACY_START_REGISTER, LEGACY_START_VALUE)
        self.client.write_register(TRIGGER_ENABLE_REGISTER, 1)
        self.acquiring = True

    def stop_acquisition(self) -> None:
        self._require_connected()
        if not self.acquiring:
            raise BoardNotAcquiringError(f"SAMIDARE board is not acquiring: {self.get_id()}")
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
            global_options={**self.state.as_options(), "calibration_ready": self.calibration_ready},
            group_options=self.group_options,
            channel_options=self.channel_options,
        )

    def _require_connected(self) -> None:
        if not self.connected:
            raise BoardNotConnectedError(f"Board not connected: {self.get_id()}")

    def _write_pon(self) -> None:
        self.client.write_register(PON_REGISTER, encode_pon(self.state))

    def _wait_for_calibration(self) -> None:
        deadline = time.monotonic() + self.calibration_timeout
        last_status = 0
        while time.monotonic() < deadline:
            last_status = self.client.read_register(CALIBRATION_STATUS_REGISTER)
            if last_status & CALIBRATION_FAILED:
                raise BoardConnectionError(f"SAMIDARE calibration failed: status=0x{last_status:08x}")
            if last_status & CALIBRATION_READY:
                self.calibration_ready = True
                return
            time.sleep(self.calibration_poll_interval)
        raise BoardConnectionError(f"SAMIDARE calibration timed out: status=0x{last_status:08x}")
