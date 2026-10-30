# BLE 短录音正常封存边界（2026-10-30）

新增默认关闭的50 MHz外部封存事务，正常采样率切换可以先阻止新录音、完成当前已接受stereo word的四个CRC byte，再冻结原object ID／frames／CRC。此阶段保留既有BLE报文、48 kHz格式和原25K默认行为；44.1 kHz新录音仍拒绝。此前通过降低`source_ready`使录音直接进入ERROR的行为仍用于真实故障，不能充当正常封存。

## 来源与最小接入

五层为138K `workstation_bluetooth` → 25K第一方`adaptations/bt_verilog_core.v` → `adaptations/bt_gatt.v` → `rtl/ble_protocol_command.v` → `rtl/ble_recording.v`。每层`EXTERNAL_SEAL_PROTOCOL`默认0；138K新native top由父级显式启用1。共享prepare只按原唯一锚点生成H5/GATT存储适配，138K工具再复制维护core/command/recording与受清单校验的vendor transport；没有复制整条链，没有修改vendor、原manifest或冻结baseline。

| 本阶段产品输入 | SHA-256 |
|---|---|
| `projects/138k/push2_workstation/usb_a/rtl/bluetooth/workstation_bluetooth.sv` | `58700059b5d9865d8d3093d65fc9c19b75f3f7c68e86cafaae6a01d1baba70fa` |
| `projects/138k/push2_workstation/usb_a/tools/workstation_bluetooth.py` | `9044cd97068ce939ae7b2302ae7a7df7e09cfa024e859734006cd1d0719608dc` |
| `projects/25k/example/RTL8723DS_PROTOCOL/adaptations/bt_verilog_core.v` | `89d47ee7ae8144e39b30743b0c1073aa9757e982fae863590ad74173252579d1` |
| `projects/25k/example/RTL8723DS_PROTOCOL/adaptations/bt_gatt.v` | `5266ea2002a8180b446a467c2cccae5c65d5409bf642319418122f50df4f658b` |
| `projects/25k/example/RTL8723DS_PROTOCOL/rtl/ble_protocol_command.v` | `608c2c818e1b3546d40983f8798a6e8d50ca26d3182870093f3fd18a05cdac00` |
| `projects/25k/example/RTL8723DS_PROTOCOL/rtl/ble_recording.v` | `f5e9447a67bb74d5b9dd80ab112a7e4d2422bbeef0f4375faa68f7400489a696` |

全部11份维护输入哈希、六份旧第一方来源身份、prepare输出和完整编译命令见[机器记录](workstation_task_20261030/ble_external_seal.json)。端口与完整状态契约见[BLE封存契约](../rtl/bluetooth/WORKSTATION_BLE_SEAL_CONTRACT.md)。本阶段不修改native top/profile或已冻结TF文件；聚合器与整机接线由父级维护。

接口为`seal_hold_i`、`seal_request_i`、`seal_ready_o`、`seal_pending_o`、`seal_done_o`、`seal_failed_o`、`seal_failure_code_o[3:0]`，并输出本事务`seal_record_state_o[7:0]`和`seal_recording_id_o`／`seal_frames_o`／`seal_crc_o[31:0]`。request当沿关闭新PCM准入；hold持续阻止REC_START/STOP/CLEAR变更。每个接受事务只有一次单拍终态；pending/持续高request不能重用旧done。真实source_ready/source_fault在活动对象ACK前丢失明确失败，不用mask掩盖。

EMPTY和READY不依赖BLE初始化、连接、订阅、enable或当前48 kHz源即可幂等确认。opt-in启用时，业务enable丢失保留EMPTY/READY，活动对象则ERROR，保持原ID；全局reset仍使volatile对象失效。零帧STARTING保留ID并封存READY frames0/CRC0，START任务失败，因为没有实际首帧。已有STOP任务在真实封存时完成；已有ERROR明确失败。hold期间尚未dispatch的完整START/STOP/CLEAR请求使用既有BUSY82拒绝，查询和READY下载保持原格式；hold解除后仍须显式CLEAR旧对象才能新建。

失败码1为已有ERROR、2为活动enable丢失、3为身份异常变化、4为封存期间源／录音故障、8为超时。64周期watchdog失败一次并继续清理，恢复后不补成功。快照只绑定接受时的原对象，不跟随新对象变化；hold须跨整个媒体/时钟事务由真实owner持有，不能以CPU复位解封。

## 冻结输入验证

最终身份为 `native-ble-external-seal-v1-3f0f0dfa5c3abb21`，完整source集合SHA为 `3f0f0dfa5c3abb2103c7cb12d9a07f0ef715a902ca983f7e048e2512e62c9818`；输入seal前后一致。首次开发期完整矩阵的全部用例虽通过，但其间为补充行为修改RTL，输入seal正确拒绝，未作为接受证据；下述结果来自重新冻结后的独立完整运行。

```sh
sh projects/25k/example/RTL8723DS_PROTOCOL/run_sim.sh
python3 projects/138k/push2_workstation/usb_a/sim/usb2/run_workstation_ble_seal.py --output /Users/sphenicidition/.cache/gw138k-task-20261030/ble-seal-final --protocol-result projects/25k/example/RTL8723DS_PROTOCOL/reports/simulations/20261030_113215_209177/result.json
python3 -m unittest discover -s projects/138k/push2_workstation/usb_a/sim -p test_workstation_bluetooth.py
python3 projects/138k/push2_workstation/usb_a/sim/test_current_workstation_sources.py
git diff --check
```

| 验证 | 结果 |
|---|---|
| 原25K完整矩阵 | 50项全通过，前后源码hash相同；vendor package 40文件通过 |
| 138K原BLE回归 | 8项通过，含实际UART/H5/patch/PCM、协议缓存及下载 |
| 录音边界专项 | 16场景、6个CRC相位、48次hold快照检查，19次独立成功和8次独立失败 |
| 真实fragment/CRC endpoint专项 | 6场景、3次seal、封存后4字节下载及整包／PCM CRC通过 |
| 实prepare后五层wrapper | 3场景通过：未初始化EMPTY、真实PCM左右声道及CRC、disabled READY保留 |
| current-workstation source／diff | 10项来源测试通过，diff检查通过 |

录音专项覆盖request跨每个剩余CRC byte及已提交边界、零帧、同沿START/CLEAR、已接受STOP、先完成CLEAR、真实ready/fault/enable丢失、最后ACK前源降、已有ERROR、timeout后恢复不补done、持续request不重复接受、禁止hold中变更对象、不可用源拒绝新START。协议专项使用原真实分片/CRC/cache helper，验证已完整组装但尚未执行的START和CLEAR被BUSY拒绝、相同请求ID精确重放、已接受STOP任务完成、INFO固定48 kHz元数据、冻结对象下载字节与CRC一致。

三个临时负向副本均被拒绝：提前跳过capture空闲条件导致CRC `38e18f26`与正确`47172216`不符；绕过变更屏障使真实组装START返回ACCEPTED01而非BUSY82；掩盖source_ready下降导致应失败事务却成功，触发结果断言。维护输入没有因负向控制修改。编译没有新增implicit或功能警告。

## 父级媒体准备聚合器独立只读复核

复核`workstation_media_preparation.sv`、runner和TB，没有修改父级文件。原9类／两负向控制独立通过；另在cache加入一类“一个backend失败后CPU reset撤caller hold，另一个仍pending”场景：聚合器继续hold至双terminal，只发失败，再等两个真实ready才重新准入。扩展运行10类、9请求、5成功、5失败及232次default透传检查通过。

在约定的同域单拍backend结果契约下未发现阻断问题：request delivery边沿忽略旧终态，两个backend都terminal前不发aggregate结果，WAIT_RESULT不受caller hold丢失提前释放，RELEASE阶段依赖两backend真实ready重新准入；默认0仍直接透传runtime。该复核使用backend接口fixture，不证明真实录音／TF／clock联合或CPU复位后完整物理时钟事务；父级仍需在同一候选完成联合回归。原复跑与额外case的输入及log hash均附机器记录。

## 接受范围及回退

原协议全矩阵证明默认路径；真实封存protocol及staged chain证明本接口边界。五层seal专项只强制BLE初始化／连接控制与直接命令注入，录音RAM/CRC、wrapper stereo适配及所有seal端口均真实，不能把它当成无线板测。没有完成整机媒体准备／时钟联合、实际BLE链路、routed CDC/timing、综合、P&R、SRAM或Flash接受，也不修复历史boot_id问题，不实现DDR长录音或TF no-DDR迁移。

回退仅撤本BLE阶段的共享第一方、wrapper、工具和契约变更，保留既有TF clear/stop及25K历史证据。新整机release输入应另有新身份、来源和物理验收，不复用accepted候选身份。

## 父级独立复验

父级在新目录重新prepare并运行unit16／protocol6／chain3及三项负控，全部通过；同时重跑原138K BLE8项和来源10项通过。规范化生成目录和仅包含绝对输出前缀差异的patch header后，全部输入内容及逐项指标与冻结子阶段一致；原50项协议结果也重新核对了所有当前source hash。独立原始证据见 [ble_external_seal_parent.json](workstation_task_20261030/ble_external_seal_parent.json)，SHA-256 `fee415c4ad4e49642e97e360c79fb61fa6dece18f0996799a77043c881639a3d`。没有将离线结果升格为整机或硬件接受。
