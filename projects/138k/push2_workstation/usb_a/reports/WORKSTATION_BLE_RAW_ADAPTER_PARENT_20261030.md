# BLE DDR 五层适配父级复验（2026-10-30）

接入 [default-off 适配](ble_raw_ddr_adaptation_20261030.md)，仅替换显式选择时的原始 PCM 存储；对象／任务／CRC／codec／线格式仍由原 BLE owner 管理。五层 checked transform 锁定原输入、唯一锚点及完整输出，保留 encoder、transfer bank 和 wire-message 字节。25K 原件、vendor、冻结输入及默认 RAM 路径未改。生产 drain budget 为 50 MHz 下 5,000,000 cycles，仿真缩短为 50,000；原 RAM 仍为 64 cycles。

父级用当前主线最终 raw store `422a1bb4…` 完整重跑：两内存时钟配置各 24 场景，472,541／470,038 checks，各 17,427 wire bytes 与原 RAM 录音器逐字比较，覆盖 RAW／Rice／二阶编码、8112-byte 最大下载、最坏 offset 28 的 255 native beats、尾帧 mask、六个 CRC 相位 STOP、实际写排空、断连／旧 fetch／CLEAR 持续、超时及同拍 source loss。真实 framing 协议六场景、五层 seal 三场景通过；27 个行为／来源／输出／伪造证据负控全拒绝，默认关闭时 staged 字节保持。原 BLE 八项和 accepted 来源 17 项通过。

独立审查再次运行 24 场景／472,541 checks，并另增两时钟共 10,118 checks：三种源丢失乘六个 CRC 相位，恢复／重连／迟到 drain，FAILED 后 START／open／replay 和新 seal，实际 CLEAR 后新对象，以及首帧前失败。单独删除 `record_state!=5` 的负控确实把 FAILED 错升 READY，反例保留。最终源码无阻断发现。父级逐项验证独立 seal 的 51 个文件以及当前 30 个回归输入，身份与 SHA 见 [机器证据](workstation_task_20261030/ble_raw_adapter_parent.json)。

本阶段仍未选入整机 profile。链测试强制 link 初始化与连接、直接注入命令；DDR 使用边界模型。实际生产接线、综合后 RAM 退休／缓存映射、完整 CDC／reset、物理资源与时序、板上 BLE／Android 仍待验证；无 SRAM／Flash 操作，不转移此前候选接受。回退为不调用此适配、保持默认参数零。
