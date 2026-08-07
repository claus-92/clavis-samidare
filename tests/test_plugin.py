import pytest

from clavis.clients.fakernet import FakernetRegisterClient
from clavis.clients.fake import FakeRegisterClient
from clavis.core.errors import BoardAlreadyAcquiringError, BoardConnectionError, BoardNotAcquiringError, BoardNotPoweredError, InvalidParameterError
from clavis.schemas import BoardMetadata
from clavis.transport.udp import UdpTransport
from clavis_samidare.board import SamidareBoard
from clavis_samidare.config import SamidareConfig
from clavis_samidare.plugin import create_board, load_parameters, plugin
from clavis_samidare.registers import CALIBRATION_DEBUG_HIGH_REGISTER, CALIBRATION_DEBUG_LOW_REGISTER, CALIBRATION_FAILED, CALIBRATION_INCOMPLETE_HIGH_REGISTER, CALIBRATION_INCOMPLETE_LOW_REGISTER, CALIBRATION_READY, CALIBRATION_STATUS_REGISTER, DELAY_ADJUST_INIT_REGISTER, PON_REGISTER, SAMPA_RESET_REGISTER, SAMPA_RESET_REQUEST, TRIGGER_ENABLE_REGISTER


class RecordingRegisterClient(FakeRegisterClient):
    def __init__(self) -> None:
        super().__init__()
        self.writes: list[tuple[int, int]] = []

    def write_register(self, address: int, value: int) -> None:
        self.writes.append((address, value))
        super().write_register(address, value)


class FailingOpenClient(FakeRegisterClient):
    def open(self) -> None:
        raise RuntimeError("open failed")


class FailingCloseClient(FakeRegisterClient):
    def close(self) -> None:
        raise RuntimeError("close failed")


class ToggleReadFailureClient(RecordingRegisterClient):
    fail_reads = False

    def read_register(self, address: int) -> int:
        if self.fail_reads:
            raise TimeoutError("status timeout")
        return super().read_register(address)


def make_board(client: FakeRegisterClient) -> SamidareBoard:
    return SamidareBoard(
        BoardMetadata(board_id="samidare-001", name="SAMIDARE", asic="SAMPA_v4", fpga="FPGA", firmware_version="unknown", board_type="samidare"),
        client,
        power_settle_time=0,
        reset_settle_time=0,
    )


def test_plugin_describes_samidare_board_type() -> None:
    board_plugin = plugin()
    assert board_plugin.board_type == "samidare"
    assert board_plugin.display_name == "SAMIDARE"


def test_parameters_load() -> None:
    parameters = load_parameters()
    assert parameters.generalParameters[0].name == "trigger"
    threshold = next(parameter for parameter in parameters.generalParameters if parameter.name == "trigger_threshold")
    assert threshold.minimum == 0
    assert threshold.maximum == 1023
    assert parameters.channelParameters == []


def test_samidare_board_uses_injected_client() -> None:
    client = FakeRegisterClient()
    board = make_board(client)

    board.connect()
    assert client.is_open is True
    board.disconnect()
    assert client.is_open is False


def test_config_defaults_to_fakernet_unreliable_udp() -> None:
    config = SamidareConfig(board_id="samidare-001", name="SAMIDARE", host="192.0.2.1")
    assert config.port_base == 15
    assert config.reliable is False


def test_plugin_constructs_its_fakernet_client_and_udp_transport() -> None:
    board = create_board(
        SamidareConfig(
            board_id="samidare-001",
            name="SAMIDARE",
            host="192.0.2.1",
            reliable=True,
            reliable_channel=2,
        )
    )

    assert isinstance(board.client, FakernetRegisterClient)
    assert board.client.reliable is True
    assert isinstance(board.client.transport, UdpTransport)
    assert board.client.transport.host == "192.0.2.1"
    assert board.client.transport.port == 18


def test_connect_maps_client_errors_to_board_connection_error() -> None:
    board = make_board(FailingOpenClient())

    with pytest.raises(BoardConnectionError, match="open failed"):
        board.connect()

    status = board.get_status()
    assert status.connected is False
    assert status.acquiring is False


def test_disconnect_preserves_last_hardware_state_when_client_close_fails() -> None:
    client = FailingCloseClient()
    board = make_board(client)
    board.connect()
    board.acquiring = True

    with pytest.raises(BoardConnectionError, match="close failed"):
        board.disconnect()

    status = board.get_status()
    assert status.connected is False
    assert status.acquiring is True
    assert status.status_fresh is False


def test_disconnect_does_not_write_hardware_and_marks_status_stale() -> None:
    client = RecordingRegisterClient()
    client.registers[PON_REGISTER] = 0xB1
    client.registers[TRIGGER_ENABLE_REGISTER] = 1
    board = make_board(client)
    board.connect()

    board.disconnect()

    status = board.get_status()
    assert client.writes == []
    assert status.connected is False
    assert status.powered is True
    assert status.acquiring is True
    assert status.status_fresh is False


def test_power_on_starts_calibration_without_waiting_for_ready() -> None:
    client = RecordingRegisterClient()
    client.registers[PON_REGISTER] = 0xB0
    client.registers[CALIBRATION_STATUS_REGISTER] = 2 << 1
    board = make_board(client)
    board.connect()

    board.power_on()

    assert client.writes == [
        (TRIGGER_ENABLE_REGISTER, 0),
        (DELAY_ADJUST_INIT_REGISTER, 0),
        (PON_REGISTER, 0xB1),
        (SAMPA_RESET_REGISTER, SAMPA_RESET_REQUEST),
        (DELAY_ADJUST_INIT_REGISTER, 1),
    ]
    options = board.get_status().global_options
    assert options["calibration_ready"] is False
    assert options["calibration_state"] == "signal_adjust"


def test_status_refresh_reports_calibration_failure_after_power_on() -> None:
    client = RecordingRegisterClient()
    board = make_board(client)
    board.connect()

    board.power_on()
    client.registers[CALIBRATION_STATUS_REGISTER] = CALIBRATION_FAILED | (3 << 1)

    options = board.get_status().global_options
    assert options["calibration_ready"] is False
    assert options["calibration_failed"] is True
    assert options["calibration_state"] == "done"


def test_status_refresh_reports_calibration_ready_after_power_on() -> None:
    client = RecordingRegisterClient()
    board = make_board(client)
    board.connect()

    board.power_on()
    client.registers[CALIBRATION_STATUS_REGISTER] = CALIBRATION_READY | (3 << 1)

    options = board.get_status().global_options
    assert options["calibration_ready"] is True
    assert options["calibration_failed"] is False
    assert options["calibration_state"] == "done"


def test_status_decodes_calibration_debug_registers() -> None:
    client = RecordingRegisterClient()
    debug = 1 | (3 << 1) | (0xA << 3) | (0x123456789A << 7) | (1 << 47) | (0x20 << 48)
    incomplete = 0xA5 | (0x12A << 8) | (0xBEEF << 17) | (17 << 33) | (1 << 39)
    client.registers[CALIBRATION_STATUS_REGISTER] = CALIBRATION_READY | (3 << 1)
    client.registers[CALIBRATION_DEBUG_LOW_REGISTER] = debug & 0xFFFFFFFF
    client.registers[CALIBRATION_DEBUG_HIGH_REGISTER] = debug >> 32
    client.registers[CALIBRATION_INCOMPLETE_LOW_REGISTER] = incomplete & 0xFFFFFFFF
    client.registers[CALIBRATION_INCOMPLETE_HIGH_REGISTER] = incomplete >> 32
    board = make_board(client)
    board.connect()

    options = board.get_status().global_options

    assert options["calibration_state"] == "done"
    assert options["calibration_init"] is True
    assert options["calibration_clock_done_mask"] == "0xa"
    assert options["calibration_lane_done_mask"] == "0x123456789a"
    assert options["calibration_done"] is True
    assert options["calibration_incomplete_lane_state"] == "0x20"
    assert options["calibration_incomplete_lane_index"] == 17
    assert options["calibration_incomplete_timeout"] == 0xBEEF
    assert options["calibration_incomplete_current_tap"] == 0x12A
    assert options["calibration_incomplete_cdc"] == "0xa5"
    assert options["calibration_controller_failed"] is True


def test_status_refreshes_power_controls_and_acquisition_from_hardware() -> None:
    client = RecordingRegisterClient()
    board = make_board(client)
    board.connect()
    client.registers[PON_REGISTER] = 0x61904B
    client.registers[TRIGGER_ENABLE_REGISTER] = 1

    status = board.get_status()

    assert status.status_fresh is True
    assert status.powered is True
    assert status.acquiring is True
    assert status.global_options["trigger"] == "self"
    assert status.global_options["trigger_threshold"] == 100
    assert status.global_options["clock_source"] == "gpio"


def test_failed_status_refresh_preserves_last_complete_snapshot() -> None:
    client = ToggleReadFailureClient()
    client.registers[PON_REGISTER] = 0xB1
    client.registers[TRIGGER_ENABLE_REGISTER] = 1
    board = make_board(client)
    board.connect()
    client.fail_reads = True

    status = board.get_status()

    assert status.status_fresh is False
    assert status.powered is True
    assert status.acquiring is True
    assert status.global_options["status_error"] == "status timeout"


def test_set_global_updates_pon_register() -> None:
    client = RecordingRegisterClient()
    client.registers[PON_REGISTER] = 0xB0
    client.registers[CALIBRATION_STATUS_REGISTER] = CALIBRATION_READY
    board = make_board(client)
    board.connect()
    board.power_on()

    board.set_global({"trigger": "self", "trigger_threshold": 100, "samples": 64})

    assert client.writes[-1] == (PON_REGISTER, 0x190BB)
    assert board.get_status().global_options["trigger"] == "self"


def test_set_global_rejects_invalid_values() -> None:
    client = RecordingRegisterClient()
    board = make_board(client)
    board.connect()

    with pytest.raises(InvalidParameterError, match="gain"):
        board.set_global({"gain": 4})

    assert client.writes == []


def test_set_global_rejects_clock_change_while_powered() -> None:
    client = RecordingRegisterClient()
    client.registers[PON_REGISTER] = 0xB1
    board = make_board(client)
    board.connect()

    with pytest.raises(InvalidParameterError, match="powered off"):
        board.set_global({"clock_source": "mikumari"})

    assert client.writes == []


def test_set_global_allows_clock_change_while_powered_off() -> None:
    client = RecordingRegisterClient()
    client.registers[PON_REGISTER] = 0xB0
    board = make_board(client)
    board.connect()

    board.set_global({"clock_source": "mikumari"})

    assert client.writes == [(PON_REGISTER, 0x8000B0)]


def test_start_acquisition_requires_power() -> None:
    client = RecordingRegisterClient()
    board = make_board(client)
    board.connect()

    with pytest.raises(BoardNotPoweredError):
        board.start_acquisition()


def test_start_stop_acquisition_writes_trigger_enable() -> None:
    client = RecordingRegisterClient()
    client.registers[CALIBRATION_STATUS_REGISTER] = CALIBRATION_READY
    board = make_board(client)
    board.connect()
    board.power_on()
    client.writes.clear()

    board.start_acquisition()
    with pytest.raises(BoardAlreadyAcquiringError):
        board.start_acquisition()
    board.stop_acquisition()
    with pytest.raises(BoardNotAcquiringError):
        board.stop_acquisition()

    assert client.writes == [
        (TRIGGER_ENABLE_REGISTER, 1),
        (TRIGGER_ENABLE_REGISTER, 0),
    ]
