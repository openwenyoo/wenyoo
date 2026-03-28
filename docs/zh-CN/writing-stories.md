# 编写故事

本指南说明推荐的创作流程。请配合以下两个权威格式文档一起阅读：

- [`prompts/story_format_description.md`](../../prompts/story_format_description.md)
- [`prompts/node_format_description.md`](../../prompts/node_format_description.md)

## 先决定故事文件布局

小型故事适合单文件：

- `stories/my_story.yaml`

较大的故事建议使用目录加 `main.yaml` 与 `includes`：

- `stories/my_story/main.yaml`
- `stories/my_story/nodes_forest.yaml`
- `stories/my_story/characters.yaml`

多文件示例可以参考 `stories/age_of_fable/main.yaml`。

## 最小可运行故事

一个完整故事最少应包含：

- `id`
- `name`
- `start_node_id`
- `nodes`

示例：

```yaml
id: cabin_demo
name: "Cabin Demo"
start_node_id: start

nodes:
  start:
    name: "Outside the Cabin"
    explicit_state: "A small cabin stands in the pines."
    actions:
      - id: enter_cabin
        text: "Enter the cabin"
        effects:
          - type: goto_node
            target: inside

  inside:
    name: "Inside"
    explicit_state: "Dust hangs in the still air."
    is_ending: true
```

新内容请优先使用规范字段名，例如 `explicit_state`、`type` 和 `target`。

## 推荐工作流

1. 先确定故事主题、范围和主要地点。
2. 决定故事保持单文件，还是拆成 `includes` 多文件。
3. 先搭建最小故事骨架。
4. 添加节点、动作、物品、触发器和角色。
5. 校验 YAML。
6. 如果故事依赖跨节点关系或生成内容，编译连接图谱。
7. 在浏览器里实际游玩测试。

## 核心创作概念

### 节点

节点表示地点、场景或故事状态。通常会包含：

- `name`
- `definition`
- `explicit_state`
- `objects`
- `actions`
- `triggers`

### 动作

动作表示玩家可以执行的行为。新内容推荐使用：

- `text` 作为玩家可见文案
- `effects` 作为确定性的状态变化
- `intent` 用于交给 Architect 做更自由的解释

### 变量和状态

用 `initial_variables` 保存故事状态、计数器、标记以及 lorebook 风格的上下文。例如：

- 像 `gold` 这样的计数器
- 像 `met_guardian` 这样的布尔标记
- 像 `lore_writing_style` 这样的风格和世界设定变量

### 角色和物品

角色与物品都遵循相似的分层模型：

- `definition`：作者定义的身份与规则
- `explicit_state`：玩家可见的基础描述
- `implicit_state`：隐藏上下文或兼容字段
- `properties`：机械状态数据

## 校验

在提交或发布故事前，先运行校验器：

```bash
python scripts/validate_story_yaml.py stories/example.yaml
```

适用场景包括：

- 校验单个故事文件
- 校验带 `main.yaml` 的故事目录
- 通过 `--all-yaml` 校验某个目录下的全部 YAML

如果 `connections` 图谱已经过期，校验器也会给出提示。

## 编译连接图谱

编辑器中的图谱以及部分运行时关系能力依赖 `connections`。

编译命令：

```bash
python tools/compile_connections.py stories/example.yaml --write
```

可选项：

- 添加 `--with-llm`，让工具推断更多关系
- 当你修改了节点结构、物品、角色位置或导航关系后，重新运行一次

不要手工编辑生成的 `connections` 区块。

## 编辑器与手写 YAML 的关系

以下场景更适合用编辑器：

- 可视化图谱创作
- 更容易浏览节点与连接
- 利用保存到服务器时的版本历史
- 使用 AI 辅助编辑流程

以下场景更适合直接写 YAML：

- 需要精确控制 schema
- 熟悉 `includes` 的多文件结构
- 需要做大规模批量修改
- 希望获得更清晰的 diff

编辑器的几个关键行为：

- 编辑器读取多文件故事时会先合并 `includes`
- 编辑器保存时会把合并后的故事写回入口故事路径
- 通过编辑器保存会在 `saves/story_versions/` 下保留版本备份

## 参考资料与示例

- `stories/example.yaml`：较完整的单文件示例
- `stories/form_demo.yaml`：表单示例
- `stories/multiplayer_coop_demo.yaml`：多人示例
- `skills/create-story/validation-checklist.md`：创作者检查清单
- `skills/create-story/story-patterns.md`：叙事结构模式

## 下一步

- [编辑器总览](editor/README.md)
- [编辑器工作流](editor/workflows.md)
- [故障排查](troubleshooting.md)
