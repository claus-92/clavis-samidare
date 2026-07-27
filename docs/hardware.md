# Hardware notes

The plugin targets SAMIDARE with SAMPA v4 and uses Fakernet word-register access
over UDP. The map was verified against the `SAMIDARE_FW` source tree at commit
`af7faa319f3085333c40f4f37aa46bf9`. Fakernet addresses are word addresses; the
firmware bridge appends two zero bits for AXI byte addressing.

## Register map

| Address | Access | Meaning |
|---:|---|---|
| `0x0500` | R/W | Physical trigger and acquisition enable in bit 0 |
| `0x0800` | R/W | PON power and global control word |
| `0x1000` | R/W | Delay-adjust calibration initialization in bit 0 |
| `0x5000` | W | SAMPA software-reset request pulse in bit 1 |
| `0x5001` | R | Calibration ready, state, and aggregate failure |
| `0x5002` | R | Calibration debug bits 31:0 |
| `0x5003` | R | Calibration debug bits 55:32, zero-extended |
| `0x5004` | R | Incomplete-lane diagnostic bits 31:0 |
| `0x5005` | R | Incomplete-lane diagnostic bits 39:32, zero-extended |

The active firmware has no acquisition-start register at `0x05`. Acquisition
is enabled by writing bit 0 of `0x0500`; the firmware gates that request with
calibration-ready and application-ready signals.

## PON control word

| Bits | Meaning |
|---:|---|
| `0` | SAMPA power enable |
| `1` | Self-trigger enable |
| `3:2` | Sample count: 16, 32, 64, or 128 |
| `6:4` | Gain/shaping control bits CG0, CG1, CTS |
| `7` | Negative polarity |
| `8` | 1 kHz periodic trigger |
| `9` | 1 MHz periodic trigger |
| `19:10` | Trigger threshold |
| `21:20` | Pretrigger selection |
| `23:22` | Clock source: internal, GPIO, Mikumari, or invalid |

The hardware can have multiple trigger bits active simultaneously. The current
configuration API intentionally exposes one trigger mode and writes a mutually
exclusive combination. Status decoding uses `self`, then `1khz`, then `1mhz`
priority if another controller has written multiple trigger bits.

## Calibration diagnostics

Calibration debug bits include initialization, controller state, four clock
done bits, 40 lane-done bits, aggregate done, and the first incomplete lane's
one-hot state. Registers `0x5004` and `0x5005` are not a lane-failure bitmap;
they expose the first incomplete lane's index, timeout counter, current tap,
and CDC handshake state.

In this firmware revision, the lane FSM clears its `failed` output but never
sets it. The aggregate calibration-failure status bit therefore cannot be
asserted by a lane failure. Clavis decodes the bit correctly, but operators
must use the incomplete-lane diagnostics when calibration does not complete.

Automated tests use injected fake register clients and loopback networking.
They verify the software interpretation but do not replace compatibility tests
with a physical board built from the identified firmware revision.
