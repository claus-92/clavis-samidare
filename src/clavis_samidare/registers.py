PON_REGISTER = 0x800

# Firmware blocks poll these BRAM/register locations. Names reflect the best
# current understanding from the Vivado design; keep raw addresses here only.
DELAY_ADJUST_INIT_REGISTER = 0x1000
TRIGGER_ENABLE_REGISTER = 0x500
SAMPA_RESET_REGISTER = 0x5000
CALIBRATION_STATUS_REGISTER = 0x5001

SAMPA_RESET_REQUEST = 1 << 1
CALIBRATION_READY = 1 << 0
CALIBRATION_STATE_SHIFT = 1
CALIBRATION_STATE_MASK = 0x3 << CALIBRATION_STATE_SHIFT
CALIBRATION_FAILED = 1 << 3

# Present in the legacy SAM_DAQ start sequence. The exact firmware meaning is
# not yet documented, so keep it isolated from named controls.
LEGACY_START_REGISTER = 0x05
LEGACY_START_VALUE = 0x03
