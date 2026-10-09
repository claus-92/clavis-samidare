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

The current driver implements global start-source, event-source, threshold,
polarity, gain, sample-count, pretrigger, and clock-source controls.
`start_source` accepts `local`, `gpio0`, or `mikumari`; `event_source` accepts
`gpio1`, `mikumari`, `self`, or `1khz`. `mikumari` selects the LACCP pulse
distributed over the Mikumari link. `clock_source` accepts
`internal`, `gpio`, or `mikumari`. Group and channel parameters are not
currently exposed.

The normal sequence is connect, select sources and clock while disarmed, power
on, arm acquisition, then start it if `start_source` is `local`. With `gpio0` or
`mikumari` selected, arming waits for the selected external pulse instead; a
Fakernet start request is rejected for those sources. Stop disarms acquisition.
Refresh status until receiver-ready after arming and confirm run-active after
starting, then power off and disconnect. Power-on performs the required power
settle and reset sequence, starts calibration, and returns without waiting for
calibration to finish. Changing the clock source while powered is rejected
because switching a live application clock can reset or stall calibration.
Power-on and acquisition operations write hardware registers; use only on a
trusted network with the intended board and firmware.

While connected, each status request reads the PON control, source selections,
run status, calibration status, and calibration diagnostic registers. Power, acquisition,
and control values therefore reflect the board rather than only the driver's
previous writes. Disconnect closes only the control channel: it does not stop
acquisition or power off the board. The last complete observation remains
available with `status_fresh=false` until a successful reconnect and refresh.
The CLI `boards status` command performs a manual refresh; the TUI refreshes
automatically every two seconds. The controller reports receiver readiness only
after arm, so CLAVIS must arm before checking that status.
