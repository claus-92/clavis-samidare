from dataclasses import dataclass, replace
from typing import Any


TRIGGERS = {"external", "self", "1khz", "1mhz"}
POLARITIES = {"positive", "negative"}
GAINS = {1, 2, 3}
SAMPLES = {16, 32, 64, 128}
PRETRIGGERS = {0, 4, 8, 16}


@dataclass(frozen=True)
class SamidareControlState:
    powered: bool = False
    trigger: str = "external"
    trigger_threshold: int = 0
    polarity: str = "negative"
    gain: int = 1
    samples: int = 16
    pretrigger: int = 0
    external_clk: bool = False

    def as_options(self) -> dict[str, Any]:
        return {
            "trigger": self.trigger,
            "trigger_threshold": self.trigger_threshold,
            "polarity": self.polarity,
            "gain": self.gain,
            "samples": self.samples,
            "pretrigger": self.pretrigger,
            "external_clk": self.external_clk,
        }


def update_state(state: SamidareControlState, options: dict[str, Any]) -> SamidareControlState:
    updates: dict[str, Any] = {}
    for key, value in options.items():
        if key == "trigger":
            updates[key] = _validate_string(key, value, TRIGGERS)
        elif key == "trigger_threshold":
            threshold = _validate_int(key, value)
            if threshold < 0 or threshold > 1023:
                raise ValueError("trigger_threshold must be between 0 and 1023")
            updates[key] = threshold
        elif key == "polarity":
            updates[key] = _validate_string(key, value, POLARITIES)
        elif key == "gain":
            updates[key] = _validate_int_choice(key, value, GAINS)
        elif key == "samples":
            updates[key] = _validate_int_choice(key, value, SAMPLES)
        elif key == "pretrigger":
            updates[key] = _validate_int_choice(key, value, PRETRIGGERS)
        elif key == "external_clk":
            if not isinstance(value, bool):
                raise ValueError("external_clk must be boolean")
            updates[key] = value
        else:
            raise ValueError(f"Unknown SAMIDARE control: {key}")
    return replace(state, **updates)


def encode_pon(state: SamidareControlState) -> int:
    value = 0
    if state.powered:
        value |= 1 << 0
    if state.trigger == "self":
        value |= 1 << 1
    elif state.trigger == "1khz":
        value |= 1 << 8
    elif state.trigger == "1mhz":
        value |= 1 << 9

    value |= _sample_bits(state.samples) << 2
    cg0, cg1, cts = _gain_bits(state.gain)
    value |= cg0 << 4
    value |= cg1 << 5
    value |= cts << 6
    if state.polarity == "negative":
        value |= 1 << 7
    value |= (state.trigger_threshold & 0x3FF) << 10
    value |= _pretrigger_bits(state.pretrigger) << 20
    if state.external_clk:
        value |= 1 << 22
    return value


def decode_pon(value: int) -> SamidareControlState:
    trigger = "external"
    if value & (1 << 1):
        trigger = "self"
    elif value & (1 << 8):
        trigger = "1khz"
    elif value & (1 << 9):
        trigger = "1mhz"

    return SamidareControlState(
        powered=bool(value & (1 << 0)),
        trigger=trigger,
        trigger_threshold=(value >> 10) & 0x3FF,
        polarity="negative" if value & (1 << 7) else "positive",
        gain=_gain_from_bits((value >> 4) & 0x1, (value >> 5) & 0x1, (value >> 6) & 0x1),
        samples=_samples_from_bits((value >> 2) & 0x3),
        pretrigger=_pretrigger_from_bits((value >> 20) & 0x3),
        external_clk=bool(value & (1 << 22)),
    )


def _validate_string(key: str, value: Any, choices: set[str]) -> str:
    if not isinstance(value, str) or value not in choices:
        allowed = ", ".join(sorted(choices))
        raise ValueError(f"{key} must be one of: {allowed}")
    return value


def _validate_int(key: str, value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} must be an integer")
    return value


def _validate_int_choice(key: str, value: Any, choices: set[int]) -> int:
    number = _validate_int(key, value)
    if number not in choices:
        allowed = ", ".join(str(choice) for choice in sorted(choices))
        raise ValueError(f"{key} must be one of: {allowed}")
    return number


def _sample_bits(samples: int) -> int:
    return {16: 0, 32: 1, 64: 2, 128: 3}[samples]


def _samples_from_bits(bits: int) -> int:
    return {0: 16, 1: 32, 2: 64, 3: 128}[bits]


def _gain_bits(gain: int) -> tuple[int, int, int]:
    return {
        1: (1, 1, 0),
        2: (0, 1, 0),
        3: (0, 0, 1),
    }[gain]


def _gain_from_bits(cg0: int, cg1: int, cts: int) -> int:
    return {
        (1, 1, 0): 1,
        (0, 1, 0): 2,
        (0, 0, 1): 3,
    }.get((cg0, cg1, cts), 1)


def _pretrigger_bits(pretrigger: int) -> int:
    return {0: 0, 4: 1, 8: 2, 16: 3}[pretrigger]


def _pretrigger_from_bits(bits: int) -> int:
    return {0: 0, 1: 4, 2: 8, 3: 16}[bits]
