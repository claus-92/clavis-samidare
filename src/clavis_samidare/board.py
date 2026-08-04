import time
from typing import Any

from clavis.boards.base import AcquisitionBoard
from clavis.clients.base import RegisterClient
from clavis.core.errors import BoardAlreadyAcquiringError, BoardAlreadyConnectedError, BoardConnectionError, BoardNotAcquiringError, BoardNotConnectedError, BoardNotPoweredError, InvalidParameterError
from clavis.schemas import BoardMetadata, BoardStatus
from clavis_samidare.controls import SamidareControlState, decode_pon, encode_pon, update_state
from clavis_samidare.registers import CALIBRATION_DEBUG_HIGH_REGISTER, CALIBRATION_DEBUG_LOW_REGISTER, CALIBRATION_FAILED, CALIBRATION_INCOMPLETE_HIGH_REGISTER, CALIBRATION_INCOMPLETE_LOW_REGISTER, CALIBRATION_READY, CALIBRATION_STATE_MASK, CALIBRATION_STATE_SHIFT, CALIBRATION_STATUS_REGISTER, DELAY_ADJUST_INIT_REGISTER, PON_REGISTER, SAMPA_RESET_REGISTER, SAMPA_RESET_REQUEST, TRIGGER_ENABLE_REGISTER


CALIBRATION_STATES = {
    0: "idle",
    1: "clock_adjust",
    2: "signal_adjust",
    3: "done",
}


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
        self.calibration_status = 0
        self.calibration_debug = 0
        self.calibration_incomplete = 0
        self.status_fresh = False
        self.status_error: str | None = None
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
            self._refresh_hardware_status()
        except Exception as exc:
            self.connected = False
            self.status_fresh = False
            self.status_error = str(exc)
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
            self.status_fresh = False
        if close_error is not None:
            raise BoardConnectionError(f"Failed to disconnect SAMIDARE board {self.get_id()}: {close_error}") from close_error

    def power_on(self) -> None:
        self._require_connected()
        self._refresh_hardware_status()
        self.client.write_register(TRIGGER_ENABLE_REGISTER, 0)
        self.acquiring = False
        self.client.write_register(DELAY_ADJUST_INIT_REGISTER, 0)
        self.calibration_ready = False
        self.calibration_status = 0
        self.calibration_debug = 0
        self.calibration_incomplete = 0
        self.status_error = None
        self.state = SamidareControlState(**{**self.state.__dict__, "powered": True})
        self._write_pon()
        time.sleep(self.power_settle_time)
        self.client.write_register(SAMPA_RESET_REGISTER, SAMPA_RESET_REQUEST)
        time.sleep(self.reset_settle_time)
        self.client.write_register(DELAY_ADJUST_INIT_REGISTER, 1)
        self._wait_for_calibration()

    def power_off(self) -> None:
        self._require_connected()
        self._refresh_hardware_status()
        self.client.write_register(TRIGGER_ENABLE_REGISTER, 0)
        self.client.write_register(DELAY_ADJUST_INIT_REGISTER, 0)
        self.acquiring = False
        self.calibration_ready = False
        self.calibration_status = 0
        self.calibration_debug = 0
        self.calibration_incomplete = 0
        self.state = SamidareControlState(**{**self.state.__dict__, "powered": False})
        self._write_pon()

    def start_acquisition(self) -> None:
        self._require_connected()
        self._refresh_hardware_status()
        if not self.state.powered:
            raise BoardNotPoweredError(f"SAMIDARE board is not powered: {self.get_id()}")
        if self.acquiring:
            raise BoardAlreadyAcquiringError(f"SAMIDARE board is already acquiring: {self.get_id()}")
        status = self.calibration_status
        if not status & CALIBRATION_READY or status & CALIBRATION_FAILED:
            self.calibration_ready = False
            raise BoardConnectionError(f"SAMIDARE board is not calibration-ready: {self._calibration_summary()}")
        self.client.write_register(TRIGGER_ENABLE_REGISTER, 1)
        self.acquiring = True

    def stop_acquisition(self) -> None:
        self._require_connected()
        self._refresh_hardware_status()
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
        self._refresh_hardware_status()
        requested_clock = options.get("clock_source")
        if self.state.powered and requested_clock is not None and requested_clock != self.state.clock_source:
            raise InvalidParameterError("clock_source can only be changed while SAMIDARE is powered off")
        try:
            self.state = update_state(self.state, options)
        except ValueError as exc:
            raise InvalidParameterError(str(exc)) from exc
        self._write_pon()

    def get_id(self) -> str:
        return self.metadata.board_id

    def get_status(self) -> BoardStatus:
        if self.connected:
            try:
                self._refresh_hardware_status()
            except Exception as exc:
                self.status_fresh = False
                self.status_error = str(exc)
        return BoardStatus(
            board_id=self.get_id(),
            connected=self.connected,
            powered=self.state.powered,
            acquiring=self.acquiring,
            status_fresh=self.status_fresh,
            global_options={**self.state.as_options(), **self._calibration_options()},
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
            self.calibration_status = last_status
            if last_status & CALIBRATION_FAILED:
                self._refresh_hardware_status()
                raise BoardConnectionError(f"SAMIDARE calibration failed: {self._calibration_summary()}")
            if last_status & CALIBRATION_READY:
                self._refresh_hardware_status()
                return
            time.sleep(self.calibration_poll_interval)
        self._refresh_hardware_status()
        raise BoardConnectionError(f"SAMIDARE calibration timed out: {self._calibration_summary()}")

    def _refresh_hardware_status(self) -> None:
        state = decode_pon(self.client.read_register(PON_REGISTER))
        acquiring = bool(self.client.read_register(TRIGGER_ENABLE_REGISTER) & 0x1)
        calibration_status = self.client.read_register(CALIBRATION_STATUS_REGISTER)
        debug_low = self.client.read_register(CALIBRATION_DEBUG_LOW_REGISTER)
        debug_high = self.client.read_register(CALIBRATION_DEBUG_HIGH_REGISTER)
        incomplete_low = self.client.read_register(CALIBRATION_INCOMPLETE_LOW_REGISTER)
        incomplete_high = self.client.read_register(CALIBRATION_INCOMPLETE_HIGH_REGISTER)
        self.state = state
        self.acquiring = acquiring
        self.calibration_status = calibration_status
        self.calibration_debug = debug_low | ((debug_high & 0xFFFFFF) << 32)
        self.calibration_incomplete = incomplete_low | ((incomplete_high & 0xFF) << 32)
        self.calibration_ready = bool(self.calibration_status & CALIBRATION_READY) and not bool(self.calibration_status & CALIBRATION_FAILED)
        self.status_fresh = True
        self.status_error = None

    def _calibration_options(self) -> dict[str, Any]:
        state = (self.calibration_status & CALIBRATION_STATE_MASK) >> CALIBRATION_STATE_SHIFT
        return {
            "calibration_ready": self.calibration_ready,
            "calibration_failed": bool(self.calibration_status & CALIBRATION_FAILED),
            "calibration_state": CALIBRATION_STATES.get(state, f"unknown_{state}"),
            "calibration_status_raw": f"0x{self.calibration_status:08x}",
            "calibration_init": bool(self.calibration_debug & 0x1),
            "calibration_clock_done_mask": f"0x{(self.calibration_debug >> 3) & 0xF:x}",
            "calibration_lane_done_mask": f"0x{(self.calibration_debug >> 7) & ((1 << 40) - 1):010x}",
            "calibration_done": bool(self.calibration_debug & (1 << 47)),
            "calibration_incomplete_lane_state": f"0x{(self.calibration_debug >> 48) & 0xFF:02x}",
            "calibration_incomplete_lane_index": (self.calibration_incomplete >> 33) & 0x3F,
            "calibration_incomplete_timeout": (self.calibration_incomplete >> 17) & 0xFFFF,
            "calibration_incomplete_current_tap": (self.calibration_incomplete >> 8) & 0x1FF,
            "calibration_incomplete_cdc": f"0x{self.calibration_incomplete & 0xFF:02x}",
            "status_error": self.status_error,
        }

    def _calibration_summary(self) -> str:
        options = self._calibration_options()
        return (
            f"status={options['calibration_status_raw']} state={options['calibration_state']} "
            f"clock_done={options['calibration_clock_done_mask']} lane_done={options['calibration_lane_done_mask']} "
            f"incomplete_lane={options['calibration_incomplete_lane_index']}"
        )
