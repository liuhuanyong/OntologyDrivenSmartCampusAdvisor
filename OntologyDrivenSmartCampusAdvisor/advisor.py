"""
第 3 层：动作 / 操作入口 + 自然语言问答路由
=====================================================
用户输入自然语言 -> 解析意图 + 提取参数 -> 调用规则(带追踪)
-> 生成答案文本 + 完整推理路径(每一步hop) + 涉及子图

返回结构里 reasoning 是一个列表, 每项描述一次规则调用:
  {
    "rule": "R2_can_take_course",
    "rule_desc": "判断学生是否满足某门课的全部先修",
    "goal": "检查 Alice 能否选修 ML401",
    "hops": [
       {"subject":"student:alice","predicate":"takes","object":"course:cs101",
        "reason":"学生已通过 程序设计基础 (成绩 A)"},
       ...
    ],
    "focus": ["student:alice","course:ml401"],
    "conclusion": "先修未满足, 缺 CS201 / STAT201"
  }
"""
from __future__ import annotations

import re
from typing import Any

from ontology import KnowledgeGraph
from rules import RuleEngine, _label


# --------------------------------------------------------------------------- #
# 实体解析辅助
# --------------------------------------------------------------------------- #
def _resolve_student(kg: KnowledgeGraph, text: str) -> str | None:
    for s in kg.list_entities("Student"):
        if s.attrs["name"].lower() in text.lower():
            return s.eid
    return None


def _resolve_career(kg: KnowledgeGraph, text: str) -> str | None:
    for c in kg.list_entities("Career"):
        if c.attrs["name"] in text:
            return c.eid
    # 模糊匹配
    for c in kg.list_entities("Career"):
        for kw in c.attrs["name"]:
            pass
    return None


def _resolve_course(kg: KnowledgeGraph, text: str) -> str | None:
    # 先按课程代码匹配 (如 CS101, ML401)
    m = re.search(r'[A-Z]{2,4}\d{3}', text.upper())
    if m:
        code = m.group()
        for c in kg.list_entities("Course"):
            if c.attrs.get("code", "").upper() == code:
                return c.eid
    # 按课程名匹配
    for c in kg.list_entities("Course"):
        if c.attrs.get("title", "") in text:
            return c.eid
    return None


def _students(kg: KnowledgeGraph) -> list[str]:
    return [s.attrs["name"] for s in kg.list_entities("Student")]


# --------------------------------------------------------------------------- #
# 推理路径聚合器：把规则执行产生的 trace 转换成可读的 hop 序列
# --------------------------------------------------------------------------- #
def _build_reasoning_block(kg: KnowledgeGraph, engine: RuleEngine,
                           rule_name: str, goal: str, conclusion: str,
                           traced_result: dict) -> dict:
    """把一次规则执行的 trace 整理成 reasoning 块。

    包含规则的完整定义(名称/描述/模式公式/类型/优先级)，以及
    本次执行的图游走 hops、关注节点 focus、结论。
    """
    trace = traced_result["trace"]
    rule = engine.rules.get(rule_name)
    hops, focus = [], []
    for h in trace["hops"]:
        item = {
            "from": h["subject"],
            "from_label": _label(kg, h["subject"]),
            "predicate": h["predicate"],
            "to": h["object"],
            "to_label": _label(kg, h["object"]),
            "reason": h["reason"],
        }
        if h["predicate"] == "__focus__":
            focus.append({"id": h["subject"], "note": h["reason"]})
        else:
            hops.append(item)
    return {
        "rule": rule_name,
        "rule_desc": rule.description if rule else _rule_desc(rule_name),
        "rule_pattern": rule.pattern if rule else "",
        "rule_kind": rule.kind if rule else "query",
        "rule_priority": rule.priority if rule else 0,
        "goal": goal,
        "hops": hops,
        "focus": focus,
        "conclusion": conclusion,
        "result": traced_result["result"],
    }


def _rule_desc(name: str) -> str:
    descs = {
        "R2_can_take_course": "判断学生是否满足某门课的全部先修",
        "R3_recommend_next_courses": "推荐下一批可修课程(先修满足且未修过)",
        "R4_skill_gap": "目标职业所需技能与学生已有技能的缺口",
        "R5_eligible_careers": "基于专业流向+技能匹配率推荐职业",
        "R6_major_completion": "专业必修课完成进度",
        "R7_recommend_electives_for_gap": "针对缺口推荐可补缺的选修课",
    }
    return descs.get(name, "")


# 规则的中文含义(给用户看的解释)
RULE_MEANINGS: dict[str, str] = {
    "R2_can_take_course": "查询学生已通过的所有课程(takes 出边)，再反向查找目标课程的所有先修课(prerequisite_of 入边)，逐一判断先修课是否都在已通过集合中。若全部满足则可选修，否则列出缺口。",
    "R3_recommend_next_courses": "遍历图谱中所有课程，对每门课取其先修课集合，若先修全部被该学生已通过且学生未修过此课，则推荐。按先修链深度排序。",
    "R4_skill_gap": "从目标职业出发查 requires_skill 得到所需技能集，从学生出发查 has_skill 得到已有技能集，二者做差集得到缺口，再为每个缺口技能反向查 teaches_skill 找能补齐的课程。",
    "R5_eligible_careers": "学生专业 leads_to 的职业 ∪ 学生 targets_career 的目标 = 候选职业集；对每个候选职业，用其 requires_skill 与学生 has_skill 求交集算匹配率，≥60% 视为可胜任。",
    "R6_major_completion": "学生 enrolled_in 的专业 requires_course 必修课集 ∩ 学生 takes(passed) 已通过集 = 已完成；完成率 = 已完成 / 必修总数。",
    "R7_recommend_electives_for_gap": "先调用 R4 得到技能缺口，对每个缺口技能反向查 teaches_skill 找课程，再调用 R2 检查该课程先修是否满足，满足则推荐为补缺选修。",
}

# 各意图的规则执行编排(展示规则之间的依赖与执行顺序)
RULE_FLOWS: dict[str, list[dict]] = {
    "recommend_courses": [
        {"rule": "R6_major_completion", "depends_on": [],
         "chinese": "先算专业必修课完成度，了解学生进度",
         "why": "了解学生当前进度，为后续推荐提供基线"},
        {"rule": "R3_recommend_next_courses", "depends_on": ["R6_major_completion"],
         "chinese": "再推荐下一批可修课程",
         "why": "在已知进度基础上，筛选先修已满足且未修过的课程"},
    ],
    "career_advice": [
        {"rule": "R5_eligible_careers", "depends_on": [],
         "chinese": "计算专业流向职业 + 目标职业的技能匹配率",
         "why": "综合学生专业和目标，给出可胜任职业列表"},
    ],
    "skill_gap": [
        {"rule": "R4_skill_gap", "depends_on": [],
         "chinese": "先分析目标职业的技能缺口",
         "why": "找出学生与目标职业的技能差距"},
        {"rule": "R7_recommend_electives_for_gap", "depends_on": ["R4_skill_gap", "R2_can_take_course"],
         "chinese": "再为缺口推荐可补齐的选修课",
         "why": "R7 内部会调用 R4(缺口) 和 R2(先修满足性) 来筛选可补缺课程"},
    ],
    "check_course": [
        {"rule": "R2_can_take_course", "depends_on": [],
         "chinese": "直接检查该课程的先修满足性",
         "why": "反向查 prerequisite_of 入边，逐一比对学生已通过课程"},
    ],
    "student_profile": [
        {"rule": "R6_major_completion", "depends_on": [],
         "chinese": "算专业必修课完成度",
         "why": "画像第一项: 学业进度"},
        {"rule": "R3_recommend_next_courses", "depends_on": ["R6_major_completion"],
         "chinese": "推荐可修课程",
         "why": "画像第二项: 下一步建议"},
        {"rule": "R5_eligible_careers", "depends_on": [],
         "chinese": "分析职业适配",
         "why": "画像第三项: 职业方向"},
    ],
}


def _extract_answer_nodes(reasoning: list[dict]) -> list[str]:
    """从 reasoning blocks 的 focus 标签里提取"结论/答案"节点。

    focus note 中包含"结论"字样的视为答案节点，去重保序。
    """
    seen = set()
    answer_nodes = []
    for rb in reasoning:
        for f in rb.get("focus", []):
            note = f.get("note", "")
            if ("结论" in note or "推理结论" in note) and f["id"] not in seen:
                answer_nodes.append(f["id"])
                seen.add(f["id"])
    return answer_nodes


# --------------------------------------------------------------------------- #
# 答案生成器：每个 action 返回 {answer, reasoning, involved}
# --------------------------------------------------------------------------- #
def answer_recommend_courses(kg: KnowledgeGraph, engine: RuleEngine,
                             student: str) -> dict:
    sname = kg.get_entity(student).attrs["name"]
    r6 = engine.query_traced("R6_major_completion", student=student)
    comp = r6["result"]
    r3 = engine.query_traced("R3_recommend_next_courses", student=student)
    recs = r3["result"]
    involved = (r6["trace"]["involved_entities"] |
                r3["trace"]["involved_entities"])

    lines = [f"【{sname}】的课程建议：",
             f"专业: {_label(kg, comp['major'])}  必修完成度: {comp['completion']*100:.0f}%"
             f"  (剩余 {len(comp['remaining'])} 门)"]
    if not recs:
        lines.append("目前没有满足先修条件的可修课程，建议先补先修课。")
    else:
        lines.append(f"下一步可修课程({len(recs)}门，按进阶顺序)：")
        for r in recs:
            prof = _label(kg, r["professor"]) if r["professor"] else "待定"
            lines.append(f"  - {r['code']} {r['title']}  难度{r['difficulty']}/5  授课: {prof}")

    reasoning = [
        _build_reasoning_block(kg, engine, "R6_major_completion",
            goal=f"计算 {sname} 的专业必修课完成进度",
            conclusion=f"必修课 {len(comp['completed'])+len(comp['remaining'])} 门, "
                       f"已完成 {len(comp['completed'])}, 完成率 {comp['completion']*100:.0f}%",
            traced_result=r6),
        _build_reasoning_block(kg, engine, "R3_recommend_next_courses",
            goal=f"为 {sname} 推荐下一批可修课程",
            conclusion=f"遍历 {len(kg.list_entities('Course'))} 门课程, 得到 {len(recs)} 门可修课程",
            traced_result=r3),
    ]
    return {"answer": "\n".join(lines), "reasoning": reasoning, "involved": involved}


def answer_career_advice(kg: KnowledgeGraph, engine: RuleEngine,
                          student: str) -> dict:
    sname = kg.get_entity(student).attrs["name"]
    r5 = engine.query_traced("R5_eligible_careers", student=student)
    careers = r5["result"]
    involved = r5["trace"]["involved_entities"]

    lines = [f"【{sname}】的职业适配分析："]
    for c in careers:
        status = "✅ 可胜任" if c["qualified"] else "⚠️ 技能不足"
        lines.append(f"  {status}  {_label(kg, c['career'])}  匹配率 {c['match_rate']*100:.0f}%")
        if c["missing_skills"]:
            lines.append(f"      缺失技能: {'、'.join(_label(kg,s) for s in c['missing_skills'])}")

    qualified = sum(1 for c in careers if c["qualified"])
    reasoning = [_build_reasoning_block(kg, engine, "R5_eligible_careers",
        goal=f"分析 {sname} 的职业适配方向",
        conclusion=f"候选职业 {len(careers)} 个, 可胜任(≥60%) {qualified} 个",
        traced_result=r5)]
    return {"answer": "\n".join(lines), "reasoning": reasoning, "involved": involved}


def answer_skill_gap_plan(kg: KnowledgeGraph, engine: RuleEngine,
                           student: str, career: str) -> dict:
    sname = kg.get_entity(student).attrs["name"]
    r4 = engine.query_traced("R4_skill_gap", student=student, career=career)
    gap = r4["result"]
    r7 = engine.query_traced("R7_recommend_electives_for_gap", student=student)
    electives = r7["result"]
    involved = (r4["trace"]["involved_entities"] |
                r7["trace"]["involved_entities"])

    lines = [f"【{sname} → {_label(kg, career)}】技能补齐方案："]
    if not gap["gap_skills"]:
        lines.append("恭喜！你已具备该职业所需的全部技能。")
    else:
        lines.append(f"技能缺口({len(gap['gap_skills'])}项): "
                     + "、".join(_label(kg, s) for s in gap["gap_skills"]))
        related = [e for e in electives if e["for_career"] == career]
        if related:
            lines.append("推荐选修(先修已满足)：")
            for e in related:
                lines.append(f"  - {_label(kg, e['course'])}  (补齐: {_label(kg, e['fix_skill'])})")

    reasoning = [
        _build_reasoning_block(kg, engine, "R4_skill_gap",
            goal=f"分析 {sname} 与 {_label(kg, career)} 的技能差距",
            conclusion=f"需要 {len(gap['required_skills'])} 项, 已有 {len(gap['have_skills'])} 项, "
                       f"缺口 {len(gap['gap_skills'])} 项",
            traced_result=r4),
        _build_reasoning_block(kg, engine, "R7_recommend_electives_for_gap",
            goal=f"为 {sname} 的技能缺口推荐可补齐的选修课",
            conclusion=f"找到 {len([e for e in electives if e['for_career']==career])} 门可补缺选修",
            traced_result=r7),
    ]
    return {"answer": "\n".join(lines), "reasoning": reasoning, "involved": involved}


def answer_check_course(kg: KnowledgeGraph, engine: RuleEngine,
                         student: str, course: str) -> dict:
    sname = kg.get_entity(student).attrs["name"]
    c = kg.get_entity(course)
    r2 = engine.query_traced("R2_can_take_course", student=student, course=course)
    result = r2["result"]
    involved = r2["trace"]["involved_entities"]

    lines = [f"【选课资格检查】{sname} → {c.attrs['code']} {c.attrs['title']}"]
    if result["eligible"]:
        lines.append("✅ 满足全部先修要求，可以选修！")
    else:
        lines.append("❌ 暂不满足，缺少先修课：")
        for p in result["missing_prerequisites"]:
            lines.append(f"  - {_label(kg, p)}")

    reasoning = [_build_reasoning_block(kg, engine, "R2_can_take_course",
        goal=f"检查 {sname} 能否选修 {c.attrs['title']}",
        conclusion=("可以选修" if result["eligible"]
                    else f"先修未满足, 缺 {len(result['missing_prerequisites'])} 门"),
        traced_result=r2)]
    return {"answer": "\n".join(lines), "reasoning": reasoning, "involved": involved}


def answer_student_profile(kg: KnowledgeGraph, engine: RuleEngine,
                            student: str) -> dict:
    s = kg.get_entity(student)
    sname = s.attrs["name"]
    r6 = engine.query_traced("R6_major_completion", student=student)
    comp = r6["result"]
    r3 = engine.query_traced("R3_recommend_next_courses", student=student)
    recs = r3["result"]
    r5 = engine.query_traced("R5_eligible_careers", student=student)
    careers = r5["result"]
    involved = (r6["trace"]["involved_entities"] |
                r3["trace"]["involved_entities"] |
                r5["trace"]["involved_entities"])

    major_eid = kg.neighbors(student, "enrolled_in")
    major = _label(kg, major_eid[0]) if major_eid else "无"
    targets = [_label(kg, c) for c in kg.neighbors(student, "targets_career")]
    passed_courses = [_label(kg, r.obj) for r in kg.out(student, "takes")
                      if r.edge.get("status") == "passed"]
    ongoing = [_label(kg, r.obj) for r in kg.out(student, "takes")
               if r.edge.get("status") == "ongoing"]
    skills = [f"{_label(kg, r.obj)}(L{r.edge.get('level')})" for r in kg.out(student, "has_skill")]

    lines = [
        f"===== 学生画像: {sname} =====",
        f"学号: {s.attrs['id']}  入学: {s.attrs['grade']}  GPA: {s.attrs['gpa']}",
        f"专业: {major}  目标: {', '.join(targets) or '未设定'}",
        f"已修通过: {', '.join(passed_courses) or '无'}",
        f"在修: {', '.join(ongoing) or '无'}",
        f"技能: {', '.join(skills) or '无'}",
        f"必修完成度: {comp['completion']*100:.0f}%  剩余: {', '.join(_label(kg,c) for c in comp['remaining']) or '无'}",
        f"可修课程({len(recs)}门): {', '.join(r['code'] for r in recs) or '无'}",
        f"职业适配: " + " | ".join(
            f"{_label(kg,c['career'])}({c['match_rate']*100:.0f}%)" for c in careers),
        "=" * 30,
    ]
    reasoning = [
        _build_reasoning_block(kg, engine, "R6_major_completion",
            goal="专业必修课完成度",
            conclusion=f"{comp['completion']*100:.0f}%",
            traced_result=r6),
        _build_reasoning_block(kg, engine, "R3_recommend_next_courses",
            goal="可修课程推荐",
            conclusion=f"{len(recs)} 门",
            traced_result=r3),
        _build_reasoning_block(kg, engine, "R5_eligible_careers",
            goal="职业适配分析",
            conclusion=f"{len(careers)} 个候选",
            traced_result=r5),
    ]
    return {"answer": "\n".join(lines), "reasoning": reasoning, "involved": involved}


# --------------------------------------------------------------------------- #
# 问题路由器 (NLU)
# --------------------------------------------------------------------------- #
INTENT_KEYWORDS = {
    "recommend_courses": ["选什么课", "下学期", "该修什么", "推荐课", "选课建议", "修哪些"],
    "career_advice":    ["适合什么", "职业方向", "什么职业", "就业", "前途"],
    "skill_gap":        ["还差什么", "差什么", "怎么补", "想成为", "想做", "目标"],
    "check_course":     ["能选", "能不能选", "可以直接", "可不可以选", "能修"],
    "student_profile":  ["画像", "完整", "概况", "档案", "情况"],
}


def parse_question(kg: KnowledgeGraph, question: str) -> tuple[dict | None, list[dict]]:
    """解析用户问题 -> ({intent, student, career?, course?}, pipeline_steps)

    pipeline_steps 记录 NLU 阶段的每一步执行过程，供前端展示。
    """
    q = question.strip()
    pipeline: list[dict] = []

    # 步骤1: 意图识别 (基于关键词匹配)
    pipeline.append({
        "step": 1, "phase": "NLU", "action": "意图识别",
        "method": "基于 INTENT_KEYWORDS 关键词词典匹配",
        "detail": f"在问题中查找预设关键词: {dict(INTENT_KEYWORDS)}",
    })
    intent = None
    matched_kw = None
    for it, keywords in INTENT_KEYWORDS.items():
        for kw in keywords:
            if kw in q:
                intent = it
                matched_kw = kw
                break
        if intent:
            break
    if not intent:
        pipeline[-1]["result"] = "❌ 未匹配到任何意图"
        return None, pipeline
    pipeline[-1]["result"] = f"✅ 识别意图 = {intent} (命中关键词 '{matched_kw}')"

    # 步骤2: 学生实体解析
    pipeline.append({
        "step": 2, "phase": "NLU", "action": "学生实体解析",
        "method": "遍历 Student 实体，用 name 做子串匹配",
        "detail": f"候选学生名: {[s.attrs['name'] for s in kg.list_entities('Student')]}",
    })
    student = _resolve_student(kg, q)
    if not student:
        students = kg.list_entities("Student")
        if students:
            student = students[0].eid
            pipeline[-1]["result"] = f"⚠️ 未显式匹配到学生，默认使用第一个: {student}"
        else:
            pipeline[-1]["result"] = "❌ 图谱中无学生实体"
    else:
        pipeline[-1]["result"] = f"✅ 解析到学生 = {student} ({kg.get_entity(student).attrs['name']})"

    # 步骤3: 职业/课程实体解析
    pipeline.append({
        "step": 3, "phase": "NLU", "action": "职业/课程实体解析",
        "method": "职业: name 子串匹配; 课程: 先正则匹配代码(如CS101), 再匹配课程名",
        "detail": f"候选职业: {[c.attrs['name'] for c in kg.list_entities('Career')]}",
    })
    career = _resolve_career(kg, q)
    course = _resolve_course(kg, q)
    parts = []
    if career:
        parts.append(f"职业={career} ({kg.get_entity(career).attrs['name']})")
    if course:
        parts.append(f"课程={course} ({kg.get_entity(course).attrs['title']})")
    pipeline[-1]["result"] = "✅ " + ("、".join(parts) if parts else "无职业/课程参数(该意图不需要)")

    return {
        "intent": intent,
        "student": student,
        "career": career,
        "course": course,
    }, pipeline


# --------------------------------------------------------------------------- #
# 问答主入口
# --------------------------------------------------------------------------- #
def ask(kg: KnowledgeGraph, engine: RuleEngine, question: str) -> dict:
    """用户提问 -> 路由 -> 规则执行 -> 返回完整结果。

    返回结构包含 pipeline: 系统从接收到问题到产出答案的完整执行流程。
    """
    # ===== 阶段1: NLU 自然语言理解 =====
    parsed, pipeline = parse_question(kg, question)
    if not parsed:
        pipeline.append({
            "step": 4, "phase": "FAIL", "action": "无法处理",
            "method": "意图识别失败，无法继续",
            "result": "❌ 请换一种问法",
        })
        return {
            "question": question,
            "intent": "unknown",
            "answer": "抱歉，我无法理解你的问题。试试这样问：\n"
                      "  - \"Alice 下学期该修什么课？\"\n"
                      "  - \"Eve 适合什么职业方向？\"\n"
                      "  - \"Carol 想成为数据科学家，还差什么？\"\n"
                      "  - \"Bob 能选 ML401 吗？\"\n"
                      "  - \"给我看看 Grace 的完整画像\"",
            "pipeline": pipeline,
            "reasoning": [], "involved": [], "subgraph": {"nodes": [], "edges": []},
        }

    intent = parsed["intent"]
    student = parsed["student"]
    sname = kg.get_entity(student).attrs["name"]

    # ===== 阶段2: 规则编排 (根据意图选择要执行的规则链) =====
    rule_flow = RULE_FLOWS.get(intent, [])
    pipeline.append({
        "step": 4, "phase": "Orchestration", "action": "规则编排",
        "method": f"根据意图 {intent} 查 RULE_FLOWS 表，确定要执行的规则链",
        "detail": "规则执行顺序及依赖: " + " → ".join(
            f"{rf['rule']}" + (f"(依赖{rf['depends_on']})" if rf['depends_on'] else "")
            for rf in rule_flow),
        "result": f"✅ 编排出 {len(rule_flow)} 条规则: " + ", ".join(rf['rule'] for rf in rule_flow),
    })

    # ===== 阶段3: 参数补全 (某些意图需要额外查图谱补参数) =====
    career = parsed["career"]
    course = parsed["course"]
    if intent == "skill_gap" and not career:
        pipeline.append({
            "step": 5, "phase": "Param Resolution", "action": "补全职业参数",
            "method": "查询 student.targets_career 出边，取第一个目标职业",
            "detail": f"查 {student} 的 targets_career 关系",
        })
        targets = kg.neighbors(student, "targets_career")
        career = targets[0] if targets else None
        if career:
            pipeline[-1]["result"] = f"✅ 补全职业 = {career} ({kg.get_entity(career).attrs['name']})"
        else:
            pipeline[-1]["result"] = "❌ 该学生未设定目标职业"
    elif intent == "check_course" and not course:
        pipeline.append({
            "step": 5, "phase": "Param Resolution", "action": "课程解析失败",
            "method": "未在问题中识别到课程代码或课程名",
            "result": "❌ 无法确定要检查的课程",
        })

    # ===== 阶段4: 执行规则链 (规则执行流程嵌入此步) =====
    pipeline.append({
        "step": 6, "phase": "Reasoning", "action": "执行规则链",
        "method": "按编排顺序逐条调用规则 action，每条规则在 KG 上做图游走并追踪",
        "detail": "每条规则执行时: 开启 trace → 图游走 → mark_hop 标注跳转 → 关闭 trace",
        "chain": [dict(rf) for rf in rule_flow],  # 规则执行流程(中文/作用/依赖)
        "result": f"开始执行 {len(rule_flow)} 条规则...",
    })

    if intent == "recommend_courses":
        result = answer_recommend_courses(kg, engine, student)
    elif intent == "career_advice":
        result = answer_career_advice(kg, engine, student)
    elif intent == "skill_gap":
        if not career:
            return {
                "question": question, "intent": intent, "student": sname,
                "answer": f"未找到职业方向，请尝试：\"{sname} 想成为数据科学家，还差什么？\"",
                "pipeline": pipeline,
                "reasoning": [], "involved": [], "subgraph": {"nodes": [], "edges": []},
            }
        result = answer_skill_gap_plan(kg, engine, student, career)
    elif intent == "check_course":
        if not course:
            return {
                "question": question, "intent": intent, "student": sname,
                "answer": f"未找到课程，请尝试：\"{sname} 能选 ML401 吗？\"",
                "pipeline": pipeline,
                "reasoning": [], "involved": [], "subgraph": {"nodes": [], "edges": []},
            }
        result = answer_check_course(kg, engine, student, course)
    elif intent == "student_profile":
        result = answer_student_profile(kg, engine, student)
    else:
        result = None

    if result is None:
        pipeline.append({
            "step": 7, "phase": "FAIL", "action": "执行失败",
            "result": "❌ 规则执行返回 None",
        })
        return {
            "question": question, "intent": "error", "student": sname,
            "answer": "处理失败", "pipeline": pipeline,
            "reasoning": [], "involved": [], "subgraph": {"nodes": [], "edges": []},
        }

    # ===== 阶段5: 子图提取 =====
    involved = set(result["involved"])
    for eid in list(result["involved"]):
        for r in kg.out(eid):
            involved.add(r.obj)
        for r in kg.inn(eid):
            involved.add(r.subject)

    pipeline.append({
        "step": 7, "phase": "Graph Extraction", "action": "提取推理子图",
        "method": "汇总所有涉及实体 + 1跳邻居，调用 subgraph_data 导出 nodes/edges",
        "result": f"✅ 子图: {len(involved)} 节点 / {sum(1 for e in kg.full_graph_data()['edges'] if e['from'] in involved and e['to'] in involved)} 边",
    })

    # ===== 阶段6: 答案生成 =====
    answer_nodes = _extract_answer_nodes(result["reasoning"])
    pipeline.append({
        "step": 8, "phase": "Answer Generation", "action": "生成自然语言答案",
        "method": "汇总各规则结论，格式化为答案文本；提取 focus 标签中的答案节点",
        "result": f"✅ 答案生成完毕，识别答案节点 {len(answer_nodes)} 个: {answer_nodes}",
    })

    subgraph = kg.subgraph_data(involved)
    return {
        "question": question,
        "intent": intent,
        "student": sname,
        "answer": result["answer"],
        "pipeline": pipeline,
        "reasoning": result["reasoning"],
        "rule_flow": rule_flow,
        "answer_nodes": answer_nodes,
        "involved": list(involved),
        "subgraph": subgraph,
    }
