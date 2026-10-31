# M14 候选：事件配置私有 cofactor 离线验证

日期：2026-11-01。对应机器记录：`DUAL138K_EVENT_CONFIG_COFACTOR_20261101.json`。

本阶段只改维护源码中的 render service 和 event workstation。目标是移除 M13 实测 `fault → accepted → automatic_config → event dispatch → engine CE` 路径中，对本周期新采样配置请求的冗余事件侧依赖。没有改变采样调度、实际配置广播、历史清除、PANIC、事务状态或公共 ready 语义；没有实施 reverb、clock50、TF、资源重写或部署操作。

## 实现和适用边界

`workstation_audio_render_service.sv` 保留完整 `core_config`，只对事件／模式准入另传 `event_config_request`。私有请求含外部配置和已有 active 请求的自动配置；省略仅由本周期 `accepted` 引发的新配置项。原始 `.rate_commit_i(core_config)` 保留，新增 `.event_rate_commit_i(event_config_request)`。

`gw138k_event_workstation.sv` 新参数 `EVENT_CONFIG_COFACTOR_ENABLE` 默认关闭，仅维护的 native request service 按 `RUNTIME_EFFECTS_ENABLE` 开启。对已知 0／1 的 `sample_ce_i` 使用私有配置围栏，对 X／Z 保留原完整围栏。只有 `dispatch` 和 `mode_valid` 消费它。完整 `core_ce`、`runtime_config_block`、rate/history readiness、实际 engine/effect broadcast 和配置状态机与实际被 M13 消费的版本一致。非 native／非 request-driven 强行开启会在完整模块运行时 fatal。

二进制等价依据来自维护源码及真实端口绑定：native `sample_ce_o=accepted`；sample=0 时被省略的新请求项严格为零；sample=1 时两个事件入口已有的 `!sample_ce_i` 严格拒绝事件。新输入不是可任意连接的公共参数通道。

## 冻结输入

| 生产输入 | SHA-256 |
| --- | --- |
| `rtl/audio/gw138k_event_workstation.sv` | `fad0203c4322b54271ef6f413a7523478cfa5101609f5b2f72e280ae3894bf09` |
| `rtl/audio/workstation_audio_render_service.sv` | `9c80e68049ec1a08b9d176bd1d7dcb22723e3058c7015166a051c45dcd9d2bd0` |

生产 pin 只涉及以上两份 RTL；没有修改生产构建工具。native composition 本来就禁用历史 `event_dispatch` 文本变换，render service 也已是 runtime profile 的维护输入，未增加来源绕行。M／W profile 刷新及 M14 prepare 由主线程执行。

精确 M13 参考为 candidate `m-demo-base-v13/workstation/Prj1`：event `src/ae350/gw138k_event_workstation.sv` SHA `5d02329a6b7f08ec30d79552a4814436b7c01611f4e4bed83c1514d154ef3fd1`；service SHA `148f0fb7b8976099d26bbf71025105c0d0df6f3b5e06ea90f1f75cdae0e46968`。各 runner 检查参考 SHA，不能改用任意历史副本。

## 已通过的验证

| 验证 | 结果 |
| --- | --- |
| 完整 M13／当前 service＋event twin，真实 native 效果及 DDR 模型 | 115,929,947 次半拍比较；50 公共输出、真实 core CE 和 31 个私有边界一致；48,691 请求／响应，48,645 独立定点 wet PCM 参考帧，两采样率、A/B/C 32 声部、矢量和释放均覆盖 |
| 取消／配置压力 | 21 配置、324 history、11 cancels、326 有序 DDR fences；12 个取消边界和 12 个恢复 Note／Mode 场景；3 次同周期 request／PANIC，epoch wrap 覆盖 |
| 正式 controlled composition／真实 serializer RTL | 1,078 个 I2S 帧与观察帧一致，其中 977 非零；1,077 显示参数元组；384 FFT bins、382 非零；2 次采样率切换；lifecycle 和显示／recorder／FFT consumer 故障边界通过 |
| 完整 W D-only 与默认关闭的 legacy twin | W 45,863 半拍，legacy 45,895 半拍；各 34 请求／响应；W 27 配置、37 history、88 事件、22 同边界场景、28 fault checks；legacy 68 事件；50 输出和 25 公共私有边界一致，native 再比较 7 个事务边界 |
| 新私有合同 Z3 证明 | 从实际 service wire、真实端口和事件表达式推导；4 个全二进制组合域性质 UNSAT，不使用状态可达性假设 |
| 新合同 Icarus 四态 | 147,456 个实际源码向量通过，其中七个 service 输入穷举 4^7 组合，其他状态独立变化；额外 seeded 向量；未知 sample 还检查内部原围栏保留合同 |
| 原 effect-slot／完整广播证明回归 | 原 native／legacy CE 证明、配置广播证明及 8 个 SAT 负控保留；先证明新私有 source 合同再组合；81,920 个四态向量通过，含直接 X／Z sample 输入 |
| 来源和 DEMO 审计 | `test_current_workstation_sources.py` 17 项、`test_workstation_demo_audit.py` 15 项通过；`git diff --check` 通过 |

完整 W／legacy runner 支持外部完整 mutant 源码对，拒绝生产目录内的 mutant 输入。七类误用负控均被拒绝：私有请求重引入 accepted 依赖、私有端口断开、真实 core CE 误用私有围栏、漏 history veto、漏已有 active 自动配置、删除未知值 fallback、强开 legacy。端口断开／漏 history／强开 legacy 三类还通过真实整模块编译并到达预期运行时 fatal；history／active／未知 fallback 另有实际源码四态负控。未知 fallback 负控验证内部原围栏保持合同；在 service 关系下，它的公共事件输出仍可能等价，不能把该负控说成已观察到外部事件错误。

## 证据与重跑

外部封存记录：`/Users/sphenicidition/.cache/gw138k-dual-20261031/event-config-cofactor-sealed-evidence-v1.json`，SHA `c52456e31fc517b472c8c2bca33cd96f51809976b2bcd2cb6d56a80ba194ea9b`，绑定 122 份验证 JSON、实际源码 fixture、日志和参考输出。机器报告记录各成功 runner、输入哈希及保留的早期失败尝试；早期 test harness 错误未改写成成功证据。

最终私有证明：`event-config-private-proof-final-v1/verification.json` SHA `31c3ee775c06854e87bc36e9cedaef849f12a8c299790944d65386338e3aa213`。最终旧证明：`event-config-effect-slot-proof-final-v1/verification.json` SHA `981c8fa1a8a9a72b12b2e342a5a75327994c03e0ee3dfe0808bf92a15b9320c8`。Z3 runner 使用 `/Users/sphenicidition/miniforge3/bin/python3`；普通系统 Python 不保证带 Z3。

重跑入口（从 `usb_a/`，所有 output 必须是新的外部目录）：

```sh
/Users/sphenicidition/miniforge3/bin/python3 -B sim/audio/prove_event_config_cofactor.py --project <exact-M13-Prj1> --output <new-proof-output> --negative-modules
/Users/sphenicidition/miniforge3/bin/python3 -B sim/audio/prove_effect_slot_admission.py --output <new-effect-proof-output>
python3 -B sim/audio/run_event_config_contract.py --project <exact-M13-Prj1> --output <new-contract-output>
python3 -B sim/audio/run_runtime_render_service.py --project <exact-M13-Prj1> --output <new-miter-output> --event-config-miter
python3 -B sim/audio/run_runtime_controlled.py --project <exact-M13-Prj1> --output <new-controlled-output> --nonzero-epoch
```

## 验证阶段和后续

本阶段是维护源码和离线验证，不是综合、P&R、资源收益或硬件验收。I2S 数量来自真实 serializer RTL 仿真，不能写成实板录音。长程 twin 与 controlled 回归绑定各自记录的精确来源；后续主线程的 TF 修改按其独立证据验证。

M14 必须重新记录来源、综合和 routed 资源／时序，确认原故障路径是否实际缩短及新最差路径，不能预记收益。未编程 SRAM，未写 Flash，未开展双板并发验收。回退只撤销以上两份私有接口 RTL 和对应 profile 输入更新；不回退或覆盖其他并行子任务源码。
