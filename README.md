# miniclaude

这是从 `agent-studio` 提炼出来的“Claude 附件专用”精简仓库。

目标只有一个: 只保留帮助模型理解项目后端主链的必要文件，尽量压缩上下文体积。

## 保留内容

- `backend/adapters`: LLM provider adapter
- `backend/api`: 当前实际挂载的 API 主入口与核心路由
- `backend/cli_support`: CLI 会话与输出支持
- `backend/common`: 错误、通用类型、工具函数
- `backend/config`: 运行时配置模型与安全占位配置
- `backend/core/permissions`
- `backend/core/s01_agent_loop`
- `backend/core/s02_tools`，但已移除非核心扩展工具
- `backend/core/s04_sub_agents`
- `backend/core/s06_context_compression`
- `backend/schemas`
- `backend/storage`
- `agents/builtin`
- `.env.example`、`AGENTS.md`、`pyproject.toml`

## 故意移除

- `frontend`、`electron`、`docs`、`deploy`、`.github`
- 所有测试、缓存、临时目录、数据库、二进制、报告、构建产物
- 非核心扩展: `proxy_*`、`x_*`、`youtube_*`
- 未接入当前主流程的模块: `s03`、`s05`、`s07-s12`
- 所有真实密钥和本机私有配置

## 说明

- `backend/config/providers.json` 和 `backend/config/mcp_servers.json` 已清空成安全占位版本
- 这个仓库优先服务“给 Claude 看代码上下文”，不是完整发布仓库
- 如果后续需要前端、代理能力或完整测试，再回原始仓库取
