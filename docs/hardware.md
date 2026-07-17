# Hardware notes

The plugin targets SAMIDARE with SAMPA v4 and uses fakernet register access over
UDP. The register map is defined in `clavis_samidare.registers` and control-bit
encoding in `clavis_samidare.controls`.

Some power, reset, calibration, and legacy acquisition addresses were derived
from the current Vivado design and earlier SAM_DAQ behavior. In particular, the
exact firmware meaning of the legacy start register is not yet documented.
Treat these mappings as firmware-specific and verify them against the hardware
design used for a deployment.

Automated tests use injected fake register clients; they do not establish
compatibility with physical hardware or a particular firmware release.
