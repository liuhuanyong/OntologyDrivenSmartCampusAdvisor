# Technical Documentation

> The Agent maintains this document after verified problem resolution or reusable technical changes. Record current facts, not investigation guesses or raw logs.

## Run and Operate

- 在 `OntologyDrivenSmartCampusAdvisor/` 目录执行 `python3 server.py`，默认监听 `8772`。
- Dashboard 地址为 `/dashboard/campus` 和 `/dashboard/procurement`。
- 图谱健康检查：`curl -s http://127.0.0.1:8772/api/campus/graph`。

## Architecture and Modules

- `ReusableHTTPServer` 为每个 HTTP 请求创建守护线程，避免 SSE 长连接阻塞图谱等其他请求。
- 每个 `/api/<scenario>/ask/stream` 请求在线程内以 `asyncio.run` 驱动对应 AgentScope 异步事件流，请求结束后发送 `done` 事件并关闭连接。

## Configuration and External Dependencies

- AgentScope 流式聊天需要根目录 `.env` 中配置 `DEEPSEEK_API_KEY`。

## Interfaces and Data

- `/api/<scenario>/ask/stream` 在 AgentScope Tool 完成后发送 `KGTraceEvent`。`data` 固定包含 `schema_version=1`、`scenario`、`question`、`tool_call_id`、`tool_name`、`tool_input`、`intent`、`status`、`kg_answer`、`rule_flow`、`reasoning`、`answer_nodes`、`subgraph`。
- Tool 返回单个 JSON `TextBlock`，其中 `kg_answer` 供模型回答，`kg_trace` 供 SSE、Dashboard 和 Eval 使用。Dashboard 不从模型正文解析推理证据。
- Campus 提供 `campus_reason` Typed Tool 和 `campus_graph_query` 通用只读 Tool；通用查询最多返回 100 条。Procurement 保留业务 Typed Tools。

## Troubleshooting

### Dashboard 图谱无数据且聊天不能连续进行

- Environment: 本地 `python3 server.py`，访问 `/dashboard/<scenario>`。
- Cause: Dashboard 初始化调用了已隐藏面板的 DOM，异常中断后续图谱加载；统计字段与接口不一致；单线程 HTTPServer 会被 SSE 长连接占用，额外子进程方案又从错误目录导入场景模块。
- Resolution: 可选面板渲染在 DOM 缺失时直接返回；Dashboard 使用图谱接口的 `entities/relations` 字段和路径场景名；服务使用 `ThreadingMixIn`，Agent 异步流直接在请求线程中执行。
- Verification: Campus 页面显示 70 个实体、271 条关系；Procurement 页面显示 97 个实体、120 条关系，均生成图谱 Canvas 且无浏览器错误。SSE 处理中并发图谱请求耗时 0.009 秒，连续两次 Campus 聊天均收到文本事件和 `done`。
- Related task, files, or commit: ODSA-001；`server.py`、`static/dashboard.html`。

### 新一轮流式回答覆盖上一轮内容

- Environment: Dashboard 连续进行多轮 SSE 聊天。
- Cause: `doAsk` 每次收到内容都查找页面中最后一个助手气泡；新一轮尚未创建气泡时，该节点仍属于上一轮。
- Resolution: 每轮请求创建并持有自己的局部 `responseBubble`，所有文本和工具事件只更新该节点；生成期间禁用发送按钮，结束或失败后恢复。
- Verification: 在真实 Campus Dashboard 依次询问 Alice、Bob、Eve，得到 3 个独立助手气泡；后续轮次完成后，前两轮文本逐字保持不变。
- Related task, files, or commit: ODSA-002；`static/dashboard.html`。

### Tool 报错 `does not implement __call__` 且计划/证据面板为空

- Environment: AgentScope ReActAgent 流式调用 Campus 或 Procurement Tool。
- Cause: 场景 Tool 只实现了旧的 `call` 方法，当前 AgentScope 通过 `__call__` 执行；同时 SSE 只透传模型文本，Dashboard 无法获得结构化 KG 计划和证据。
- Resolution: Tool 基类实现 `__call__` 并返回统一 JSON；服务端按 `tool_call_id` 缓冲 Tool 结果并发送 `KGTraceEvent`；Dashboard 按调用顺序聚合 `rule_flow`、`reasoning` 和推理子图。
- Verification: Campus 规则推理、教授实体查询和 Procurement 货源推荐均产生非空 Trace；写 Tool 单次执行测试通过；未调用 Tool 时面板显示明确失败提示。
- Related task, files, or commit: ODSA-003；`scenarios/*/agentscope_agent.py`、`static/dashboard.html`、`test_kg_tools.py`。

## Technical Decisions

- LLM 负责选择 Tool 和填写业务参数；KG 负责确定性事实、规则执行和证据链；最终回答必须以 Tool 结果为事实边界。
- 同一轮多个 `KGTraceEvent` 按 `tool_call_id` 和到达顺序聚合。当前只提供稳定 Trace 契约，不持久化 Eval 数据，也不记录模型隐藏思维链。
