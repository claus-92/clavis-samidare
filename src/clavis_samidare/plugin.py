import json
from importlib.resources import files

from pydantic import BaseModel

from clavis.clients.fakernet import FakernetRegisterClient
from clavis.plugins import BoardPlugin
from clavis.schemas import BoardMetadata, ParameterDefinitions
from clavis.transport.udp import UdpTransport
from clavis_samidare.board import SamidareBoard
from clavis_samidare.config import SamidareConfig


def create_board(config: BaseModel) -> SamidareBoard:
    samidare_config = _as_config(config)
    if samidare_config.board_type != "samidare":
        raise ValueError("SAMIDARE plugin can only create board_type='samidare'")

    port = samidare_config.port_base
    if samidare_config.reliable:
        port = samidare_config.port_base + 1 + samidare_config.reliable_channel

    transport = UdpTransport(
        host=samidare_config.host,
        port=port,
        timeout=samidare_config.timeout,
    )
    client = FakernetRegisterClient(
        transport=transport,
        reliable=samidare_config.reliable,
    )
    metadata = BoardMetadata(
        board_id=samidare_config.board_id,
        name=samidare_config.name,
        asic=samidare_config.asic,
        fpga=samidare_config.fpga,
        firmware_version=samidare_config.firmware_version,
        board_type="samidare",
    )
    return SamidareBoard(
        metadata,
        client,
        power_settle_time=samidare_config.power_settle_time,
        reset_settle_time=samidare_config.reset_settle_time,
    )


def load_parameters() -> ParameterDefinitions:
    path = files("clavis_samidare") / "parameter_definitions" / "samidare.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return ParameterDefinitions.model_validate(data)


def plugin() -> BoardPlugin:
    return BoardPlugin(
        board_type="samidare",
        display_name="SAMIDARE",
        config_model=SamidareConfig,
        create_board=create_board,
        load_parameters=load_parameters,
    )


def _as_config(config: BaseModel) -> SamidareConfig:
    if isinstance(config, SamidareConfig):
        return config
    return SamidareConfig.model_validate(config.model_dump())
