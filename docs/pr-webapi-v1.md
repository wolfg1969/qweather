# 迁移到 WebAPI v1：实时/每日/小时天气 + 天气预警 + 空气质量

分支：`feat/webapi-v1`（基于 `upstream/master`）

## 背景

和风天气官方已公布 v7 停服时间表（https://dev.qweather.com/docs/deprecated/）：

- `/v7/air/now`、`/v7/air/5d`：2026-06-01
- `/v7/warning/now`：2026-10-01
- `/v7/weather/now`、`/v7/weather/{days}`、`/v7/weather/{hours}`：2027-06-01

本 PR 将实时天气、每日预报、小时预报、天气预警、空气质量迁移到 v1，并删除不再需要的 `fxLink` 网页抓取与 `/v7/astronomy/sun` 请求。

## 端点对照

| 原 v7 | 新 v1 |
|---|---|
| `/v7/weather/now` | `/weather/v1/current/{lat}/{lon}?localTime=true&lang=zh` |
| `/v7/weather/{n}d` | `/weather/v1/daily/{lat}/{lon}?days={n}&localTime=true&lang=zh` |
| `/v7/weather/{n}h` | `/weather/v1/hourly/{lat}/{lon}?hours={n}&localTime=true&lang=zh` |
| `/v7/warning/now` | `/weatheralert/v1/current/{lat}/{lon}?localTime=true&lang=zh` |
| 硬编码 `api.qweather.com/airquality/v1` | `{host}/airquality/v1/current/{lat}/{lon}?lang=zh` |
| 硬编码 `geoapi.qweather.com/v2` | `{host}/geo/v2/city/lookup`，失败回落旧域名 |
| `/v7/astronomy/sun` | 删除，改用 `daily.days[0].astro` |

生活指数 `/v7/indices/1d` 与分钟级降雨 `/v7/minutely/5m` 未列入停服表，保持 v7。

## 单位换算

- `humidity`、`cloudCover`、`precipitation.probability`：0–1 → 百分数（×100）。
- `wind.speed`：m/s → km/h（×3.6）。
- `visibility`：m → km（÷1000）。
- 每日降水：白天 + 夜间 amount 相加。
- v1 日均没有气压/能见度，对应字段返回 `None`。

## Breaking changes

**无。** 实体 ID、`unique_id`、属性名、forecast 键名、`WarningData` 字段、前端卡片资源均未改变。每日/小时 forecast 仅新增可选键（`native_precipitation_probability` / `vis`），HA 会忽略未知键。

## 已知行为变化

- 气压口径：v1 为海平面气压，v7 为站点气压。
- 露点：v7 数值有误，v1 修正为合理值。
- `moonPhase`：中文 → `new-moon`、`waning-gibbous` 等英文枚举。
- 每日预报不再提供气压与能见度。
- 预警请求失败/节流时保留上一条，成功空结果才清空。
- `hourly_summary` 改为本地模板生成。

## 测试

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
# 32 tests, OK
```

fixture 为 2026-11-09 的真实 v1 响应（已脱敏，不含 Host/坐标）。实机验收清单见 `REPORT.md` §8.2。

## 与 PR #1 的关系

- 保留其 `iss`（开发者 ID）思路：配置中可填写 `dev_id`，但**非必填**，不填时 JWT 不带 `iss`（实测可用）。
- Geo/air 端点的 Host 对齐思路与 PR #1 一致；本 PR 进一步把 air/geo 从硬编码域名改为使用配置的 `api_host`。
- 本 PR 还覆盖了 PR #1 未涉及的 `/v7/weather/*` 迁移，属于部分 supersede。

## 新增选项

- `api_version`：`v1`（默认）/ `v7`，可随时在集成选项中切换回退。
- `dev_id`：可选开发者 ID（JWT `iss`）。
