# Configuration and operation

Create a board with at least `board_id`, `name`, and `host`. The plugin also
accepts:

| Field | Default | Meaning |
|---|---:|---|
| `port_base` | `15` | Base fakernet UDP port |
| `reliable` | `false` | Enable fakernet reliable-channel setup |
| `reliable_channel` | `0` | Reliable channel offset |
| `timeout` | `0.1` | UDP timeout in seconds |
| `power_settle_time` | `2.2` | Delay after enabling power |
| `reset_settle_time` | `0.01` | Delay after SAMPA reset |
| `calibration_timeout` | `15.0` | Maximum calibration wait |
| `calibration_poll_interval` | `0.05` | Calibration polling interval |

The current driver implements global trigger, threshold, polarity, gain,
sample-count, pretrigger, and clock-source controls. `clock_source` accepts
`internal`, `gpio`, or `mikumari`. Group and channel parameters are not
currently exposed.

The normal sequence is connect, power on, wait for calibration, start and stop
acquisition, power off, then disconnect. Power-on and acquisition operations
write hardware registers; use only on a trusted network with the intended
board and firmware.

While connected, each status request reads the PON control, trigger-enable,
calibration status, and calibration diagnostic registers. Power, acquisition,
and control values therefore reflect the board rather than only the driver's
previous writes. Disconnect closes only the control channel: it does not stop
acquisition or power off the board. The last complete observation remains
available with `status_fresh=false` until a successful reconnect and refresh.
