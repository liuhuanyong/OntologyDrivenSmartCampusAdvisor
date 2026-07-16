# Project Plan

## In Progress

## Done

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
