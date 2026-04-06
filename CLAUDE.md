# Claude Notes

- 使用中文回复。
- 把这个仓库视为 `Agent Studio` 的后端核心快照，不是完整工程。
- 优先阅读 `README.md` 和 `AGENTS.md`。
- 修改代码时遵守这些约束:
  - Python 3.11+，尽量完整 type hints
  - 类型定义优先 Pydantic v2 `BaseModel`
  - `backend/core/` 保持纯 Python + asyncio，不直接依赖 FastAPI
  - `backend/core/` 不直接调 LLM API，统一通过 adapter
  - 工具通过 `ToolRegistry` 注册，不要硬编码
  - 模块间通过各子模块 `__init__.py` 暴露接口
- 这个仓库已经移除了前端、测试和非核心扩展，不要假设它们仍然存在。
