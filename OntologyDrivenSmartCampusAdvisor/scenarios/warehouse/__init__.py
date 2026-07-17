"""
仓库场景 (Warehouse Scenario) 包入口
====================================
SAP 操作自动化 + 库存预测场景: 通过 ontology.py / knowledge_base.py /
rules.py / advisor.py 四件套实现模块化注册。

主要能力:
  - 智能体编排: 收料 / 发料 / 调拨 / 盘点 / 报表生成
  - 跨部门交互: 采购 → 仓储 → 计划 自动衔接
  - 异常兜底:   库存不足 / 库位满载 / 批次冲突时输出备选方案
  - 库存风险预警: 呆滞料识别 + 跨工厂物化
"""
from scenarios.warehouse.ontology import (
    WAREHOUSE_ENTITY_COLORS,
    WAREHOUSE_ENTITY_SCHEMAS,
    WAREHOUSE_RELATION_SCHEMAS,
)
from scenarios.warehouse.knowledge_base import build_warehouse_knowledge_base
from scenarios.warehouse.rules import build_warehouse_rules, RuleEngine
from scenarios.warehouse.advisor import (
    EXAMPLE_QUESTIONS,
    INTENT_KEYWORDS,
    RULE_FLOWS as WAREHOUSE_RULE_FLOWS,
    ask as warehouse_ask,
)

__all__ = [
    "WAREHOUSE_ENTITY_COLORS",
    "WAREHOUSE_ENTITY_SCHEMAS",
    "WAREHOUSE_RELATION_SCHEMAS",
    "build_warehouse_knowledge_base",
    "build_warehouse_rules",
    "RuleEngine",
    "EXAMPLE_QUESTIONS",
    "INTENT_KEYWORDS",
    "WAREHOUSE_RULE_FLOWS",
    "warehouse_ask",
]