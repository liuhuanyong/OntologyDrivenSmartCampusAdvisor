"""
第 1 层：本体定义 (Ontology / TBox) + 知识图谱底座
=====================================================
Smart Campus Course & Career Advisor 本体模型。

提供：
  1) 实体类型 (Concept) + 属性 schema (Data Property)
  2) 关系类型 (Object Property) —— 含可推理的派生关系
  3) KnowledgeGraph：存储实体 / 属性 / 三元组，支持图游走查询
  4) 图访问追踪 (tracing)：记录推理过程中的实体/关系访问路径，
     用于在 UI 上展示推理过程 + 高亮子图
  5) 子图提取：根据涉及到的实体集合导出可视化所需 nodes/edges
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


# --------------------------------------------------------------------------- #
# 1. 实体类型 + 属性 schema  (TBox)
# --------------------------------------------------------------------------- #
ENTITY_SCHEMAS: dict[str, dict[str, type]] = {
    "Department": {"code": str, "name": str},
    "Major":      {"code": str, "name": str, "degree": str},
    "Professor":  {"id": str, "name": str, "title": str, "research_area": str},
    "Course":     {"code": str, "title": str, "credits": int, "difficulty": int, "semester": str},
    "Skill":      {"name": str, "category": str},
    "Student":    {"id": str, "name": str, "grade": int, "gpa": float},
    "Career":     {"name": str, "field": str, "avg_salary": str, "growth_rate": str},
}

# 实体类型 -> 显示颜色 (供前端可视化使用)
ENTITY_COLORS: dict[str, str] = {
    "Department": "#6366f1",
    "Major":      "#8b5cf6",
    "Professor":  "#ec4899",
    "Course":     "#f59e0b",
    "Skill":      "#10b981",
    "Student":    "#3b82f6",
    "Career":     "#ef4444",
}


# --------------------------------------------------------------------------- #
# 2. 关系类型 (Object Property)
# --------------------------------------------------------------------------- #
RELATION_SCHEMAS: dict[str, dict[str, Any]] = {
    # 组织结构
    "offered_by":   {"domain": "Course",    "range": "Department", "edge": {}},
    "belongs_to":   {"domain": "Professor", "range": "Department", "edge": {}},
    "enrolled_in":   {"domain": "Student",   "range": "Major",      "edge": {}},
    "major_in_dept": {"domain": "Major",     "range": "Department", "edge": {}},

    # 课程 / 教学
    "taught_by":       {"domain": "Course",    "range": "Professor", "edge": {}},
    "teaches":          {"domain": "Professor", "range": "Course",    "edge": {}},
    "prerequisite_of":  {"domain": "Course",    "range": "Course",    "edge": {}},
    "teaches_skill":    {"domain": "Course",    "range": "Skill",     "edge": {}},

    # 专业 / 职业
    "requires_course": {"domain": "Major",  "range": "Course", "edge": {}},
    "leads_to":         {"domain": "Major",  "range": "Career", "edge": {}},
    "requires_skill":   {"domain": "Career", "range": "Skill",  "edge": {}},

    # 学生学习
    "takes":          {"domain": "Student", "range": "Course", "edge": {"grade": str, "status": str}},
    "has_skill":      {"domain": "Student", "range": "Skill",  "edge": {"level": int}},
    "targets_career": {"domain": "Student", "range": "Career", "edge": {}},

    # 派生关系 (推理生成)
    "eligible_for":   {"domain": "Student", "range": "Career", "edge": {"match_rate": float}},
}


# --------------------------------------------------------------------------- #
# 3. 实体 + 关系数据结构
# --------------------------------------------------------------------------- #
@dataclass
class Entity:
    eid: str
    etype: str
    attrs: dict[str, Any] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return (self.attrs.get("name") or self.attrs.get("title")
                or self.attrs.get("code") or self.eid)

    def __repr__(self) -> str:
        return f"<{self.etype}:{self.label}>"


@dataclass
class Relation:
    subject: str
    predicate: str
    obj: str
    edge: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return f"<{self.subject} --{self.predicate}--> {self.obj}>"


# --------------------------------------------------------------------------- #
# 4. 知识图谱：实体 + 关系 + 图游走 + 访问追踪 + 子图提取
# --------------------------------------------------------------------------- #
class KnowledgeGraph:
    def __init__(self) -> None:
        self.entities: dict[str, Entity] = {}
        self._out: dict[str, dict[str, list[Relation]]] = defaultdict(lambda: defaultdict(list))
        self._in: dict[str, dict[str, list[Relation]]] = defaultdict(lambda: defaultdict(list))
        self._inferred: set[tuple[str, str, str]] = set()

        # ---- 推理追踪 ---- #
        self._trace_active = False
        self._trace_walks: list[dict] = []        # 图游走步骤: {subject, predicate, object, direction}
        self._trace_hops: list[dict] = []          # 高亮游走: 推理路径上的边
        self._trace_entities: set[str] = set()
        self._trace_relations: set[tuple[str, str, str]] = set()

    # ===== 实体操作 ===== #
    def add_entity(self, eid: str, etype: str, **attrs) -> Entity:
        if etype not in ENTITY_SCHEMAS:
            raise ValueError(f"未知实体类型: {etype}")
        ent = Entity(eid=eid, etype=etype, attrs=dict(attrs))
        self.entities[eid] = ent
        return ent

    def get_entity(self, eid: str) -> Entity | None:
        return self.entities.get(eid)

    def list_entities(self, etype: str | None = None) -> list[Entity]:
        if etype is None:
            return list(self.entities.values())
        return [e for e in self.entities.values() if e.etype == etype]

    # ===== 关系操作 ===== #
    def add_relation(self, subject: str, predicate: str, obj: str, **edge) -> Relation:
        if predicate not in RELATION_SCHEMAS:
            raise ValueError(f"未知关系类型: {predicate}")
        rel = Relation(subject=subject, predicate=predicate, obj=obj, edge=edge)
        self._out[subject][predicate].append(rel)
        self._in[obj][predicate].append(rel)
        return rel

    def out(self, eid: str, predicate: str | None = None) -> list[Relation]:
        # 记录一次图游走：访问出边
        if self._trace_active:
            rels = (list(self._out[eid].get(predicate, [])) if predicate
                    else [r for preds in self._out[eid].values() for r in preds])
            for r in rels:
                self._record_walk(r.subject, r.predicate, r.obj, direction="out")
            return rels
        if predicate is None:
            return [r for preds in self._out[eid].values() for r in preds]
        return list(self._out[eid].get(predicate, []))

    def inn(self, eid: str, predicate: str | None = None) -> list[Relation]:
        # 记录一次图游走：访问入边
        if self._trace_active:
            rels = (list(self._in[eid].get(predicate, [])) if predicate
                    else [r for preds in self._in[eid].values() for r in preds])
            for r in rels:
                self._record_walk(r.subject, r.predicate, r.obj, direction="in")
            return rels
        if predicate is None:
            return [r for preds in self._in[eid].values() for r in preds]
        return list(self._in[eid].get(predicate, []))

    def neighbors(self, eid: str, predicate: str) -> list[str]:
        rels = self.out(eid, predicate)
        return [r.obj for r in rels]

    def exists(self, subject: str, predicate: str, obj: str) -> bool:
        return any(r.obj == obj for r in self.out(subject, predicate))

    # ===== 推理事实写回 ===== #
    def add_inferred(self, subject: str, predicate: str, obj: str, **edge) -> bool:
        key = (subject, predicate, obj)
        if key in self._inferred or self.exists(subject, predicate, obj):
            return False
        self._inferred.add(key)
        self.add_relation(subject, predicate, obj, **edge)
        return True

    # ===== 推理追踪 ===== #
    def start_trace(self) -> None:
        """开启一次推理追踪。规则执行期间的图游走会被记录成 hops。"""
        self._trace_active = True
        self._trace_walks = []
        self._trace_hops = []
        self._trace_entities = set()
        self._trace_relations = set()

    def stop_trace(self) -> dict:
        """结束追踪并返回:
           - walks: 所有图游走 (subject--pred-->object, direction)
           - hops:  显式标注的推理跳转 (含 reason / rule)
           - involved_entities / involved_relations
        """
        self._trace_active = False
        return {
            "walks": list(self._trace_walks),
            "hops": list(self._trace_hops),
            "involved_entities": set(self._trace_entities),
            "involved_relations": set(self._trace_relations),
        }

    def _record_walk(self, subject: str, predicate: str, obj: str,
                     direction: str = "out") -> None:
        """记录一次图游走: subject --predicate--> object。"""
        if not self._trace_active:
            return
        self._trace_walks.append({
            "subject": subject, "predicate": predicate, "object": obj,
            "direction": direction,
        })
        self._trace_entities.add(subject)
        self._trace_entities.add(obj)
        self._trace_relations.add((subject, predicate, obj))

    def mark_hop(self, subject: str, predicate: str, obj: str,
                 reason: str = "") -> None:
        """显式标注一条推理跳转 (用于在图谱上高亮)。

        reason 例: "学生已通过 CS101" / "职业需要 Python"
        """
        if not self._trace_active:
            return
        self._trace_hops.append({
            "subject": subject, "predicate": predicate, "object": obj,
            "reason": reason,
        })

    def mark_focus(self, eid: str, note: str = "") -> None:
        """标记推理关注的核心实体 (起点/终点)。"""
        if not self._trace_active:
            return
        self._trace_entities.add(eid)
        self._trace_hops.append({
            "subject": eid, "predicate": "__focus__", "object": eid,
            "reason": note,
        })

    # ===== 子图提取：导出 nodes + edges 供可视化 ===== #
    def full_graph_data(self) -> dict:
        """导出完整图谱的 nodes + edges (JSON 可序列化)。"""
        nodes = []
        for eid, ent in self.entities.items():
            nodes.append({
                "id": eid,
                "label": ent.label,
                "type": ent.etype,
                "color": ENTITY_COLORS.get(ent.etype, "#6b7280"),
                "attrs": ent.attrs,
            })
        edges = []
        seen = set()
        for subj, preds in self._out.items():
            for pred, rels in preds.items():
                for r in rels:
                    key = (r.subject, r.predicate, r.obj)
                    if key in seen:
                        continue
                    seen.add(key)
                    edges.append({
                        "from": r.subject,
                        "to": r.obj,
                        "label": r.predicate,
                        "edge": r.edge,
                        "inferred": key in self._inferred,
                    })
        return {"nodes": nodes, "edges": edges}

    def subgraph_data(self, entity_ids: set[str]) -> dict:
        """导出指定实体集合的子图 (仅含集合内实体间的边)。"""
        nodes = []
        for eid in entity_ids:
            ent = self.entities.get(eid)
            if not ent:
                continue
            nodes.append({
                "id": eid,
                "label": ent.label,
                "type": ent.etype,
                "color": ENTITY_COLORS.get(ent.etype, "#6b7280"),
                "attrs": ent.attrs,
            })
        edges = []
        seen = set()
        for eid in entity_ids:
            for pred, rels in self._out[eid].items():
                for r in rels:
                    if r.obj not in entity_ids:
                        continue
                    key = (r.subject, r.predicate, r.obj)
                    if key in seen:
                        continue
                    seen.add(key)
                    edges.append({
                        "from": r.subject,
                        "to": r.obj,
                        "label": r.predicate,
                        "edge": r.edge,
                        "inferred": key in self._inferred,
                    })
        return {"nodes": nodes, "edges": edges}

    # ===== 统计 ===== #
    def stats(self) -> dict[str, int]:
        rel_count = sum(len(rs) for preds in self._out.values() for rs in preds.values())
        return {
            "entities": len(self.entities),
            "relations": rel_count,
            "inferred_facts": len(self._inferred),
        }

    def __repr__(self) -> str:
        s = self.stats()
        return f"<KnowledgeGraph entities={s['entities']} relations={s['relations']}>"
