# 服务适配器真实验证记录

验证日期：2026-10-20
验证环境：Home Assistant 2026.10.2，OneConnect Bridge 0.1.x（`f2c7e25` 之前的旧版映射格式），
3 个父网关 / 137 个子设备在线。

> 说明：本次新增的适配器在**未升级集成**的前提下，用真实 HA 状态离线验证
> （直接调用适配器的 `read_state` / `apply_command`，数据来自 HA REST API）。
> 集成侧注册与 MQTT 回推在旧版映射格式下已由现有 137 个设备验证过；
> 新版映射格式下的端到端注册需升级后才能跑，已单独标注。

## 1. switch1（多键开关 Profile）

| 项 | 内容 |
|---|---|
| 来源单品 | `ZG2R` 智能开关 奥斯陆(无线版) 1键 |
| Profile | https://smarthome-drcn.dbankcdn.com/device/guide/ZG2R/ZG2R.json |
| 默认契约 | `switch1.on` 为 `bool`；`on_type: int`（默认）上传 0/1，`on_type: bool` 上传 JSON 布尔 |
| 真实设备 | 20 个 ZG2R 开关子设备（旧版映射下已注册并双向验证） |

验证结果：

- HA 状态 → `{"on": 0}` / `{"on": 1}`，JSON 类型为 int ✅
- `on_type: bool` → `{"on": true}` / `{"on": false}` ✅
- 华为下发 1/0 → `switch.turn_on` / `switch.turn_off` ✅
- 实体域限制 `light` / `switch` / `fan` ✅
- 离线真实数据验证：143 个 `switch.sonoff_*` 全部输出 int ✅

## 2. mode（枚举模式服务）

| 项 | 内容 |
|---|---|
| 来源单品 | `A0E0` 海尔智能空调 |
| Profile | https://smarthome-drcn.dbankcdn.com/device/guide/A0E0/A0E0.json |
| 默认契约 | `mode` 为 `enum`：1=auto、2=cool、3=heat、4=fan_only、5=dry |
| 真实设备 | 8 台 A0E0 空调子设备（旧版映射下已注册并双向验证） |

验证结果：

- HA `hvac_mode` → `{"mode": 2}`（cool），JSON 类型为 int ✅
- `heat_cool` 归并到 `auto`（enum 1）✅
- 华为下发 2 → `climate.set_hvac_mode(hvac_mode="cool")` ✅
- 华为下发 3 → `climate.set_hvac_mode(hvac_mode="heat")` ✅
- `mapping` contract 覆盖整表生效 ✅
- `select` 实体支持（`select_option`）✅
- 空调关机（`state=off`）→ `{}`：A0E0 的 `mode` enum 没有 off 值，
  关机由同 Profile 的 `switch.on` 表达，符合 Profile 语义 ✅

## 3. temperature（温度服务，十分之一度）

| 项 | 内容 |
|---|---|
| 来源单品 | `A0E0` 海尔智能空调 |
| Profile | https://smarthome-drcn.dbankcdn.com/device/guide/A0E0/A0E0.json |
| 默认契约 | `temperature.target`（int 16..30）与 `temperature.current`（int -20..50），线上单位为十分之一度；`step: 1.0` |
| 真实设备 | 8 台 A0E0 空调子设备 |

验证结果（离线真实数据，8 台空调）：

- `target=16` → `{"target": 160}`，int ✅
- `target=25` → `{"target": 250}`，int ✅
- `current=29` → `{"current": 290}`，int ✅
- 华为下发 250 → `climate.set_temperature(temperature=25.0)` ✅
- `factor: 1`（整度 Profile）→ `{"target": 25}` ✅
- `step: 0.5` → 23.4 ℃ 量化为 23.5 ℃ → `{"target": 235}` ✅
- `min/max`（摄氏度域）→ 99 ℃ 被 clamp 到 30 ℃ → `{"target": 300}` ✅
- `unavailable` → `{}` ✅

开发中抓到并修复的问题：

- `step` 最初按线上值量化而非摄氏度域，导致 `step: 0.5` 时 23.4 ℃ 输出 234 而不是 235。
  已修：`min`/`max`/`step` 统一在摄氏度域量化，最后才乘以 `factor`。

## 4. motorization（窗帘电机服务）

| 项 | 内容 |
|---|---|
| 来源单品 | `1004` 杜亚电动窗帘 DT360E |
| Profile | https://smarthome-drcn.dbankcdn.com/device/guide/1004/1004.json |
| 默认契约 | `operationMode`（W，1 开 / 2 关 / 3 停）、`targetPercent`（RW，1..100 %）、`currentPercent`（R，1..100 %） |
| 真实设备 | 4 个杜亚窗帘 + 1 个投影幕布子设备 |

验证结果（离线真实数据，9 个 cover）：

- `state=open, position=100` → `{"currentPercent": 100}`，int ✅
- `state=closed, position=0` → `{"currentPercent": 0}`，int ✅
- 华为下发 `operationMode=1/2/3` → `cover.open_cover` / `close_cover` / `stop_cover` ✅
- 华为下发 `targetPercent=50` → `cover.set_cover_position(position=50)` ✅
- `action`（OTA 触发：0 检查升级 / 1 启动升级）**故意不映射**，不驱动窗帘 ✅
- `unavailable` → `{}` ✅

开发中抓到并修复的问题：

- 默认 `min` 最初沿用 Profile 文档的 1，导致全关窗帘上报 1 而不是 0。
  已修：默认 `min: 0` 对齐 HA cover 的 0..100 语义，需要时用 `min: 1` 显式覆盖。

## 5. 已知限制（提交时如实记录）

1. **`mode` 的默认表来自 A0E0**。其他产品的 `mode` enum 集不同，必须通过
   `mapping` contract 覆盖；未覆盖的值会被丢弃而不是猜测。
2. **`temperature` 的默认 `factor: 10`** 来自 A0E0。整度 Profile 需要
   `factor: 1`。
3. **`motorization` 只覆盖 `operationMode` 与百分比**。同服务的
   `direction` / `favoriteLimit` / `version` 等特性未映射。
4. **新版映射格式下的端到端注册未验证**。旧版映射格式下这四类服务的
   注册与双向同步已由生产环境 137 个设备验证；切换到新版 `entities:` 语法后
   需要重新跑一次端到端（升级本身是破坏性变更，已与使用者确认推迟）。

## 6. 单元测试

```
tests/test_real_device_adapters.py   28 个用例
tests/test_service_adapters.py        9 个用例（上游原有）
─────────────────────────────────────────────
合计                                   37 passed
```

覆盖：四个适配器的默认契约、全部可覆盖 contract 变体
（`on_type` / `mapping` / `factor` / `min` / `max` / `step`）、
非法 service_type / contract 键 / 实体域 / 实体数量的拒绝、
`unavailable` 与缺失属性的处理、注册表暴露检查。

---

# 补充：第二批适配器（2026-10-20 追加验证）

## 5. boolean（冰箱单特性布尔服务）

来源单品 `A0VG`，Profile https://smarthome-drcn.dbankcdn.com/device/guide/A0VG/A0VG.json
覆盖 sid：`intelligenceMode` / `dailyStatus` / `travelMode` / `quickFreezingMode` / `quickRefrigeratingMode`
（五个服务的 sid、st、characteristic 三者同名，仅布尔值不同）

真实验证（5 个冰箱开关实体）：

- `dailyStatus` 开机 → `{"dailyStatus": true}` ✅
- 其余关机 → `{"<sid>": false}` ✅
- 华为下发 → `switch.turn_on` / `turn_off` ✅
- `on_value`/`off_value` contract 支持 int 编码 ✅
- `characteristic` contract 支持改名 ✅

## 6. clothesHanger（好太太晾衣机）

来源单品 `174P`，Profile https://smarthome-drcn.dbankcdn.com/device/guide/174P/174P.json

真实验证（1 台晾衣机，3 个实体）：

- `field: action` + cover → `closed` 报 `{"action": 0}`、`open` 报 `{"action": 1}` ✅
- 华为下发 0/1/2 → `cover.close_cover` / `open_cover` / `stop_cover` ✅
- `field: lighting` + light → `{"lighting": false}`，下发 → `light.turn_on` ✅
- `field: disinfect` + switch → `{"disinfect": false}` ✅
- field 与实体域不匹配时抛 `ValueError` ✅
- 同服务多绑定通过重复声明 `clothesHanger` + 不同 `field` contract 实现 ✅

## 7. enum_service（action / status，无默认表）

来源单品 `A2GQ` / `A2GT` / `2QXU`，Profile 见各适配器 docstring。

真实验证：

- `status` + A2GQ 表 → 烘干机 `finished` 报 `{"status": 2}` ✅
- `status` + A2GT 表 → 洗碗机 `unknown` 报 `{}`（未知状态丢弃）✅
- `action` + A2GT 表 → 洗碗机 `off` 报 `{"action": 1}` ✅
- 空 `mapping` 或缺失 `mapping` → `ValueError` ✅
- `status` 注册为只读（两个来源 Profile 均 `method: R`），不下发 HA 服务 ✅
- `action` 注册为可写（`method: RW`）✅

## 8. leftTime / lefttime1（剩余时间）

来源单品 `A2GQ`（`leftTime.time`）与 `A2GT`（`lefttime1.lefttime`），均为 `int` 0..1440 分钟。

真实验证：

- 烘干机 `remaining_program_time=0` → `{"time": 0}` ✅
- 洗碗机 `remaining_program_time=3` → `{"time": 3}` ✅
- 实体 state 为字符串 `"55"` 时正确解析为 `{"time": 55}` ✅
- 超出 0..1440 被 clamp ✅
- `characteristic` 默认按 sid 取自来源 Profile（`leftTime→time`、`lefttime1→lefttime`）✅

## 第二批开发中抓到并修复的问题

| 问题 | 现象 | 修法 |
| --- | --- | --- |
| `leftTime` characteristic 默认值取自 service_type | A2GT 输出 `lefttime1` 而非 `lefttime` | 增加已知 sid→characteristic 默认表 |
| `leftTime` 不接受字符串 state | HA state `"55"` 被丢弃返回 `{}` | 增加 `_as_number` 解析（HA state 永远是字符串） |
| `clothesHanger` 域校验缺失 | `validate_entities` 不校验实体域 | 拆为全域集合校验 + field 级域校验 |
| `status` 被注册为可写 | 会对只读特性误发 HA 服务 | 注册时 `writable=False` |

## 单元测试（第二批后）

```
tests/test_service_adapters.py            9
tests/test_real_device_adapters.py       28
tests/test_real_device_adapters_extra.py 24
─────────────────────────────────────────────
合计                                     61 passed
```
