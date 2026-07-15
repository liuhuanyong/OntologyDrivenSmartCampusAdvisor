# Smart Campus Course & Career Advisor

基于知识图谱的智能校园课程与职业规划顾问。通过本体建模 + 规则推理 + 自然语言问答，为学生提供选课建议、职业规划、技能缺口分析等服务，并完整可视化每一步推理路径。

纯 Python 实现，**零第三方依赖**（前端仅使用 vis-network CDN）。

## 目录

- [架构总览](#架构总览)
- [本体模型](#本体模型)
- [推理规则](#推理规则)
- [运作机制](#运作机制)
- [快速开始](#快速开始)
- [API 接口](#api-接口)
- [项目结构](#项目结构)
- [不足与建议](#不足与建议)

---

## 架构总览

项目采用严格的三层架构，自底向上分层加载：

| 层级 | 文件 | 职责 |
|------|------|------|
| Layer 1 | [ontology.py](ontology.py) / [knowledge_base.py](knowledge_base.py) | 本体定义 (TBox) + 实例数据 (ABox) + 知识图谱底座 |
| Layer 2 | [rules.py](rules.py) | 业务推理规则定义 + JSON 落盘存储 + 正向链式推理引擎 |
| Layer 3 | [advisor.py](advisor.py) / [main.py](main.py) / [server.py](server.py) | 自然语言问答路由 + 动作入口 + Web 服务 |

数据流自底向上单向流动：底层 KG 不感知上层规则，规则不感知上层问答路由，层间只通过明确接口耦合。

---

## 本体模型

### 实体类型 (7 类)

| 类型 | 属性 | 颜色 |
|------|------|------|
| Department | code, name | #6366f1 |
| Major | code, name, degree | #8b5cf6 |
| Professor | id, name, title, research_area | #ec4899 |
| Course | code, title, credits, difficulty, semester | #f59e0b |
| Skill | name, category | #10b981 |
| Student | id, name, grade, gpa | #3b82f6 |
| Career | name, field, avg_salary, growth_rate | #ef4444 |

### 关系类型 (14 类)

- **组织结构**：`offered_by` / `belongs_to` / `enrolled_in` / `major_in_dept`
- **课程教学**：`taught_by` / `teaches` / `prerequisite_of` / `teaches_skill`
- **专业职业**：`requires_course` / `leads_to` / `requires_skill`
- **学生学习**：`takes`(含 grade/status 边属性) / `has_skill`(含 level 边属性) / `targets_career`
- **派生关系**（推理生成）：`eligible_for`(含 match_rate 边属性)

### 实例规模

6 院系 · 8 专业 · 12 教授 · 18 课程 · 12 技能 · 6 职业 · 8 学生，含多级先修链、技能等级、进行中/已通过课程状态等真实场景数据。

---

## 推理规则

共 8 条规则，分两类：

| 规则 | 类型 | 优先级 | 说明 |
|------|------|--------|------|
| R1_prerequisite_satisfied | query | 10 | 检查课程先修结构完整性（目录级） |
| R2_can_take_course | query | 20 | 判断学生是否满足某门课的全部先修 |
| R3_recommend_next_courses | query | 30 | 推荐下一批可修课程（先修满足且未修过） |
| R4_skill_gap | query | 40 | 目标职业所需技能与学生已有技能的缺口 |
| R5_eligible_careers | query | 50 | 基于专业流向 + 技能匹配率（≥60%）推荐职业 |
| R6_major_completion | query | 60 | 专业必修课完成进度 |
| R7_recommend_electives_for_gap | query | 70 | 针对缺口推荐可补缺的选修课（内部复用 R4 + R2） |
| M1_materialize_eligible_for | materialize | 5 | 把技能匹配达标的 student→career 物化为 `eligible_for` |

每条规则内部通过 `kg.mark_hop()` 标注推理跳转、`kg.mark_focus()` 标记关注节点，这些 trace 数据驱动前端逐步高亮图谱。

---

## 运作机制

### 1. 系统启动流程

```
build_knowledge_base()   # 构建本体实例底座 (ABox)
        ↓
RuleEngine(kg)           # 绑定推理引擎
        ↓
build_default_rules()    # 注册 8 条默认规则
        ↓
dump_rules_json()        # 规则序列化落盘 rules_store.json
        ↓
forward_chain()          # 正向链式：执行 M1 物化 eligible_for
        ↓
serve_forever()          # Web 服务就绪
```

### 2. 问答处理管线（8 个阶段）

用户提问进入 [advisor.py](advisor.py) 的 `ask()` 后，依次经过：

**阶段 1 · NLU 意图识别**
基于 `INTENT_KEYWORDS` 关键词词典匹配 5 种意图：
- `recommend_courses`（选什么课/下学期/该修什么…）
- `career_advice`（适合什么/职业方向/就业…）
- `skill_gap`（还差什么/怎么补/想成为…）
- `check_course`（能选/能不能选/可以直接…）
- `student_profile`（画像/完整/概况…）

**阶段 2 · 学生实体解析**
遍历 Student 实体，用 `name` 做子串匹配；未命中时回退到第一个学生。

**阶段 3 · 职业/课程实体解析**
- 职业：name 子串匹配
- 课程：先正则 `[A-Z]{2,4}\d{3}` 匹配课程代码（如 ML401），再按课程名匹配

**阶段 4 · 规则编排**
查 `RULE_FLOWS` 表，根据意图确定要执行的规则链及依赖关系。例如 `skill_gap` 意图编排为 `R4 → R7`，其中 R7 内部还依赖 R2。

**阶段 5 · 参数补全**
某些意图需要额外查图谱补参数，例如 `skill_gap` 若问题中未指定职业，则查 `student.targets_career` 取第一个目标。

**阶段 6 · 执行规则链（核心）**
对每条规则调用 `engine.query_traced()`：
```
kg.start_trace()           # 开启追踪
rule.action(kg, ...)       # 规则在 KG 上图游走 + mark_hop
trace = kg.stop_trace()    # 关闭追踪，返回 walks/hops/involved
```
规则执行时通过 `kg.out()` / `kg.inn()` 做图游走，每次游走自动记入 `walks`；规则内显式调 `mark_hop()` 标注带 reason 的推理跳转。

**阶段 7 · 子图提取**
汇总所有涉及实体 + 各实体 1 跳邻居，调 `kg.subgraph_data()` 导出 nodes/edges 供前端可视化。

**阶段 8 · 答案生成**
从 reasoning blocks 的 focus 标签中提取标注"结论"的答案节点，汇总各规则结论格式化为自然语言答案。

### 3. 正向链式推理（物化）

启动时执行一次 `forward_chain()`，遍历所有 `kind == "materialize"` 的规则：
- `M1_materialize_eligible_for`：对每个学生调用 R5，匹配率 ≥60% 的职业写成 `eligible_for` 边物化进 KG，供后续查询直接读取。

### 4. 推理追踪机制

[ontology.py](ontology.py) 的 `KnowledgeGraph` 内置 trace 子系统：

| 方法 | 作用 |
|------|------|
| `start_trace()` / `stop_trace()` | 开启/结束一次追踪会话 |
| `_record_walk()` | 自动记录每次 `out()`/`inn()` 图游走 |
| `mark_hop(s, p, o, reason)` | 显式标注带原因的推理跳转 |
| `mark_focus(eid, note)` | 标记推理关注的起点/终点/结论节点 |

追踪数据结构：
```json
{
  "walks": [{"subject": "...", "predicate": "...", "object": "...", "direction": "out"}],
  "hops": [{"subject": "...", "predicate": "...", "object": "...", "reason": "..."}],
  "involved_entities": ["student:alice", "course:ml401", ...],
  "involved_relations": [["student:alice", "takes", "course:cs101"], ...]
}
```

### 5. 前端可视化

[static/index.html](static/index.html) 使用 vis-network 渲染知识图谱，左侧为图谱，右侧为问答区 + 数据浏览 Tab（实体/关系/规则）。每次提问后，前端根据返回的 `subgraph` 高亮涉及节点、根据 `pipeline` 展示 8 阶段执行流程、根据 `reasoning` 展示每条规则的 hop 序列。

---

## 快速开始

环境要求：Python 3.10+

### 1. 命令行演示

```bash
python main.py
```

依次演示三层架构：构建本体 → 注册规则并落盘 → 正向链式推理 → 6 个 Q&A 示例（选课推荐/职业适配/技能缺口/选课检查/补齐方案/学生画像）。

### 2. Web 界面

```bash
python server.py
```

浏览器访问 `http://localhost:8772`，支持：
- 自然语言提问（含 20 个示例问题）
- 知识图谱可视化与子图高亮
- 推理路径逐步追踪展示
- 实体 / 关系 / 规则浏览

### 3. 示例问题

```
Alice 下学期该修什么课？
Eve 适合什么职业方向？
Carol 想成为数据科学家，还差什么？
Bob 能选 ML401 吗？
给我看看 Grace 的完整画像
```

---

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 问答界面 |
| GET | `/api/graph` | 完整知识图谱数据 |
| GET | `/api/rules` | 规则列表（含中文含义） |
| GET | `/api/stats` | 图谱统计信息 |
| GET | `/api/entities` | 所有实体（按类型分组，含属性） |
| GET | `/api/relations` | 所有关系（含 schema + 实例三元组） |
| GET | `/api/examples` | 20 个示例问题 |
| POST | `/api/ask` | 问答接口，body: `{"question": "..."}` |

`/api/ask` 返回结构包含：`question` / `intent` / `student` / `answer` / `pipeline`(8 阶段执行流程) / `reasoning`(每条规则的 hop 序列) / `rule_flow` / `answer_nodes` / `involved` / `subgraph`(nodes+edges)。

---

## 项目结构

```
smart_campus_advisor/
├── ontology.py          # 本体定义 + 知识图谱底座 (实体/关系/trace/子图)
├── knowledge_base.py    # 实例数据 (ABox) 硬编码构建
├── rules.py             # 8 条规则定义 + RuleEngine + JSON 落盘
├── advisor.py           # NLU 路由 + 8 阶段问答管线 + 答案生成
├── main.py              # 命令行演示入口
├── server.py            # Web 服务器 (http.server, 端口 8772)
├── rules_store.json     # 规则 JSON 落盘
├── report.html          # 项目设计报告 (静态 HTML)
└── static/
    └── index.html       # Web 前端 (vis-network 可视化)
```

---

## 不足与建议

### 不足

**1. NLU 过于简陋**
意图识别和实体解析全部基于关键词/子串匹配，无法处理同义词、否定句、复杂问法（如"除了 ML401 还能选什么"）、多意图复合问题；课程代码正则 `[A-Z]{2,4}\d{3}` 会误匹配无关文本。

**2. 数据硬编码无持久化**
全部实例数据写死在 [knowledge_base.py](knowledge_base.py)，无法运行时增删改学生/课程/选课记录；重启后所有变更丢失，`rules_store.json` 仅落盘规则定义而非图谱数据。

**3. 规则引擎能力有限**
- 规则 `pattern` 字段只是描述性字符串，无可执行语义，无法做模式匹配反查
- `forward_chain()` 只执行一轮，不支持迭代到不动点
- 无冲突解决策略、规则互斥/优先级冲突处理
- R7 复用 R4/R2 是代码级硬调用，非引擎级编排

**4. 推理模型过于简化**
- 技能匹配率仅用 `|R∩S| / |R|`，未考虑 `has_skill` 的 level 等级
- 课程推荐只看先修满足性，不考虑学期开课、容量、学生工作量、GPA 门槛
- 职业推荐阈值 60% 硬编码，无校准

**5. 工程化缺失**
- Web 服务器用单线程 `http.server`，无并发能力，不适合生产
- 无用户认证、多用户会话、权限控制
- 无单元测试、无错误监控
- 无日志系统（`log_message` 被静默）
- KG 全局单例，请求间状态共享存在风险

**6. 可扩展性不足**
- 实体/关系 schema 在代码中硬编码，新增类型需改源码
- 规则只能用 Python 函数定义，非业务人员无法维护
- 前端为单文件 HTML，无组件化，维护困难

### 建议

**短期（低改造成本）**

1. **NLU 升级**：引入jieba 分词 + 同义词扩展，或直接接入 LLM 做意图识别和槽位抽取
2. **数据持久化**：图谱数据落 SQLite/JSON 文件，提供 CRUD API；启动时加载，变更时写回
3. **匹配率改进**：把 `has_skill.level` 纳入计算（如加权或门槛过滤）
4. **Web 框架**：迁移到 FastAPI/Flask，获得异步、中间件、自动文档
5. **测试覆盖**：为 8 条规则和 NLU 路由补单元测试

**中期**

6. **规则引擎增强**：
   - 设计可执行 DSL 或用 Datalog，让 pattern 真正可匹配
   - `forward_chain` 迭代到不动点
   - 引入规则优先级冲突解决
7. **课程推荐约束**：加入学期开课、容量上限、工作量上限、GPA 门槛
8. **用户系统**：学生登录、会话隔离、个人推理历史持久化
9. **图数据库**：迁移到 Neo4j，获得声明式查询（Cypher）和原生图遍历能力

**长期**

10. **多轮对话**：支持上下文追问（"那 Bob 呢"、"换成数据科学家呢"）
11. **规则可视化编辑**：前端提供规则编辑器，业务人员自助维护
12. **推荐解释增强**：引入因果推理，输出"为什么推荐 A 而不是 B"
13. **数据回流**：记录真实选课/就业结果，反哺规则阈值校准
14. **部署改造**：容器化 + 反向代理 + 鉴权网关，支持多实例水平扩展
