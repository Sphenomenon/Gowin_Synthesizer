# C2103102 显示请求候选：物理输入父级复核

本阶段只接受已生成的物理实验输入，不是 P&R、整机功能或板卡验收。固定候选为 `custom138k-workstation-r00-no-local-panel-v1-222fb761448fb6c0`，编译源码 `9bc8fc5063f34c914553e725264a0566eba7cea0`；后来维护工具交付检查点为 `94fd199`，不回填为编译源码。用户最新 task.md 转入 AE350 优化主线；本实验保持固定输入，作为独立物理对照，不等待它通过才开展业务迁移。

## 输入与配置

实际输出为 cache 下 `runtime-display-load-no-local-panel-physical-C2103102`，manifest SHA256 `469eb0338cd5fe1ca3204e935155a656f78eeb9a8bd3cdfccd4b1b6086882deb`。父级逐文件复核全部 4,748 项输入，启动前完整目录恰为这 4,748 项加 manifest。源清单保留 599 staged、269 enabled、原 prepare 644 文件；实际 VG 为 `f621fcbecb79012c0486e248a1cc686437b9d11ab887c22b2c8554a62f8b49af`，此前综合通过，不能据此接受物理资源或时序。

SDC `06e9739cf9b6dc73352c0dd161095d298dba32c08311c5e233bd29c02fc3f5cc` 和 CST `8c3f8415936623883006f02b6c70ad464f323337d9ed486583fee4349cbead3e` 与失败的 C2103101 完全相同；Tcl 仅 UserCode 从 C2103101 改为 C2103102，SHA256 `ca53c0c2af97912448bfe6d00ce0cd5ffa4dac0269e4fc3a1b536d7a52ed0ba5`。仍为 place1／route0、timing driven／hold correction 开、resource replication 关。未降低时钟、增添例外或移除其他功能；no-CNN／no-local-panel 是已有显式来源策略。后来新增 TF direct 组件未选入本 VG。

## 实际验证

适配器的 21 项定向测试及父级完整重放通过；父级随后执行真实 preflight 和 prepare，均退出 0。独立检查从六组 seal 重新构造期望副本，而非只信 manifest：4,618 原证据输入对应 4,622 份副本，另核对 101 maintained helpers、7 recipe 文件及其余源／输出。15 项内存中的边界、参数和副本篡改全部被拒绝。父级启动前完整重放该独立检查，并自行核对 4,748 文件、全部 staged 输入、101 helper 与 Git 检查点、Tcl 单一差异及 SDC／CST 字节。

v3 启动器 `39822f394f106dbee1fe87140d3cd3ba10873b6438666054a47565571749573f` 有 8 项无 EDA 的边界／失败／工具漂移／完整输出库存回归；实际安装的 250 项 Mach-O／dylib／Tcl／OpenSSL 输入在准备时匹配。启动器将在调用工具前绑定、结束后重验这些字节，并登记所有 implementation 输出（包括 `.db`／`.p`）；这不是完整 vendor 数据库闭包或实际加载镜像追踪。Gowin 调用串行使用 `/private/tmp/gw138k-build.lock`。

父级最初两次重放因 cache 工作目录选中 Python 3.9、缺少 `hashlib.file_digest` 而未执行验证；保留失败日志，改用明确的 `/opt/homebrew/bin/python3` 后完整通过，未改变封存脚本。独立 seal 为 `6ce8960a57d15588702baedd629d492a17d84bb930982bd952bd22dcd9137422`。父级另捕获 60 项实际引用的 root 源码，使后续主线修改不改写历史输入；父级 seal 为 `81fad1e3cab10731a25aee28059b4ae7db6d53cc2a52a89f55cfb61220a2a525`（74 本地文件、9,614 外部输入）。后续 hash-only 核验不重跑已分配 UserCode／尚未启动实现的历史前置条件。

## 下一步与边界

本报告提交并 push 后，以封存 v3 对该目录启动一次 P&R，实际结果另行记录。完整 CDC／reset、实际工具查询与例外传播、PLL／routed STA、功能保全和实板仍未接受。本阶段没有位流、板卡操作、SRAM 或 Flash 写入。回退保留原部署身份、锁定基线及 C2103101 失败证据；此 cache 实验在维护实现入口具备同等输入检查后退役。

机器摘要见 [display_load_C2103102_prelaunch_parent.json](workstation_task_20261030/display_load_C2103102_prelaunch_parent.json)。完整父级证据保存在本机 cache 的 `display-load-physical-preparation-parent-v1`，不将生成数据库、波形或位流提交到源码。
