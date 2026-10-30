# BLE raw DDR 原生组合 revision2

日期：2026-10-30。此阶段将已封存的 raw store、boot-only authority、owner8 两客户端 mux 与 checked BLE 五层适配接入原生组合。只升级 `custom138k-workstation-r00-no-local-panel-v1` 至 revision2；生产来源检查与 prepare 通过，未执行 EDA 或板卡操作，不勾选整机验收。

## 来源和行为

no-local-panel provider 独占定义并在 include 后撤销 `WORKSTATION_BLE_RAW_DDR`，配置新增 `ble_recording_storage_policy=native_raw_ddr_v1`，组合身份改为 `custom138k-native-dual-rate-r00-no-local-panel-revision2`。其他 provider 不选择新增路径；四个原 provider 的预处理 token 身份回归保持通过。

CPU 继续占用 first 64 KiB、native `0x0c140000..0x0c143fff`；BLE 使用 second 64 KiB、native `0x0c144000..0x0c147fff`，字节窗口为 `0x30510000..0x3051ffff`。数值来自唯一 `ddr_address_map.vh`。顶层 guard 检查字节／native 单位、64 KiB 容量、完整末 BL8、pool 内与 CPU 两种单位不重叠，实际 native 首写地址另有动态断言。

两个 client 保有自己的 native-commit bridge。mux 只汇聚桥的**已注册 protocol fault**、全局 arbiter fault 和 authority fault；inclusive transport fault 只送给 owners，避免组合反馈。共同 root reset 经两个 memory edges 释放后才给 mux 与 CPU runtime；raw store 和 authority 接真正 root 并使用内部本地释放链。ledger reset 只作为 authority 的观测输入，不能清除 owner 或 mux 的故障与未返回事务。CPU backend readiness 使用 memory-domain grant，BLE source/start 资格使用其 50 MHz 两级同步投影。

BLE endpoint 继续唯一拥有对象、任务、CRC、codec、second40 传输和原 wire format。raw PCM 和绝对地址缓存逐项直连，无第二次声道交换；格式1仍限制为 48 kHz。五层 `EXTERNAL_RAW_STORE=1` 由显式顶层参数启用，raw drain 预算为 5,000,000 个 50 MHz cycles，command/read 预算各 10,000 memory cycles。准备过程先完成原适配，再校验输入身份／锚点并生成 opt-in 路径；最终来源验证重新计算五份输出及保护区域身份。原 25K、vendor 与 frozen baseline bytes 不改。

## 验证

机器证据：[ble_ddr_native_composition_r2.json](workstation_task_20261030/ble_ddr_native_composition_r2.json)。基础依赖为 `3080579` 与 BLE adaptation `5e389657a46935eba0c9b4e3d9986560eb07f5d2`；最终 raw store SHA 为 `422a1bb4c3b0cf842b416b65f714d023c65b270d0fa5219f9adec1c72d290ede`。

| 范围 | 结果 |
|---|---|
| 真实 selected top、CPU service/backend/PCM CDC、raw store、mux、authority | 3 正向场景通过：并发窗口／下载／迟到响应、ready 前 ledger loss、停 memory 时共同 root release；共 119 checks |
| native 实际访问 | CPU 3 次写／1 次读，BLE 3 次写／4 次读；PCM32、尾 mask、CPU snapshot、BLE 1-cycle cache 和 owner 返回匹配 |
| 地址 guard 负控 | 容量、byte/native 单位、末 BL8 截断、CPU 重叠、pool 外五项全部拒绝 |
| 最终 raw store | FIFO depth256／异步 memory：94,742 checks；depth8／100 MHz memory：93,244 checks；5 mutants 拒绝；lint 精确4个已审 warning |
| CPU runtime | 14 正向与5 mutants 通过 |
| 新 BLE integration／prepared 篡改 | 5/5，通过 policy、输出 hash 伪造及 staged wrapper 漂移拒绝 |
| no-local-panel profile | 6/6，含真实 prepare 及退休输入／时钟恢复等篡改拒绝 |
| local-panel／旧 provider token | 8/8 |
| current workstation sources | 17/17 |
| 原 recording profile | 5 项通过，2 项原 R00 prepare／物理前置未提供而跳过；无自动 fallback |

顶层动态 fixture 直接编译真实 no-panel provider 与录音 owners；无关整机模块、BLE radio/business endpoint 使用 Icarus `-i` 黑盒，CPU command/raw interface 与全局 DDR slot/native/response 为 fixture。它不替代真实 BLE business 回归、完整 global arbiter 测试或板级联调；BLE checked adaptation 的独立回归另见[适配报告](ble_raw_ddr_adaptation_20261030.md)。

真实 prepare 候选：`custom138k-workstation-r00-no-local-panel-v1-cd44adf6419fcc0c`，269 个 enabled inputs，profile SHA `744975c2aff1fda3d6db089608d664532f54e3c7c8b02bafd77fdd22a6743696`。以下命令在隔离工作树执行并通过：

```sh
python3 projects/138k/push2_workstation/usb_a/build.py --prepare-custom-board \
  --workstation-profile custom138k-workstation-r00-no-local-panel-v1 \
  --netlist-dir /Users/sphenicidition/.cache/gw138k-task-20261030/netlists \
  --custom-board-output /Users/sphenicidition/.cache/gw138k-task-20261030/ble-ddr-native-r2-prepare-v1 \
  --riscv-prefix /Users/sphenicidition/.local/opt/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf
GW138K_BLE_DDR_PREPARED=/Users/sphenicidition/.cache/gw138k-task-20261030/ble-ddr-native-r2-prepare-v1 \
  python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_ble_ddr_integration.py
GW138K_NO_LOCAL_PANEL_PREPARE=/Users/sphenicidition/.cache/gw138k-task-20261030/ble-ddr-native-r2-prepare-v1 \
  python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_no_local_panel_profile.py
python3 projects/138k/push2_workstation/usb_a/sim/memory/run_ble_ddr_top_composition.py --output <新目录>
```

## 未完成门禁与回退

没有完整新 revision2 的 CDC／reset／PLL、综合、物理 BSRAM／CLS 净收益、STA／P&R、非零音频、BLE／Android 或共同 reset 物理验收，也没有 SRAM／Flash 部署。旧 revision1 precision checker 的配置锁继续拒绝新配置；新增邮箱、authority 与资格同步需要在新真实网表上建立明确审计范围，不能直接继承旧接受。组件 authority 的录音保护不代表其他 DDR clients 的 reset 安全已完成。

退回 `3080579` 的 no-panel revision1 来源，或选择未开启此新 policy 的原 R00 profile，即恢复原 BLE RAM 后端；新位流必须使用新的候选及部署身份。生成物只在本机任务缓存，未提交实现数据库、位流、波形或抓取。
