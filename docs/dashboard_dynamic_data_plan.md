# 仪表盘动态数据改造 — 任务清单与文档

## 概述

当前 `dashboard.html` 使用静态 `MOCK_DATA` 模拟数据,需改造为调用后端真实推理引擎的动态数据。
改造原则:**不改 UI 结构和 render 函数签名,只替换数据来源**。

---

## 一、现状分析

### 1.1 静态数据结构 (MOCK_DATA)

```javascript
const MOCK_DATA = {
  campus: {
    question: 'Alice 下学期该修什么课？',
    pipeline: [...],   // 5个阶段的执行状态
    hops: [...],       // 推理路径 hops
    plan: [...],       // Agent 执行计划
    chat: [...],        // 对话历史
    evidence: [...],    // 证据/论证
    graphNodes: [...],  // 图谱节点
    graphEdges: [...],  // 图谱边
  },
  warehouse: { ... },
  procurement: { ... },
};
```

### 1.2 五个面板对应的 render 函数

| 面板 | render 函数 | 入参类型 |
|------|------------|---------|
| 认知流程管道 | `renderPipeline(pipeline)` | `PipelineStep[]` |
| 本体推理路径图谱 | `renderFullGraph()` / `renderSubGraph(mock)` | `GraphData` |
| Agent 执行计划验证 | `renderPlan(plan)` | `PlanStep[]` |
| 执行模拟对话 | `appendChat(msg)` | `ChatMessage` |
| 证据/论证面板 | `renderEvidence(evidence)` | `EvidenceBlock[]` |

### 1.3 现有后端 API (已可用)

| API | 方法 | 返回内容 |
|-----|------|---------|
| `/api/<scenario>/ask` | POST | 完整推理结果(答案、规则、hops、pipeline) |
| `/api/<scenario>/graph` | GET | 全量图谱数据(nodes + edges) |
| `/api/<scenario>/stats` | GET | 统计信息(实体数、关系数、规则数) |
| `/api/<scenario>/entities` | GET | 实体列表 |
| `/api/<scenario>/rules` | GET | 规则列表 |

---

## 二、目标数据结构

### 2.1 `doAsk()` API 响应 → 映射到面板数据

后端 `/api/<scenario>/ask` 返回结构(需确认/扩展):

```json
{
  "scenario": "campus",
  "scenario_title": "Smart Campus · 课程职业规划顾问",
  "question": "Alice 下学期该修什么课？",
  "answer": "根据学业进度,Alice 接下来可以选修: CS305 计算机网络、ML301 机器学习、STAT302 高级统计",
  "answer_node_ids": ["course:cs305", "course:ml301", "course:stat302"],
  "pipeline": [
    { "stage": "用户请求解析", "icon": "💬", "status": "done", "duration": "8ms", "detail": "提取到学生: Alice" },
    { "stage": "意图识别", "icon": "🧠", "status": "done", "duration": "12ms", "detail": "意图: recommend_courses" },
    ...
  ],
  "reasoning": [
    {
      "rule": "R6_major_completion",
      "ruleLabel": "R6 专业完成度",
      "kind": "query",
      "conclusion": "Alice 已完成 83% (5/6) 专业必修课",
      "facts": [
        { "from": "Alice", "pred": "已通过", "to": "CS101 程序设计基础", "reason": "成绩 A", "status": "pass" },
        ...
      ],
      "hops": [
        { "from": "student:alice", "fromLabel": "Alice", "predicate": "takes", "to": "course:cs101", "toLabel": "CS101", "reason": "已通过,成绩A", "highlight": false, "passed": true, "answer": false },
        ...
      ]
    },
    {
      "rule": "R3_recommend_next_courses",
      "ruleLabel": "R3 推荐课程",
      "conclusion": "推荐 CS305, ML301, STAT302",
      "facts": [...],
      "hops": [...]
    }
  ],
  "plan": [
    { "step": 1, "action": "R6_major_completion", "desc": "计算专业必修课完成度", "preconditions": [...], "postconditions": [...], "status": "pass" },
    { "step": 2, "action": "R3_recommend_next_courses", "desc": "推荐下一批可修课程", "preconditions": [...], "postconditions": [...], "status": "pass" }
  ],
  "subgraph": {
    "nodes": [...],
    "edges": [...]
  }
}
```

### 2.2 各面板数据映射关系

```
API 响应
  ├── pipeline[]          → renderPipeline()
  ├── reasoning[].hops[]  → 聚合 allHops, renderEvidence()
  ├── reasoning[].facts[] → renderEvidence()
  ├── plan[]              → renderPlan()
  ├── answer              → appendChat({ role: 'assistant', content })
  ├── subgraph            → renderSubGraph()
  └── answer_node_ids[]   → highlight answer nodes in graph
```

---

## 三、任务清单

### Phase 1: 确认/扩展后端 API 响应结构

- [ ] **T1.1** 检查 `advisor.py` 中 `ask()` 方法的返回结构,确认是否包含 `pipeline`、`reasoning`/`hops`、`plan`、`subgraph` 字段
- [ ] **T1.2** 如缺少字段,在 `advisor.py` 的 `ask()` 返回值中补充
- [ ] **T1.3** 如 `reasoning` 中缺少 `hops`,从 `rule_engine.py` 的执行 trace 中提取每步推理的 (from, predicate, to) 三元组
- [ ] **T1.4** 确认 `subgraph` 字段:返回本次推理涉及的所有节点和边(用于 Panel 2 推理路径图谱)

### Phase 2: 前端数据映射层

- [ ] **T2.1** 创建 `dashboard/static/js/dashboard-api.js` (或内联在 `dashboard.html` 底部),实现 `fetchDashboardData(scenario, question)` 函数,封装 POST `/api/<scenario>/ask`
- [ ] **T2.2** 实现 `mapApiResponseToPanels(data)` 映射函数,将 API 响应转换为各 render 函数的入参格式:

  ```javascript
  function mapApiResponseToPanels(data) {
    return {
      pipeline:    data.pipeline,
      plan:        data.plan,
      evidence:    data.reasoning.map(r => ({
        rule: r.rule,
        ruleLabel: r.ruleLabel,
        conclusion: r.conclusion,
        facts: r.facts,
      })),
      hops:        data.reasoning.flatMap(r => r.hops || []),
      subgraph:    data.subgraph,
      answer:      data.answer,
    };
  }
  ```

- [ ] **T2.3** 确认/扩展 `PipelineStep`、`PlanStep`、`EvidenceBlock`、`HopItem`、`ChatMessage` 的 TypeScript/JSDoc 类型定义(写在注释中即可)

### Phase 3: 重构 `doAsk()` 函数

- [ ] **T3.1** 修改 `doAsk()` 函数,替换静态 `MOCK_DATA` 调用为:

  ```javascript
  async function doAsk() {
    const question = document.getElementById('questionInput').value.trim();
    if (!question) return;

    appendChat({ role: 'user', content: question });
    appendChat({ role: 'system', content: '正在分析用户意图并执行推理...' });

    try {
      const resp = await fetch(`/api/${currentScenario}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      });
      const data = await resp.json();
      const panels = mapApiResponseToPanels(data);

      // 更新所有面板
      renderPipeline(panels.pipeline);
      renderPlan(panels.plan);
      renderEvidence(panels.evidence);

      // 对话历史
      appendChat({ role: 'assistant', content: panels.answer });

      // 图谱切换到推理路径模式
      allHops = panels.hops;
      currentHopIndex = -1;
      renderSubGraphDynamic(panels.subgraph, panels.hops);
      showSubGraph();

    } catch (err) {
      appendChat({ role: 'system', content: `推理出错: ${err.message}` });
    }
  }
  ```

- [ ] **T3.2** 实现 `renderSubGraphDynamic(subgraph, hops)` 函数 — 接收 API 返回的 `subgraph` 数据,渲染 vis-network,高亮 `answer_node_ids` 对应的节点

### Phase 4: 图谱增强

- [ ] **T4.1** 在 `renderSubGraphDynamic` 中高亮 answer 节点(橙色边框 + 特殊 shape)
- [ ] **T4.2** 支持 hop 导航:点击"上一步/下一步"时,动态高亮当前 hop 对应的边和节点
- [ ] **T4.3** 在 `showFullGraph` 中,answer 节点做持久高亮

### Phase 5: 错误处理与边界情况

- [ ] **T5.1** 网络错误:显示 "推理服务暂不可用" 提示
- [ ] **T5.2** 空结果:各面板显示"暂无数据"占位
- [ ] **T5.3** 推理超时:后端设置超时(如 10s),前端显示加载进度
- [ ] **T5.4** 切换场景后清空图谱状态,防止旧数据残留

### Phase 6: 优化与增强(可选)

- [ ] **T6.1** 增量图谱动画:从全图逐步"生长"出推理子图(而不是一次性渲染子图)
- [ ] **T6.2** Pipeline 阶段实时更新(非等到全部完成才展示)
- [ ] **T6.3** 对话流式输出(后端流式返回,前端逐字展示答案)
- [ ] **T6.4** 历史会话:将每次问答存入 `sessionStorage`,支持回退

---

## 四、关键改造点速查

```
┌─────────────────────────────────────────────────────────────┐
│  改造文件                                                     │
├─────────────────────────────────────────────────────────────┤
│  1. backend/advisor.py         → 扩展 ask() 返回字段        │
│  2. backend/rule_engine.py     → 暴露 hops trace           │
│  3. static/dashboard.html      → 重构 doAsk()               │
│  4. static/js/dashboard-api.js → 新增 API 封装层(可选)      │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  不需要改动的部分                                              │
├─────────────────────────────────────────────────────────────┤
│  · renderPipeline() 函数签名和渲染逻辑                       │
│  · renderPlan() 函数签名和渲染逻辑                           │
│  · renderEvidence() 函数签名和渲染逻辑                       │
│  · appendChat() 函数                                         │
│  · 图谱 vis-network 初始化代码                               │
│  · 场景切换 switchScenario()                                 │
│  · 左侧栏拖拽 resize 逻辑                                    │
│  · Panel 1-5 的 HTML 结构和 CSS 样式                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 五、测试用例

改造完成后,需验证以下场景:

| 场景 | 输入 | 预期结果 |
|------|------|---------|
| Campus | Alice 下学期该修什么课？ | 5步pipeline全部完成,图谱高亮推荐课程节点 |
| Campus | Bob 适合什么职业方向？ | 推理路径展示职业匹配过程 |
| Warehouse | RM001 怎么安排入库？ | 仓位分配推理 hops 清晰展示 |
| Procurement | 帮我创建一个采购申请 | PR 创建 plan + 预算校验 evidence |
| 错误 | (网络断开) | 显示错误提示,面板保持占位状态 |
| 场景切换 | Campus → Warehouse | 面板清空,图谱重置,输入框可用 |

---

## 六、里程碑

| 里程碑 | 内容 | 依赖 |
|--------|------|------|
| **M1** 核心链路通 | T1.1+T1.2+T2.1+T2.2+T3.1+T3.2 | Phase 1, 2, 3 |
| **M2** 图谱联动 | T4.1+T4.2 (hop导航高亮) | M1 |
| **M3** 鲁棒性 | T5.1~T5.4 (错误处理) | M1 |
| **M4** 增强体验 | T6.1~T6.4 (可选优化) | M2 |
