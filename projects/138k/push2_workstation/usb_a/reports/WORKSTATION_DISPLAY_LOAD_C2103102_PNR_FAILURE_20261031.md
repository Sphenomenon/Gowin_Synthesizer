# C2103102：显示请求候选实际 P&R 失败

固定候选 `custom138k-workstation-r00-no-local-panel-v1-222fb761448fb6c0`、VG SHA256 `f621fcbecb79012c0486e248a1cc686437b9d11ab887c22b2c8554a62f8b49af` 的 `C2103102` 实验已结束：工具退出 1，launcher 实测 1364.352449333 秒。实际工具日志、impl 日志及 P&R 报告一致给出 DesRoute／PR0004 和 **3014 条未布通网络**。报告中的 placement 为 3 分 30 秒、routing 为 18 分 57 秒。没有 `.fs`、`.tr` 或 `.sdf`，没有完整 routed STA 或可部署位流。

实际物理报告：Logic 95,255／138,240、Register 60,576／139,095、CLS 61,440／69,120、BSRAM 284／340、DSP 123／298；PRIMARY 和 LW 均为 8／8。综合阶段 BSRAM 237 与物理打包 284 分列。较前一 C2103101 的 589 条未布通网络增加，不能由 CLS 下降 66 推断布线改善，也不能从两次失败推断某一逻辑路径已经满足时序。

schema 2／v3 launcher 在启动前后绑定的 4,748 项冻结输入及 250 项安装工具／Mach-O／dylib／Tcl／OpenSSL 文件保持。该工具清单不等于整套 vendor 数据库闭包或实际加载镜像追踪。父级重放独立 reviewer 成功，并直接核对实际资源报告、日志和全部九份 impl 输出；集合、长度及 SHA256 与 launcher 输出登记一致，包含 `.db`、`.p`、`.vo`。五项内存内负控均拒绝：漏数据库、漏网表、虚构 exit 0、冻结 VG 漂移和虚构位流。没有重跑要求 impl 不存在的历史准备门禁，未改预启动封存包。

证据：[机器记录](workstation_task_20261030/display_load_C2103102_postrun_parent.json)。原输出目录为 `/Users/sphenicidition/.cache/gw138k-task-20261030/runtime-display-load-no-local-panel-physical-C2103102`；独立 review SHA256 `95efd23ffc12bfa57c90fb75cdd76c733b3e3a5d0424a9b936b586c908a5a029`。父级只读 hash 包为 `display-load-C2103102-postrun-parent-v1`，seal SHA256 `ec269368a6f9c96b8c0524973cf748a641261afe4af5bd68bbd1d9b1a5a09e93`，其 `verify.py` 可复核。

本次沿用原 SDC／CST、名义频率、place1／route0、timing-driven／hold correction 和 replicate=false，没有新增时钟例外或删功能。后来的 TF 直接组件、quiesce 注册及 C02 行绘制不在此固定候选中。它也不证明综合报告 57.039 MHz 是同步计算上限；具体跨域关系另见[时序解释](WORKSTATION_DISPLAY_LOAD_TIMING_INTERPRETATION_20261031.md)。

没有操作板卡、SRAM 或 Flash，不推断当前板上内容。固定输入及较早回退身份保留；下一批改为 AE350 本地存储和业务 owner 迁移后产生新候选，再做实际同功能资源与物理验证。C2103102 保持失败状态，不授予硬件或部署接受。
