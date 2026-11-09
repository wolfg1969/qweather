"""Offline unit tests for the pure v1 mapping helpers.

Run with either:

    python3 -m unittest discover -s tests -p 'test_*.py' -v
    python3 -m pytest -q tests/
"""
import json
import sys
import unittest
from pathlib import Path

QW_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "qweather"
if str(QW_DIR) not in sys.path:
    sys.path.insert(0, str(QW_DIR))

from condition import EXCEPTIONAL  # noqa: E402
import mapping  # noqa: E402


FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / f"v1_{name}.json").read_text(encoding="utf-8"))


class TestMapCurrent(unittest.TestCase):
    def setUp(self):
        self.result = mapping.map_current(load("current"))

    def test_required_values(self):
        self.assertEqual(self.result["native_temperature"], 9.15)
        self.assertEqual(self.result["humidity"], 30)
        self.assertEqual(self.result["native_wind_speed"], 13.5)
        self.assertEqual(self.result["vis"], 30.1)
        self.assertEqual(self.result["cloud"], "0")
        self.assertEqual(self.result["winddir"], "南西南风")
        self.assertEqual(self.result["windscale"], "3")
        self.assertEqual(self.result["obsTime"], "2026-11-09T11:45+08:00")

    def test_extra_values(self):
        self.assertEqual(self.result["condition"], "sunny")
        self.assertEqual(self.result["icon"], "100")
        self.assertEqual(self.result["condition_cn"], "晴")
        self.assertEqual(self.result["native_pressure"], 1038.75)
        self.assertEqual(self.result["feelslike"], 5.07)
        self.assertEqual(self.result["dew"], -7.77)
        self.assertEqual(self.result["precip"], 0.0)
        self.assertEqual(self.result["wind_bearing"], 207.0)

    def test_empty_payload_uses_none_not_zero(self):
        result = mapping.map_current({})
        self.assertEqual(result["condition"], EXCEPTIONAL)
        for key in (
            "native_temperature", "humidity", "native_pressure",
            "native_wind_speed", "wind_bearing", "windscale", "feelslike",
            "cloud", "vis", "precip", "dew", "obsTime", "icon",
        ):
            self.assertIsNone(result[key], key)
        self.assertEqual(result["winddir"], "")
        self.assertEqual(result["condition_cn"], "")

    def test_numeric_condition_code_is_stringified(self):
        payload = {"condition": {"code": 100, "text": "晴"}}
        self.assertEqual(mapping.map_current(payload)["condition"], "sunny")
        self.assertEqual(mapping.map_current(payload)["icon"], "100")

    def test_unknown_condition_falls_back(self):
        payload = {"condition": {"code": "12345", "text": "未知"}}
        self.assertEqual(mapping.map_current(payload)["condition"], EXCEPTIONAL)


class TestMapDaily(unittest.TestCase):
    def setUp(self):
        self.days = mapping.map_daily(load("daily"), 7)

    def test_count_and_required_values(self):
        self.assertEqual(len(self.days), 7)
        first = self.days[0]
        self.assertEqual(first["native_templow"], -1.38)
        self.assertEqual(first["native_temperature"], 11.43)
        self.assertEqual(first["uv_index"], 2)
        self.assertEqual(first["native_precipitation"], 0.0)
        self.assertEqual(first["sunrise"], "2026-11-09T06:52+08:00")
        self.assertEqual(first["sunset"], "2026-11-09T17:04+08:00")
        self.assertEqual(first["moonphase"], "new-moon")

    def test_v1_daily_has_no_pressure_or_visibility(self):
        first = self.days[0]
        self.assertIsNone(first["native_pressure"])
        self.assertIsNone(first["vis"])

    def test_scaled_and_derived_values(self):
        first = self.days[0]
        self.assertEqual(first["humidity"], 48)
        self.assertEqual(first["cloud"], "0")
        self.assertEqual(first["native_wind_speed"], 6.9)
        self.assertEqual(first["wind_bearing"], 204.0)
        self.assertEqual(first["winddirday"], "南西南风")
        self.assertEqual(first["winddirnight"], "西南风")
        self.assertEqual(first["windscaleday"], "2")
        self.assertEqual(first["windscalenight"], "1")
        self.assertEqual(first["text"], "晴")
        self.assertEqual(first["textnight"], "晴")
        self.assertEqual(first["icon"], "100")
        self.assertEqual(first["iconnight"], "100")
        self.assertEqual(first["native_precipitation_probability"], 0)

    def test_days_argument_slices(self):
        self.assertEqual(len(mapping.map_daily(load("daily"), 3)), 3)

    def test_precipitation_sums_day_and_night(self):
        payload = {"days": [{
            "forecastStartTime": "2026-11-09T00:00+08:00",
            "daytime": {"precipitation": {"amount": {"value": 0.5}}},
            "nighttime": {"precipitation": {"amount": {"value": 0.25}}},
        }]}
        self.assertEqual(mapping.map_daily(payload)[0]["native_precipitation"], 0.75)

    def test_precipitation_one_side_missing(self):
        payload = {"days": [{
            "daytime": {"precipitation": {"amount": {"value": 0.6}}},
            "nighttime": {"precipitation": {"amount": {"value": None}}},
        }]}
        self.assertEqual(mapping.map_daily(payload)[0]["native_precipitation"], 0.6)

    def test_precipitation_both_missing(self):
        payload = {"days": [{"daytime": {}, "nighttime": {}}]}
        self.assertIsNone(mapping.map_daily(payload)[0]["native_precipitation"])


class TestMapHourly(unittest.TestCase):
    def setUp(self):
        self.hours = mapping.map_hourly(load("hourly"), 24)

    def test_every_hour_has_pressure(self):
        self.assertEqual(len(self.hours), 3)
        for hour in self.hours:
            self.assertIsNotNone(hour["native_pressure"])
            self.assertIsInstance(hour["native_precipitation_probability"], int)
            self.assertGreaterEqual(hour["native_precipitation_probability"], 0)
            self.assertLessEqual(hour["native_precipitation_probability"], 100)

    def test_first_hour_values(self):
        first = self.hours[0]
        self.assertEqual(first["datetime"], "2026-11-09T13:00+08:00")
        self.assertEqual(first["native_temperature"], 9.64)
        self.assertEqual(first["humidity"], 34)
        self.assertEqual(first["native_wind_speed"], 11.6)
        self.assertEqual(first["wind_bearing"], 206.0)
        self.assertEqual(first["native_pressure"], 1037.01)
        self.assertEqual(first["native_precipitation_probability"], 0)
        self.assertEqual(first["winddir"], "南西南风")
        self.assertEqual(first["windscale"], "2")
        self.assertEqual(first["vis"], 25.5)
        self.assertEqual(first["condition"], "sunny")
        self.assertEqual(first["text"], "晴")

    def test_probability_conversion_and_clamp(self):
        payload = {"hours": [
            {"precipitation": {"probability": 0.03}},
            {"precipitation": {"probability": 1.0}},
            {"precipitation": {"probability": 1.5}},
        ]}
        values = [
            item["native_precipitation_probability"]
            for item in mapping.map_hourly(payload)
        ]
        self.assertEqual(values, [3, 100, 100])


class TestMapAlerts(unittest.TestCase):
    def test_zero_result_returns_empty_list(self):
        self.assertEqual(mapping.map_alerts(load("alert")), [])

    def test_empty_or_missing_alerts(self):
        self.assertEqual(mapping.map_alerts({}), [])
        self.assertEqual(mapping.map_alerts({"alerts": []}), [])
        self.assertEqual(mapping.map_alerts(None), [])

    def test_active_alert_mapping(self):
        payload = {
            "metadata": {"zeroResult": False},
            "alerts": [{
                "id": "alert-1",
                "senderName": None,
                "issuedTime": "2026-11-09T10:00+08:00",
                "headline": "大风蓝色预警",
                "onsetTime": None,
                "effectiveTime": "2026-11-09T11:00+08:00",
                "expireTime": "2026-11-09T23:00+08:00",
                "messageType": {"code": "alert", "supersedes": ["old-id"]},
                "color": {
                    "code": "blue", "red": 0, "green": 0, "blue": 255,
                },
                "severity": "Minor",
                "eventType": {"code": "1006", "name": "大风"},
                "urgency": None,
                "certainty": "likely",
                "description": "预计未来 12 小时有大风。",
            }],
        }
        alerts = mapping.map_alerts(payload)
        self.assertEqual(len(alerts), 1)
        alert = alerts[0]
        self.assertEqual(alert.id, "alert-1")
        self.assertEqual(alert.sender, "")
        self.assertEqual(alert.pubTime, "2026-11-09T10:00+08:00")
        self.assertEqual(alert.title, "大风蓝色预警")
        self.assertEqual(alert.startTime, "2026-11-09T11:00+08:00")
        self.assertEqual(alert.endTime, "2026-11-09T23:00+08:00")
        self.assertEqual(alert.status, "alert")
        self.assertEqual(alert.level, "蓝色")
        self.assertEqual(alert.severity, "minor")
        self.assertEqual(alert.severityColor, "#0000FF")
        self.assertEqual(alert.type, "1006")
        self.assertEqual(alert.typeName, "大风")
        self.assertEqual(alert.urgency, "")
        self.assertEqual(alert.certainty, "likely")
        self.assertEqual(alert.text, "预计未来 12 小时有大风。")
        self.assertEqual(alert.related, "old-id")

    def test_missing_color_is_empty(self):
        payload = {"alerts": [{"id": "x", "color": None}]}
        alert = mapping.map_alerts(payload)[0]
        self.assertEqual(alert.level, "")
        self.assertEqual(alert.severityColor, "")


class TestMapAirQuality(unittest.TestCase):
    def setUp(self):
        self.result = mapping.map_air_quality(
            load("air"), "2026-11-09T12:03:26+08:00"
        )

    def test_required_values(self):
        self.assertEqual(self.result["aqi"], 17)
        self.assertEqual(self.result["level"], "1")
        self.assertEqual(self.result["category"], "优")
        self.assertEqual(self.result["primary"], "NA")
        self.assertEqual(self.result["pm2p5"], 8.0)
        self.assertEqual(self.result["pm10"], 16.0)
        self.assertEqual(self.result["no2"], 20.0)
        self.assertEqual(self.result["o3"], 39.0)
        self.assertEqual(self.result["so2"], 3.0)
        self.assertEqual(self.result["co"], 0.5)
        self.assertEqual(self.result["pubTime"], "2026-11-09T12:03:26+08:00")
        self.assertTrue(self.result["indexes"])
        self.assertTrue(self.result["pollutants"])

    def test_aqi_is_int_convertible(self):
        self.assertEqual(int(self.result["aqi"]), 17)

    def test_empty_payload(self):
        result = mapping.map_air_quality({})
        self.assertIsNone(result["aqi"])
        self.assertEqual(result["primary"], "NA")
        self.assertEqual(result["indexes"], [])
        self.assertEqual(result["pollutants"], [])


class TestBuildHourlySummary(unittest.TestCase):
    def test_fixture_summary(self):
        current = mapping.map_current(load("current"))
        days = mapping.map_daily(load("daily"))
        aqi = mapping.map_air_quality(load("air"))
        summary = mapping.build_hourly_summary(
            current["native_temperature"], days[0], aqi
        )
        self.assertEqual(
            summary,
            "今天白天晴，夜间晴，-1~11°C，当前9°C，空气质量优。",
        )

    def test_missing_daily_returns_empty(self):
        self.assertEqual(mapping.build_hourly_summary(9.0, None, None), "")


if __name__ == "__main__":
    unittest.main()
