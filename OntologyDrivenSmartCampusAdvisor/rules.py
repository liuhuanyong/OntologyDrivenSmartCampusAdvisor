"""
第 2 层：业务推理规则 + 规则存储 + 推理引擎
=====================================================
规则用来"游走 / 操作"底层本体中的实体与关系。

规则在执行时会通过 kg.mark_hop(...) 标注每一步推理跳转，并
通过 kg.mark_focus(...) 标记推理关注的起点/终点实体。
这些 hops 会被前端用来逐步高亮图谱、展示完整推理路径。

  - Rule dataclass：结构化描述 (名称/模式/类型/优先级/action)
  - dump_rules_json：规则序列化落盘存储
  - RuleEngine:
      forward_chain()     正向链式，物化新事实到 KG
      query()             即席查询
      query_traced()      带追踪的查询 —— 返回 {result, trace}
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from ontology import KnowledgeGraph


# --------------------------------------------------------------------------- #
# 规则数据结构
# --------------------------------------------------------------------------- #
@dataclass
class Rule:
    name: str
    description: str
    pattern: str
    kind: str = "query"
    priority: int = 100
    action: Callable[..., Any] = field(default=None, repr=False)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "pattern": self.pattern,
            "kind": self.kind,
            "priority": self.priority,
        }


# --------------------------------------------------------------------------- #
# 辅助函数
# --------------------------------------------------------------------------- #
def _passed_courses(kg: KnowledgeGraph, student: str) -> set[str]:
    """查询学生已通过课程。同时标注图游走。"""
    out = set()
    for r in kg.out(student, "takes"):
        if r.edge.get("status") == "passed":
            out.add(r.obj)
            kg.mark_hop(student, "takes", r.obj,
                        reason=f"学生已通过 {_label(kg, r.obj)} (成绩 {r.edge.get('grade')})")
    return out


def _student_skills(kg: KnowledgeGraph, student: str) -> dict[str, int]:
    out = {}
    for r in kg.out(student, "has_skill"):
        out[r.obj] = r.edge.get("level", 0)
        kg.mark_hop(student, "has_skill", r.obj,
                    reason=f"学生已掌握 {_label(kg, r.obj)} (等级 L{r.edge.get('level')})")
    return out


def _chain_depth(kg: KnowledgeGraph, course: str,
                 _depth_cache: dict | None = None) -> int:
    if _depth_cache is None:
        _depth_cache = {}
    if course in _depth_cache:
        return _depth_cache[course]
    prereqs = [r.subject for r in kg.inn(course, "prerequisite_of")]
    if not prereqs:
        d = 0
    else:
        d = 1 + max(_chain_depth(kg, p, _depth_cache) for p in prereqs)
    _depth_cache[course] = d
    return d


def _label(kg: KnowledgeGraph, eid: str) -> str:
    e = kg.get_entity(eid)
    return e.label if e else eid


# --------------------------------------------------------------------------- #
# 规则实现 —— 每条规则内部通过 mark_hop / mark_focus 记录推理路径
# --------------------------------------------------------------------------- #
def rule_prerequisite_satisfied(kg: KnowledgeGraph, course: str) -> dict:
    kg.mark_focus(course, note="目标课程")
    prereqs = [r.obj for r in kg.out(course, "prerequisite_of")]
    missing = [p for p in prereqs if kg.get_entity(p) is None]
    for p in prereqs:
        kg.mark_hop(course, "prerequisite_of", p,
                    reason=f"{_label(kg, course)} 的先修课是 {_label(kg, p)}")
    return {"course": course, "satisfied": len(missing) == 0, "missing": missing}


def rule_can_take_course(kg: KnowledgeGraph, student: str, course: str) -> dict:
    """推理路径:
        起点: Student(student)
          ↓ enrolled_in? (无需, 直接查 takes 出边)
          ↓ takes(...passed) -> 已通过课程集合
        然后: 反向查 Course(course) <- prerequisite_of <- 先修课
        判定: 每个 prereq ∈ passed?
        终点: 结论 {eligible, missing}
    """
    kg.mark_focus(student, note="推理起点: 学生")
    kg.mark_focus(course, note="目标: 待选课程")

    # 步骤1: 查询学生已通过课程 (会在 _passed_courses 内部 mark_hop)
    passed = _passed_courses(kg, student)

    # 步骤2: 反向遍历 prerequisite_of 入边, 取出该课程的全部先修课
    prereqs = [r.subject for r in kg.inn(course, "prerequisite_of")]
    for p in prereqs:
        kg.mark_hop(p, "prerequisite_of", course,
                    reason=f"{_label(kg, p)} 是 {_label(kg, course)} 的先修课")

    # 步骤3: 逐一比对
    missing = []
    for p in prereqs:
        if p in passed:
            kg.mark_hop(student, "takes", p,
                        reason=f"已通过先修 {_label(kg, p)} ✓")
        else:
            kg.mark_hop(student, "__missing__", p,
                        reason=f"未通过先修 {_label(kg, p)} ✗")
            missing.append(p)

    kg.mark_focus(course, note=f"结论: {'可以选修' if not missing else '先修未满足'}")
    return {
        "course": course,
        "eligible": len(missing) == 0,
        "missing_prerequisites": missing,
        "prerequisites": prereqs,
    }


def rule_recommend_next_courses(kg: KnowledgeGraph, student: str) -> list[dict]:
    """推理路径:
        起点: Student(student) -> takes(passed) -> 已通过课程集 P
        遍历: 所有 Course(c)
          ↘ inn(prerequisite_of) -> 先修集 R(c)
          判定: R(c) ⊆ P ?
        终点: 推荐课程列表
    """
    kg.mark_focus(student, note="推理起点: 学生")
    passed = _passed_courses(kg, student)

    recs: list[dict] = []
    for c in kg.list_entities("Course"):
        cid = c.eid
        if cid in passed:
            continue
        if any(r.obj == cid and r.edge.get("status") == "ongoing"
               for r in kg.out(student, "takes")):
            continue
        # 反向取该课程所有先修
        prereqs = [r.subject for r in kg.inn(cid, "prerequisite_of")]
        all_met = all(p in passed for p in prereqs) if prereqs else True
        if prereqs:
            for p in prereqs:
                kg.mark_hop(p, "prerequisite_of", cid,
                            reason=f"{_label(kg, p)} 是 {_label(kg, cid)} 的先修; "
                                  f"已通过={'是' if p in passed else '否'}")
        if all_met:
            depth = _chain_depth(kg, cid)
            prof = kg.neighbors(cid, "taught_by")
            if prof:
                kg.mark_hop(cid, "taught_by", prof[0],
                            reason=f"推荐 {_label(kg, cid)} (授课 {_label(kg, prof[0])})")
            recs.append({
                "course": cid, "title": c.attrs["title"], "code": c.attrs["code"],
                "difficulty": c.attrs["difficulty"], "credits": c.attrs["credits"],
                "professor": prof[0] if prof else None, "depth": depth,
            })
    recs.sort(key=lambda x: (x["depth"], -x["difficulty"]))
    for r in recs:
        kg.mark_focus(r["course"], note="推理结论: 推荐课程")
    return recs


def rule_skill_gap(kg: KnowledgeGraph, student: str, career: str) -> dict:
    """推理路径:
        Student(student) -> has_skill -> 已有技能集 S
        Career(career) -> requires_skill -> 所需技能集 R
        gap = R - S
        对 gap 中每项: <- teaches_skill <- 能补齐的课程
    """
    kg.mark_focus(student, note="推理起点: 学生")
    kg.mark_focus(career, note="目标: 职业")
    have = _student_skills(kg, student)
    required = {r.obj for r in kg.out(career, "requires_skill")}
    for sk in required:
        kg.mark_hop(career, "requires_skill", sk,
                    reason=f"{_label(kg, career)} 需要技能 {_label(kg, sk)}")
    gap = required - set(have.keys())
    fix_courses: dict[str, list[str]] = {}
    for sk in gap:
        kg.mark_focus(sk, note=f"缺口技能: {_label(kg, sk)}")
        courses = [r.subject for r in kg.inn(sk, "teaches_skill")]
        fix_courses[sk] = courses
        for c in courses:
            kg.mark_hop(c, "teaches_skill", sk,
                        reason=f"选修 {_label(kg, c)} 可补齐 {_label(kg, sk)}")
    return {
        "career": career,
        "required_skills": sorted(required),
        "have_skills": sorted(have.keys()),
        "gap_skills": sorted(gap),
        "fix_courses": fix_courses,
    }


def rule_eligible_careers(kg: KnowledgeGraph, student: str) -> list[dict]:
    """推理路径:
        Student(student) -> enrolled_in -> Major(m)
        Major(m) -> leads_to -> 候选职业 C1
        Student(student) -> targets_career -> 候选职业 C2
        Student(student) -> has_skill -> 已有技能 S
        对每个候选职业 c: c -> requires_skill -> R, 匹配率 = |R∩S| / |R|
    """
    kg.mark_focus(student, note="推理起点: 学生")
    have = _student_skills(kg, student)
    major = kg.neighbors(student, "enrolled_in")
    leads_to = set()
    if major:
        kg.mark_hop(student, "enrolled_in", major[0],
                    reason=f"学生专业 {_label(kg, major[0])}")
        leads_to = {r.obj for r in kg.out(major[0], "leads_to")}
        for c in leads_to:
            kg.mark_hop(major[0], "leads_to", c,
                        reason=f"专业流向职业 {_label(kg, c)}")
    targets = set(kg.neighbors(student, "targets_career"))
    for c in targets:
        kg.mark_hop(student, "targets_career", c,
                    reason=f"学生目标职业 {_label(kg, c)}")
    candidates = leads_to | targets
    results = []
    for career in candidates:
        required = {r.obj for r in kg.out(career, "requires_skill")}
        matched = required & set(have.keys())
        rate = len(matched) / len(required) if required else 0.0
        for sk in matched:
            kg.mark_hop(student, "has_skill", sk,
                        reason=f"已掌握 {_label(kg, sk)} ✓")
        for sk in required - set(have.keys()):
            kg.mark_hop(career, "requires_skill", sk,
                        reason=f"{_label(kg, career)} 需要但学生缺失 {_label(kg, sk)} ✗")
        if rate >= 0.6:
            kg.mark_focus(career,
                          note=f"结论: 可胜任 (匹配率 {rate*100:.0f}%)")
        results.append({
            "career": career, "match_rate": round(rate, 2),
            "qualified": rate >= 0.6,
            "matched_skills": sorted(matched),
            "missing_skills": sorted(required - set(have.keys())),
        })
    results.sort(key=lambda x: x["match_rate"], reverse=True)
    return results


def rule_major_completion(kg: KnowledgeGraph, student: str) -> dict:
    """推理路径:
        Student(student) -> enrolled_in -> Major(m)
        Major(m) -> requires_course -> 必修课集 R
        Student(student) -> takes(passed) -> 已通过 P
        完成 = R ∩ P
    """
    kg.mark_focus(student, note="推理起点: 学生")
    passed = _passed_courses(kg, student)
    major = kg.neighbors(student, "enrolled_in")
    if not major:
        return {"major": None, "completion": 0.0, "remaining": [], "completed": []}
    major = major[0]
    kg.mark_hop(student, "enrolled_in", major,
                reason=f"学生专业 {_label(kg, major)}")
    required = {r.obj for r in kg.out(major, "requires_course")}
    for c in required:
        kg.mark_hop(major, "requires_course", c,
                    reason=f"{_label(kg, major)} 必修课 {_label(kg, c)}; "
                          f"状态={'已通过' if c in passed else '未通过'}")
    done = required & passed
    return {
        "major": major,
        "completion": round(len(done) / len(required), 2) if required else 0.0,
        "completed": sorted(done),
        "remaining": sorted(required - passed),
    }


def rule_recommend_electives_for_gap(kg: KnowledgeGraph, student: str) -> list[dict]:
    """推理路径: 复用 R4(缺口) + R2(先修满足性)"""
    kg.mark_focus(student, note="推理起点: 学生")
    targets = kg.neighbors(student, "targets_career")
    recs = []
    for career in targets:
        kg.mark_hop(student, "targets_career", career,
                    reason=f"目标职业 {_label(kg, career)}")
        gap = rule_skill_gap(kg, student, career)["gap_skills"]
        for sk in gap:
            for c in kg.inn(sk, "teaches_skill"):
                cid = c.subject
                kg.mark_hop(cid, "teaches_skill", sk,
                            reason=f"{_label(kg, cid)} 教授 {_label(kg, sk)}")
                can = rule_can_take_course(kg, student, cid)
                if can["eligible"]:
                    kg.mark_focus(cid, note=f"结论: 推荐选修(补齐 {_label(kg, sk)})")
                    course = kg.get_entity(cid)
                    recs.append({
                        "course": cid, "title": course.attrs["title"],
                        "code": course.attrs["code"], "fix_skill": sk,
                        "for_career": career,
                    })
    return recs


# --------------------------------------------------------------------------- #
# materialize 规则
# --------------------------------------------------------------------------- #
def _materialize_eligible_for(kg: KnowledgeGraph) -> int:
    n = 0
    for s in kg.list_entities("Student"):
        for item in rule_eligible_careers(kg, s.eid):
            if item["qualified"]:
                if kg.add_inferred(s.eid, "eligible_for", item["career"],
                                   match_rate=item["match_rate"]):
                    n += 1
    return n


# --------------------------------------------------------------------------- #
# 推理引擎
# --------------------------------------------------------------------------- #
class RuleEngine:
    def __init__(self, kg: KnowledgeGraph) -> None:
        self.kg = kg
        self.rules: dict[str, Rule] = {}

    def register(self, rule: Rule) -> None:
        self.rules[rule.name] = rule

    def dump_rules_json(self, path: str | None = None) -> str:
        data = [r.to_dict() for r in
                sorted(self.rules.values(), key=lambda r: r.priority)]
        text = json.dumps(data, ensure_ascii=False, indent=2)
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        return text

    def forward_chain(self) -> dict[str, int]:
        added: dict[str, int] = {}
        for rule in sorted(self.rules.values(), key=lambda r: r.priority):
            if rule.kind != "materialize":
                continue
            n = rule.action(self.kg)
            added[rule.name] = int(n or 0)
        return added

    def query(self, rule_name: str, **params) -> Any:
        if rule_name not in self.rules:
            raise KeyError(f"未知规则: {rule_name}")
        return self.rules[rule_name].action(self.kg, **params)

    def query_traced(self, rule_name: str, **params) -> dict:
        """带追踪的查询: 返回 {result, trace}。

        trace 包含:
          walks: 所有图游走 subject--predicate-->object
          hops:  显式推理跳转 (含 reason)
          involved_entities / involved_relations
        """
        self.kg.start_trace()
        result = self.query(rule_name, **params)
        trace = self.kg.stop_trace()
        return {"result": result, "trace": trace}


# --------------------------------------------------------------------------- #
# 默认规则集
# --------------------------------------------------------------------------- #
def build_default_rules() -> list[Rule]:
    return [
        Rule("R1_prerequisite_satisfied", "检查课程先修结构完整性(目录级)",
             "Course(?c) -> prerequisite_of(?p) -> exists(Course(?p))",
             "query", 10, lambda kg, course: rule_prerequisite_satisfied(kg, course)),
        Rule("R2_can_take_course", "判断学生是否满足某门课的全部先修",
             "Student(?s) -takes(passed)-> P; Course(?c) <-prerequisite_of- prereq; prereq∈P?",
             "query", 20, lambda kg, student, course: rule_can_take_course(kg, student, course)),
        Rule("R3_recommend_next_courses", "推荐下一批可修课程(先修满足且未修过)",
             "Student(?s) -takes-> P; ∀Course(c): prereqs(c)⊆P ∧ ¬takes(?s,c)",
             "query", 30, lambda kg, student: rule_recommend_next_courses(kg, student)),
        Rule("R4_skill_gap", "目标职业所需技能与学生已有技能的缺口",
             "Career(?c) -requires_skill-> R; Student(?s) -has_skill-> S; gap=R-S",
             "query", 40, lambda kg, student, career: rule_skill_gap(kg, student, career)),
        Rule("R5_eligible_careers", "基于专业流向+技能匹配率推荐职业(≥60%)",
             "Major(?m) -leads_to-> C; Student(?s) -has_skill-> S; rate=|R∩S|/|R|≥0.6",
             "query", 50, lambda kg, student: rule_eligible_careers(kg, student)),
        Rule("R6_major_completion", "专业必修课完成进度",
             "Major(?m) -requires_course-> R; Student(?s) -takes(passed)-> P; done=R∩P",
             "query", 60, lambda kg, student: rule_major_completion(kg, student)),
        Rule("R7_recommend_electives_for_gap", "针对缺口推荐可补缺的选修课",
             "Student(?s) -targets_career-> C; C -requires_skill-> gap; <-teaches_skill- course; R2 eligible",
             "query", 70, lambda kg, student: rule_recommend_electives_for_gap(kg, student)),
        Rule("M1_materialize_eligible_for", "[物化]把技能匹配达标的student→career写成eligible_for",
             "∀Student ∀Career: qualified => eligible_for(?s,?c)",
             "materialize", 5, _materialize_eligible_for),
    ]
