# 板级工程

本目录是 138K 和 25K 工程的共同父目录；Git 根目录为上一级 `fpga/`。两个工程使用同一仓库、同一分支历史，不建立嵌套 Git 仓库。

| 目录 | 职责 | 当前内容 |
|---|---|---|
| [138k/](138k/README.md) | USB Host、音源、公共参数、识别与公共显示数据；Push 直接连接本机 | 从原 `migration/gw138k_audio/` 整体迁入，保留其内部目录和本地构建资料 |
| [25k/](25k/README.md) | 触摸转 MIDI、本地移调、SPI 屏和外围驱动 | 已导入 GW_25K 源码、独立例程、约束、硬件资料和历史验证摘要 |
| [../整机接口规划.md](../整机接口规划.md) | 跨板职责、消息、值域、消费端和待定接口 | 公共接口的维护入口 |

从仓库根目录暂存 138K 工作站：

```sh
python3 projects/138k/push2_workstation/usb_a/tools/build_current_workstation.py --prepare-only
```

该命令只准备本地工程，默认按 full83 清单取 CNN 输入，不烧录。功能先完善，时序集中到功能稳定后处理。

当前整机 prepare 已切到[可版本化输入闭包](138k/push2_workstation/usb_a/baselines/README.md)，不再要求本机保留忽略的 full83／full85／资源优化暂存目录；输入策略、迁移比较与干净克隆验证见[闭包记录](138k/push2_workstation/usb_a/reports/SOURCE_CLOSURE_20261021.md)。历史编号实验入口不因此统一迁移。

兼容链接 `migration/gw138k_audio -> ../projects/138k` 保留旧命令和历史记录中的绝对路径。新增引用采用新目录。历史证据、验收快照、清单和内容哈希保留原样；不为目录整理重写既有来源记录。

源码、必要冻结依赖、仿真和验证摘要进入 Git；`results/`、实现数据库、波形和生成位流继续按根目录 `.gitignore` 留在本地。现有冻结 `Prj1` 源码例外及供应商文件的原始字节属性继续保留。其他人的 worktree 和参考工程未迁移。

本次迁移已核对1546个既有文件，新旧路径的full83暂存入口均通过，CNN输入边界10项测试通过。目录和文件核对结果见 [迁移验证记录](138k/push2_workstation/usb_a/reports/repository_layout_20261018/verification.json)。上述验证基于迁移时的本地工作区；功能和时序改动独立保留，目录提交仅调整工程位置及配套文档。
