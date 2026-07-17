"""
仓库场景 TBox (Ontology 定义)
=============================
仓库管理与库存控制场景的本体 Schema: 8 类实体 + 12 类关系 + 颜色方案。

本模块与全局 ontology.py 解耦 —— 不修改全局 schema,
而是把仓库专属的 schema 注册为独立的常量, 供 build_warehouse_* 流程使用。
"""
from __future__ import annotations


# --------------------------------------------------------------------------- #
# 1. 实体类型 (Concept) + 属性 schema
# --------------------------------------------------------------------------- #
WAREHOUSE_ENTITY_SCHEMAS: dict[str, dict[str, type]] = {
    "Plant": {
        "code": str,
        "name": str,
        "region": str,        # 华东/华南/西南
        "plant_type": str,    # DC(中央仓) / Regional(区域仓)
    },
    "Material": {
        "code": str,
        "name": str,
        "category": str,      # 原材料 / 半成品 / 成品 / 备件
        "uom": str,           # 单位: EA / KG / BOX / L
        "perishable": bool,   # 是否易腐
        "hazardous": bool,    # 是否危险品
    },
    "Supplier": {
        "code": str,
        "name": str,
        "rating": str,        # A/B/C/D
        "payment_terms": str, # Net30 / Net60 等
    },
    "Customer": {
        "code": str,
        "name": str,
        "customer_type": str, # internal(内部需求部门) / external(外部客户)
    },
    "StorageBin": {
        "bin_id": str,
        "zone": str,          # A 区常温 / B 区冷藏 / C 区危险品 / D 区高架
        "capacity": int,
        "location": str,      # 物理位置描述
    },
    "StockRecord": {
        "qty": int,
        "lot_no": str,
        "last_movement": str,    # ISO 日期
        "days_idle": int,        # 距上次移动天数
        "status": str,           # normal / obsolete / frozen
        "safety_stock": int,
    },
    "AgentTask": {
        "task_id": str,
        "task_type": str,    # receipt / issue / transfer / stocktake / report
        "state": str,        # pending / running / done / failed
        "assignee": str,     # 智能体角色: 采购员/仓储员/计划员/调度员
        "priority": str,     # standard / urgent / return
        "created_at": str,
    },
    "KBDoc": {
        "doc_id": str,
        "title": str,
        "category": str,     # SOP / 培训 / FAQ / 政策
        "content": str,
    },
}


# --------------------------------------------------------------------------- #
# 2. 关系类型 (Object Property) —— 12 类
# --------------------------------------------------------------------------- #
WAREHOUSE_RELATION_SCHEMAS: dict[str, dict] = {
    # ---- 组织结构 ---- #
    "supplies_to":     {"domain": "Supplier", "range": "Material",
                       "edge": {"lead_time_days": int, "min_order_qty": int}},
    "demands":         {"domain": "Customer", "range": "Material",
                       "edge": {"avg_monthly_qty": int}},
    "belongs_to_plant": {"domain": "Material", "range": "Plant", "edge": {}},

    # ---- 库存物理 ---- #
    "stored_at":       {"domain": "StockRecord", "range": "StorageBin", "edge": {}},
    "holds_stock":     {"domain": "StorageBin", "range": "Material",
                       "edge": {"qty": int, "safety_stock": int}},

    # ---- SAP 事务操作 (智能体编排动作) ---- #
    "sap_receipt":     {"domain": "AgentTask", "range": "StockRecord",
                       "edge": {"qty": int, "lot_no": str, "supplier": str,
                                "bin": str, "step": str}},
    "sap_issue":       {"domain": "AgentTask", "range": "StockRecord",
                       "edge": {"qty": int, "customer": str, "bin": str, "step": str}},
    "sap_transfer":    {"domain": "AgentTask", "range": "StockRecord",
                       "edge": {"qty": int, "from_bin": str, "to_bin": str, "step": str}},
    "sap_stocktake":   {"domain": "AgentTask", "range": "StorageBin",
                       "edge": {"strategy": str, "step": str}},
    "sap_report":      {"domain": "AgentTask", "range": "Plant",
                       "edge": {"report_type": str, "step": str}},

    # ---- 任务编排关联 ---- #
    "task_targets_material": {"domain": "AgentTask", "range": "Material", "edge": {}},
    "task_in_plant":         {"domain": "AgentTask", "range": "Plant",    "edge": {}},
    "requires_role":         {"domain": "AgentTask", "range": "KBDoc",
                             "edge": {"role": str}},

    # ---- 派生关系 (物化) ---- #
    "at_risk_of_obsolete":   {"domain": "Material", "range": "StockRecord",
                             "edge": {"risk_level": str, "days_idle": int,
                                      "excess_qty": int}},
}


# --------------------------------------------------------------------------- #
# 3. 实体类型颜色 (前端可视化)
# --------------------------------------------------------------------------- #
WAREHOUSE_ENTITY_COLORS: dict[str, str] = {
    "Plant":       "#0ea5e9",  # 蓝
    "Material":    "#f59e0b",  # 橙
    "Supplier":    "#8b5cf6",  # 紫
    "Customer":    "#ec4899",  # 粉
    "StorageBin":  "#14b8a6",  # 青
    "StockRecord": "#10b981",  # 绿
    "AgentTask":   "#6366f1",  # 靛
    "KBDoc":       "#64748b",  # 灰
}


# 实体类型中文含义 (给前端 / 终端用户看)
ENTITY_LABELS_CN: dict[str, str] = {
    "Plant": "工厂/仓库",
    "Material": "物料",
    "Supplier": "供应商",
    "Customer": "需求部门/客户",
    "StorageBin": "库位",
    "StockRecord": "库存记录",
    "AgentTask": "智能体任务",
    "KBDoc": "知识库文档",
}