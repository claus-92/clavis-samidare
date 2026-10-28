# Hardware notes

The plugin targets SAMIDARE with SAMPA v4 and uses Fakernet word-register access
over UDP. The map follows the SAMIDARE capture ABI identified by magic value
`0x53414d33` (`SAM3`). Fakernet addresses are word addresses; the
firmware bridge appends two zero bits for AXI byte addressing.

## Register map

| Address | Access | Meaning |
|---:|---|---|
| `0x0500` | R/W | Acquisition arm: `0` disarm, `1` arm |
| `0x0501` | R/W | Start source: `0` local Fakernet, `1` GPIO0, `2` Mikumari/LACCP |
| `0x0502` | R/W | Event source: `0` GPIO1, `1` Mikumari/LACCP, `2` self, `3` 1 kHz |
| `0x0503` | W1P | Local Fakernet start strobe |
| `0x0504` | R | Run status: state, receiver ready, primed, armed, fault, active |
| `0x0800` | R/W | PON power and global control word |
| `0x1000` | R/W | Delay-adjust calibration initialization in bit 0 |
| `0x5000` | W | SAMPA software-reset request pulse in bit 1 |
| `0x5001` | R | Calibration ready, state, and aggregate failure |
| `0x5002` | R | Calibration debug bits 31:0 |
| `0x5003` | R | `{8'b0, cal_debug[55:32]}` |
| `0x5004` | R | Failed data-lane mask bits 31:0 |
| `0x5005` | R | Failed data-lane mask bits 39:32, zero-extended |
| `0x5006` | R | Receiver lock, trigger, sync-error, and FIFO status |
| `0x5007` | R | Phase-5 calibration lock, error, and activity status (if implemented) |
| `0x5008` | R | Capture ABI magic; must equal `0x53414d33` for SAM3 control writes |
| `0x5009` | R | Capture status and sticky fault summary |
| `0x500a` | R | Accepted-trigger counter |
| `0x500b` | R | Trigger requests rejected while busy |
| `0x500c` | R | Expired ring-window counter |
| `0x500d` | R | Event-FIFO-capacity drop counter |
| `0x500e` | W | Write bit 0 to clear capture counters/sticky faults |

Source configuration is accepted only while disarmed. Arm at `0x0500` and wait
for receiver-ready. With the local start source selected, a separate Start
operation writes `1` to `0x0503`; with GPIO0 or Mikumari/LACCP selected, the
corresponding external pulse starts the run and a Fakernet start request is
invalid. Select Mikumari/LACCP as the event source to use its distributed
trigger pulse for events. Event requests are enabled only after the capture
history is primed.

## PON control word

| Bits | Meaning |
|---:|---|
| `0` | SAMPA power enable |
| `1` | Retired; must be zero |
| `3:2` | Sample count: 16, 32, 64, or 128 |
| `6:4` | Gain/shaping control bits CG0, CG1, CTS |
| `7` | Negative polarity |
| `9:8` | Retired; must be zero |
| `19:10` | Self-trigger threshold |
| `21:20` | Pretrigger selection |
| `23:22` | Clock source: internal, GPIO, Mikumari, or invalid |

Start and event source selection are independent of PON. The plugin verifies
the SAM3 ABI before writing any PON or source-control register.

Capture status `0x5009` uses bit 0 for busy, bits 2:1 for active trigger mode,
bit 3 for invalid-rate status (currently tied low in the documented firmware),
bits 4 and 5 for expired-window and FIFO-capacity-drop sticky indications, and
bit 6 for current FIFO capacity.

## Calibration diagnostics

`0x5001` is a live aggregate status word: bit 0 is `ready` (`cal_done`), bits
2:1 are `cal_state` (`idle`, `sweep`, `apply`, `lock`), and bit 3 is aggregate
`cal_failed`.

The Phase-5 calibration debug word is `cal_debug[55:0]`, with `0x5002` holding
bits 31:0 and `0x5003[23:0]` holding bits 55:32. Its fields are:

| `cal_debug` bits | Meaning |
|---:|---|
| `10:0` | `data_done[10:0]` |
| `14:11` | `epoch_sync_debug[3:0]` |
| `26:15` | `lock_state[11:0]` |
| `31:27`, `35:32` | `sweep_tap_idx[4:0]`, `sweep_tap_idx[8:5]` |
| `36` | `measure_valid` |
| `37` | `sweep_done` |
| `39:38` | `cal_state` (`idle`, `sweep`, `apply`, `lock`) |
| `43:40` | `cal_sync_error[3:0]` |
| `47:44` | `cal_locked[3:0]` |
| `51:48` | `clock_cal_failed[3:0]` |
| `52`, `53`, `54`, `55` | `cal_failed`, `cal_done`, `idelay_rdy`, `cal_start` |

Registers `0x5004` and `0x5005` form a 40-bit failed-data-lane mask.
Bits 9:0 belong to chip 0, bits 19:10 to chip 1, bits 29:20 to chip 2, and bits
39:30 to chip 3. Within each group, bit 0 is the first serial-output data bit.

Receiver status at `0x5006` uses four-bit masks: locked at bits 3:0, accepted
trigger pending at 7:4, sync error at 11:8, FIFO empty at 15:12, and FIFO full
at 19:16. Chip 0 is the least significant bit in each field.

When implemented by the firmware, `0x5007` provides per-chip calibration lock,
sync-error, and clock-failure masks at bits 3:0, 7:4, and 11:8 respectively;
bits 12:15 report IDELAY ready, calibration active, trigger enabled, and
calibration start. Bits 16 and 17 are sticky terminal-completion and
terminal-failure status. The plugin treats this word as optional for firmware
that predates it; all `0x5007`-derived fields, including the sticky fields, are
reported as unavailable when the register cannot be read.

Automated tests use injected fake register clients and loopback networking.
They verify the software interpretation but do not replace compatibility tests
with a physical board built from the identified firmware revision.
