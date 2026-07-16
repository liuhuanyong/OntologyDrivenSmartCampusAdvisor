# System Function Documentation

> The Agent maintains this document after verified scenario delivery. Describe what the system currently does, not unimplemented ideas.

## Users and Roles

Record system users and their goals.

## Capability Map

- Campus Dashboard：规则型选课/职业推理、实体列表查询和实体一跳关系查询。
- Procurement Dashboard：PR、PO、交货和寻源业务 Tool 调用。
- 每次 KG Tool 调用会同步展示规则执行计划、推理证据和精简推理子图。

## User Scenarios

### 基于 KG Tool 的可解释问答

- User: Campus 或 Procurement Dashboard 用户。
- Goal: 获得由知识图谱事实与规则支撑的模型回答，并查看可评测的执行计划和证据链。
- Preconditions: 服务已配置 `DEEPSEEK_API_KEY`，对应场景知识图谱已加载。
- Flow: 用户提问 → LLM 选择 Typed Tool 并填写参数 → KG 执行 → LLM 根据 KG 结果回答 → Dashboard 展示 Trace。
- Result: 聊天显示自然语言回答；计划、证据和推理路径面板显示本轮全部 KG Tool 结果。
- Exceptions and boundaries: 通用 Campus 图查询最多返回 100 条；模型未调用 KG Tool 时面板明确提示，不把普通聊天伪装成 KG 推理。
- UI, API, or command entry point: `/dashboard/campus`、`/dashboard/procurement`、`/api/<scenario>/ask/stream`。
- Related task, files, or commit: ODSA-003。

## Business Rules

Record rules reused across scenarios or affecting business decisions.
