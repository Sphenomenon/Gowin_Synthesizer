# 冻结构建输入

这个目录只保存 USB-A 工作站构建实际读取、但原先位于其他本地迁移目录中的文件。

- `workstation_inputs.json` 绑定冻结的 `Prj1` 源码。
- `usb_host_fs_8fc3` 包含 8FC3 USB Host 的 11 个 RTL 文件、启动代码和 USB 固件库。`inputs.json` 记录每个文件按 LF 统一换行后的 SHA256。
- `ddr3_reference/ddr3_memory_interface.vo` 是 DDR reset 审计使用的参考网表，SHA256 为 `0a21efa69eab7d8b9912bb6aaf880ad35de00d562cc451587c11bd3c002ed17b`。对应的 `.v` 由已跟踪的 Prj1 vendor 源码复制，不在这里重复保存。

这些文件是输入快照，不是新的综合或布局布线结果。`build.py` 会在创建结果目录前校验清单，CRLF 和 LF 视为同一份文本；需要更换任何输入时，应建立新版本并重新审计。
