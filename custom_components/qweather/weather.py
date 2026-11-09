import logging
import time
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from urllib.parse import urlencode

import jwt

from homeassistant.components.weather import (
    Forecast,
    WeatherEntity,
    WeatherEntityFeature,
)

from homeassistant.const import (
    CONF_HOST,
    CONF_API_KEY,
    CONF_NAME,
    UnitOfLength,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
import homeassistant.util.dt as dt_util
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.components.http import StaticPathConfig
from homeassistant.components import frontend

from .const import (
    VERSION,
    ROOT_PATH,
    ATTRIBUTION,
    MANUFACTURER,
    DOMAIN,
    CONF_USE_TOKEN,
    CONF_LOCATION,
    CONF_HOURLYSTEPS,
    CONF_DAILYSTEPS,
    CONF_LIFEINDEX,
    CONF_CUSTOM_UI,
    CONF_UPDATE_INTERVAL,
    ATTR_CONDITION_CN,
    ATTR_UPDATE_TIME,
    ATTR_AQI,
    ATTR_SUGGESTION,
    SUGGESTIONTPYE2NAME,
    CONF_PROJECT_ID,
    CONF_KEY_ID,
    CONF_PRIVATE_KEY,
    CONF_API_VERSION,
    DEFAULT_API_VERSION,
)
from .condition import CONDITION_MAP, EXCEPTIONAL
from .mapping import (
    WarningData,
    build_hourly_summary,
    map_current,
    map_daily,
    map_hourly,
)

_LOGGER = logging.getLogger(__name__)

VERSION = "2026.2.5"

# Falsey sentinel: tells the warning block apart from "request failed".
_SKIP = False

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up QWeather entry."""
    await hass.http.async_register_static_paths([
        StaticPathConfig(ROOT_PATH, hass.config.path('custom_components/qweather/local'), False)
    ])

    frontend.add_extra_js_url(hass, f"{ROOT_PATH}/qweather-card/qweather-card.js?ver={VERSION}")
    frontend.add_extra_js_url(hass, f"{ROOT_PATH}/qweather-card/qweather-more-info.js?ver={VERSION}")

    location = config_entry.data.get(CONF_LOCATION) or \
               f"{round(hass.config.longitude, 2)},{round(hass.config.latitude, 2)}"

    name = config_entry.data.get(CONF_NAME, "和风天气")
    host = config_entry.data.get(CONF_HOST, "api.qweather.com")
    usetoken = config_entry.data.get(CONF_USE_TOKEN, False)
    unique_id = config_entry.unique_id or f"qw_{location.replace(',', '_')}"

    data = WeatherData(hass, name, unique_id, host, config_entry.data, usetoken, location, config_entry.options)
    data.set_session(async_get_clientsession(hass))

    weather_entity = HeFengWeather(data, config_entry.options.get(CONF_CUSTOM_UI, False), unique_id, name)
    async_add_entities([weather_entity], False)

    async def _initial_fetch():
        try:
            await data.async_update(dt_util.now())
            weather_entity.async_write_ha_state()
        except Exception as e:
            _LOGGER.error("[%s] Initial fetch failed: %s", name, e)

    hass.async_create_task(_initial_fetch())

    update_interval = config_entry.options.get(CONF_UPDATE_INTERVAL, 10)
    async_track_time_interval(hass, weather_entity.async_update_external, timedelta(minutes=update_interval))

    return True

class HeFengWeather(WeatherEntity):
    """Representation of a weather condition."""

    def __init__(self, data, custom_ui, unique_id, name):
        self._data = data
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._custom_ui = custom_ui

        self._attr_native_precipitation_unit = UnitOfLength.MILLIMETERS
        self._attr_native_pressure_unit = UnitOfPressure.HPA
        self._attr_native_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_native_visibility_unit = UnitOfLength.KILOMETERS
        self._attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR

        self._attr_supported_features = (
            WeatherEntityFeature.FORECAST_DAILY |
            WeatherEntityFeature.FORECAST_HOURLY
        )

    @property
    def device_info(self):
        from homeassistant.helpers.device_registry import DeviceEntryType
        return {
            "identifiers": {(DOMAIN, self._attr_unique_id)},
            "name": self._attr_name,
            "manufacturer": MANUFACTURER,
            "entry_type": DeviceEntryType.SERVICE,
            "sw_version": VERSION,
        }

    @property
    def available(self): return True

    @property
    def native_temperature(self): return self._data._native_temperature
    @property
    def humidity(self): return self._data._humidity
    @property
    def native_pressure(self): return self._data._native_pressure
    @property
    def native_wind_speed(self): return self._data._native_wind_speed
    @property
    def wind_bearing(self): return self._data._wind_bearing
    @property
    def condition(self): return self._data._condition
    @property
    def native_visibility(self): return self._data._vis

    async def async_update_external(self, _):
        await self._data.async_update(dt_util.now())
        self.async_write_ha_state()

    async def async_forecast_daily(self) -> list[Forecast] | None:
        return self._data._daily_forecast

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        return self._data._hourly_forecast

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        data = self._data
        attrs = super().state_attributes or {}
        if data._condition:
            attrs.update({
                "city": data._city,
                "qweather_icon": data._icon,
                ATTR_UPDATE_TIME: data._refreshtime,
                ATTR_CONDITION_CN: data._condition_cn,
                ATTR_AQI: data._aqi,
                "feels_like": data._feelslike,
                "cloud": data._cloud,
                "sunrise": data._sun_data.get("sunrise"),
                "sunset": data._sun_data.get("sunset"),
                "hourly_summary": data._hourly_summary,
                "minutely_summary": data._minutely_summary,
                "winddir": data._winddir,
                "windscale": data._windscale,
                "vis": data._vis,
                "precip": data._precip,
                "dew": data._dew,
                "obsTime": data._obsTime,
                "forecast_hourly": data._hourly_summary,
                "forecast_minutely": data._minutely_summary,
                ATTR_SUGGESTION: [asdict(s) for s in data._suggestion],
                "warning": [asdict(w) for w in data._weather_warning],
            })
            if self._custom_ui:
                attrs["custom_ui_more_info"] = "qweather-more-info"
        return attrs

@dataclass
class Suggestion:
    title: str
    title_cn: str
    brf: str
    txt: str

class WeatherData:
    def __init__(self, hass, name, unique_id, host, config, usetoken, location, options):
        self._hass = hass
        self._name = name
        self._host = host
        self._config = config
        self._use_token = usetoken
        self._location = location
        self._options = options
        self._api_version = options.get(CONF_API_VERSION, DEFAULT_API_VERSION)

        self._condition = None
        self._condition_cn = None
        self._icon = None
        self._native_temperature = None
        self._humidity = None
        self._native_pressure = None
        self._native_wind_speed = None
        self._wind_bearing = None
        self._winddir = None
        self._windscale = None
        self._feelslike = None
        self._cloud = None
        self._vis = None
        self._precip = None
        self._dew = None
        self._obsTime = None
        self._aqi = {}
        self._suggestion = []
        self._weather_warning = []
        self._daily_forecast = []
        self._hourly_forecast = []
        self._sun_data = {}
        self._city = None
        self._hourly_summary = ""
        self._minutely_summary = ""
        self._refreshtime = None

        self._updates = {k: 0 for k in ['now', 'daily', 'hourly', 'air', 'warning', 'indices', 'geo', 'sun', 'minutely']}

    def set_session(self, session):
        self._session = session

    def generate_jwt(self):
        try:
            now_ts = int(time.time())
            payload = {'iat': now_ts - 30, 'exp': now_ts + 900, 'sub': self._config.get(CONF_PROJECT_ID)}
            headers = {'kid': self._config.get(CONF_KEY_ID)}
            return jwt.encode(payload, self._config.get(CONF_PRIVATE_KEY), algorithm='EdDSA', headers=headers)
        except Exception as e:
            _LOGGER.error("JWT Error: %s", e)
            return None

    def _coords(self):
        """Return (lat, lon) with two decimals for v1 path parameters."""
        parts = str(self._location or "").replace(" ", "").split(",")
        if len(parts) != 2:
            return None
        try:
            lon = round(float(parts[0]), 2)
            lat = round(float(parts[1]), 2)
        except (TypeError, ValueError):
            return None
        return f"{lat}", f"{lon}"

    def _update_sun_from_daily(self):
        if self._daily_forecast:
            first = self._daily_forecast[0]
            self._sun_data = {
                "sunrise": first.get("sunrise"),
                "sunset": first.get("sunset"),
            }

    def _refresh_hourly_summary(self):
        first = self._daily_forecast[0] if self._daily_forecast else None
        self._hourly_summary = build_hourly_summary(
            self._native_temperature, first, self._aqi
        )

    async def async_update(self, now):
        """Fetch data from QWeather API."""
        current_ts = int(time.time())
        headers = {}
        if self._use_token:
            token = self.generate_jwt()
            if token: headers["Authorization"] = f"Bearer {token}"
        else:
            headers["X-QW-Api-Key"] = self._config.get(CONF_API_KEY)

        intervals = {
            'now': 600, 'daily': 3600, 'hourly': 3600,
            'air': 3600, 'warning': 300, 'indices': 3600,
            'sun': 43200, 'minutely': 600
        }

        async def fetch(url, key, params=None, validate=None, auth_log=logging.WARNING):
            last_upd = self._updates.get(key, 0)
            if last_upd > 0 and (current_ts - last_upd < intervals.get(key, 600)):
                return _SKIP

            if params:
                connector = "&" if "?" in url else "?"
                url = f"{url}{connector}{urlencode(params)}"

            try:
                async with self._session.get(url, headers=headers, timeout=10) as resp:
                    if resp.status in (401, 403):
                        _LOGGER.log(auth_log, "[%s] auth/permission %s: HTTP %s", self._name, key, resp.status)
                        return None
                    if resp.status >= 400:
                        _LOGGER.warning("[%s] HTTP %s fetching %s", self._name, resp.status, key)
                        return None
                    data = await resp.json(content_type=None)
            except Exception as e:
                _LOGGER.error("[%s] Error fetching %s: %s", self._name, key, e)
                return None

            if not isinstance(data, dict) or "error" in data:
                return None
            if data.get("code") == "200" or "metadata" in data:
                ok = True
            else:
                ok = False
            if not ok or (validate is not None and not validate(data)):
                return None

            self._updates[key] = current_ts
            return data

        coords = self._coords()
        use_v1 = self._api_version == "v1" and coords is not None
        if use_v1:
            await self._update_v1(fetch, coords)
        else:
            if self._api_version == "v1":
                _LOGGER.warning(
                    "[%s] api_version=v1 requires 'lon,lat' location, got '%s'; falling back to v7",
                    self._name, self._location,
                )
            await self._update_v7(fetch)

        # 4. Air Quality
        try:
            location_parts = self._location.split(',')
            lon, lat = location_parts[0].strip(), location_parts[1].strip()
            # V1 新版接口
            air_v1_url = f"https://api.qweather.com/airquality/v1/current/{lat}/{lon}"
            air_data = await fetch(air_v1_url, 'air', params={'lang': 'zh'})

            if air_data:
                # 兼容 V1 airNow 或 v7 now
                self._aqi = air_data.get('airNow') or air_data.get('now') or air_data
            else:
                # 回退到 V7 (适配部分未开通V1权限的KEY)
                air_v7_url = f"https://{self._host}/v7/air/now?location={self._location}"
                air_v7_data = await fetch(air_v7_url, 'air', params={'lang': 'zh'})
                if air_v7_data:
                    self._aqi = air_v7_data.get('now', {})
        except Exception as e:
            _LOGGER.error("[%s] AQI error: %s", self._name, e)
            self._aqi = {}

        # 5. Others (Warning & Indices & Astronomy & Minutely)
        warn_resp = await fetch(f"https://{self._host}/v7/warning/now?location={self._location}", 'warning', params={'lang': 'zh'})

        if warn_resp and 'warning' in warn_resp:
            self._weather_warning = [
                WarningData(
                    id=w.get('id', ''),
                    sender=w.get('sender', ''),
                    pubTime=w.get('pubTime', ''),
                    title=w.get('title', ''),
                    startTime=w.get('startTime', ''),
                    endTime=w.get('endTime', ''),
                    status=w.get('status', ''),
                    level=w.get('level', ''),
                    severity=w.get('severity', ''),
                    severityColor=w.get('severityColor', ''),
                    type=w.get('type', ''),
                    typeName=w.get('typeName', ''),
                    urgency=w.get('urgency', ''),
                    certainty=w.get('certainty', ''),
                    text=w.get('text', ''),
                    related=w.get('related', '')
                ) for w in warn_resp['warning']
            ]
        elif warn_resp is not _SKIP:
            self._weather_warning = [] # Clear on a real empty response

        if self._options.get(CONF_LIFEINDEX, True):
            idx_resp = await fetch(f"https://{self._host}/v7/indices/1d?type=0&location={self._location}", 'indices', params={'lang': 'zh'})
            if idx_resp and 'daily' in idx_resp:
                self._suggestion = [Suggestion(title=SUGGESTIONTPYE2NAME.get(v.get('type'), "未知"), title_cn=v.get('name'), brf=v.get('category'), txt=v.get('text')) for v in idx_resp['daily']]

        # 6. Geo (City Lookup)
        if self._city is None:
            try:
                # GeoAPI 使用独立的域名 geoapi.qweather.com
                geo_url = f"https://geoapi.qweather.com/v2/city/lookup?location={self._location}&lang=zh"

                # 复用上面已经定义好的 headers (包含 token 或 api key)
                async with self._session.get(geo_url, headers=headers, timeout=10) as resp:
                    geo_data = await resp.json(content_type=None)
                    if geo_data.get("code") == "200" and geo_data.get("location"):
                        city_name = geo_data["location"][0]["name"]
                        self._city = city_name
                        _LOGGER.info("[%s] City initialized: %s", self._name, self._city)
                    else:
                        _LOGGER.warning("[%s] GeoAPI failed: %s", self._name, geo_data.get("code"))
                        self._city = "未知" # 避免反复请求失败
            except Exception as e:
                _LOGGER.error("[%s] GeoAPI Request Error: %s", self._name, e)
                self._city = "未知" # 出错暂定未知，下次重启再试

        min_resp = await fetch(f"https://{self._host}/v7/minutely/5m?location={self._location}", 'minutely', params={'lang': 'zh'})
        if min_resp and min_resp is not _SKIP: self._minutely_summary = min_resp.get("summary", "")

        if use_v1:
            self._update_sun_from_daily()
        self._refresh_hourly_summary()

        self._available = True
        self._refreshtime = dt_util.as_local(dt_util.now()).strftime('%Y-%m-%d %H:%M')

    async def _update_v1(self, fetch, coords):
        lat, lon = coords

        # 1. Current
        now_resp = await fetch(
            f"https://{self._host}/weather/v1/current/{lat}/{lon}", 'now',
            params={'localTime': 'true', 'lang': 'zh'},
            validate=lambda data: "temperature" in data,
        )
        if now_resp:
            mapped = map_current(now_resp)
            self._condition = mapped["condition"]
            self._condition_cn = mapped["condition_cn"]
            self._icon = mapped["icon"]
            self._native_temperature = mapped["native_temperature"]
            self._humidity = mapped["humidity"]
            self._native_pressure = mapped["native_pressure"]
            self._native_wind_speed = mapped["native_wind_speed"]
            self._wind_bearing = mapped["wind_bearing"]
            self._winddir = mapped["winddir"]
            self._windscale = mapped["windscale"]
            self._feelslike = mapped["feelslike"]
            self._cloud = mapped["cloud"]
            self._vis = mapped["vis"]
            self._precip = mapped["precip"]
            self._dew = mapped["dew"]
            self._obsTime = mapped["obsTime"]

        # 2. Daily
        daily_steps = self._options.get(CONF_DAILYSTEPS, 7)
        if daily_steps > 10:
            _LOGGER.warning(
                "[%s] API v1 daily supports at most 10 days, clamping %s -> 10",
                self._name, daily_steps,
            )
            daily_steps = 10
        daily_resp = await fetch(
            f"https://{self._host}/weather/v1/daily/{lat}/{lon}", 'daily',
            params={'days': daily_steps, 'localTime': 'true', 'lang': 'zh'},
            validate=lambda data: "days" in data,
        )
        if daily_resp:
            self._daily_forecast = map_daily(daily_resp, daily_steps)

        # 3. Hourly
        hourly_steps = self._options.get(CONF_HOURLYSTEPS, 24)
        hourly_resp = await fetch(
            f"https://{self._host}/weather/v1/hourly/{lat}/{lon}", 'hourly',
            params={'hours': hourly_steps, 'localTime': 'true', 'lang': 'zh'},
            validate=lambda data: "hours" in data,
        )
        if hourly_resp:
            self._hourly_forecast = map_hourly(hourly_resp, hourly_steps)

    async def _update_v7(self, fetch):
        # 1. Now
        now_resp = await fetch(f"https://{self._host}/v7/weather/now?location={self._location}", 'now', params={'lang': 'zh'})
        if now_resp and 'now' in now_resp:
            c = now_resp['now']
            self._condition = CONDITION_MAP.get(c.get('icon'), EXCEPTIONAL)
            self._condition_cn = c.get('text')
            self._native_temperature = float(c.get('temp', 0))
            self._humidity = int(c.get('humidity', 0))
            self._native_pressure = int(c.get('pressure', 0))
            self._native_wind_speed = float(c.get('windSpeed', 0))
            self._wind_bearing = float(c.get('wind360', 0))
            self._winddir = c.get('windDir')
            self._windscale = c.get('windScale')
            self._feelslike = float(c.get('feelsLike', 0))
            self._cloud = c.get('cloud')
            self._icon = c.get('icon')
            self._vis = float(c.get('vis', 0))
            self._precip = float(c.get('precip', 0))
            self._dew = float(c.get('dew', 0))
            self._obsTime = c.get('obsTime')

        # 2. Daily
        daily_steps = self._options.get(CONF_DAILYSTEPS, 7)
        daily_resp = await fetch(f"https://{self._host}/v7/weather/{daily_steps}d?location={self._location}", 'daily', params={'lang': 'zh'})
        if daily_resp and 'daily' in daily_resp:
            new_daily = []
            for d in daily_resp['daily']:
                raw_date = d.get('fxDate')
                if raw_date and "T" not in raw_date:
                    # 将 "2026-02-01" 转换为 "2026-02-01T00:00:00"
                    fixed_datetime = f"{raw_date}T00:00:00"
                else:
                    fixed_datetime = raw_date

                new_daily.append({
                    # 标准 HA 字段
                    "datetime": fixed_datetime,
                    "native_temperature": float(d.get('tempMax', 0)),
                    "native_templow": float(d.get('tempMin', 0)),
                    "condition": CONDITION_MAP.get(d.get('iconDay'), "exceptional"),
                    "native_precipitation": float(d.get('precip', 0)),
                    "native_pressure": float(d.get('pressure', 0)),
                    "native_wind_speed": float(d.get('windSpeedDay', 0)),
                    "wind_bearing": float(d.get('wind360Day', 0)),
                    "humidity": float(d.get("humidity", 0)),

                    # 扩展字段 (供自定义卡片使用)
                    "text": d.get('textDay'),           # 白天天气文字
                    "icon": d.get('iconDay'),           # 白天图标代码
                    "textnight": d.get("textNight"),    # 夜间天气文字
                    "iconnight": d.get("iconNight"),    # 夜间图标代码
                    "winddirday": d.get("windDirDay"),  # 白天风向
                    "winddirnight": d.get("windDirNight"), # 夜间风向
                    "windscaleday": d.get("windScaleDay"), # 白天风力等级
                    "windscalenight": d.get("windScaleNight"), # 夜间风力等级
                    "uv_index": d.get("uvIndex"),       # 紫外线
                    "vis": d.get("vis"),                # 能见度
                    "cloud": d.get("cloud"),            # 云量
                    "sunrise": d.get("sunrise"),        # 日出
                    "sunset": d.get("sunset"),          # 日落
                    "moonphase": d.get("moonPhase"),    # 月相
                })
            self._daily_forecast = new_daily

        # 3. Hourly
        hourly_steps = self._options.get(CONF_HOURLYSTEPS, 24)
        hourly_resp = await fetch(f"https://{self._host}/v7/weather/{hourly_steps}h?location={self._location}", 'hourly', params={'lang': 'zh'})
        if hourly_resp and 'hourly' in hourly_resp:
            new_hourly = []
            for h_item in hourly_resp['hourly']:
                try:
                    dt_obj = datetime.fromisoformat(h_item.get("fxTime").replace('Z', '+00:00'))
                    time_iso = dt_obj.isoformat()
                except:
                    time_iso = h_item.get("fxTime")
                new_hourly.append({
                    # 标准 HA 字段
                    "datetime": time_iso,
                    "native_temperature": float(h_item.get('temp', 0)),
                    "condition": CONDITION_MAP.get(h_item.get('icon'), "exceptional"),
                    "native_precipitation": float(h_item.get('precip', 0)),
                    "native_pressure": float(h_item.get('pressure', 0)),
                    "humidity": float(h_item.get('humidity', 0)),
                    "native_wind_speed": float(h_item.get('windSpeed', 0)),
                    "wind_bearing": float(h_item.get('wind360', 0)),

                    # 扩展字段
                    "native_precipitation_probability": int(h_item.get('pop', 0)), # 降水概率
                    "text": h_item.get('text'),   # 天气文字
                    "icon": h_item.get('icon'),   # 图标代码
                    "winddir": h_item.get('windDir'), # 风向
                    "windscale": h_item.get('windScale') # 风力等级
                })
            self._hourly_forecast = new_hourly

        # 4. Astronomy (kept for the v7 rollback path; v1 uses daily.astro)
        today_str = datetime.now().strftime("%Y%m%d")
        sun_resp = await fetch(f"https://{self._host}/v7/astronomy/sun?location={self._location}&date={today_str}", 'sun', params={'lang': 'zh'})
        if sun_resp:
            self._sun_data = {"sunrise": sun_resp.get("sunrise"), "sunset": sun_resp.get("sunset")}
