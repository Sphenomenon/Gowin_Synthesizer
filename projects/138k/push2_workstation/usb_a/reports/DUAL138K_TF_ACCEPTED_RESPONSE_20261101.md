# TF accepted occupancy 响应尺寸维护阶段

实际消费的维护DMA已精确落为 `31dcbf5f65d7e7f16aca1cca6189f5975a7adec46c4b2ef03514f5ad2cce07b7`。仅将两条accepted-after-read算术改为full／pending／partial六种预计算，再按原条件选择；未知控制仍回原generic分支。原read_buf私有预装、全部NBA目标／右值／顺序、接口、请求／响应／发布／取消／复位周期保持。

当前M18 default的−1.652ns及far的16级／−.864ns真实 `available_bytes → accepted_used` 路径支持此改动；其物理结果属于旧5fc来源，不能记作新31dcb收益。far原始路径和输入hash已绑定本阶段。

维护测试通过72自由位两表达式UNSAT、完整实际模块2,097,152四态向量和5个源码负控。旧available2,097,152／3负控、response1,048,576／6负控、occupancy14 runs含8负控、threshold8 runs含6负控及private-preload符号／双容量四态／4负控全部通过。严格inverse保持31dcb→5fc→1baa→3f9→5ac；旧oracle与fixture不改，旧mutants带着新hunk运行实际新RTL。这是手工表达式证明及有限模块仿真，不冒称完整SV形式验证或硬件验收。

主线程重验258阶段产物、25输入及3owned文件；逐文件身份、命令及具体范围见[机器报告](DUAL138K_TF_ACCEPTED_RESPONSE_20261101.json)。阶段seal `c3825ffde341b15a16efa39257278e89fb9cc182caa496fb9922ab7e245ad521`。维护生产源直接被profile消费，测试重构不生成生产实现。

下一候选需刷新锁并用新身份重做全量综合/P&R，检查accepted D与read_buf CE实际映射及完整资源／STA／CDC／PLL。未预记资源或时序收益，未操作硬件、未写SRAM／Flash；冻结M18/W16保留。
