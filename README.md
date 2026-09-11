# Reco

将 Android XML 转为**紧凑页面表示 → 模型按区域读取并提取**。
本地算法只维护结构、索引和读取窗口，不判定商品名称、价格或销量。

## 一条命令构建所有页面

Python 3.8+，无第三方依赖，在仓库目录运行：

```sh
python3 xml_probe.py run examples --out runs
```

也支持单 XML：

```sh
python3 xml_probe.py run examples/meituan_takeout_food2/meituan_takeout_food2.xml --out runs
```

`run` 递归扫描 XML，顺序构建结构树、文本索引、首屏概览和组件目录。
不会调用模型，也不会再生成 result.json、价格字段或预判商品区域。
输出按 XML 相对路径隔离；失败不阻塞其他用例，批次存在失败时退出码为 1。

## 模型由整体到局部读取

以 food2 为例，以下为本快照的公开整数 ID，仅作为操作示例，不是算法常量：

```sh
# 第一屏，只看根区域和下一层子区域
python3 xml_probe.py view runs/meituan_takeout_food2/meituan_takeout_food2

# 功能区域快捷目录：输入、列表、滚动区域、翻页容器
python3 xml_probe.py catalog runs/meituan_takeout_food2/meituan_takeout_food2

# 对选中的列表区域细分一层；expand 与 view 相同
python3 xml_probe.py expand runs/meituan_takeout_food2/meituan_takeout_food2 41

# 对其中一项继续细分
python3 xml_probe.py expand runs/meituan_takeout_food2/meituan_takeout_food2 58

# 只读取该区域的原始文本，附公开 item 编号和字符区间
python3 xml_probe.py read runs/meituan_takeout_food2/meituan_takeout_food2 58 --limit 8 --max-chars 800

# 必要时查看该区域的操作范围和状态，不返回原始实现属性
python3 xml_probe.py node runs/meituan_takeout_food2/meituan_takeout_food2 58
```

`view/catalog` 返回 next_offset 时，用 `--offset` 续读；`read` 返回 next 时，
把 offset、char_offset 分别传给 `--offset`、`--char-offset`。单个超长文本也可分段续读。
区域 summary 由本地直接拼接功能/展示类型与区域内 text、content-desc、hint，不需要模型先判断。它是有长度限制的初始摘要，完整取值仍可通过 read 获取。

默认视图格式如下；子区域不逐个附带 bounds，只有展开选中区域时才显示它的范围：

```json
{"id": 41, "bounds": [0,258,1080,2400], "summary": "list", "sub-regions": 6, "regions": [
  {"id": 42, "summary": "clickable", "sub-regions": 3, "expandable": true},
  {"id": 58, "summary": "long-press", "sub-regions": 1, "expandable": true}
]}
```

这是省略文本的示意。实际 summary 例如 `clickable: 徐记肉筋卷饼 更多选择按钮 4.8 分 月售100+ 人均 ¥17…`。
`sub-regions` 是该区域所有层级后代区域的总数（不含自身），不受分页影响；每一层都携带，叶子为 0。离散文本用空格拼接，原文中的斜杠保持不变。
按原节点顺序收集区域内文本、描述和提示，折叠空白并去重，最多取 6 段、正文 120 字符，省略部分标记为 …；原文不修改。没有文本时保留类型描述。

## 接入 agent harness

`model_interface.py` 提供不绑定模型供应商的 JSON Schema 工具定义和本地调用入口：

```python
from model_interface import PageSession

session = PageSession.load("runs/meituan_takeout_food2/meituan_takeout_food2")
initial_context = session.start()  # instructions、tools、根区域概览

# harness 将 initial_context 和用户字段要求交给模型。
# 收到模型工具调用后，将名称和已解析 JSON 参数传给本地入口：
tool_result = session.call("page_view", {"key": 41})
# 将 tool_result 返回模型，继续 page_view/page_read，最终由模型输出所需数据。
```

工具为 `page_view`、`page_catalog`、`page_read`、`page_node`。会话绑定单份快照，
模型不能通过参数切换文件路径或执行任意代码。start 中的工具为供应商中立的 input_schema，
调用方按实际 SDK 转换工具声明。项目未内置 LLM 客户端、鉴权或调用循环。

这条边界是有意的：本地交付可读表示和可导航工具；语义提取交给调用方的模型。
结构维护无模型调用，但**模型阅读概览/局部文本仍产生 token**，不是整次提取零成本。

## 结构算法

本地结构索引与模型展示层分离，`presentation.py` 实现浅层功能区域：

1. 输入、列表、翻页、滚动、点击、长按、选择控件以各自的操作边界作为区域。
   嵌套操作目标保持独立，即使它们 bounds 相同，也不会合并成一个可操作目标。
2. 非操作包装层直接穿透，不再要求 bounds 相同，也不以包装层深度划分模型区域。
3. 纯展示节点以类型为边界，连续同类型的文本/图像区域合并；不同类型、不同操作区域之间不合并。
4. 包装层上的文字仍归属最近保留的区域，原节点和父子关系完整留在本地索引，read 不丢文本。
5. 文本和 resource-id 均不参与结构分区；分区完成后，text、content-desc、hint 直接用于 summary 拼装。resource-id 仍不发送模型。

模型侧不再看 repeated_structure、指纹或原始控件类名。它们只属于可选的本地结构诊断。
仍不删除疑似隐藏内容，不把正面积 bounds 当作可见证明，不强行推断视觉遮挡关系。

## 本地产物与模型输入

| 文件 | 用途 |
|---|---|
| runs/summary.json | 按 case_id 汇总构建状态，ready 不代表已提取业务数据 |
| tree.json | 完整本地结构树、区域跨度、节点归属；不整体发送模型 |
| regions.json | 完整浅层区域树，采用公开 id/summary/bounds/regions 格式，可本地查看 |
| index.json | 原始节点全部属性与父节点；用于核查 |
| payload.json | 原始 text/content-desc/hint 内容；不整体发送模型 |
| overview.json | 默认根区域及下一层的紧凑概览，可作为首屏上下文 |
| catalog.json | 第一页结构快捷目录；更多页通过 catalog 读取 |
| metrics.json | 字节体积和 model_calls=0；没有推算 token |

完整索引追求证据保存，不保证磁盘比 XML 小；节省输入来自每次只发有界视图。
read 的 max_chars 限制值文本字符总数，分页元数据另占体积。
view/read/catalog/node 均显式选择公开字段，不返回 hash、snapshot_sha256、shape、原节点号、
原父节点号、resource-id、package、原始 class 或节点归属表。page_node 也不能绕过这条边界。
这些内部信息继续保存在本地，用于验证和回查。item 是公开证据编号，harness 可在本地将其映射回原节点。
同一快照内公开 ID 稳定；快照变化后需要新会话，不能跨快照复用 ID。

`runs/` 可重建且已 gitignore。重跑会清除同一用例旧版提取产物和过期视图，批次消费以最新
summary.json 为准；不要同时向同一输出目录运行两个批次。

## Web 可视化调试

```sh
python3 -m dfx --runs runs --port 8767
```

打开 http://127.0.0.1:8767 。调试器复用现有 runs，通过模型公开接口从根到叶读取，提供矩形画布、区域树、悬停详情及双向定位。使用说明见 [dfx/README.md](dfx/README.md)。

## 测试

```sh
python3 -m unittest discover -s tests -v
node --test dfx/tests/core.test.mjs
```

7 个异构用例全部构建成功，21 项测试通过。测试重点是文本变更不影响结构、所有节点/属性保留、树中所有区域
可达、分页无漏字、区域隔离、未知控件回退及失败清理；不再用固定商品答案衡量结构算法。
见 STRUCTURE_REPORT.md。旧 MULTICASE_REPORT.md 和 examples 内已有提取结果属于上一轮实验档案，
不再由当前命令生成或消费。
