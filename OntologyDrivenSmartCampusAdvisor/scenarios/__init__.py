"""
场景注册中心 (Scenario Registry)
================================

提供 Scenario 协议类 + load_scenario 工厂,统一管理同一 Web 应用下的
多个业务场景(Smart Campus 课程职业顾问、Procurement 采购管理)。

调用方式:
    from scenarios import load_scenario
    ctx = load_scenario("procurement")  # 返回 ScenarioCtx
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class ScenarioCtx:
    """场景运行期上下文 —— 把 KG / Engine / NLQ 路由捆绑到一起。"""

    name: str                      # "campus" | "procurement"
    title: str                     # 显示标题
    subtitle: str                  # 副标题
    kg: Any                        # ontology.KnowledgeGraph
    engine: Any                    # rules.RuleEngine
    intents: dict[str, list[str]]  # 意图关键词表
    ask: Callable[[str], dict]     # 场景级 ask(question) -> dict
    example_questions: list[str]   # 示例问题
    entity_schemas: dict[str, dict[str, type]]
    relation_schemas: dict[str, dict[str, Any]]
    entity_colors: dict[str, str]


_REGISTRY: dict[str, Callable[[], ScenarioCtx]] = {}


def register_scenario(name: str, factory: Callable[[], ScenarioCtx]) -> None:
    """注册一个场景工厂函数 (延迟加载, 避免循环导入)。"""
    _REGISTRY[name] = factory


def load_scenario(name: str) -> ScenarioCtx:
    """按名加载场景, 自动调用对应的工厂函数完成 KG + 引擎初始化。"""
    if name not in _REGISTRY:
        raise KeyError(f"未知场景: {name}; 可用: {list(_REGISTRY)}")
    return _REGISTRY[name]()


def list_scenarios() -> list[str]:
    return list(_REGISTRY.keys())


# ---- Campus 场景工厂 ---- #
def _make_campus() -> ScenarioCtx:
    from knowledge_base import build_knowledge_base
    from ontology import ENTITY_COLORS, ENTITY_SCHEMAS, RELATION_SCHEMAS
    from rules import RuleEngine, build_default_rules
    from advisor import RULE_MEANINGS, ask as campus_ask

    kg = build_knowledge_base()
    engine = RuleEngine(kg)
    for r in build_default_rules():
        engine.register(r)
    engine.forward_chain()

    examples = [
        "Alice 下学期该修什么课？",
        "Eve 适合什么职业方向？",
        "Carol 想成为数据科学家，还差什么？",
        "Bob 能选 ML401 吗？",
        "给我看看 Grace 的完整画像",
    ]

    return ScenarioCtx(
        name="campus",
        title="Smart Campus · 课程职业规划顾问",
        subtitle="本体知识图谱 · 推理引擎 · 自然语言问答",
        kg=kg, engine=engine,
        intents={
            "recommend_courses": ["选什么课", "下学期", "该修什么", "推荐课", "选课建议"],
            "career_advice":    ["适合什么", "职业方向", "什么职业", "就业", "前途"],
            "skill_gap":        ["还差什么", "差什么", "怎么补", "想成为", "想做"],
            "check_course":     ["能选", "能不能选", "可以直接", "可不可以选", "能修"],
            "student_profile":  ["画像", "完整", "概况", "档案", "情况"],
        },
        ask=campus_ask,
        example_questions=examples,
        entity_schemas=ENTITY_SCHEMAS,
        relation_schemas=RELATION_SCHEMAS,
        entity_colors=ENTITY_COLORS,
    )


# ---- Procurement 场景工厂 ---- #
def _make_procurement() -> ScenarioCtx:
    from scenarios.procurement.knowledge_base import build_procurement_knowledge_base
    from scenarios.procurement.ontology import (
        PROCUREMENT_ENTITY_COLORS,
        PROCUREMENT_ENTITY_SCHEMAS,
        PROCUREMENT_RELATION_SCHEMAS,
    )
    from scenarios.procurement.rules import build_procurement_rules, RuleEngine
    from scenarios.procurement.advisor import (
        INTENT_KEYWORDS, ask as procurement_ask, EXAMPLE_QUESTIONS,
    )

    kg = build_procurement_knowledge_base()
    engine = RuleEngine(kg)
    for r in build_procurement_rules():
        engine.register(r)
    engine.forward_chain()

    return ScenarioCtx(
        name="procurement",
        title="Procurement · SAP 采购管理智能体",
        subtitle="Source-to-Award · 寻源 → PR → PO → GR 全链路追溯",
        kg=kg, engine=engine,
        intents=INTENT_KEYWORDS,
        ask=procurement_ask,
        example_questions=EXAMPLE_QUESTIONS,
        entity_schemas=PROCUREMENT_ENTITY_SCHEMAS,
        relation_schemas=PROCUREMENT_RELATION_SCHEMAS,
        entity_colors=PROCUREMENT_ENTITY_COLORS,
    )


# ---- 注册场景 ---- #
register_scenario("campus", _make_campus)
register_scenario("procurement", _make_procurement)
