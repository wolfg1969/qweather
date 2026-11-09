# QWeather WebAPI v7 → v1 迁移报告

分支：`feat/webapi-v1`
基线：`master`（集成版本 2026.2.5）
目标版本：`2026.11.0`
日期：2026-11-09

## 1. 背景

和风天气官方停服时间表（https://dev.qweather.com/docs/deprecated/）：

| API | endpoint | 停服日期 |
|---|---|---|
| 空气质量 | `/v7/air/now`、`/v7/air/5d` | 2026-06-01 |
| 太阳辐照 | `/v7/solar-radiation/{hours}` | 2026-09-01 |
| 天气预警 | `/v7/warning/now` | 2026-10-01 |
| 城市天气 | `/v7/weather/now`、`/v7/weather/{days}`、`/v7/weather/{hours}` | 2027-06-01 |

本次把实时、每日、小时、预警、空气质量迁移到 v1，并保留完整 v7 代码路径用于回退。

## 2. 端点对照

| 原 v7 | 新 v1 |
|---|---|
| `/v7/weather/now?location={lon},{lat}` | `/weather/v1/current/{lat}/{lon}?localTime=true&lang=zh` |
| `/v7/weather/{n}d?location=...` | `/weather/v1/daily/{lat}/{lon}?days={n}&localTime=true&lang=zh`（n>10 钳到 10） |
| `/v7/weather/{n}h?location=...` | `/weather/v1/hourly/{lat}/{lon}?hours={n}&localTime=true&lang=zh` |
| `/v7/warning/now?location=...` | `/weatheralert/v1/current/{lat}/{lon}?localTime=true&lang=zh` |
| `https://api.qweather.com/airquality/v1/current/...`（硬编码域名） | `{host}/airquality/v1/current/{lat}/{lon}?lang=zh`，失败回落 `/v7/air/now` |
| `https://geoapi.qweather.com/v2/city/lookup`（硬编码域名） | `{host}/geo/v2/city/lookup`，失败回落旧域名 |
| `/v7/astronomy/sun` | v1 分支删除；日出日落取 `daily.days[0].astro` |
| `/v7/indices/1d` | 保持不变（未列入停服表） |
| `/v7/minutely/5m` | 保持不变（未列入停服表） |

## 3. 字段与单位换算

- 实时：`humidity × 100`、`wind.speed × 3.6`（m/s→km/h）、`visibility ÷ 1000`（m→km）、`cloudCover × 100`；`validTime` 作为 `obsTime`。
- 每日：降水为白天+夜间 amount 之和；`humidity`/`cloudCover`/`probability × 100`；`native_pressure` 与 `vis` 为 `None`（v1 日均无此数据）。
- 小时：有气压；`probability × 100` 并限制在 0–100。
- 预警：`onsetTime or effectiveTime`、`messageType.code`、`color.code`→中文、`color.rgb`→`#RRGGBB`、`eventType.*`、`messageType.supersedes[0]`。
- 空气质量：输出保持 v7 形状（`aqi.aqi`、`level`、`category`、`primary`、`pm2p5/pm10/no2/o3/so2/co`、`pubTime`），并保留原始 `indexes`/`pollutants`。
- `hourly_summary` 改为本地拼装，不再抓取 `fxLink` 网页；移除 `beautifulsoup4` 依赖。

## 4. 不可破坏的契约（已用测试锁定）

- 实体 `weather.tian_qi`、`unique_id`（`qw_{lon}_{lat}`）、`supported_features` 不变。
- 实体属性名清单不变（`city`、`qweather_icon`、`condition_cn`、`aqi`、`warning`、`suggestion`、`forecast_hourly` 等）。
- 每日/小时 forecast 字典键名保持；每日仅**新增** `native_precipitation_probability`，小时仅**新增** `vis`（前端不读取，HA 忽略未知键）。
- `WarningData` 16 个字段名称与顺序不变。
- `local/qweather-card/*.js` 一行未改。

## 5. 已知行为变化（非 breaking）

| 项 | 变化 |
|---|---|
| 气压 | v1 为海平面气压，v7 为站点气压，数值差几 hPa |
| 露点 | v7 露点明显错误；v1 数值正确，迁移后 `dew` 会“突变”为合理值 |
| 月相 | 中文 → `new-moon`、`waning-gibbous` 等英文枚举 |
| 每日预报 | 不再提供气压与能见度（字段保留为 `None`） |
| 预警 | 请求失败/节流时保留上一条预警（仅成功空结果才清空） |
| 摘要 | `hourly_summary` 由本地模板生成，不再是网页摘要原文 |

## 6. 回退

1. **UI 回退（推荐）**：集成 → 选项 → `API 版本` 选择 `v7` → 保存，集成自动重载。
2. **代码回退**：`git checkout master -- custom_components/qweather` 或恢复部署前备份：
   ```bash
   tar czf /tmp/qweather-2026.2.5.tar.gz <HA_CONFIG_DIR>/custom_components/qweather
   rm -rf <HA_CONFIG_DIR>/custom_components/qweather
   tar xzf /tmp/qweather-2026.2.5.tar.gz -C <HA_CONFIG_DIR>/custom_components
   ```
   然后重启 Home Assistant Core。
3. **配置兼容**：`ConfigFlow.VERSION` 仍为 1，无配置条目迁移，旧条目升级后直接可用。

## 7. 未做的事

- `/v7/indices/1d`（生活指数）与 `/v7/minutely/5m`（分钟级降雨）仍走 v7，二者未列入停服表。项目 Host 上 minutely 返回 403 时保持空字符串，不重试报错。
- v7 代码路径未删除；待 v1 稳定运行后另开 PR 清理。
- `CONF_ALERT`、`CONF_GIRD` 选项仍未被 `weather.py` 使用（迁移前即如此，不在本次范围）。

## 8. 验证

### 8.1 离线单测

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m pytest -q tests/   # 若已安装 pytest
```

当前结果：32 个用例全部通过（fixture 为 2026-11-09 真实响应，坐标/主机信息未入库）。

### 8.2 实机验收清单（部署后逐项勾选）

- [ ] `state` 非 `unknown`/`unavailable`；`condition_cn` 与 `qweather_icon` 匹配
- [ ] `temperature` 与体感温度合理（与天气 App 差 ≤2°C）
- [ ] `humidity` 是 0–100 整数（不是 0/1 小数）
- [ ] `wind_speed` 单位 km/h，数量级 0–80
- [ ] `visibility` 单位 km，常见 5–30
- [ ] `cloud` 0–100
- [ ] `sunrise`/`sunset` 为带时区 ISO，与日历一致（不差 8 小时）
- [ ] `aqi.aqi` 有数值，`aqi.category` 为中文
- [ ] `suggestion` 10+ 条，`title` 含 `sport/cw/uv`
- [ ] 无预警时 `warning` 为 `[]`，不是 `null` 或旧数据
- [ ] 每日预报 7 条，`templow < temperature`，`textnight`/`iconnight` 有值
- [ ] 小时预报 24 条，`datetime` 递增且带 `+08:00`
- [ ] `update_time` 每 10 分钟刷新
- [ ] `qweather-card`：AQI 徽标、24h 曲线、预警区、生活指数正常
- [ ] more-info：图标、天气文字、温湿度/气压/风速/能见度、每日/小时 tab、日出日落正常
- [ ] 冷启动 30 分钟日志无 `ERROR`，核心端点无 401/403/4xx

### 8.3 日志与请求量

- 删除 astronomy 请求后请求总量应下降；按默认 10 分钟刷新估算约 529 次/天（含重试余量）。
- v1 air 首次探测与 minutely 使用 DEBUG 级别记录权限失败，避免日志刷 WARNING。
