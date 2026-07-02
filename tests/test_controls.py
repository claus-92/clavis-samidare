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
        external_clk=True,
    )

    assert encode_pon(state) == 0x61904B


def test_decode_pon_round_trips_supported_values() -> None:
    state = SamidareControlState(
        powered=True,
        trigger="1mhz",
        trigger_threshold=1023,
        polarity="negative",
        gain=2,
        samples=128,
        pretrigger=16,
        external_clk=True,
    )

    assert decode_pon(encode_pon(state)) == state


def test_update_state_validates_values() -> None:
    with pytest.raises(ValueError, match="trigger_threshold"):
        update_state(SamidareControlState(), {"trigger_threshold": 1024})

    with pytest.raises(ValueError, match="gain"):
        update_state(SamidareControlState(), {"gain": 4})
