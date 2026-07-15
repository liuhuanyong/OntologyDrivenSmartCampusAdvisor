"""
Smart Campus Course & Career Advisor —— Ontology 最小化演示
============================================================
完整打通三层：
  Layer 1  ontology.py + knowledge_base.py   本体 + 实例底座
  Layer 2  rules.py                           规则定义 + 存储 + 推理引擎
  Layer 3  advisor.py + main.py              动作入口 + Q&A

运行:  python main.py
"""
from __future__ import annotations

from knowledge_base import build_knowledge_base
from ontology import ENTITY_SCHEMAS, RELATION_SCHEMAS
from rules import RuleEngine, build_default_rules
from advisor import (
    action_check_course,
    action_career_advice,
    action_recommend_courses,
    action_skill_gap_plan,
    action_student_profile,
)


def banner(title: str) -> None:
    print("\n" + "=" * 64)
    print(f"  {title}")
    print("=" * 64)



def main() -> None:
    # ---------- Layer 1: 构建本体 + 实例底座 ---------- #
    banner("Layer 1 · 本体定义 (Ontology)")
    print(f"  实体类型数: {len(ENTITY_SCHEMAS)}  关系类型数: {len(RELATION_SCHEMAS)}")
    print("  实体类型:", ", ".join(ENTITY_SCHEMAS.keys()))
    print("  关系类型:", ", ".join(RELATION_SCHEMAS.keys()))

    kg = build_knowledge_base()
    banner("Layer 1 · 实例数据 (ABox)")
    print(f"  {kg}")
    print(f"  统计: {kg.stats()}")
    from collections import Counter
    dist = Counter(e.etype for e in kg.list_entities())
    print("  实体分布:", dict(dist))

    # ---------- Layer 2: 规则存储 + 推理引擎 ---------- #
    banner("Layer 2 · 业务推理规则 (Rule Store)")
    engine = RuleEngine(kg)
    for r in build_default_rules():
        engine.register(r)
    # 规则以 JSON 形式落盘存储
    rules_json = engine.dump_rules_json("rules_store.json")
    print(f"  已注册规则 {len(engine.rules)} 条，已存储到 rules_store.json")
    for r in sorted(engine.rules.values(), key=lambda r: r.priority):
        print(f"  [{r.kind:10}] {r.name:32} {r.description}")

    # 正向链式：把可推导事实物化进 KG
    banner("Layer 2 · 正向链式推理 (Forward Chaining)")
    added = engine.forward_chain()
    print(f"  物化新事实: {added}")
    print(f"  推理后 KG: {kg}")
    print(f"  例如 student:alice 的 eligible_for 出边:")
    for r in kg.out("student:alice", "eligible_for"):
        print(f"    --eligible_for(match={r.edge['match_rate']})--> {r.obj}")

    # ---------- Layer 3: 动作入口 / Q&A ---------- #
    banner("Layer 3 · 动作入口演示 (用户提问 -> 规则执行 -> 答案)")

    # Q1: Alice 下学期该修什么课？
    banner("Q1  用户: \"Alice 下学期该修什么课？\"")
    print(action_recommend_courses(kg, engine, "Alice"))

    # Q2: Alice 适合什么职业方向？
    banner("Q2  用户: \"Alice 适合什么职业方向？\"")
    print(action_career_advice(kg, engine, "Alice"))

    # Q3: Carol 想做数据科学家，还差什么？怎么补？
    banner("Q3  用户: \"Carol 想成为数据科学家，还差什么？该怎么补？\"")
    print(action_skill_gap_plan(kg, engine, "Carol", "数据科学家"))

    # Q4: Bob 现在能直接选 ML401 机器学习吗？
    banner("Q4  用户: \"Bob 现在能直接选 ML401 机器学习吗？\"")
    print(action_check_course(kg, engine, "Bob", "ML401"))

    # Q5: Bob 想做数据科学家，补齐方案
    banner("Q5  用户: \"Bob 想做数据科学家，给我一个补齐方案\"")
    print(action_skill_gap_plan(kg, engine, "Bob", "数据科学家"))

    # Q6: 综合画像
    banner("Q6  用户: \"给我看看 Carol 的完整画像\"")
    print(action_student_profile(kg, engine, "Carol"))

    # ---------- 收尾 ---------- #
    banner("演示完成")
    print(f"  最终知识图谱: {kg}")
    print(f"  其中被推理物化的新事实: {len(kg._inferred)} 条")
    print("  规则已落盘: rules_store.json")

if __name__ == "__main__":
    main()
