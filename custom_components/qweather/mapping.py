"""Pure mapping helpers for QWeather WebAPI v1 responses.

This module intentionally has no Home Assistant imports so it can be unit
tested offline. Both the package import (Home Assistant runtime) and a plain
top-level import (tests put this directory on ``sys.path``) are supported.
"""
from dataclasses import dataclass

if __package__:
    from .const import ALERT_COLOR_CN, COMPASS_CN
    from .condition import CONDITION_MAP, EXCEPTIONAL
else:  # pragma: no cover - used by offline tests
    from const import ALERT_COLOR_CN, COMPASS_CN
    from condition import CONDITION_MAP, EXCEPTIONAL


@dataclass
class WarningData:
    id: str             # 预警ID
    sender: str         # 发布单位
    pubTime: str        # 发布时间
    title: str          # 标题
    startTime: str      # 开始时间
    endTime: str        # 结束时间
    status: str         # 状态 (active/update/cancel)
    level: str          # 等级 (蓝色/黄色/橙色/红色)
    severity: str       # 严重程度 (Unknown/Minor/Moderate/Severe/Extreme)
    severityColor: str  # 严重程度颜色
    type: str           # 预警类型ID
    typeName: str       # 预警类型名称
    urgency: str        # 紧迫程度
    certainty: str      # 确定性
    text: str           # 详细描述
    related: str        # 关联的预警ID


def _as_float(value):
    """Return value as float, or None. Never invents a 0 for missing data."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _value(obj):
    """Return the ``value`` member of a QWeather ``{"value": x, "unit": ...}``."""
    if isinstance(obj, dict):
        return _as_float(obj.get("value"))
    return _as_float(obj)


def _percent(value):
    """QWeather v1 ratios (0..1) -> percentage integer (0..100)."""
    number = _as_float(value)
    return None if number is None else int(round(number * 100))


def _clamped_percent(value):
    result = _percent(value)
    if result is None:
        return None
    return max(0, min(100, result))


def _text(value):
    return "" if value is None else str(value)


def _scale(value):
    number = _as_float(value)
    if number is None:
        return None
    return str(int(number)) if number.is_integer() else str(number)


def _cloud(value):
    percentage = _percent(value)
    return None if percentage is None else str(percentage)


def _compass(direction):
    """Map a v1 English compass point (ssw) to the Chinese label."""
    if not isinstance(direction, dict):
        return ""
    compass = direction.get("compass")
    if compass is None:
        return ""
    key = str(compass).lower()
    return COMPASS_CN.get(key, str(compass))


def _wind_speed_kmh(speed):
    """v1 wind speed is m/s; the entity declares km/h."""
    if not isinstance(speed, dict):
        return None
    number = _as_float(speed.get("value"))
    if number is None:
        return None
    unit = str(speed.get("unit") or "m/s").lower()
    if unit in ("m/s", "mps", "ms"):
        number *= 3.6
    return round(number, 1)


def _visibility_km(visibility):
    """v1 visibility is metres; the entity declares km."""
    if not isinstance(visibility, dict):
        return None
    number = _as_float(visibility.get("value"))
    if number is None:
        return None
    unit = str(visibility.get("unit") or "m").lower()
    if unit in ("m", "meter", "meters", "metre", "metres"):
        number /= 1000
    return round(number, 1)


def _condition(condition):
    """Return (raw code as str, HA condition)."""
    if not isinstance(condition, dict):
        return None, EXCEPTIONAL
    raw = condition.get("code")
    if raw is None:
        return None, EXCEPTIONAL
    code = str(raw)
    return code, CONDITION_MAP.get(code, EXCEPTIONAL)


def _hex_color(color):
    if not isinstance(color, dict):
        return ""
    channels = [color.get("red"), color.get("green"), color.get("blue")]
    if any(channel is None for channel in channels):
        return ""
    try:
        return "#{:02X}{:02X}{:02X}".format(
            *(max(0, min(255, int(channel))) for channel in channels)
        )
    except (TypeError, ValueError):
        return ""


def _sum_present(first, second):
    if first is None and second is None:
        return None
    return (first or 0.0) + (second or 0.0)


def map_current(payload):
    """Map ``/weather/v1/current`` to the entity's current-condition fields."""
    payload = payload if isinstance(payload, dict) else {}
    condition = payload.get("condition") or {}
    code, ha_condition = _condition(condition)
    wind = payload.get("wind") or {}
    direction = wind.get("direction") or {}
    precipitation = payload.get("precipitation") or {}

    return {
        "condition": ha_condition,
        "condition_cn": _text(condition.get("text")),
        "icon": code,
        "native_temperature": _value(payload.get("temperature")),
        "humidity": _percent(payload.get("humidity")),
        "native_pressure": _value(payload.get("pressure")),
        "native_wind_speed": _wind_speed_kmh(wind.get("speed")),
        "wind_bearing": _as_float(direction.get("degree")),
        "winddir": _compass(direction),
        "windscale": _scale(wind.get("scale")),
        "feelslike": _value(payload.get("feelsLike")),
        "cloud": _cloud(payload.get("cloudCover")),
        "vis": _visibility_km(payload.get("visibility")),
        "precip": _value(precipitation.get("amount")),
        "dew": _value(payload.get("dewPoint")),
        "obsTime": payload.get("validTime"),
    }


def map_daily(payload, days=7):
    """Map ``/weather/v1/daily`` to the existing daily forecast keys."""
    result = []
    for day in (payload.get("days") or [])[:days]:
        day = day or {}
        daytime = day.get("daytime") or {}
        nighttime = day.get("nighttime") or {}
        astro = day.get("astro") or {}
        day_condition = daytime.get("condition") or {}
        night_condition = nighttime.get("condition") or {}
        day_code, ha_condition = _condition(day_condition)
        night_code, _ = _condition(night_condition)
        day_wind = daytime.get("wind") or {}
        night_wind = nighttime.get("wind") or {}
        day_precipitation = daytime.get("precipitation") or {}
        night_precipitation = nighttime.get("precipitation") or {}

        result.append({
            # Standard HA forecast fields
            "datetime": day.get("forecastStartTime"),
            "native_temperature": _value(day.get("temperatureMax")),
            "native_templow": _value(day.get("temperatureMin")),
            "condition": ha_condition,
            "native_precipitation": _sum_present(
                _value(day_precipitation.get("amount")),
                _value(night_precipitation.get("amount")),
            ),
            # v1 daily has no pressure/visibility; keep the keys, no fake 0.
            "native_pressure": None,
            "native_wind_speed": _wind_speed_kmh(day_wind.get("speed")),
            "wind_bearing": _as_float((day_wind.get("direction") or {}).get("degree")),
            "humidity": _percent(daytime.get("humidity")),

            # Extended fields used by the custom card
            "text": day_condition.get("text"),
            "icon": day_code,
            "textnight": night_condition.get("text"),
            "iconnight": night_code,
            "winddirday": _compass(day_wind.get("direction")),
            "winddirnight": _compass(night_wind.get("direction")),
            "windscaleday": _scale(day_wind.get("scale")),
            "windscalenight": _scale(night_wind.get("scale")),
            "uv_index": day.get("uvIndexMax"),
            "vis": None,
            "cloud": _cloud(daytime.get("cloudCover")),
            "sunrise": astro.get("sunrise"),
            "sunset": astro.get("sunset"),
            "moonphase": astro.get("moonPhase"),
            "native_precipitation_probability": _clamped_percent(
                day_precipitation.get("probability")
            ),
        })
    return result


def map_hourly(payload, hours=24):
    """Map ``/weather/v1/hourly`` to the existing hourly forecast keys."""
    result = []
    for hour in (payload.get("hours") or [])[:hours]:
        hour = hour or {}
        condition = hour.get("condition") or {}
        code, ha_condition = _condition(condition)
        wind = hour.get("wind") or {}
        direction = wind.get("direction") or {}
        precipitation = hour.get("precipitation") or {}

        result.append({
            # Standard HA forecast fields
            "datetime": hour.get("forecastTime"),
            "native_temperature": _value(hour.get("temperature")),
            "condition": ha_condition,
            "native_precipitation": _value(precipitation.get("amount")),
            "native_pressure": _value(hour.get("pressure")),
            "humidity": _percent(hour.get("humidity")),
            "native_wind_speed": _wind_speed_kmh(wind.get("speed")),
            "wind_bearing": _as_float(direction.get("degree")),

            # Extended fields used by the custom card
            "native_precipitation_probability": _clamped_percent(
                precipitation.get("probability")
            ),
            "text": condition.get("text"),
            "icon": code,
            "winddir": _compass(direction),
            "windscale": _scale(wind.get("scale")),
            "vis": _visibility_km(hour.get("visibility")),
        })
    return result


def map_alerts(payload):
    """Map ``/weatheralert/v1/current`` to ``WarningData`` entries."""
    if not isinstance(payload, dict):
        return []
    metadata = payload.get("metadata") or {}
    if metadata.get("zeroResult") is True:
        return []

    result = []
    for alert in payload.get("alerts") or []:
        alert = alert or {}
        color = alert.get("color") or {}
        message_type = alert.get("messageType") or {}
        event_type = alert.get("eventType") or {}
        supersedes = message_type.get("supersedes") or []
        color_code = color.get("code")

        result.append(WarningData(
            id=_text(alert.get("id")),
            sender=_text(alert.get("senderName")),
            pubTime=_text(alert.get("issuedTime")),
            title=_text(alert.get("headline")),
            startTime=_text(alert.get("onsetTime") or alert.get("effectiveTime")),
            endTime=_text(alert.get("expireTime")),
            status=_text(message_type.get("code")),
            level=ALERT_COLOR_CN.get(str(color_code).lower(), _text(color_code)),
            severity=_text(alert.get("severity")).lower(),
            severityColor=_hex_color(color),
            type=_text(event_type.get("code")),
            typeName=_text(event_type.get("name")),
            urgency=_text(alert.get("urgency")),
            certainty=_text(alert.get("certainty")),
            text=_text(alert.get("description")),
            related=_text(supersedes[0]) if supersedes else "",
        ))
    return result


def map_air_quality(payload, pub_time=None):
    """Map ``/airquality/v1/current`` to the legacy v7-shaped AQI dict."""
    payload = payload if isinstance(payload, dict) else {}
    indexes = payload.get("indexes") or []
    index = next(
        (
            item for item in indexes
            if isinstance(item, dict) and item.get("code") == "cn-mee"
        ),
        None,
    )
    if index is None:
        index = indexes[0] if indexes and isinstance(indexes[0], dict) else {}
    index = index or {}

    primary = index.get("primaryPollutant")
    if isinstance(primary, dict):
        primary_name = primary.get("name") or "NA"
    elif primary:
        primary_name = str(primary)
    else:
        primary_name = "NA"

    pollutants = payload.get("pollutants") or []
    concentrations = {}
    for pollutant in pollutants:
        if not isinstance(pollutant, dict):
            continue
        code = pollutant.get("code")
        if code:
            concentrations[code] = _value(pollutant.get("concentration"))

    try:
        aqi = int(index["aqi"]) if index.get("aqi") is not None else None
    except (TypeError, ValueError):
        aqi = None

    return {
        "aqi": aqi,
        "level": _text(index.get("level")),
        "category": _text(index.get("category")),
        "primary": primary_name,
        "pm2p5": concentrations.get("pm2p5"),
        "pm10": concentrations.get("pm10"),
        "no2": concentrations.get("no2"),
        "o3": concentrations.get("o3"),
        "so2": concentrations.get("so2"),
        "co": concentrations.get("co"),
        "pubTime": pub_time or _text((payload.get("metadata") or {}).get("pubTime")),
        "indexes": indexes,
        "pollutants": pollutants,
    }


def build_hourly_summary(temperature, daily_first, aqi):
    """Build the ``hourly_summary`` string locally (v1 has no ``fxLink``)."""
    if not daily_first:
        return ""

    def fmt(value):
        return "--" if value is None else f"{value:.0f}"

    current = temperature if temperature is not None else daily_first.get("native_temperature")
    category = (aqi or {}).get("category") or "未知"
    return (
        f"今天白天{_text(daily_first.get('text')) or '--'}，"
        f"夜间{_text(daily_first.get('textnight')) or '--'}，"
        f"{fmt(daily_first.get('native_templow'))}~"
        f"{fmt(daily_first.get('native_temperature'))}°C，"
        f"当前{fmt(current)}°C，空气质量{category}。"
    )
