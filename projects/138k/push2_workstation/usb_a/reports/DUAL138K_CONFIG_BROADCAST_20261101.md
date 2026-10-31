# 运行时配置广播的组合路径简化

2026-11-01。M12b 默认实际最差配置路径由 `config_accept_pending` 经事件资格进入效果历史清理，setup −1.656 ns；far 中也保留配置／引擎就绪重汇合。本次修改维护 `gw138k_event_workstation.sv` 的配置接受点，以既有广播阻止事件分发的条件简化组合计算，engines 和 effects 共用 `engine_rate_commit`。公开 `rate_ready_o`、历史请求、状态／优先级和取样周期保持。

`{rate_commit_i,busy}` 为10时，既有 `runtime_config_block` 确定为1，dispatch、mode和两个core event有效位均为0，PANIC资格只剩USB生命周期；因此配置接受只需复位、故障、pipeline quiet、USB生命周期及效果就绪条件。其他三个二态组合结果为0；任一控制未知时使用原 `rate_commit_i && rate_ready_o`，保留原四态语义。新源 SHA256 为 `5d02329a6b7f08ec30d79552a4814436b7c01611f4e4bed83c1514d154ef3fd1`。

复用既有证明及完整服务／控制测试，结果如下：

- 实际源码方程的全域二态等价为UNSAT，4个配置资格破坏模型产生反例；原effect-slot证明和4个负控保持。实际事件过程、case和ready方程另经81,920个有限四态向量对照，全部相同。
- 完整旧M11／新服务逐半周期比较115,929,947次，50个公开输出及实际 `core_ce` 相同；独立PCM模型通过48k的24,323帧及44.1k的24,322帧，覆盖21次配置、324次历史事务、11次取消和326次有序DDR fence。
- 实际APB／USB／CPU、完整效果、物理I2S模型及显示消费通过：1,078音频帧、1,077显示tuple、384 FFT bins；另验in-flight score取消。来源17项和DEMO审计15项通过。

旧限制语法解析器首次拒绝多位十进制比较常量，已修正并重新证明；没有据此修改生产RTL条件。四态向量是有限检查；理想RTL仿真不证明模拟亚稳态、routed时序或实板功能。[机器证据](dual138k_config_broadcast_20261101.json)固定全部来源和外部日志，SHA256 `1c2e3f7524694f14a0bd7501900a106c61fd70111acb3e95f69e4686eae3946a`。

两份DEMO的822项来源锁已刷新；M13 `eae1eec8001e068f` prepare完成，588封存／261启用源复验，新配置广播、chorus和TF DMA确被实际编译消费，正全量综合。第一次prepare误用系统编译器的失败目录保留，重试显式使用与M12b相同的xPack工具链。W11封存目录及正在P&R的 `D2110101` 输入保持原字节；后续W候选才消费本次新共享音频源码。新源码尚无综合／物理收益或部署声明。回退恢复父event源 `87d9497e…19809` 并以新身份重建。
