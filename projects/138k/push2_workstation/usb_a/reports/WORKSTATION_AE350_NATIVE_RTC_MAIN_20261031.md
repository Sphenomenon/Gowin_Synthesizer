# 原生 AE350 独立 RTC 父级集成复验

2026-10-31，导入 `7d82699e1b317505dfad5574620eeeeda3c16035` 为主树 `914fda7`，
保留已合并的 ROM128 helper 哈希。机器索引：`workstation_task_20261030/ae350_native_rtc_main.json`。

首次主树 prepare 正确拒绝新纳入 RTC 来源闭包的旧 `sim/test_ae350_local_probe.py` 哈希。
父级核对旧哈希来自 `3cce72e`，新文件来自已提交的完整 64 字 GAO 阶段 `1ff14c3`，
仅刷新六个 native profile 中这一键；frozen baseline、accepted 和用户 task.md 不变。
失败记录保留在外部 `native-ae350-rtc-main-v1`，未绕过来源检查。

最终以合并源实际重新 prepare，全部 staged 输入逐字核对：

| 配置 | 新候选后缀 | staged／enabled | 实际编译单元／module／package |
|---|---|---:|---:|
| business revision 4 | `0981b403bb531b2b` | 614／272 | 269／301／2 |
| 默认 revision 5 | `36edc57605b9a09f` | 581／261 | 258／290／2 |

源码与固定旧网表检查 75 项、accepted 17 项、generic prepare 5 项、
业务实际 prepare 11 项、默认实际 prepare 17 项及一秒 RTC 波形 1 项通过，
共 126 项成功，5 项 opt-in 跳过。
默认历史预处理 token 保持；实际旧整机 VG 完整解析后因缺新 RTC 正确拒绝。
C10 固定探针用于 RTC 端点正例，不向新完整候选继承物理或硬件接受。

RTC 复用已有维护累加器，平均 32,768 Hz，半周期 762／763 个 50 MHz 周期；
STA 用最短完整周期 1524（30,480 ns）。新源、prepare、VG／VO 直接接线子门禁
和 business revision 4 已接入；新整机实际综合与 routed STA 尚待执行。

父级包 `~/.cache/gw138k-task-20261030/native-ae350-rtc-main-parent-v1`：
462 份来源快照、1,374 个固定外部文件，seal
`8a74bee1445696783bd61c0dba36c48caa2644632fb144d8294124ba6e826d6d`，校验器通过。
作者交付校验器也独立通过 53 个文件、4,843 个外部输入和 27 个变更源码。

本阶段没有新 EDA、板卡操作或 SRAM／Flash 部署；CPU 频率／周期、Cache 属性、
完整业务并发及 RTC 实际抖动仍待验证。新物理门禁不放宽时钟或例外。
回退为本批之前的固定来源；改变 RTC 接线／约束须使用新候选身份。
