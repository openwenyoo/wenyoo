# 故障排查

## 服务无法启动

请先检查：

- Python 版本是否至少为 3.10
- 是否已经安装 `requirements.txt` 中的依赖
- `config.yaml` 是否存在
- 如果当前 provider 需要 API key，`.env` 是否存在

先尝试 mock 模式：

```bash
python -m src.main --llm-provider mock
```

## API Key 报错

如果服务提示缺少密钥，请检查：

- `.env` 中是否存在对应变量
- `config.yaml` 里的 `api_key_env` 是否指向同一个变量名
- 修改 `.env` 后是否重启了服务

## 端口被占用

可以换一个端口启动：

```bash
python -m src.main --port 9000
```

然后使用对应的新端口打开游戏和编辑器。

## 编辑器打不开

请检查：

- 服务是否已经启动
- `http://localhost:8000/editor` 是否可访问
- `static/editor/` 是否存在

如果你最近改过编辑器源码，请重新构建：

```bash
cd editor
npm install
npm run build
```

## 故事没有出现在列表里

请检查：

- 文件是否位于 `stories/` 下
- 故事是否有合法的 `id`
- 完整故事是否定义了 `start_node_id` 和 `nodes`
- YAML 语法是否有效

运行：

```bash
python scripts/validate_story_yaml.py stories/your_story.yaml
```

## 连接图谱缺失或过期

重新编译：

```bash
python tools/compile_connections.py stories/your_story.yaml --write
```

然后重新在编辑器或游戏中加载故事。

## 编辑器保存失败

请检查：

- 服务进程是否有权限写入 `stories/`
- 故事 ID 是否合法
- 如果启用了编辑器鉴权，`editor_secret` 是否配置正确

另外要注意，编辑器保存会写回故事入口文件，并在 `saves/story_versions/` 下生成版本备份。

## Windows 下 Docker 路径问题

示例 `docker run` 使用的是 Unix 风格的 `$(pwd)`。在 Windows 上：

- 请使用显式绝对路径
- 或改写为当前 shell 对应的挂载语法

## 无法重连

重连依赖浏览器存储以及服务端仍保留活动会话。

请检查：

- 浏览器没有清空本地存储
- 仍然使用同一个浏览器配置文件
- 断线时间没有超过服务端的保留时间

## 日志在哪里

- `wenyoo.log`
- 当前运行服务的终端输出

## 相关文档

- [快速开始](getting-started.md)
- [配置说明](configuration.md)
- [游玩故事](playing-stories.md)
- [编辑器参考](editor/reference.md)
