# 文柚AI原生游戏引擎

中文 | [English](README.md)

文柚是一款基于 Python 的 AI 原生游戏引擎。作者通过 YAML 声明式地定义世界, 包括节点、角色、物品和规则, 再由 LLM 驱动的 Architect 智能体将其变为可游玩的体验, 理解玩家意图、执行作者编写的规则, 并把后果传播到整个世界。

## 特性

- **声明式世界构建**: 用自然语言定义实体（节点、角色、物品）的规则, LLM 会将其作为运行时指令执行, 无论是战斗、谜题、交易、对话, 还是你能描述的其他机制
- **LLM Architect 智能体**: 统一的工具调用智能体, 解析玩家自由文本输入, 根据作者编写的规则处理行为, 并提交世界事件
- **实体模型**: 每个实体都包含 `definition`（LLM 遵循的静态规则）、`explicit_state`（玩家看到的内容）和 `properties`（如背包、状态、位置等机械数据）
- **连接图谱**: 实体关系图帮助 Architect 传播后果, 例如一个房间中的拉杆会影响另一个房间里的机关
- **多人游戏**: 多名玩家共享同一个世界, 同时保留各自的玩家状态、本地发言、物品交接和跨房间通信
- **Web 界面**: 基于 WebSocket 的现代前端界面
- **可视化故事编辑器**: 基于 React 的节点图编辑器, 用于创作和可视化故事
- **YAML 故事格式**: 人类可读的故事文件, 支持表单、触发器、脚本效果和 LLM 生成内容

## 环境要求

- Python 3.10 或更高版本
- Node.js 18+（仅在你需要重新构建故事编辑器时才需要）
- Docker（可选, 用于容器化部署）

## 快速开始

### 方式 A: Docker（推荐）

1. 克隆仓库:
   ```bash
   git clone <your-repo-url>
   cd wenyoo
   ```

2. 配置环境:
   ```bash
   cp config.example.yaml config.yaml
   cp .env.example .env
   # 编辑 .env 填写 API 密钥
   # 编辑 config.yaml 配置你的 LLM 供应商
   ```

3. 构建并运行:
   ```bash
   docker build -t wenyoo .
   docker run -p 8000:8000 \
     -v $(pwd)/config.yaml:/app/config.yaml \
     -v $(pwd)/.env:/app/.env \
     -v $(pwd)/stories:/app/stories \
     -v $(pwd)/saves:/app/saves \
     wenyoo
   ```

4. 打开浏览器:
   - **游戏**: http://localhost:8000
   - **故事编辑器**: http://localhost:8000/editor

### 方式 B: 本地 Python

1. 克隆仓库:
   ```bash
   git clone <your-repo-url>
   cd wenyoo
   ```

2. 快速安装并启动:
   Linux:
   ```bash
   ./scripts/run-linux.sh
   ```
   Windows PowerShell:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\run-windows.ps1
   ```
   第一次运行时，脚本会进入交互式终端向导，帮助你选择是否使用 `venv`、
   配置 `config.yaml`、把 API Key 写入 `.env`，以及设置 provider 的 base URL 和 model name。
   之后如果你不带参数再次运行，它会显示一个简单的启动菜单，让你选择 config group 或重新打开设置向导。
   如果你已经知道要用哪个 group，也可以继续直接传参，例如 `./scripts/run-linux.sh --config-group claude`。

3. 手动方式:
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # macOS/Linux
   source venv/bin/activate
   pip install -r requirements.txt
   cp config.example.yaml config.yaml
   cp .env.example .env
   ```
   如果你想使用真实 LLM，请编辑 `.env` 填写 API 密钥，并按需调整 `config.yaml`。

4. **（可选）从源码构建故事编辑器:**
   ```bash
   cd editor && npm install && npm run build && cd ..
   ```
   仓库已经包含 `static/editor/` 下的预构建编辑器文件。只有在你修改编辑器源码时才需要这一步。

5. 手动启动服务器:
   ```bash
   python -m src.main
   ```

6. 打开浏览器:
   - **游戏**: http://localhost:8000
   - **故事编辑器**: http://localhost:8000/editor

## 项目结构

```
Wenyoo/
├── src/                    # 游戏引擎（Python 后端）
│   ├── core/               # 核心游戏逻辑
│   │   ├── game_kernel.py      # 主编排器
│   │   ├── architect.py        # 统一 LLM 智能体（工具调用循环）
│   │   ├── node_generator.py   # 动态节点生成（LLM）
│   │   └── ...
│   ├── models/             # Pydantic 数据模型
│   ├── adapters/           # 外部系统桥接（FastAPI、LLM）
│   └── main.py             # 入口文件
├── static/                 # Web 前端
│   ├── index.html          # 游戏界面
│   ├── js/app.js           # 游戏客户端逻辑
│   ├── css/style.css       # 游戏样式
│   └── editor/             # 故事编辑器（已编译）
├── editor/                 # 故事编辑器源码（React/Vite）
├── stories/                # 故事内容（YAML 文件）
├── prompts/                # LLM 提示词模板
└── saves/                  # 游戏存档
```

## 配置

引擎使用 YAML 配置文件（`config.yaml`）、环境变量（`.env`）以及可选的命令行覆盖。

### 快速配置

```bash
# 复制示例文件
cp config.example.yaml config.yaml
cp .env.example .env

# 根据需要在 .env 中添加 API 密钥
echo "LLM_API_KEY=your_openai_compatible_key_here" >> .env
echo "CLAUDE_API_KEY=your_claude_key_here" >> .env
```

### 配置组

`config.yaml` 可以在共享的顶层设置之外, 通过 `config_groups` 定义具名配置组。如果你没有传入 `--config-group`, 加载器会自动使用 `config_groups.default`。

```yaml
server:
  host: 127.0.0.1
  port: 8000

config_groups:
  default:
    llm:
      provider: openai-compatible
      base_url: https://api.openai.com/v1
      model: gpt-4o-mini
      api_key_env: LLM_API_KEY

  claude:
    llm:
      provider: claude
      model: claude-sonnet-4-6
      api_key_env: CLAUDE_API_KEY
```

### 优先级

当多个来源定义了同一个值时, 按以下顺序应用:

1. 内置默认值
2. `config.yaml` 顶层共享配置
3. 选中的 `config_groups.<name>` 配置块, 或 `config_groups.default`
4. `LLM_PROVIDER` 之类的环境变量覆盖
5. `--llm-provider`、`--port` 之类的显式命令行参数

### 命令行选项

```bash
python -m src.main [options]
```

| 选项 | 说明 |
|------|------|
| `--config PATH` | `config.yaml` 路径 |
| `--config-group NAME` | 从 `config_groups` 中选择要加载的配置组 |
| `--llm-provider TYPE` | LLM 供应商: `openai-compatible`, `ollama`, `claude`, `mock` |
| `--llm-base-url URL` | LLM API 基础 URL |
| `--llm-model NAME` | 使用的模型名称 |
| `--host HOST` | 服务器主机（默认取自配置文件） |
| `--port PORT` | 服务器端口（默认取自配置文件） |

**示例:**
```bash
# 使用 config.yaml 中的 config_groups.default
python -m src.main

# 使用 config.yaml 中的 claude 配置组
python -m src.main --config-group claude

# 使用 mock 模式快速测试（无需 API）
python -m src.main --config-group mock

# 在选定配置组的基础上覆盖一个字段
python -m src.main --config-group claude --port 9000

# 不修改配置文件, 直接接入本地 vLLM
python -m src.main --llm-base-url http://localhost:8080/v1 --llm-model mistral-7b
```

## 创建故事

故事通过 YAML 文件定义, 但完整格式比较大, 因此最佳起点是专门的创作文档, 而不是 README 里的一个简化示例。

从这里开始:

- **[编写故事](docs/zh-CN/writing-stories.md)** - 推荐的创作流程、校验方式、示例以及编辑器如何参与工作流
- **[故事格式指南](prompts/story_format_description.md)** - 权威的故事顶层 schema
- **[节点与效果参考](prompts/node_format_description.md)** - 权威的节点、动作、触发器与效果 schema

### 故事结构

- **id**: 故事唯一标识
- **name**: 故事标题
- **start_node_id**: 起始节点
- **initial_variables**: 故事级变量、计数器、标记、lore 和派生值
- **nodes**: 故事中的地点或场景, 使用 DSPP 模型编写:
  - **definition**: 节点是什么, 以及它应如何运作
  - **explicit_state**: 玩家当前能感知到的内容
  - **properties**: 机械状态与自定义结构化数据
  - 以及局部的 **actions**、**objects** 和 **triggers**
- **objects**: 世界中的物品同样使用 DSPP:
  - **definition**: 物品身份与作者定义的交互规则
  - **explicit_state**: 当前可见表现
  - **properties**: 例如容器关系、状态标记或自定义字段等机械数据
- **characters**: 角色使用 DSPPM:
  - **definition**: 身份、性格与行为规则
  - **explicit_state**: 当前对玩家可见的真实状态
  - **properties**: 属性、位置、背包、状态和其他机制数据
  - **memory**: 该角色累计的互动历史

如果你想查看完整的创作 schema, 请以上面的专门文档为准, 不要把这个 README 小结当成完整规范。

## 故事编辑器

可视化故事编辑器允许你通过节点图界面创建和编辑故事。

**[编辑器总览](docs/zh-CN/editor/README.md)** - 故事编辑器文档入口页

### 构建编辑器

```bash
cd editor
npm install
npm run build
```

构建后的文件会自动复制到 `static/editor/`。

## 故事创作文档

如需查看更详细的故事创作文档:

- **[故事格式指南](prompts/story_format_description.md)** - 故事 YAML 结构完整指南
- **[节点与效果参考](prompts/node_format_description.md)** - 节点、触发器、动作和效果的详细参考

## 许可证

本项目采用 MIT 许可证, 详见 LICENSE 文件。

## 社区

欢迎加入文柚官方 Discord 社区, 获取公告、使用支持和交流讨论:

[Wenyoo 官方 Discord](https://discord.gg/ZjaHZqCACG)

如果你正在电脑上阅读本 README, 可以使用手机扫描下方二维码加入:

![文柚 Discord 二维码](docs/assets/wenyoo-discord-qrcode.png)
