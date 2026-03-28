# 配置说明

运行时配置来自 `config.yaml`、环境变量，以及可选的命令行覆盖。

## 核心文件

- `config.example.yaml`：带注释的基础配置
- `config.yaml`：你的本地运行配置
- `.env.example`：环境变量示例
- `.env`：你的本地密钥和覆盖项

## `config.yaml`

### LLM

主要字段包括：

- `provider`
- `base_url`
- `model`
- `api_key_env`
- `timeout_connect`
- `timeout_read`

常见的 `provider` 取值：

- `openai-compatible`
- `ollama`
- `mock`

当你使用 OpenAI、DashScope、vLLM、LM Studio、Together.ai 等兼容接口时，通常选择 `openai-compatible`。

### Server

重要字段：

- `host`
- `port`
- `editor_secret`

`host: 127.0.0.1` 是更安全的本地默认值。

如果你把服务暴露到 `0.0.0.0` 供局域网访问，请务必阅读下方的编辑器鉴权说明。

### Paths

服务会从 `paths` 中读取这些目录：

- `stories_dir`
- `saves_dir`
- `static_dir`

### Logging

日志相关的重要字段：

- `level`
- `file`

默认情况下，文件日志写入 `wenyoo.log`。

## 环境变量

常用变量包括：

- `LLM_API_KEY`
- `LLM_PROVIDER`
- `LLM_BASE_URL`
- `LLM_MODEL`
- `SERVER_HOST`
- `SERVER_PORT`
- `LOG_LEVEL`

API 密钥变量名不是写死的。真正读取哪个变量，由 `config.yaml` 里的 `api_key_env` 决定。

## 命令行覆盖

`python -m src.main` 支持这些常用覆盖参数：

- `--config`
- `--llm-provider`
- `--llm-base-url`
- `--llm-model`
- `--host`
- `--port`
- `--stories-dir`
- `--saves-dir`
- `--static-dir`
- `--log-level`

如果你只是想临时改一次配置，而不想修改 `config.yaml`，命令行参数非常方便。

## 编辑器鉴权

编辑器可以保存故事并调用编辑 API。如果服务不只是在本机访问，建议在 `config.yaml` 中设置 `server.editor_secret`。

配置了 `editor_secret` 后：

- 编辑器写接口会要求 `X-Editor-Token` 请求头
- 编辑器 UI 可以通过 `editor_token` 查询参数接收令牌并保存在本地

如果你只在可信的本地机器上开发，不设置 `editor_secret` 也可以。

## 推荐配置场景

### 本地测试

- `provider: mock`
- `host: 127.0.0.1`
- 不需要 `editor_secret`

### 本地真实创作

- `provider: openai-compatible` 或 `ollama`
- `host: 127.0.0.1`
- `editor_secret` 可选

### 局域网或共享机器

- 检查防火墙和反向代理设置
- 设置 `editor_secret`
- 不要在无鉴权的情况下直接暴露编辑器

## 相关文档

- [快速开始](getting-started.md)
- [故障排查](troubleshooting.md)
