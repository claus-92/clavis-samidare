from pydantic import BaseModel


class SamidareConfig(BaseModel):
    board_id: str
    board_type: str = "samidare"
    name: str
    host: str
    port_base: int = 15
    reliable: bool = True
    reliable_channel: int = 0
    timeout: float = 0.1
    asic: str = "SAMPA_v4"
    fpga: str = "Artix_Ultrascale_Plus"
    firmware_version: str = "unknown"
