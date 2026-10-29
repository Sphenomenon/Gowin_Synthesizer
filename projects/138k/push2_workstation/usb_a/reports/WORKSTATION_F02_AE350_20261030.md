# F02：AE350 可维护固件及显式整机接入

日期：2026-10-30（Asia/Shanghai），源码基点 `cc499f6`。维护入口为 [firmware/ae350/README.md](../firmware/ae350/README.md)，九项源码／启动汇编／链接脚本从已版本化的 resource 基线按原始身份导出，来源及原 ROM 保留；不再依赖旧 AE350 脚本的私有目录。导入后只把两个未调用的旧绘图 helper 改为 `static inline`，以通过现代 GCC 的未使用函数检查。

## 构建与装配

`stage_ae350_firmware.py` 从维护源码生成 ELF、binary、4096 字的 `boot.mem`、map／size／nm／逐函数栈报告和工具／输入／输出哈希；独立检查 16 KiB ROM、8 KiB RAM、对齐及最少 4 KiB 栈空间。输出目录必须不存在，缺源、编译或容量失败不回退到旧 ROM。

`custom138k-workstation-v1` **revision 2** 显式选择 `maintained_ae350_v1`，真实三网表 prepare 先验证父 ROM 身份，再将新 ROM 安装到该候选的 `firmware/boot.mem`。完整固件来源、工具、ELF／ROM、容量和生成证据纳入候选身份；accepted／pinned／resource 和未指定 profile 的 a26 仍保留原锁定 ROM，已用真实默认 prepare 对照证明。

候选为 `custom138k-workstation-v1-2bce61be83aaff38`，244 项来源、230 个编译输入；[完整 profile](workstation_task_20261030/f02_profile.json) 和 [验证记录](workstation_task_20261030/f02_verification.json) 保存逐文件身份。xPack GCC 15.2.0-1 的 binary 为 10,840／16,384 B，静态 RAM 60 B、结束地址 572，栈容量余量 7,620 B。逐函数栈报告不等于完整调用链上界或实板水位，C04 继续验收这些项目。

新 ROM SHA256 `3ded01f97acaa87a9331038cc490e2dc03f7afbfa7bd4880296dbfad8632435b`，ELF SHA256 `4986d67e445aa593575b76cf17065e4561a315f10b19c43111dee693ef753845`；与原 ROM 有 2,578 个 word 不同，不冒充旧候选的字节复现或硬件验收。默认 a26 的原 ROM `8645399a…` 逐字保持。F01 revision 1 的来源和证据继续由其提交 `cbb9687` 及原报告保留。

## 验证与剩余范围

profile 12 项（含真实新／旧装配、缺源拒绝、固件证据／安装 ROM 篡改拒绝）、AE350 固件 7 项（含两次真实编译哈希一致）、USB staging 7 项、accepted 来源 10 项均通过。三类无私有暂存 prepare 的 23 项再次通过；既有 UI PANIC C 测试在新头文件上编译执行通过。冻结基线未改，F02 的源码到 ROM 维护链完成。

本候选尚未综合／P&R、未验证运行时栈和 AE350 服务最坏时限、未 SRAM 下载或写 Flash。CPU 复杂业务迁移和实时数据面分工仍由 C01—C05 继续，不因重新编译原 UI 固件而勾选这些功能。

另已完成的 F01 revision 1 综合见 [f01_synthesis.json](workstation_task_20261030/f01_synthesis.json)：工具正常完成，原 staged 输入未变化，24 项 feature／storage 层次检查通过；合成等效 BSRAM 272、LUT 73,648、寄存器 55,571。新增的 `Prj1.gprj.user` 是工具会话文件。该结果仍采用旧 AE350 ROM，不能移作 revision 2 的综合或物理证据；没有 routed STA／CDC／PLL、物理 BSRAM 或本轮板测结论。
