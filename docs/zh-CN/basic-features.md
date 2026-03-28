# 基础功能

Wenyoo 同时是一个可游玩的 Web 游戏和一个故事创作平台。

## 面向玩家的功能

- 在浏览器中进行自由文本游玩
- 基于 WebSocket 的实时更新
- 共享世界状态的多人会话
- 通过会话码加入已有房间
- 支持存档和读档
- 支持刷新页面后重连
- 浏览器端导出消息历史
- 玩家客户端内置中英文界面文本

## 面向作者的功能

- 基于 YAML 的故事编写
- 支持单文件和 `includes` 多文件故事
- 支持节点、动作、触发器、物品、角色、表单和变量
- 通过 `tools/compile_connections.py` 编译连接图谱
- 通过 `scripts/validate_story_yaml.py` 校验故事
- 在 `/editor` 提供可视化故事编辑器
- 编辑器保存时自动保留版本备份

## 引擎能力

- 由 LLM 驱动的 Architect 运行时
- 支持 OpenAI 兼容接口、Ollama 和 mock 模式
- 支持 Lua 派生变量和脚本钩子
- 支持状态栏显示配置
- 多人故事中同时支持共享状态和每个玩家的独立状态

## 下一步阅读

- 想体验游戏：看 [游玩故事](playing-stories.md)
- 想创作内容：看 [编写故事](writing-stories.md)
- 想用可视化方式创作：看 [编辑器总览](editor/README.md)
