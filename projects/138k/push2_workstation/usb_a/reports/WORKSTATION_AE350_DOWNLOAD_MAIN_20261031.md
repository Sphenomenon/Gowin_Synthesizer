# C03 下载第二批主树独立复验

作者 `47041a605fb75d2bafd2c6c7391f48c895441308` 的 23 份修改按原字节导入主树 `564a1b7`，保留原生邮箱优化及探针工作。READ／ACK／combined ACK、续传、引用与 30 秒策略现在由实际 C owner 管理；采集、CRC、DDR、Rice 与线格式继续由原硬件路径承担，详细行为见[第二批报告](WORKSTATION_AE350_BLE_DOWNLOAD_SECOND_BATCH_20261031.md)。

父级在主树重跑实际 maintained C/APB/parser/raw-DDR 联仿：1,701 checks、136 条完整 WIRE/BLOCK 逐字对照、15 个实际 C 变异拒绝全部通过。夹具明确采用修正后的 control 20 ns／memory 14 ns，保持原生产时钟／deadline；首批 ps/ns 差异的历史日志保留。prepared/source 八项、accepted sources 十七项、固件十项、callback 四项、ProfileSources 六项、实际 runtime 来源十二项全部通过。

实际主树 prepare／verify 身份 `custom138k-workstation-ae350-business-v1-fa5d45ee77c98b1d`，配置 SHA256 `7b1e10e64c4b139174c2c2545df08c26c1e10a32080f36c534b30ce45dc7e90b`，612 staged／271 enabled，实际 268 编译单元／300 modules／2 packages。与作者固定 `54e6f30a859dc9f7` 比较仅 USB build.log 的源码路径不同；替换前缀后其余字节完全一致，不转移作者身份。

ELF／BIN／ROM 与作者完全相同。冷镜像 29,808 B、ILM 29,200 B、DLM 静态 624 B，73 个实际 JALR 位置绑定严格回调证明，保守栈 1,344／16,384 B。正式字节的独立启动模型执行 235,597 条指令后进入 ILM services_main；这不是实际周期或完整业务运行期。父级另新编译默认及 recording 固件，其 BIN／ROM 与已封存迁移前对应产物逐字一致。

机器记录见 [ae350_download_main_parent.json](workstation_task_20261030/ae350_download_main_parent.json)。父级包 `/Users/sphenicidition/.cache/gw138k-task-20261030/ae350-download-main-parent-v1` 保存源码快照并绑定 752 项外部文件，seal SHA256 `617f3e598d9157faf364b56a90da25493a1f20b77119b2653d59ee5cdef83658`。作者原包的 1,011 项产物／23 份源码亦独立重验通过。

本候选尚无新的综合／P&R、净资源、完整 CDC／时序、CPU 周期／Cache、真实 BLE／Android 或部署接受。C7／C8 独立探针结果与此完整工作站身份分开记录，C01／C03 整项保持未完成。后续以新完整综合核算接口成本；回退选择第一批显式配置或原 no-panel 配置并重新准备。
