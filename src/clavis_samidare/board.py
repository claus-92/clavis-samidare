import time
from dataclasses import replace
from typing import Any

from clavis.boards.base import AcquisitionBoard
from clavis.clients.base import RegisterClient
from clavis.core.errors import (
    BoardAlreadyAcquiringError,
    BoardAlreadyConnectedError,
    BoardConnectionError,
    BoardNotAcquiringError,
    BoardNotConnectedError,
    BoardNotPoweredError,
    InvalidParameterError,
)
from clavis.schemas import BoardMetadata, BoardStatus

from clavis_samidare.controls import (
    SamidareControlState,
    decode_pon,
    encode_pon,
    update_state,
)
from clavis_samidare.registers import (
    ACCEPTED_TRIGGER_COUNT_REGISTER,
    ACQUISITION_ARM_REGISTER,
    CALIBRATION_DEBUG_HIGH_REGISTER,
    CALIBRATION_DEBUG_LOW_REGISTER,
    CALIBRATION_DETAIL_STATUS_REGISTER,
    CALIBRATION_FAILED,
    CALIBRATION_FAILED_HIGH_REGISTER,
    CALIBRATION_FAILED_LOW_REGISTER,
    CALIBRATION_READY,
    CALIBRATION_STATE_MASK,
    CALIBRATION_STATE_SHIFT,
    CALIBRATION_STATUS_REGISTER,
    CAPTURE_ABI_MAGIC,
    CAPTURE_ABI_REGISTER,
    CAPTURE_STATUS_REGISTER,
    CAPTURE_STATUS_CLEAR_REGISTER,
    DELAY_ADJUST_INIT_REGISTER,
    EXPIRED_WINDOW_COUNT_REGISTER,
    FIFO_CAPACITY_DROP_COUNT_REGISTER,
    EVENT_SOURCE_REGISTER,
    LOCAL_START_REGISTER,
    PON_REGISTER,
    RECEIVER_STATUS_REGISTER,
    RUN_ACTIVE,
    RUN_ARMED,
    RUN_CAPTURE_PRIMED,
    RUN_CONFIG_FAULT,
    RUN_RECEIVER_READY,
    RUN_STATUS_REGISTER,
    REJECTED_BUSY_COUNT_REGISTER,
    SAMPA_RESET_REGISTER,
    SAMPA_RESET_REQUEST,
    START_SOURCE_REGISTER,
)

CALIBRATION_STATES = {
    0: "idle",
    1: "sweep",
    2: "apply",
    3: "lock",
}


class SamidareBoard(AcquisitionBoard):
    def __init__(
        self,
        metadata: BoardMetadata,
        client: RegisterClient,
        *,
        power_settle_time: float = 0.01,
        reset_settle_time: float = 0.01,
    ) -> None:
        self.metadata = metadata
        self.client = client
        self.connected = False
        self.acquiring = False
        self.calibration_ready = False
        self.calibration_status = 0
        self.calibration_debug = 0
        self.calibration_failed_mask = 0
        self.receiver_status = 0
        self.calibration_detail_status: int | None = None
        self.capture_abi: int | None = None
        self.capture_status = 0
        self.run_status = 0
        self.armed = False
        self.receiver_ready = False
        self.capture_primed = False
        self.config_fault = False
        self.accepted_trigger_count = 0
        self.rejected_busy_count = 0
        self.expired_window_count = 0
        self.fifo_capacity_drop_count = 0
        self.status_fresh = False
        self.status_error: str | None = None
        self.power_settle_time = power_settle_time
        self.reset_settle_time = reset_settle_time
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
        self.client.write_register(ACQUISITION_ARM_REGISTER, 0)
        self.acquiring = False
        self.armed = False
        self.client.write_register(DELAY_ADJUST_INIT_REGISTER, 0)
        self.calibration_ready = False
        self.calibration_status = 0
        self.calibration_debug = 0
        self.calibration_failed_mask = 0
        self.receiver_status = 0
        self.calibration_detail_status = None
        self.status_error = None
        self.state = SamidareControlState(**{**self.state.__dict__, "powered": True})
        self._write_pon()
        #time.sleep(self.power_settle_time)
        self.client.write_register(SAMPA_RESET_REGISTER, SAMPA_RESET_REQUEST)
        #time.sleep(self.reset_settle_time)
        self.client.write_register(DELAY_ADJUST_INIT_REGISTER, 1)

    def power_off(self) -> None:
        self._require_connected()
        self._refresh_hardware_status()
        self.client.write_register(ACQUISITION_ARM_REGISTER, 0)
        self.client.write_register(DELAY_ADJUST_INIT_REGISTER, 0)
        self.acquiring = False
        self.armed = False
        self.calibration_ready = False
        self.calibration_status = 0
        self.calibration_debug = 0
        self.calibration_failed_mask = 0
        self.receiver_status = 0
        self.calibration_detail_status = None
        self.state = SamidareControlState(**{**self.state.__dict__, "powered": False})
        self._write_pon()

    def arm_acquisition(self) -> None:
        self._require_connected()
        self._refresh_hardware_status()
        if self.armed:
            raise BoardAlreadyAcquiringError(f"SAMIDARE board is already armed: {self.get_id()}")
        if not self.state.powered:
            raise BoardNotPoweredError(f"SAMIDARE board is not powered: {self.get_id()}")
        self._write_sources()
        self.client.write_register(ACQUISITION_ARM_REGISTER, 1)
        self.armed = True

    def start_acquisition(self) -> None:
        self._require_connected()
        self._refresh_hardware_status()
        if not self.state.powered:
            raise BoardNotPoweredError(f"SAMIDARE board is not powered: {self.get_id()}")
        if not self.armed:
            raise BoardNotAcquiringError(f"SAMIDARE board is not armed: {self.get_id()}")
        if self.acquiring:
            raise BoardAlreadyAcquiringError(f"SAMIDARE board is already running: {self.get_id()}")
        if self.state.start_source != "local":
            raise InvalidParameterError(
                "A Fakernet start request requires start_source='local'; the selected external source starts the run"
            )
        if not self.receiver_ready:
            raise InvalidParameterError("SAMIDARE receiver is not ready; wait for receiver-ready status before starting")
        self.client.write_register(LOCAL_START_REGISTER, 1)
        self._refresh_hardware_status()

    def stop_acquisition(self) -> None:
        self._require_connected()
        if not self.armed:
            self._refresh_hardware_status()
        if not self.armed:
            raise BoardNotAcquiringError(f"SAMIDARE board is not armed: {self.get_id()}")
        self.client.write_register(ACQUISITION_ARM_REGISTER, 0)
        self.armed = False
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
        if self.armed and ({"start_source", "event_source"} & options.keys()):
            raise InvalidParameterError("start_source and event_source can only be changed while SAMIDARE is disarmed")
        try:
            self.state = update_state(self.state, options)
        except ValueError as exc:
            raise InvalidParameterError(str(exc)) from exc
        self._write_pon()
        self._write_sources()

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
        if self.capture_abi != CAPTURE_ABI_MAGIC:
            raise InvalidParameterError(
                "SAMIDARE firmware does not expose the required SAM3 ABI; refusing control write"
            )
        self.client.write_register(PON_REGISTER, encode_pon(self.state))

    def _write_sources(self) -> None:
        if self.capture_abi != CAPTURE_ABI_MAGIC:
            raise InvalidParameterError("SAMIDARE firmware does not expose the required SAM3 ABI; refusing source write")
        self.client.write_register(
            START_SOURCE_REGISTER,
            {"local": 0, "gpio0": 1, "mikumari": 2}[self.state.start_source],
        )
        self.client.write_register(
            EVENT_SOURCE_REGISTER,
            {"gpio1": 0, "mikumari": 1, "self": 2, "1khz": 3}[self.state.event_source],
        )

    def _refresh_hardware_status(self) -> None:
        capture_abi = self.client.read_register(CAPTURE_ABI_REGISTER)
        state = decode_pon(self.client.read_register(PON_REGISTER))
        run_status = self.client.read_register(RUN_STATUS_REGISTER)
        acquiring = bool(run_status & RUN_ACTIVE)
        calibration_status = self.client.read_register(CALIBRATION_STATUS_REGISTER)
        debug_low = self.client.read_register(CALIBRATION_DEBUG_LOW_REGISTER)
        debug_high = self.client.read_register(CALIBRATION_DEBUG_HIGH_REGISTER)
        failed_low = self.client.read_register(CALIBRATION_FAILED_LOW_REGISTER)
        failed_high = self.client.read_register(CALIBRATION_FAILED_HIGH_REGISTER)
        receiver_status = self.client.read_register(RECEIVER_STATUS_REGISTER)
        try:
            calibration_detail_status = self.client.read_register(CALIBRATION_DETAIL_STATUS_REGISTER)
        except Exception:  # noqa: BLE001
            # 0x5007 is absent on firmware built before the Phase-5 status-word
            # addition. Its absence must not invalidate the remaining snapshot.
            calibration_detail_status = None
        if capture_abi == CAPTURE_ABI_MAGIC:
            start_source = self.client.read_register(START_SOURCE_REGISTER)
            event_source = self.client.read_register(EVENT_SOURCE_REGISTER)
            state = replace(
                state,
                start_source={0: "local", 1: "gpio0", 2: "mikumari"}.get(start_source, "local"),
                event_source={0: "gpio1", 1: "mikumari", 2: "self", 3: "1khz"}.get(event_source, "gpio1"),
            )
            capture_status = self.client.read_register(CAPTURE_STATUS_REGISTER)
            accepted_trigger_count = self.client.read_register(ACCEPTED_TRIGGER_COUNT_REGISTER)
            rejected_busy_count = self.client.read_register(REJECTED_BUSY_COUNT_REGISTER)
            expired_window_count = self.client.read_register(EXPIRED_WINDOW_COUNT_REGISTER)
            fifo_capacity_drop_count = self.client.read_register(FIFO_CAPACITY_DROP_COUNT_REGISTER)
        else:
            capture_status = 0
            accepted_trigger_count = 0
            rejected_busy_count = 0
            expired_window_count = 0
            fifo_capacity_drop_count = 0
        self.state = state
        self.acquiring = acquiring
        self.calibration_status = calibration_status
        self.calibration_debug = debug_low | ((debug_high & 0xFFFFFF) << 32)
        self.calibration_failed_mask = failed_low | ((failed_high & 0xFF) << 32)
        self.receiver_status = receiver_status
        self.calibration_detail_status = calibration_detail_status
        self.capture_abi = capture_abi
        self.capture_status = capture_status
        self.run_status = run_status
        self.armed = bool(run_status & RUN_ARMED)
        self.receiver_ready = bool(run_status & RUN_RECEIVER_READY)
        self.capture_primed = bool(run_status & RUN_CAPTURE_PRIMED)
        self.config_fault = bool(run_status & RUN_CONFIG_FAULT)
        self.accepted_trigger_count = accepted_trigger_count
        self.rejected_busy_count = rejected_busy_count
        self.expired_window_count = expired_window_count
        self.fifo_capacity_drop_count = fifo_capacity_drop_count
        self.calibration_ready = bool(self.calibration_status & CALIBRATION_READY) and not bool(self.calibration_status & CALIBRATION_FAILED)
        self.status_fresh = True
        self.status_error = None

    def _calibration_options(self) -> dict[str, Any]:
        state = (self.calibration_status & CALIBRATION_STATE_MASK) >> CALIBRATION_STATE_SHIFT
        # 0x5003 carries cal_debug[55:32] in its low 24 bits.  Keep the
        # assembled value here, so these shifts are cal_debug bit positions,
        # not 0x5003 word bit positions.
        debug_state = (self.calibration_debug >> 38) & 0x3
        failed_lanes = [lane for lane in range(40) if self.calibration_failed_mask & (1 << lane)]
        failed_chip_bits = [f"{lane // 10}:{lane % 10}" for lane in failed_lanes]
        detail = self.calibration_detail_status
        return {
            "calibration_ready": self.calibration_ready,
            "calibration_failed": bool(self.calibration_status & CALIBRATION_FAILED),
            "calibration_state": CALIBRATION_STATES.get(state, f"unknown_{state}"),
            "calibration_status_raw": f"0x{self.calibration_status:08x}",
            "calibration_debug_start": bool(self.calibration_debug & (1 << 55)),
            "calibration_debug_idelay_ready": bool(self.calibration_debug & (1 << 54)),
            "calibration_done": bool(self.calibration_debug & (1 << 53)),
            "calibration_debug_failed": bool(self.calibration_debug & (1 << 52)),
            "calibration_debug_clock_failed_mask": f"0x{(self.calibration_debug >> 48) & 0xF:x}",
            "calibration_debug_locked_mask": f"0x{(self.calibration_debug >> 44) & 0xF:x}",
            "calibration_debug_sync_error_mask": f"0x{(self.calibration_debug >> 40) & 0xF:x}",
            "calibration_debug_state": CALIBRATION_STATES.get(debug_state, f"unknown_{debug_state}"),
            "calibration_sweep_done": bool(self.calibration_debug & (1 << 37)),
            "calibration_measure_valid": bool(self.calibration_debug & (1 << 36)),
            "calibration_sweep_tap_index": (self.calibration_debug >> 27) & 0x1FF,
            "calibration_lock_state": f"0x{(self.calibration_debug >> 15) & 0xFFF:03x}",
            "calibration_epoch_sync_debug_mask": f"0x{(self.calibration_debug >> 11) & 0xF:x}",
            "calibration_data_done_mask": f"0x{self.calibration_debug & 0x7FF:03x}",
            "calibration_failed_lane_mask": f"0x{self.calibration_failed_mask:010x}",
            "calibration_failed_lanes": failed_lanes,
            "calibration_failed_chip_bits": failed_chip_bits,
            "receiver_locked_mask": f"0x{self.receiver_status & 0xF:x}",
            "receiver_trigger_pending_mask": f"0x{(self.receiver_status >> 4) & 0xF:x}",
            "receiver_sync_error_mask": f"0x{(self.receiver_status >> 8) & 0xF:x}",
            "receiver_fifo_empty_mask": f"0x{(self.receiver_status >> 12) & 0xF:x}",
            "receiver_fifo_full_mask": f"0x{(self.receiver_status >> 16) & 0xF:x}",
            "calibration_detail_status_available": detail is not None,
            "calibration_detail_status_raw": None if detail is None else f"0x{detail:08x}",
            "calibration_locked_mask": None if detail is None else f"0x{detail & 0xF:x}",
            "calibration_sync_error_mask": None if detail is None else f"0x{(detail >> 4) & 0xF:x}",
            "calibration_clock_failed_mask": None if detail is None else f"0x{(detail >> 8) & 0xF:x}",
            "calibration_idelay_ready": None if detail is None else bool(detail & (1 << 12)),
            "calibration_active": None if detail is None else bool(detail & (1 << 13)),
            "calibration_trigger_enabled": None if detail is None else bool(detail & (1 << 14)),
            "calibration_start": None if detail is None else bool(detail & (1 << 15)),
            # These bits were added after the rest of 0x5007.  A firmware
            # without the whole word reports None rather than a false result.
            "calibration_terminal_valid": None if detail is None else bool(detail & (1 << 16)),
            "calibration_terminal_failed": None if detail is None else bool(detail & (1 << 17)),
            "capture_abi_compatible": self.capture_abi == CAPTURE_ABI_MAGIC,
            "capture_abi_raw": None if self.capture_abi is None else f"0x{self.capture_abi:08x}",
            "run_status_raw": f"0x{self.run_status:08x}",
            "run_armed": self.armed,
            "run_active": self.acquiring,
            "run_receiver_ready": self.receiver_ready,
            "run_capture_primed": self.capture_primed,
            "run_config_fault": self.config_fault,
            "capture_event_busy": bool(self.capture_status & 0x1),
            "capture_active_trigger_mode": (self.capture_status >> 1) & 0x3,
            "capture_invalid_rate_fault": bool(self.capture_status & (1 << 3)),
            "capture_expired_window_sticky": bool(self.capture_status & (1 << 4)),
            "capture_fifo_capacity_drop_sticky": bool(self.capture_status & (1 << 5)),
            "capture_fifo_capacity_ok": bool(self.capture_status & (1 << 6)),
            "capture_accepted_trigger_count": self.accepted_trigger_count,
            "capture_rejected_busy_count": self.rejected_busy_count,
            "capture_expired_window_count": self.expired_window_count,
            "capture_fifo_capacity_drop_count": self.fifo_capacity_drop_count,
            "status_error": self.status_error,
        }

    def clear_capture_status(self) -> None:
        self._require_connected()
        if self.capture_abi != CAPTURE_ABI_MAGIC:
            raise InvalidParameterError("capture status is unavailable on this firmware")
        self.client.write_register(CAPTURE_STATUS_CLEAR_REGISTER, 1)

    def _calibration_summary(self) -> str:
        options = self._calibration_options()
        return (
            f"status={options['calibration_status_raw']} state={options['calibration_state']} "
            f"clock_failed={options['calibration_debug_clock_failed_mask']} data_done={options['calibration_data_done_mask']} "
            f"failed_lanes={options['calibration_failed_chip_bits']}"
        )
