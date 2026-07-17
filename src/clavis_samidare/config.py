from pydantic import BaseModel


class SamidareConfig(BaseModel):
    board_id: str
    board_type: str = "samidare"
    name: str
    host: str
    port_base: int = 15
    reliable: bool = False
    reliable_channel: int = 0
    timeout: float = 0.1
    power_settle_time: float = 2.2
    reset_settle_time: float = 0.01
    calibration_timeout: float = 15.0
    calibration_poll_interval: float = 0.05
    asic: str = "SAMPA_v4"
    fpga: str = "Artix_Ultrascale_Plus"
    firmware_version: str = "unknown"
