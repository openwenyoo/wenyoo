# 快速开始

本指南帮助你在本地启动游戏服务和故事编辑器。

## 环境要求

- Python 3.10+
- `pip`
- Node.js 18+，仅在你需要重新构建编辑器时才需要
- Docker，仅在你希望容器化部署时需要

## 最快启动方式

1. 克隆仓库并进入项目目录。
2. 启动交互式启动脚本：

```bash
./scripts/run-linux.sh
```

Windows PowerShell 使用：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-windows.ps1
```

第一次运行时会进入设置向导，可以配置 `venv`、`config.yaml`、`.env`、
API Key、base URL 和 model name。之后如果不带参数再次运行，它会显示 config group 选择菜单。

3. 打开：
   - 游戏：`http://localhost:8000`
   - 编辑器：`http://localhost:8000/editor`

如果你只是想先做一次快速联调检查，可以在向导里选择 mock 配置。

## 本地 Python 安装

### Windows PowerShell

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-windows.ps1
```

运行脚本会自动处理首次安装，然后直接启动服务。
完成设置后，如果你不带参数运行，它会显示 config group 选择菜单。
如果你想直接进入已知配置，也可以正常传入服务参数，例如：

```powershell
.\scripts\run-windows.ps1 --config-group claude
```

### macOS 与 Linux

```bash
./scripts/run-linux.sh
```

运行脚本会自动处理首次安装，然后直接启动服务。
完成设置后，如果你不带参数运行，它会显示 config group 选择菜单。
如果你想直接进入已知配置，也可以正常传入服务参数，例如：

```bash
./scripts/run-linux.sh --config-group claude
```

## 配置真实 LLM

编辑 `config.yaml`：

```yaml
llm:
  provider: openai-compatible
  base_url: https://api.openai.com/v1
  model: gpt-4o-mini
  api_key_env: LLM_API_KEY
```

然后在 `.env` 中配置密钥：

```env
LLM_API_KEY=your_key_here
```

更完整的供应商配置见 [配置说明](configuration.md)。

## Docker 部署

构建镜像：

```bash
docker build -t wenyoo .
```

运行容器：

```bash
docker run -p 8000:8000 \
  -v "$(pwd)/config.yaml:/app/config.yaml" \
  -v "$(pwd)/.env:/app/.env" \
  -v "$(pwd)/stories:/app/stories" \
  -v "$(pwd)/saves:/app/saves" \
  wenyoo
```

在 Windows 上，请把 `$(pwd)` 替换成显式绝对路径，或使用当前 shell 对应的路径语法。

## 重新构建编辑器

通常不需要这一步。仓库已经包含 `static/editor/` 下的预构建产物。

如果你修改了 `editor/` 下的源码：

```bash
cd editor
npm install
npm run build
```

编辑器行为说明见 [编辑器快速上手](editor/getting-started.md)。

## 首次运行检查清单

- `config.yaml` 已存在
- `.env` 已存在
- `python -m src.main` 可以正常启动
- `http://localhost:8000` 能打开玩家界面
- `http://localhost:8000/editor` 能打开编辑器
- 玩家界面能显示故事列表

## 下一步

- [基础功能](basic-features.md)
- [游玩故事](playing-stories.md)
- [编写故事](writing-stories.md)
