# Reco

本地将 Android XML 转为紧凑区域树，由模型通过四个查询功能读取内容。解析、建树、区域合并和摘要拼装均由本地算法完成，不调用模型。

## 模块入口

工程根目录通过 `__init__.py` 导出 PageSession，没有嵌套的 reco 目录。在其他项目的 Python 环境安装后，以小写 `reco` 导入：

```sh
python3 -m pip install -e /path/to/Reco
```

也可将工程的父目录加入 Python 搜索路径，直接 `from Reco import PageSession`（包名跟随工程目录名）。安装配置将同一个根目录映射为 `reco`，没有复制实现。

```python
from pathlib import Path
from reco import PageSession

xml = Path("examples/meituan_takeout_food2/meituan_takeout_food2.xml").read_text(encoding="utf-8")
page = PageSession(xml)
context = page.start()  # instructions、七个工具定义、根区域视图
view = page.call("page_view", {})
catalog = page.call("page_catalog", {})
text = page.call("page_read", {"key": view["id"]})
node = page.call("page_node", {"key": view["id"]})

# 可选：保存到 runs，供后续恢复快照；查询本身不需要落盘。
page.save("runs/meituan_takeout_food2/meituan_takeout_food2")
restored = PageSession.load("runs/meituan_takeout_food2/meituan_takeout_food2")
```

`PageSession(xml)` 接收 XML 内容字符串并完成解析和建树，不读取路径。非字符串输入抛出 TypeError，XML 格式无效时抛出解析异常；文件读取由调用方负责。每个实例对应一个固定快照。工程根目录本身就是包，不再提供 xml_probe 命令。以 `_` 开头的模块属于内部能力。

## 四个查询功能

| 工具 | 内容 |
|---|---|
| page_view | 当前区域及下一层子区域，可继续按 ID 展开 |
| page_catalog | 结构快捷目录 |
| page_read | 区域完整文本、描述、提示及公开证据编号 |
| page_node | 区域 bounds 和控件状态 |

`view/catalog/read` 的 `limit` 默认 `-1`，返回 offset 起全部剩余条目；正整数表示条目上限。`page_read.max_chars` 也默认 `-1`，不限制字符总数；显式正整数仍可控制输入预算。0 和其他负数无效。

不限条目不改变树的层级：`page_view` 返回完整的下一层视图，按子区域 ID 继续查询下层。分页时跟随 `next_offset` 或 `next`，文本分片按同一 item 的 char_range 顺序拼接。

`sub-regions` 统计全部层级的后代区域，不含自身，叶子为 0，不受分页影响。summary 由类型与去重文本用空格拼装，不添加 region 或斜杠分隔符；原文中的斜杠保留。

批量保存可直接复用同一个入口：

```python
from pathlib import Path
from reco import PageSession

source = Path("examples")
for xml in sorted(source.rglob("*.xml")):
    PageSession(xml.read_text(encoding="utf-8")).save(Path("runs") / xml.relative_to(source).with_suffix(""))
```

## 结构算法

本地结构索引与模型展示层分离，`_presentation.py` 实现浅层功能区域：

1. 输入、列表、翻页、滚动、点击、长按、选择控件以各自的操作边界作为区域。
   嵌套操作目标保持独立，即使它们 bounds 相同，也不会合并成一个可操作目标。
2. 非操作包装层直接穿透，不再要求 bounds 相同，也不以包装层深度划分模型区域。
3. 纯展示节点以类型为边界，连续同类型的文本/图像区域合并；不同类型、不同操作区域之间不合并。
4. 包装层上的文字仍归属最近保留的区域，原节点和父子关系完整留在本地索引，read 不丢文本。
5. 文本和 resource-id 均不参与结构分区；分区完成后，text、content-desc、hint 直接用于 summary 拼装。resource-id 仍不发送模型。

模型侧不再看 repeated_structure、指纹或原始控件类名。它们只属于可选的本地结构诊断。
仍不删除疑似隐藏内容，不把正面积 bounds 当作可见证明，不强行推断视觉遮挡关系。

## 本地产物与模型输入

PageSession.save 保存快照和公开视图；summary.json、metrics.json 属于内部批量实验统计，不由 save 生成。

| 文件 | 用途 |
|---|---|
| runs/summary.json | 按 case_id 汇总构建状态，ready 不代表已提取业务数据 |
| tree.json | 完整本地结构树、区域跨度、节点归属；不整体发送模型 |
| regions.json | 完整浅层区域树，采用公开 id/summary/bounds/regions 格式，可本地查看 |
| index.json | 原始节点全部属性与父节点；用于核查 |
| payload.json | 原始 text/content-desc/hint 内容；不整体发送模型 |
| overview.json | 默认根区域及下一层的紧凑概览，可作为首屏上下文 |
| catalog.json | 完整结构快捷目录 |
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
python3 -m reco.dfx --examples examples --port 8767
```

打开 http://127.0.0.1:8767 。调试器递归扫描 examples 中的 XML 并直接建树，通过模型公开接口从根到叶读取，提供矩形画布、区域树、悬停详情及双向定位。默认关闭的 Sync 开关支持切换 XML 时同步旧树，并标红变化节点和属性。使用说明见 [dfx/README.md](dfx/README.md)。

## 测试

```sh
python3 -m unittest discover -s tests -t .. -v
node --test dfx/tests/core.test.mjs
```

当前 8 个异构用例参与回归，24 项 Python 测试通过。测试重点是文本变更不影响结构、所有节点/属性保留、树中所有区域
可达、分页无漏字、区域隔离、未知控件回退及失败清理；不再用固定商品答案衡量结构算法。
见 STRUCTURE_REPORT.md。旧 MULTICASE_REPORT.md 和 examples 内已有提取结果属于上一轮实验档案，
不再由当前命令生成或消费。

## Agent assigned ID

在原有四个查询工具之外，新增 update_aaid 与 select_aaid，也可直接调用同名 PageSession 方法：

```python
page.call("update_aaid", {"id": 1, "value": "12"})  # 返回 None，JSON 中为 null
node = page.call("select_aaid", {"aaid": 12})
assert node == page.call("page_node", {"key": 1})
assert node["aaid"] == "12"
```

update_aaid 的 id 为公开区域整数 ID，value 为字符串。select_aaid 按约定接收整数，将其十进制字符串用于哈希索引查找：12 匹配 "12"，不匹配 "012"。任意字符串均可赋值，但非规范整数字符串无法通过当前整数查询接口定位，仍可通过 page_node 查看。

同一 aaid 只能属于一个节点；重复赋给自身是幂等操作，赋给其他节点则报 ValueError。更新后旧映射删除，未知 ID/aaid 与类型错误也报 ValueError。索引查询为平均 O(1)。aaid 是会话内的节点属性，不修改原始 XML，不随 save/load 持久化，新的页面会话需要重新赋值。

## 滑动后刷新树

```python
from pathlib import Path
from reco import build_tree, sync

old = build_tree(Path("before.xml").read_text(encoding="utf-8"))
old.update_aaid(12, "101")
new = build_tree(Path("after.xml").read_text(encoding="utf-8"))
changed_root = sync(old, new)
# old 已就地切换到新页面状态；new 保持独立，不被修改。
node = old.select_aaid(101)
ratio = old.update_ratio(12)
# 模型侧也可查询：old.call("update_ratio", {"id": 12})
```

也可使用 `PageSession.build_tree(xml)`、`old.sync(new)`。build_tree/sync 是宿主 Python 接口；模型工具新增 update_ratio。sync 返回包含全部变化的最小子树根节点详情，完整区域可再用 page_view 读取。没有变化时返回 None；对应根 ID 保存在 old.last_change_root，深度优先变化记录保存在 old.last_changes。

匹配采用 [React 的位置和类型规则](https://react.dev/learn/preserving-and-resetting-state)：在匹配父节点内按兄弟位置比较公开 type，根到叶深度优先遍历。同类型保留公开 ID 与旧 aaid；文本、bounds、状态和节点自身的原始属性变化记为更新。不同类型会删除整个旧子树并为新子树分配新的、不复用的公开 ID，后代 aaid 同时失效。新树自带的 aaid 不覆盖旧树身份。

未引入业务 key，因此同位置同类型的列表行会保留身份，即使滑动后文本属于另一个商品。这遵循当前指定规则，不能据此认定是同一业务实体。aaid 不是新 XML 的匹配依据。

变化检测使用本节点拥有的属性和文本，不用汇总后代的 summary，避免一次叶子文本变化错误地标记所有祖先更新。删除节点的变化位置以其当前仍存在的父节点为锚点；多个位置取当前树中的最近公共祖先。

update_ratio 使用最近一次 sync：分母为旧子树节点数（含自身）；分子累计属性更新节点、新增节点和删除节点。类型替换计为 max(旧子树大小, 新子树大小)，不重复加总删除和新增；子列表增删不再额外把父节点算一次更新。结果 min(1, 分子/分母)。新增节点为 1、已删除历史 ID 为 1、未变化为 0，初始树为 0。未知 ID 或非法参数报 ValueError。每次 sync 会重置存活节点的上次比例。

删除的 aaid 返回以下结构，不会误指向新节点：

```json
{"node": null, "error": {"code": "node_deleted", "id": 12, "aaid": "101", "reason": "type_changed"}}
```

reason 为 removed 或 type_changed；从未赋值的未知 aaid 仍报 ValueError。主动重新赋值同一个 aaid 后指向新指定节点。构建、对比完成后才提交状态，失败不改写 old。刷新历史、失效报告和 aaid 均为会话状态；save/load 开始新会话，不用于恢复刷新历史或延续旧 ID。
