"""Contract tests: entity/forecast keys and warning fields must not drift."""
import dataclasses
import json
import sys
import unittest
from pathlib import Path

QW_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "qweather"
if str(QW_DIR) not in sys.path:
    sys.path.insert(0, str(QW_DIR))

from condition import CONDITION_MAP  # noqa: E402
import mapping  # noqa: E402


FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / f"v1_{name}.json").read_text(encoding="utf-8"))


CURRENT_KEYS = [
    "condition", "condition_cn", "icon", "native_temperature", "humidity",
    "native_pressure", "native_wind_speed", "wind_bearing", "winddir",
    "windscale", "feelslike", "cloud", "vis", "precip", "dew", "obsTime",
]

DAILY_KEYS = [
    "datetime", "native_temperature", "native_templow", "condition",
    "native_precipitation", "native_pressure", "native_wind_speed",
    "wind_bearing", "humidity", "text", "icon", "textnight", "iconnight",
    "winddirday", "winddirnight", "windscaleday", "windscalenight",
    "uv_index", "vis", "cloud", "sunrise", "sunset", "moonphase",
    "native_precipitation_probability",
]

HOURLY_KEYS = [
    "datetime", "native_temperature", "condition", "native_precipitation",
    "native_pressure", "humidity", "native_wind_speed", "wind_bearing",
    "native_precipitation_probability", "text", "icon", "winddir",
    "windscale", "vis",
]

WARNING_FIELDS = [
    "id", "sender", "pubTime", "title", "startTime", "endTime", "status",
    "level", "severity", "severityColor", "type", "typeName", "urgency",
    "certainty", "text", "related",
]

AIR_KEYS = [
    "aqi", "level", "category", "primary", "pm2p5", "pm10", "no2", "o3",
    "so2", "co", "pubTime", "indexes", "pollutants",
]


class TestForecastKeyContracts(unittest.TestCase):
    def test_current_keys_and_order(self):
        self.assertEqual(list(mapping.map_current(load("current"))), CURRENT_KEYS)

    def test_daily_keys_and_order(self):
        first = mapping.map_daily(load("daily"))[0]
        self.assertEqual(list(first), DAILY_KEYS)

    def test_hourly_keys_and_order(self):
        first = mapping.map_hourly(load("hourly"))[0]
        self.assertEqual(list(first), HOURLY_KEYS)


class TestWarningContracts(unittest.TestCase):
    def test_warning_field_names_and_order(self):
        names = [field.name for field in dataclasses.fields(mapping.WarningData)]
        self.assertEqual(names, WARNING_FIELDS)

    def test_warning_dataclass_has_no_extra_fields(self):
        self.assertEqual(len(dataclasses.fields(mapping.WarningData)), 16)


class TestAirContracts(unittest.TestCase):
    def test_air_keys(self):
        self.assertEqual(
            list(mapping.map_air_quality(load("air"))), AIR_KEYS
        )


class TestConditionMap(unittest.TestCase):
    def test_keys_are_three_digit_strings(self):
        for code in CONDITION_MAP:
            self.assertIsInstance(code, str)
            self.assertRegex(code, r"^[1-9]\d{2}$")

    def test_fixture_code_hits(self):
        self.assertEqual(CONDITION_MAP["100"], "sunny")


if __name__ == "__main__":
    unittest.main()
