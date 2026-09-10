# 浅层区域视图与内部标识隔离

模型侧已改为 id / bounds / summary / regions。原树的包装层不会直接映射为模型需要逐层展开的区域。
操作边界保留独立，纯展示内容按类型合并；文字仍由模型按区域读取。

| 用例 | 本地结构树最大深度 | 模型区域最大深度 | 模型区域数 | 首屏 UTF-8 字节 |
|---|---:|---:|---:|---:|
| meituan_main | 12 | 4 | 71 | 1196 |
| meituan_takeout_food1 | 16 | 8 | 136 | 941 |
| meituan_takeout_food2 | 17 | 8 | 156 | 872 |
| meituan_takeout_merchant1 | 19 | 6 | 143 | 1059 |
| meituan_takeout_merchant2 | 21 | 6 | 155 | 1146 |
| meituan_takeout_merchant3 | 20 | 6 | 108 | 1056 |
| meituan_takeout_merchant4 | 21 | 6 | 146 | 1272 |

深度以根为 0。4–8 层的深度仍含真实嵌套操作目标，例如列表、翻页容器、列表项、项内按钮；
不为追求更浅而合并不同操作目标。上述首屏只是导航描述，不包含正文，也不是整次提取的 token 数。

## 本轮变更

- 任意深度的无操作包装层均可穿透，不要求其 bounds 与子层一致。
- 文本、图像等纯展示区域按类型边界组织；跨包装层连续的同类型展示节点可合并。
- 点击、长按、输入、选择、滚动、列表和翻页区域独立存在。focusable 本身不等同于可操作目标。
- summary 在结构分区后直接拼装类型与区域文本/描述/提示；文本不影响结构边界。空白归一化、去重后最多保留 6 段和 120 字符正文，超出加省略号。
- hash、结构指纹、原始 n/g ID、原父节点、package、resource-id、class 等字段只保留本地。
- 全部模型读取接口包括 page_node 使用公开字段白名单；公开区域 id 和文本 item 编号是必要导航/引用句柄。
- 操作范围仅在展开选中区域或查询详情时返回；子区域摘要不再重复携带几何及技术属性。

## 验证

21 项测试通过。覆盖七用例的文本替换不影响分区、全部原节点本地保留、公开区域可达、分页文本完整，
以及 30 层不同 bounds 包装层压平至 1 层、视觉类型合并、同 bounds 嵌套操作不误合并、
所有模型工具返回字段中不含内部标识。工作区 test.py 也已迁移为公开整数 ID，并加 main guard。

## 交付入口

- 构建：python3 xml_probe.py run examples --out runs
- 查看：python3 xml_probe.py view runs/meituan_takeout_food2/meituan_takeout_food2
- 代码：presentation.py；harness 接口：model_interface.py。
- 完整公开树：每个用例的 regions.json；完整诊断树仍是本地 tree.json，不应发送模型。

当前 summary 直接使用区域内容作为初始值，不需要模型先判断功能名称；没有文本则回退到节点类型描述。摘要不等于完整原文，read 继续提供完整内容。
没有新增模型调用，亦未运行独立模型的费用或提取准确率实验。
