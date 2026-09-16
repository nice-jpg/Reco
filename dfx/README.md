# DFX 页面结构调试器

在仓库根目录启动，无需安装前端依赖：

```sh
python3 -m reco.dfx --examples examples --port 8767
```

打开 http://127.0.0.1:8767 ，选择 XML 用例。默认目录为仓库下的 examples，与启动工作目录无关；显式相对路径则相对于当前工作目录。启动页面时递归扫描所有 XML，选择器按相对目录分组；加载所选文件时直接解析并建树，无需预先生成 runs。

左侧 SVG 绘制区域 bounds 和文本，右侧使用可折叠 HTML 树。悬停查看公开属性，点击任一侧会高亮并定位另一侧。支持缩放、适合宽度、文本开关、重新读取和停止读取。底部工具记录显示接口调用顺序。

## 读取边界

服务端先以 UTF-8 读取 XML 文件内容，再通过 `from reco import PageSession` 的 `PageSession.build_tree(xml).start()` 创建快照，并将浏览器的工具请求原样委托给 `PageSession.call()`。浏览器从根节点深度优先遍历，逐区域调用 `page_view`、`page_node`、`page_read`，完整跟随结构分页和文本字符分页。不调用模型，不生成业务提取结论，也不额外读取 index 中的内部属性。

`/api/session` 的 session 是 HTTP 会话标识，不放入公开工具结果。修改 XML 后点击“重新读取”获取新快照；新增文件后刷新浏览器重新扫描目录。已有会话继续使用加载时的快照。最多保留 32 个会话。

公开接口的 read 包含区域后代文本。画布减去直接子区域已覆盖的证据编号，避免祖先重复绘制同一文本；详情保留完整区域内容。文本只作为数据呈现，不作为 HTML 执行。提示框只展示公开接口可见的属性，因此不会显示 hash、resource-id 等内部标识。

## 同步调试

Sync 默认关闭，每次选取 XML 都独立建树。开启后，切换用例或点击“重新读取”会调用 `POST /api/sync`，请求包含旧 `session` 和新 XML 的 `case`。服务端对旧快照的副本调用 `sync(new)`，浏览器仍通过原有公开工具遍历同步后的树。只有完整加载成功才更新同步基准；停止读取或加载失败不会改变基准。

变化节点在画布和 DOM 树中标红；悬停或选中节点后，变化属性以红色显示“旧值 → 新值”。删除节点保留红色虚线轮廓，并可在删除记录中查看旧属性。差异数据仅用于 DFX 显示，不加入模型工具返回值。关闭 Sync 后再次加载会清除变化标记。

## 坐标与交互

- 原点位于 (0, 0)，x 向右、y 向下。SVG viewBox 覆盖所有区域和原点，负坐标向左、向上延展。
- 反向 bounds 仅在绘图时归一化，零宽高以至少 1 个坐标单位显示，两者用异常框标记；详情保留原值。缺失 bounds 的区域仍保留在树中。
- 重叠区域点击命中面积最小的区域，同面积时优先深层区域；大区域可直接通过右侧树选中。
- 画布文字按区域空间裁剪，完整文本可在详情中查看。此视图表达公开结构，不模拟 Android 遮挡关系或推断隐藏状态。

## 实现选择与验证

评估了开源 [Headless Tree](https://github.com/lukasbach/headless-tree)。当前用例为百余区域，原生 HTML details 和 [SVG viewBox](https://developer.mozilla.org/en-US/docs/Web/SVG/Reference/Attribute/viewBox) 即可完成折叠、矩形坐标及联动，无需引入 React 或虚拟化依赖。

```sh
python3 -m unittest discover -s tests -t .. -q
node --test dfx/tests/core.test.mjs
```

测试覆盖递归 XML 发现、接口结果一致性、同步属性差异、替换及删除、aaid 保留与失效、快照隔离、非法请求、根到叶遍历、分页、Unicode 文本、负坐标及重叠命中。
