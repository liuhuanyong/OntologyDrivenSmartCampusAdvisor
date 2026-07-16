# Project Plan

## In Progress

## Done

[ODSA-003][problem] KG Tool 推理链未进入 Dashboard 面板

Goal or symptom: AgentScope Tool 未实现当前版本要求的 `__call__`，KG 推理没有执行；SSE 也未输出结构化规则计划和证据，导致执行计划与论证面板为空。
Acceptance scenarios:
- [x] Given Campus 规则问题，when LLM 调用 Typed KG Tool，then Tool 返回结构化 Trace，最终回答基于 KG，两个面板均有数据。
- [x] Given “有哪些教授”，when LLM 调用通用只读图查询，then 返回实体查询计划与证据，数量最多 100 条。
- [x] Given Procurement 查询或写操作，when LLM 动态组装参数调用 Tool，then Trace 可评测且写操作只执行一次。
- [x] Given 一轮调用多个 Tool，when SSE 逐个返回 Trace，then Dashboard 按 tool_call_id 和调用顺序聚合。
- [x] Given 模型未调用 KG Tool，when 回答结束，then 两个面板明确显示本轮未调用 KG Tool。
- [x] Given 非流式 `/api/<scenario>/ask`，when 原有客户端调用，then 返回结构保持兼容。
Acceptance confirmed: 2026-07-16 用户要求实施已确认计划。
Result: 修复 Tool 协议；增加 Campus Typed/通用图 Tool；统一 KG Trace 并接入 SSE、计划、证据和推理子图。真实模型与浏览器均已验证。
Documents: `SPEC.md` 的 Interfaces and Data、Technical Decisions；`SYSTEM.md` 的 Capability Map、User Scenarios。
Related files or commit: `scenarios/*/agentscope_agent.py`、`scenarios/procurement/advisor.py`、`static/dashboard.html`、`test_kg_tools.py`。

[ODSA-002][problem] 新一轮流式回答覆盖上一轮聊天内容

Goal or symptom: 连续聊天时，新一轮响应错误复用上一轮助手气泡，导致历史答案被覆盖。
Acceptance scenarios:
- [x] Given 已完成两轮聊天，when 发起第三轮并接收流式内容，then 每轮均有独立助手气泡且顺序正确。
- [x] Given 新一轮正在流式输出，when 内容持续到达，then 只更新本轮气泡，历史消息保持不变。
- [x] Given 一轮请求失败，when 再次发送消息，then 历史仍保留且下一轮可正常进行。
Acceptance confirmed: 2026-07-16 用户已批准。
Result: 每轮请求改为持有独立的局部助手气泡；生成期间阻止重复发送并在成功或失败后恢复。真实页面三轮聊天历史均保留。
Documents: `SPEC.md` 的 Troubleshooting。
Related files or commit: `static/dashboard.html`。

[ODSA-001][problem] 启动后图谱无数据且聊天不能连续进行

Goal or symptom: Dashboard 启动后图谱不可见，流式聊天一次后无法继续；确认是否由服务线程模型导致并修复共同根因。
Acceptance scenarios:
- [x] Given 服务启动，when 打开 Campus 或 Procurement Dashboard，then 图谱接口返回非空节点和边且页面可渲染。
- [x] Given 同一场景，when 连续发送至少两次消息，then 两次响应均正常结束且后续请求不被阻塞。
- [x] Given 修复完成，when 执行接口级回归检查，then 原有非流式图谱与问答接口仍可用。
Acceptance confirmed: 2026-07-16 用户已批准。
Result: 修复 Dashboard 初始化与场景/统计字段映射；SSE 改为在线程化 HTTP 请求内直接运行异步事件流。两场景图谱页面和连续两次聊天均已验证。
Documents: `SPEC.md` 的 Run and Operate、Architecture and Modules、Configuration and External Dependencies、Troubleshooting。
Related files or commit: `server.py`、`static/dashboard.html`。

## Card

```markdown
[ID][problem|scenario] Title

Goal or symptom:
Acceptance scenarios:
- [ ] Given ... when ... then ...
Acceptance confirmed:
Result:
Documents:
Related files or commit:
```
