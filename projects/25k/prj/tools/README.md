# 本板构建与调试工具

```sh
sh prj/tools/gowin.sh prj/lcd_bringup/build.tcl
```

`gowin.sh` 对所有文件名匹配 `build*.tcl` 的入口（包括 `build_serial_gao.tcl`）自动使用 `gowin_build.py`：

- 将源码复制到全新 `/private/tmp/gw25k-build-*` 英文目录；原始 vendor 文件保持不变。
- 全局构建锁拒绝同时启动另一构建；不自动重试失败的编译。
- 独立进程运行综合，冻结显式设置；另一个独立进程仅加载生成的 `.vg` 和约束运行 PnR。
- 要求日志明确确认跳过综合、完成 bitstream 生成。返回码异常、文本错误或重复综合都会停止发布。
- 成功产物保存到对应项目 `builds/<时间戳>/impl`，不覆盖之前的镜像。`reports/last_build.json` 是**最近一次成功**的产物路径和 SHA256，失败详情在 `last_failure.json` 及每次独立日志中。

下载应选择本次成功清单中的路径并核对 SHA256；不要从旧 `impl` 目录中猜选镜像。此工具不自动烧录，也不把构建成功等同于时序或外设功能通过；仍需检查新产物的 `.tr` 和实板表现。USB 工程的综合后 GAO 分进程流程已实际构建、SRAM 校验和采集通过，要求 PnR 的 `-gao` 插入网表存在、`-gao_crc` 与 XML ID/bitstream 匹配，禁止混入 `-rtl_gao`。完整记录见 `../usb1_device/debug/GAO.md`。

## 2026-10-16 崩溃规避

用户提供的报告中，Gowin V1.9.12.03 原生 ARM64 `gw_sh` 在 `VLGPARSE::Vlgreader::dupPortPin` 读取综合网表时被 libmalloc 检测到空闲块内存损坏，终止信号 SIGTRAP。此报告不能确定具体的 RTL 或路径根因。

除分阶段、英文临时目录外，LCD 字体逻辑将乘法寻址与动态位选择改为固定 `case`，像素内容不变；完整仿真通过，新网表不再包含新增的 MULT12X12。完整隔离构建已实际通过，PnR 日志确认没有重跑综合，50 MHz setup/hold 违规均 0（Fmax 68.714 MHz）。这是已验证可完成本轮构建的规避组合，不能据此保证第三方编译器以后不会崩溃。

本机 `saveto -all_options` 会导出器件拒绝的默认 `vccaux`，故只用 `saveto` 冻结显式设置。虽然本机文档列出 `-type vg`，当前实现拒绝该字符串；实际支持的是 `-type netlist`，已由新 USB 构建验证。一个工程只能启用一个 SDC，USB GAO 将 50/60 MHz 和观察器约束合并后添加，避免前一个 SDC 被悄然禁用。

RTL GAO 的 `.rao` 会使独立 PnR 进程重复追加调试核 RTL 并重新综合；禁用它则丢失 GAOCRC。工具现在明确拒绝该组合，不降低元数据校验。USB 使用正式的综合后 `.gao` 流程，综合保留真实观测寄存器，PnR 只插入一次分析器。旧 BLE `.rao` 构建入口尚未迁移到该流程；此前成功的 BLE 源码、镜像和下载记录均保留，不能把旧入口误称为已通过新的分进程构建验证。

没有关闭系统内存错误检测或崩溃报告。当前 Gowin 安装包只有 ARM64，不能直接用 Rosetta 切换。官方版本说明没有列出本机 macOS 27.2 的验证结果；升级软件或换其他系统可留作后续选择，当前没有变更全局安装。

01:43 新增 USB2 `build_serial_gao.tcl` 时暴露了原入口只匹配两个固定名字的遗漏，脚本回落到直接 `gw_sh` 后再次 SIGTRAP，未发布或下载该产物。现统一按 basename `build*.tcl` 进入安全构建，并对所有 `_gao` 后缀强制检查启用的 GAO 输入。隔离的假工具分派检查覆盖原两个名字、新串行名字、其他 build 变体和非 build 查询入口，全部通过；修复后的实际串行构建已通过分进程流程，仍须独立检查时序。根本编译器缺陷未宣称已修复。

## macOS USB1 主机验证

`usb_check.py` 默认目标为本次 CDC 镜像的 `FB9A:FB9A`、产品名 `FPGA-USB-Serial`。先保存枚举记录；此模式使用标准库，只查询 I/O Registry，不打开串口：

```sh
python3 prj/tools/usb_check.py --output /private/tmp/gw25k-usb-enumeration.json
```

记录包含 VID/PID、设备描述符对应的注册表字段、产品/厂商名、locationID、registry ID、速度、接口 class/subclass/protocol 和关联的 `/dev/cu.*` 路径。脚本先用 `ioreg -a` 解析 plist；归档失败时回退到普通 IOService 树，保留原错误。两个查询都失败时状态为 `host_query_failed`，不会当作“设备未枚举”。普通 IOUSB 树可用于判断物理设备出现，但 CDC 路径归属应从 IOService 子树确认。注册表未公开的完整配置/端点描述符不在本脚本的验证范围内，也不会主动向设备发送 GET_DESCRIPTOR。

在已有 `pyserial` 的 Python 环境中显式开启回环：

```sh
python3 prj/tools/usb_check.py --loopback --timeout 3 --rounds 8 --output /private/tmp/gw25k-usb-loopback.json
```

脚本要求精确 VID/PID/产品名匹配的物理设备只有一个，CDC control/data 接口均存在，目标子树只有一个 callout；打开前重新查询，要求 registry ID 和路径仍一致。没有扫描或尝试其他串口，也不支持手填任意串口路径。`--vid`、`--pid` 按十六进制解析，可与 `--product` 一起显式换目标。枚举 JSON 会在打开串口前先写入文件。

回环设置115200、DTR开、RTS关；当前 FPGA echo 不依赖 DTR，波特率是 CDC line coding 参数。主机按1/7/31/32/33/63/64字节分批写入，每批完全读回后再发下一批，默认8轮共1848字节，包含新随机前缀和完整二进制0…255序列。逐字节比较、短读补齐及每批超时会发现丢字节、改字节、重复或顺序错误；主机写入长度不等于实际USB包边界。初测不使用大块连续灌入，避免上游有限echo队列掩盖基础链路判断。通过后JSON包含字节数、每批结果及payload SHA256；`unique_target_enumerated` 只表示枚举通过，数据链路需 `mode=loopback` 且 `passed=true`。

如设备不出现，可加 `--logs-seconds 60` 保存最近一分钟的 USB unified log（最多2000行，并保留查询权限错误）。枚举失败早期可能还没有 VID/PID，故按 USB subsystem / IOUSB sender / kernel USB 消息和插入时间定位，不能把所有事件归因于目标。日志为空或查询受限也不能证明没有总线活动。需要捕获连接瞬间时，在下载/重新插入前由主调试流程启动以下只读流，并在观察结束后停止：

```sh
/usr/bin/log stream --style ndjson --level debug --predicate 'subsystem CONTAINS[c] "usb" OR senderImagePath CONTAINS[c] "IOUSB" OR (process == "kernel" AND eventMessage CONTAINS[c] "USB")' > /private/tmp/gw25k-usb-live.ndjson
```

不更改系统日志设置或清空日志。脚本离线测试（不查询硬件、不打开串口）可运行 `python3 -B -m unittest discover -s prj/tools -p test_usb_check.py -v`，覆盖树解析、重复root去重、hub子设备隔离、目标/接口/串口歧义拒绝、归档失败回退、查询错误、短读回环、数据损坏与超时。
