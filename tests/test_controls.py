import pytest

from clavis_samidare.controls import SamidareControlState, decode_pon, encode_pon, update_state


def test_encode_default_pon_has_default_gain_and_negative_polarity() -> None:
    assert encode_pon(SamidareControlState()) == 0xB0


def test_encode_full_pon_control_state() -> None:
    state = SamidareControlState(
        powered=True,
        trigger="self",
        trigger_threshold=100,
        polarity="positive",
        gain=3,
        samples=64,
        pretrigger=8,
        clock_source="gpio",
    )

    assert encode_pon(state) == 0x619149


def test_decode_pon_round_trips_supported_values() -> None:
    state = SamidareControlState(
        powered=True,
        trigger="10khz",
        trigger_threshold=1023,
        polarity="negative",
        gain=2,
        samples=16,
        pretrigger=16,
        clock_source="gpio",
    )

    assert decode_pon(encode_pon(state)) == state


def test_clock_source_uses_both_firmware_bits() -> None:
    state = SamidareControlState(clock_source="mikumari")

    assert encode_pon(state) & (0x3 << 22) == 0x2 << 22
    assert decode_pon(encode_pon(state)).clock_source == "mikumari"
    assert decode_pon(0x3 << 22).clock_source == "invalid"


def test_update_state_validates_values() -> None:
    with pytest.raises(ValueError, match="trigger_threshold"):
        update_state(SamidareControlState(), {"trigger_threshold": 1024})

    with pytest.raises(ValueError, match="gain"):
        update_state(SamidareControlState(), {"gain": 4})

    with pytest.raises(ValueError, match="10khz"):
        update_state(SamidareControlState(), {"trigger": "10khz", "samples": 32, "pretrigger": 4})
