# 空调接入：从 A0E0 迁到 2FAT（协议空调）

实测日期：2026-10-21 · 8 台三菱重工 MIAS 空调

## 为什么必须换 Profile

物理空调的 HA 实体属性：

```
step=0.5         target_temp_step     0.5 ℃
current=28.5     current_temperature  小数
fan_modes=['自动','静音','超低','低风','中风','高风','超高']   7 档
hvac_modes=['off','cool','heat','dry','fan_only','auto']
```

原用的 `A0E0`（海尔，manu `371`）在 Profile 层面无法表达这些：

| 特性 | A0E0 | 2FAT（协议空调 MC3-Ac）|
| --- | --- | --- |
| prodId / manu | A0E0 / 371 | **2FAT / c4a（成都美景舒适家）** |
| temperature.target | int 16..30 | **targetFloat float 16..35** |
| temperature.current | int **R**（只读）| **current RW -100..550** |
| fan | 无 gear 细分 | **gear enum 10 档 + 上下/左右扫风** |
| 湿度 / 滤网 / 故障码 | 无 | 有 |

## 迁移后云端实测（智慧生活 App 自己的接口）

```
8 台全部 MC3-Ac，0 异常

开机中的西边卧室空调（4/4 有数据）:
  switch       {"on": 1}
  mode         {"mode": 2}                      制冷
  fan          {"gear": 2}                      低风
  temperature  {"current": 29, "targetFloat": 26}

关机中的其余 7 台（3/4 有数据）:
  switch       {"on": 0}
  mode         null                             HA 侧 hvac_mode 为空，符合预期
  fan          {"gear": 0..5}
  temperature  {"current": 28.5..29.5, "targetFloat": 16..26}
```

**迁移前 `temperature.current` 恒为 `null`，迁移后拿到真实室温（28.5 / 29 / 29.5 ℃）。**

## 投影写法

```yaml
product:
  prod_id: 2FAT
  sub_prod_id: "00"
  device_type: "012"
  manufacturer: "c4a"
  model: MC3-Ac
  device_name: 客厅空调
  protocol_type: 1
  setup_type: 0
  services:
    - {st: switch, sid: switch}
    - {st: mode, sid: mode}
    - {st: fan, sid: fan}
    - st: temperature
      sid: temperature
      contract: {characteristic: targetFloat, float: true,
                 min: 16, max: 35, step: 0.5, factor: 1}
bindings:
  - {sid: switch,      entities: [climate.xxx]}
  - {sid: mode,        entities: [climate.xxx]}
  - {sid: fan,         entities: [climate.xxx]}
  - {sid: temperature, entities: [climate.xxx]}
```

`mode` 的默认表（`1 自动 / 2 制冷 / 3 制热 / 4 送风 / 5 除湿`）与 2FAT 一致，
无需覆盖。

## 新增的 fan 适配器

`fan.gear` 十档 ↔ HA `fan_mode`，按「精确匹配 → 英文别名 → 最长子串匹配」
三级回退。MIAS 实体的七个中文档位全部往返成功：

```
自动→0  静音→9  超低→1  低风→2  中风→3  高风→5  超高→7
```

## temperature 的 float 支持

`contract.float: true` 时保留小数（`round(value, 2)`）而不是因非整数丢弃。
这是 0.5 ℃ 步进空调的必要条件——旧的 `_quantize` 会把 28.5 直接判为无效。

## 复现要点

换 Profile 必须删掉该子设备的 `children/<key>/` 目录（identity + material），
否则沿用旧 devId，云端仍是旧产品身份。改完适配器代码后还要**完整重启
Home Assistant**（`reload` 只重读 mapping，不重新导入模块）。
