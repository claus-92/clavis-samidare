from clavis.clients.fake import FakeRegisterClient
from clavis.schemas import BoardMetadata
from clavis_samidare.board import SamidareBoard
from clavis_samidare.config import SamidareConfig
from clavis_samidare.plugin import load_parameters, plugin


def test_plugin_describes_samidare_board_type() -> None:
    board_plugin = plugin()
    assert board_plugin.board_type == "samidare"
    assert board_plugin.display_name == "SAMIDARE"


def test_parameters_load() -> None:
    parameters = load_parameters()
    assert parameters.channelParameters[0].name == "power"


def test_samidare_board_uses_injected_client() -> None:
    client = FakeRegisterClient()
    board = SamidareBoard(
        BoardMetadata(board_id="samidare-001", name="SAMIDARE", asic="SAMPA_v4", fpga="FPGA", firmware_version="unknown", board_type="samidare"),
        client,
    )

    board.connect()
    assert client.is_open is True
    board.disconnect()
    assert client.is_open is False


def test_config_defaults_to_fakernet_reliable_udp() -> None:
    config = SamidareConfig(board_id="samidare-001", name="SAMIDARE", host="192.0.2.1")
    assert config.port_base == 15
    assert config.reliable is True
