# B04 SBC 来源组件主树独立复验

主树 `3d3a50e` 按原字节导入作者 `cd0699183cb4193b382fb854f0b48d108b6a4739` 的 43 份新增源码／许可／向量／工具。固定 Apache 原件不改，精确适配另列；完整来源和算术修正依据见[来源阶段报告](WORKSTATION_AE350_SBC_SOURCE_20261031.md)。当前生产 profile 未选择该组件，B04 尚未完成。

父级重新运行全部 53 组独立参考向量：3392 音乐帧、577536 scalar samples，原生／ASan＋UBSan 各 62593 checks，PCM 字节相同；另有 6784 帧 CRC 有效极端 payload，六个来源／行为突变全部拒绝。相对参考 PCM 最大误差 6 LSB、最大 RMS 1.7346916941、最低 SNR 75.7623994410 dB，未将项目自制刺激称为 SIG qualification vectors。默认固件十项、accepted sources 十七项通过。

实际重新编译的 RV32 独立增量链接 text 16883／data 0／BSS 2752 B，最大单函数静态 frame 80 B；它使用 section GC，不是完整 UI／BLE 固件 fit、完整调用链栈、实际周期或持续吞吐。真实手机标准协议、统一 HCI credit/handle owner、队列／DMA、现有效果／I2S 接线和长期频差处理仍须完成。

第一次父级调用给错外部 reference 根目录，读取 verification.json 失败；原日志保留。正确固定参考根的 v2 完整重跑通过，没有改写作者封存目录。作者 `verify_seal.py` 也已独立重跑，源码／输出／工具／研究输入保持。

机器记录：[ae350_sbc_main_parent.json](workstation_task_20261030/ae350_sbc_main_parent.json)。父级包 `/Users/sphenicidition/.cache/gw138k-task-20261030/ae350-sbc-main-parent-v1` 的 `verify.py` 可只读校验 43 份源码快照及全部本次输入／输出。此组件阶段没有 EDA、板卡或部署动作，也未把增量容量预记成完整业务收益；回退移除未选择组件即可，不改既有候选和已部署配置。
