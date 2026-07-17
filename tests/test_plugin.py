import pytest

from clavis.clients.fake import FakeRegisterClient
from clavis.core.errors import BoardAlreadyAcquiringError, BoardConnectionError, BoardNotAcquiringError, BoardNotPoweredError, InvalidParameterError
from clavis.schemas import BoardMetadata
from clavis_samidare.board import SamidareBoard
from clavis_samidare.config import SamidareConfig
from clavis_samidare.plugin import load_parameters, plugin
from clavis_samidare.registers import CALIBRATION_FAILED, CALIBRATION_READY, CALIBRATION_STATUS_REGISTER, DELAY_ADJUST_INIT_REGISTER, LEGACY_START_REGISTER, LEGACY_START_VALUE, PON_REGISTER, SAMPA_RESET_REGISTER, SAMPA_RESET_REQUEST, TRIGGER_ENABLE_REGISTER


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


def make_board(client: FakeRegisterClient) -> SamidareBoard:
    return SamidareBoard(
        BoardMetadata(board_id="samidare-001", name="SAMIDARE", asic="SAMPA_v4", fpga="FPGA", firmware_version="unknown", board_type="samidare"),
        client,
        power_settle_time=0,
        reset_settle_time=0,
        calibration_timeout=0.01,
        calibration_poll_interval=0,
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


def test_config_defaults_to_fakernet_reliable_udp() -> None:
    config = SamidareConfig(board_id="samidare-001", name="SAMIDARE", host="192.0.2.1")
    assert config.port_base == 15
    assert config.reliable is False


def test_connect_maps_client_errors_to_board_connection_error() -> None:
    board = make_board(FailingOpenClient())

    with pytest.raises(BoardConnectionError, match="open failed"):
        board.connect()

    status = board.get_status()
    assert status.connected is False
    assert status.acquiring is False


def test_disconnect_clears_local_state_when_client_close_fails() -> None:
    client = FailingCloseClient()
    board = make_board(client)
    board.connect()
    board.acquiring = True

    with pytest.raises(BoardConnectionError, match="close failed"):
        board.disconnect()

    status = board.get_status()
    assert status.connected is False
    assert status.acquiring is False


def test_power_on_writes_pon_register() -> None:
    client = RecordingRegisterClient()
    client.registers[PON_REGISTER] = 0xB0
    client.registers[CALIBRATION_STATUS_REGISTER] = CALIBRATION_READY
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
    assert board.get_status().global_options["calibration_ready"] is True


def test_power_on_reports_calibration_failure() -> None:
    client = RecordingRegisterClient()
    client.registers[CALIBRATION_STATUS_REGISTER] = CALIBRATION_FAILED
    board = make_board(client)
    board.connect()

    with pytest.raises(BoardConnectionError, match="calibration failed"):
        board.power_on()

    assert client.writes[-1] == (DELAY_ADJUST_INIT_REGISTER, 1)
    assert board.get_status().global_options["calibration_ready"] is False


def test_power_on_reports_calibration_timeout() -> None:
    client = RecordingRegisterClient()
    board = make_board(client)
    board.connect()

    with pytest.raises(BoardConnectionError, match="calibration timed out"):
        board.power_on()

    assert board.get_status().global_options["calibration_ready"] is False


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


def test_start_acquisition_requires_power() -> None:
    client = RecordingRegisterClient()
    board = make_board(client)
    board.connect()

    with pytest.raises(BoardNotPoweredError):
        board.start_acquisition()


def test_start_stop_acquisition_writes_legacy_sequence() -> None:
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
        (LEGACY_START_REGISTER, LEGACY_START_VALUE),
        (TRIGGER_ENABLE_REGISTER, 1),
        (TRIGGER_ENABLE_REGISTER, 0),
    ]
