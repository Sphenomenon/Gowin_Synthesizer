# F6：仅约束 DQS HOLD LUT 的物理失败记录

2026-10-30，UserCode `C11030F6`。本次 P&R 返回 1，报告 **302 条未布通网络**，未生成 FS 或完整 routed timing 报告。该候选不可部署；没有进行 SRAM、Flash 或板卡操作。

## 精确输入与范围

候选目录为 `/Users/sphenicidition/.cache/gw138k-task-20261030/f06-dqs-lut-only-C11030F6`。
prepare manifest SHA256：`37ce33f6db55f44d850aadcb8c2db9f4bb3644cfe10629b5c4d225e370a1e929`。
来源、拓扑审计与 39 项准备回归见 [F6 prepare](WORKSTATION_F06_DQS_LUT_ONLY_PREPARE_20261030.md)。

本次仍使用 F3 的固定 revision 2 synthesis 网表与 SDC，保留原 capture region。
相对于 F5，仅释放四个 `read_rclksel_conf_*` 配置 FF 的位置；四个 HOLD LUT 继续使用原区域。
place option 2 / route option 0，未启用复制，没有改时钟、例外、vendor bytes 或 feature。
它不包含后续双率音频、ADSR、灯光、readiness 或扫描诊断源码修复。

runner 在 `/private/tmp/gw138k-build.lock` 下串行执行已锁定的 Gowin CLI。
开始/结束全部 physical input 哈希一致；固定 manifest、runner/tool、日志、失败 VO 与报告身份保存在
[f06_physical.json](workstation_task_20261030/f06_physical.json)。

## 结果与可解释范围

| 实验 | 位置约束 | 未布通网络 | 位流 / 完整 STA |
|---|---|---:|---|
| F5 | 四个 FF + 四个 HOLD LUT | 297 | 无 |
| F6 | 仅四个 HOLD LUT | 302 | 无 |

放开配置 FF 没有使这组 HOLD LUT 区域变得可布通。工具只给出未布通总数，失败 VO 没有可用 LOC 属性；本次无法给出八个目标的实际落点，也无法确定失败网络全在某个区域。
因此不能把 CST 的请求范围当作实际落点，或根据 297/302 推断已经证明的因果关系。

由于路由未完成，未对该输出运行完整 timing/CDC/PLL 接受门禁，也没有引用局部资源或工具进度代替通过。
F3 仍是最近有完整 routed 产物的参考，其全局 setup 失败不变。F6 未部署，回退无需板卡操作。

这组区域约束目前没有可部署结果；后续需依据真实未布通路径/器件路由能力重新设计，或在下一明确整机源码候选中复测。
新原生音频组件的独立综合另行建身份，不继承本次或 F3 的物理接受。
