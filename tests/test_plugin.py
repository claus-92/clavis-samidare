import pytest

from clavis.clients.fake import FakeRegisterClient
from clavis.core.errors import BoardAlreadyAcquiringError, BoardNotAcquiringError, BoardNotPoweredError, InvalidParameterError
from clavis.schemas import BoardMetadata
from clavis_samidare.board import SamidareBoard
from clavis_samidare.config import SamidareConfig
from clavis_samidare.plugin import load_parameters, plugin
from clavis_samidare.registers import DELAY_ADJUST_INIT_REGISTER, LEGACY_START_REGISTER, LEGACY_START_VALUE, PON_REGISTER, TRIGGER_ENABLE_REGISTER


class RecordingRegisterClient(FakeRegisterClient):
    def __init__(self) -> None:
        super().__init__()
        self.writes: list[tuple[int, int]] = []

    def write_register(self, address: int, value: int) -> None:
        self.writes.append((address, value))
        super().write_register(address, value)


def make_board(client: FakeRegisterClient) -> SamidareBoard:
    return SamidareBoard(
        BoardMetadata(board_id="samidare-001", name="SAMIDARE", asic="SAMPA_v4", fpga="FPGA", firmware_version="unknown", board_type="samidare"),
        client,
    )


def test_plugin_describes_samidare_board_type() -> None:
    board_plugin = plugin()
    assert board_plugin.board_type == "samidare"
    assert board_plugin.display_name == "SAMIDARE"


def test_parameters_load() -> None:
    parameters = load_parameters()
    assert parameters.generalParameters[0].name == "trigger"
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
    assert config.reliable is True


def test_power_on_writes_pon_register() -> None:
    client = RecordingRegisterClient()
    client.registers[PON_REGISTER] = 0xB0
    board = make_board(client)
    board.connect()

    board.power_on()

    assert client.writes == [(PON_REGISTER, 0xB1)]


def test_set_global_updates_pon_register() -> None:
    client = RecordingRegisterClient()
    client.registers[PON_REGISTER] = 0xB0
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
        (DELAY_ADJUST_INIT_REGISTER, 1),
        (TRIGGER_ENABLE_REGISTER, 1),
        (LEGACY_START_REGISTER, LEGACY_START_VALUE),
        (DELAY_ADJUST_INIT_REGISTER, 0),
        (TRIGGER_ENABLE_REGISTER, 0),
    ]
