PON_REGISTER = 0x800

# Firmware blocks poll these BRAM/register locations. Names reflect the best
# current understanding from the Vivado design; keep raw addresses here only.
DELAY_ADJUST_INIT_REGISTER = 0x1000
TRIGGER_ENABLE_REGISTER = 0x500

# Present in the legacy SAM_DAQ start sequence. The exact firmware meaning is
# not yet documented, so keep it isolated from named controls.
LEGACY_START_REGISTER = 0x05
LEGACY_START_VALUE = 0x03
