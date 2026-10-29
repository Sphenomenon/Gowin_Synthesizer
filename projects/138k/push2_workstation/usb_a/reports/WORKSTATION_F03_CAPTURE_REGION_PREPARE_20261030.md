# F03独立DDR capture区域准备（2026-10-30）

`custom138k-native-physical-C11030F3`已经完成离线prepare，尚未运行综合／P&R或访问板卡。输出位于 `/Users/sphenicidition/.cache/gw138k-task-20261030/f03-capture-region-C11030F3`；[机器记录](workstation_task_20261030/f03_capture_region_preparation.json)包含完整manifest、输入身份、逐字节差异检查和测试。父F02原失败证据与已接受profile保持原样。

这是固定rev2 F02网表的物理实验，源提交为`3d4b3175d0f20d0b787b61b43e4543739b26bca1`、profile revision2；**不包含当前工作树正在迭代的RTL**。`source_policy=hash_locked_previous_physical_VG_and_SDC_with_only_explicit_DDR_capture_region_CST_append`。新的RTL或其他约束变化需要另外的综合／部署身份。

| 输入 | SHA256／变化 |
| --- | --- |
| `physical_inputs.json` | `39f97ac143e5b02ce1e85e47a91896c4c2bd4c619758ad7b661564126d947554` |
| VG | 原F02逐字节相同，`27b30ac791323f05dc68cd5d9ea6ccaaf14d6a122c5fe2b978cb4714b7fdcf18` |
| SDC | 原F02逐字节相同，`bfcf675d98f07dbcb51eaedfa554b59e14b3f9efca0c2b66822e774ef5198354` |
| CST | 原字节后仅追加下列一条约束，`4931317d74a07e7826448c2eea134465fdf813b44504c4e3bdaf6c392f214fef` |
| `run.tcl` | 相比F02只将UserCode换为C11030F3，`45714dcfaeee9ca6966b2ea9a146aea91101dee2edeaf5b43f1c1f9f5aa00525` |

```tcl
INS_LOC "u_memory/u_ddr3/gw3_top/u_ddr_phy_top/wloadn_3_s0" R[40:50]C[70:90];
```

维护入口 [workstation_custom_board_implementation.py](../tools/workstation_custom_board_implementation.py)增加显式物理派生模式，默认综合准备路径不变。它要求选定原F02版本化证据及其SHA，重核34份物理证据、父manifest和全部7项原输入。DDR内部在VG中加密，因此精确DFFCE类型／INIT、Q→D、共复位／常开CE、UI CLKDIV／4和直接50MHz来自同一VG绑定的原routed VO，不能声称直接从VG解析了内部结构。目标已有约束、三硬资源位置漂移、0.800ns min-delay缺失／重复／变化、任何文件hash漂移均拒绝。

独立检查已确认全部9项新manifest输入、CST精确前缀及唯一追加、VG／SDC字节、TCL仅UserCode变化和无`impl/`。保留原综合`parent_candidate`路径供现有冻结门禁查找scripts，独立`parent_physical_*`字段记录物理父级；prepare后在EDA前修正该元数据，全部9项输入字节未变。保留place2／route0／replicate0、自动hold修复、全部引脚／ULPI声明及三DDR硬资源位置；没有添加false path或修改时钟。新增7项回归和原22项准备器回归通过，`git diff --check`通过。

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_ddr_capture_floorplan.py
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_custom_board_implementation.py
PYTHONPATH=projects/138k/push2_workstation/usb_a python3 projects/138k/push2_workstation/usb_a/tools/workstation_custom_board_implementation.py --source /Users/sphenicidition/.cache/gw138k-task-20261030/f02-physical-C11030F2 --output /Users/sphenicidition/.cache/gw138k-task-20261030/f03-capture-region-C11030F3 --user-code C11030F3 --acknowledge-electrical-risk --ddr-capture-region-parent-evidence projects/138k/push2_workstation/usb_a/reports/workstation_task_20261030/f02_physical.json --expected-parent-evidence-sha256 9d4a4bd9cad00deb0d276f2b617d6bd0f5a1a994067a9c1ffb628222fe1f36be
```

prepare命令拒绝已存在输出，以上命令记录实际创建过程，不能覆盖重跑。下一阶段需核对target CLK／D落入区域、精确hold含clock skew非负，并重新执行完整STA／PLL／CDC／资源／feature门禁。原F02 audio／USB／DDR setup和readiness2ns失败仍是独立阻塞项；F03 prepare不宣称任何时序闭合或硬件通过。回滚只需放弃此独立输出，父F02及音频探针B7均未改。
