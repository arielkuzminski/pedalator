import struct

from pedalator.ftms import on_bike_data, on_control_point, parse_bike_data, simulation_command
from pedalator.state import state


def test_parses_speed_cadence_power():
    # flags 0x0044: speed present (bit 0 clear), cadence (bit 2), power (bit 6)
    pkt = struct.pack("<HHHh", 0x0044, 2500, 180, 175)
    assert parse_bike_data(pkt) == {"speed": 25.0, "cadence": 90.0, "power": 175}


def test_real_trainer_packet_when_not_pedalling():
    # a Van Rysel D500 at rest: a longer packet than the fields we read, the extra bytes are ignored
    pkt = bytes.fromhex("44000000000000000000f1ff00001b015004")
    out = parse_bike_data(pkt)
    assert out["power"] == 0 and out["cadence"] == 0 and out["speed"] == 0


def test_distance_resistance_and_heart_rate_fields():
    # speed, distance (3 bytes), resistance, power, heart rate
    flags = 0x0200 | 0x0040 | 0x0020 | 0x0010
    pkt = struct.pack("<HH", flags, 1800) + (1234).to_bytes(3, "little") + struct.pack("<hh", 40, 210) + bytes([151])
    out = parse_bike_data(pkt)
    assert out == {"speed": 18.0, "distance": 1234, "resistance": 40, "power": 210, "hr": 151}


def test_more_data_flag_means_no_speed():
    pkt = struct.pack("<Hh", 0x0001 | 0x0040, 99)
    assert parse_bike_data(pkt) == {"power": 99}


def test_negative_power_is_kept_as_reported():
    assert parse_bike_data(struct.pack("<HHh", 0x0040, 0, -3))["power"] == -3


def test_simulation_command_encodes_grade_in_hundredths_of_a_percent():
    assert simulation_command(5.0) == bytes([0x11, 0, 0, 0xF4, 0x01, 40, 51])
    assert struct.unpack_from("<h", simulation_command(-2.5), 3)[0] == -250


def test_on_bike_data_updates_state_and_survives_garbage():
    on_bike_data(None, bytearray(struct.pack("<HHHh", 0x0044, 1000, 120, 130)))
    assert state["power"] == 130 and state["cadence"] == 60.0 and state["t_packet"] > 0
    on_bike_data(None, bytearray(b"\x44"))                 # too short: must not raise
    assert state["power"] == 130


def test_control_point_responses_are_decoded():
    on_control_point(None, bytearray([0x80, 0x11, 0x01]))
    assert state["cp_last"] == "op 0x11: ok"
    on_control_point(None, bytearray([0x80, 0x11, 0x03]))
    assert state["cp_last"] == "op 0x11: invalid parameter"
