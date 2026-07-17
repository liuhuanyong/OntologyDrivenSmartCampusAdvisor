"""
采购场景 (Procurement Scenario) 包入口
======================================
SAP-like P2P Source-to-Award 业务场景: 通过 ontology.py / knowledge_base.py /
rules.py / advisor.py 四件套实现模块化注册。

主要能力:
  - 寻源管理: SourceList 推荐 + 物料价格主数据校验
  - 智能体编排: 创建 PR → 审批 → 转 PO → 审批 → 跟踪交货
  - 跨单据追溯: PR → PO → GR 三单匹配
  - 风险预警: 价格偏离 + 交货逾期 + 审批延期
"""
from scenarios.procurement.ontology import (
    PROCUREMENT_ENTITY_COLORS,
    PROCUREMENT_ENTITY_SCHEMAS,
    PROCUREMENT_RELATION_SCHEMAS,
)
from scenarios.procurement.knowledge_base import build_procurement_knowledge_base
from scenarios.procurement.rules import build_procurement_rules, RuleEngine
from scenarios.procurement.advisor import (
    EXAMPLE_QUESTIONS,
    INTENT_KEYWORDS,
    RULE_FLOWS as PROCUREMENT_RULE_FLOWS,
    RULE_MEANINGS,
    ask as procurement_ask,
)

__all__ = [
    "PROCUREMENT_ENTITY_COLORS",
    "PROCUREMENT_ENTITY_SCHEMAS",
    "PROCUREMENT_RELATION_SCHEMAS",
    "build_procurement_knowledge_base",
    "build_procurement_rules",
    "RuleEngine",
    "EXAMPLE_QUESTIONS",
    "INTENT_KEYWORDS",
    "PROCUREMENT_RULE_FLOWS",
    "RULE_MEANINGS",
    "procurement_ask",
]
