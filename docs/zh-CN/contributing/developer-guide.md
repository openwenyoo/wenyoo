# 开发者指南

本指南用于补充仓库级别的贡献规则，配套文档见 [`CONTRIBUTING.md`](../../../CONTRIBUTING.md)。

## 主要组成部分

- `src/`：Python 后端和游戏引擎
- `static/`：面向玩家的 Web 客户端
- `editor/`：基于 React 的故事编辑器源码
- `stories/`：故事内容
- `prompts/`：权威提示词和 schema 参考
- `docs/`：用户和贡献者文档

## 架构速览

- `src/main.py`：运行入口
- `src/core/`：GameKernel、Architect 和核心服务
- `src/models/`：故事和运行时数据模型
- `src/adapters/`：FastAPI 路由、WebSocket 处理器和外部适配层
- `static/`：浏览器游戏客户端
- `editor/src/`：可视化编辑器客户端

如果你想了解 Architect 本身的设计意图，请继续阅读 [`architect-design.md`](architect-design.md)。

## 开发流程

### 后端

```bash
python -m venv venv
pip install -r requirements.txt
pip install -r requirements-test.txt
python -m src.main --llm-provider mock
```

### 编辑器

```bash
cd editor
npm install
npm run dev
```

需要生产构建时：

```bash
npm run build
```

## 文档放置规则

新增或修改文档时，请遵循这些规则：

- `README.md` 和 `README_CN.md`：保持为简洁的入口页
- `docs/`：面向任务的产品和贡献者文档
- `prompts/`：权威的故事 schema 和 prompt 参考
- `skills/`：面向代理工作流的说明，不是通用公开文档

尽量不要把同一份 schema 解释复制到多个位置。能链接到 `prompts/story_format_description.md` 和 `prompts/node_format_description.md` 时，就优先链接。

## 故事开发工作流

1. 在 `stories/` 中手写 YAML，或通过编辑器修改
2. 使用 `scripts/validate_story_yaml.py` 校验
3. 需要时编译 `connections`
4. 在浏览器里试玩
5. 如果行为或流程变化，顺手更新文档

## 编辑器开发说明

- 编辑器通过 `/api/story/*` 加载故事
- 保存时由后端写回 YAML
- 版本历史保存在 `saves/story_versions/`
- 编辑器文档位于 `docs/editor/`

如果你修改了编辑器能力，请同步更新：

- `editor/README.md`
- `docs/editor/`
- `docs/` 下受影响的顶层文档

## 测试

常用命令：

```bash
pytest
pytest --cov=src
python scripts/validate_story_yaml.py stories/example.yaml
python tools/compile_connections.py stories/example.yaml --write
```

## 双语文档

当你修改面向用户的文档时：

- 先更新英文页面
- 再更新 `docs/zh-CN/` 下对应页面
- 如果导航结构变化，也要同步更新 `README.md` 和 `README_CN.md`
