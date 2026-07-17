"""
采购场景 TBox (Ontology 定义)
=============================
基于用户提供的 p2pjh713.yaml SAP-like 采购 to Pay (P2P) Source-to-Award 本体模型:

  15 类实体 + 18 类关系 + 颜色方案

覆盖: 采购需求 PR → 采购订单 PO → 货物收货 GR 完整闭环
       + 供应商寻源 / 信息记录 (价格主数据) / 货源清单
"""
from __future__ import annotations


# --------------------------------------------------------------------------- #
# 1. 实体类型 (Concept) + 属性 schema
# --------------------------------------------------------------------------- #
PROCUREMENT_ENTITY_SCHEMAS: dict[str, dict[str, type]] = {
    # ---- 业务单据 (Source-to-Award 核心单据) ---- #
    "PurchaseRequisition": {
        "pr_id": str,
        "pr_type": str,          # standard / consignment / subcontract / service
        "pr_status": str,        # draft / pending_approval / approved / rejected / converted
        "doc_date": str,
        "applicant": str,        # 申请人姓名
        "dept": str,             # 申请部门
        "priority": str,         # normal / urgent
        "total_amount": int,
    },
    "RequisitionItem": {
        "pr_item_id": str,
        "quantity": int,
        "unit": str,             # EA / KG / M / L / BOX
        "unit_price": int,       # 不含税净价
        "delivery_date": str,    # 期望交货日期 (ISO)
        "plant_id": str,
        "location_id": str,
        "vendor_id": str,        # 建议供应商 (可空, 但 query 时用于推荐)
        "item_status": str,      # open / ordered / closed
        "cost_center": str,
    },
    "PurchaseOrder": {
        "po_id": str,
        "po_type": str,          # standard / urgent / cost_center / consignment
        "currency": str,         # CNY / USD / EUR
        "payment_terms": str,    # Net30 / Net60 / Net45
        "incoterms": str,        # FOB / CIF / EXW / DDP
        "doc_status": str,       # draft / pending_approval / approved / sent / partial / closed
        "doc_date": str,
        "vendor_id": str,
        "contract_amount": int,
    },
    "PurchaseOrderItem": {
        "po_item_id": str,
        "material_id": str,
        "quantity": int,
        "unit_price": int,
        "net_price": int,
        "delivery_date": str,
        "plant_id": str,
        "location_id": str,
        "delivered_qty": int,
        "invoiced_qty": int,
        "pr_ref": str,           # 上游 PR 号
    },
    "GoodsReceipt": {
        "gr_id": str,
        "gr_date": str,
        "vendor_id": str,
        "movement_type": str,    # 101 (收货) / 102 (退货冲销)
        "po_ref": str,           # 关联 PO 号
        "doc_status": str,       # posted / reversed
    },
    "GoodsReceiptItem": {
        "gr_item_id": str,
        "material_id": str,
        "quantity": int,
        "amount": int,
        "batch_id": str,
        "plant_id": str,
        "location_id": str,
        "stock_qty": int,        # 入库后库存
    },

    # ---- 主数据 ---- #
    "Supplier": {
        "vendor_id": str,
        "name": str,
        "country": str,
        "city": str,
        "contact": str,
        "phone": str,
        "email": str,
        "rating": str,           # A / B / C / D
        "payment_terms": str,    # 默认账期
    },
    "PurchasingOrg": {
        "org_id": str,
        "name": str,
        "company_id": str,
        "company_name": str,
    },
    "PurchasingGroup": {
        "group_id": str,
        "name": str,
        "email": str,
    },
    "Plant": {
        "plant_id": str,
        "name": str,
        "company_id": str,
        "address": str,
        "city": str,
    },
    "StorageLocation": {
        "location_id": str,
        "name": str,
        "plant_id": str,
        "status": str,           # active / inactive
    },
    "Material": {
        "material_id": str,
        "name": str,
        "category": str,         # 原材料 / 设备配件 / 服务 / 备件 / 成品
        "unit": str,
        "weight": int,
        "volume": int,
        "mat_group": str,
    },

    # ---- 寻源/价格 主数据 ---- #
    "SourceList": {
        "source_id": str,
        "material_id": str,
        "vendor_id": str,
        "plant_id": str,
        "org_id": str,
        "valid_from": str,
        "valid_to": str,
        "fixed_flag": bool,      # 是否固定供应商
        "mrp_flag": bool,        # 是否 MRP 自动货源
    },
    "InfoRecord": {
        "record_id": str,
        "material_id": str,
        "vendor_id": str,
        "net_price": int,        # 信息记录价格
        "moq": int,              # 最小订单量
        "lead_time": int,        # 计划交货时间 (天)
        "currency": str,
        "valid_from": str,
        "valid_to": str,
    },

    # ---- 知识库 ---- #
    "KBDoc": {
        "doc_id": str,
        "title": str,
        "category": str,         # SOP / 培训 / FAQ / 政策
        "content": str,
    },
}


# --------------------------------------------------------------------------- #
# 2. 关系类型 (Object Property) —— 18 类
# --------------------------------------------------------------------------- #
PROCUREMENT_RELATION_SCHEMAS: dict[str, dict] = {
    # ---- 单据关联 (Document Linking) ---- #
    "has_item":              {"domain": "PurchaseRequisition", "range": "RequisitionItem",
                              "edge": {}},
    "converts_to":           {"domain": "PurchaseRequisition", "range": "PurchaseOrder",
                              "edge": {"convert_date": str}},
    "has_po_item":           {"domain": "PurchaseOrder", "range": "PurchaseOrderItem",
                              "edge": {}},
    "receipt_of":            {"domain": "GoodsReceipt", "range": "PurchaseOrder",
                              "edge": {}},
    "receipt_item_of":       {"domain": "GoodsReceiptItem", "range": "PurchaseOrderItem",
                              "edge": {}},

    # ---- 组织关联 ---- #
    "belongs_to_org":        {"domain": "PurchaseOrder", "range": "PurchasingOrg",
                              "edge": {}},
    "belongs_to_group":      {"domain": "PurchaseOrder", "range": "PurchasingGroup",
                              "edge": {}},
    "belongs_to_plant":      {"domain": "RequisitionItem", "range": "Plant",
                              "edge": {}},
    # PR 创建流程推理链: Plant → 所属活跃库位 (可视化辅助)
    "has_location":          {"domain": "Plant", "range": "StorageLocation",
                              "edge": {"status": str}},
    "stored_at":             {"domain": "GoodsReceiptItem", "range": "StorageLocation",
                              "edge": {}},

    # ---- 寻源 / 价格 主数据关联 ---- #
    "supplies":              {"domain": "Supplier", "range": "Material",
                              "edge": {"lead_time_days": int, "min_order_qty": int}},
    "preferred_source":      {"domain": "Material", "range": "Supplier",
                              "edge": {"source_id": str}},
    "priced_by":             {"domain": "Material", "range": "InfoRecord",
                              "edge": {"net_price": int}},
    "source_by":             {"domain": "Material", "range": "SourceList",
                              "edge": {"valid": bool}},
    # PR 创建流程推理链: SourceList → 供应商 (可视化辅助)
    "sourced_from":          {"domain": "SourceList", "range": "Supplier",
                              "edge": {"rating": str, "fixed_flag": bool,
                                       "mrp_flag": bool, "score": int}},

    # ---- 业务归属 ---- #
    "po_targets_vendor":     {"domain": "PurchaseOrder", "range": "Supplier",
                              "edge": {}},
    "po_item_targets_material": {"domain": "PurchaseOrderItem", "range": "Material",
                                 "edge": {}},

    # ---- 任务编排 / 知识库关联 ---- #
    "task_targets_pr":       {"domain": "KBDoc", "range": "PurchaseRequisition",
                              "edge": {"role": str}},
    "task_targets_po":       {"domain": "KBDoc", "range": "PurchaseOrder",
                              "edge": {"role": str}},
    "requires_role":         {"domain": "PurchaseRequisition", "range": "KBDoc",
                              "edge": {"role": str}},

    # ---- 派生关系 (物化) ---- #
    "at_risk_of_delay":      {"domain": "PurchaseRequisition", "range": "PurchaseRequisition",
                              "edge": {"days_pending": int, "severity": str}},
}


# --------------------------------------------------------------------------- #
# 3. 实体类型颜色 (前端可视化)
# --------------------------------------------------------------------------- #
PROCUREMENT_ENTITY_COLORS: dict[str, str] = {
    "PurchaseRequisition": "#f59e0b",   # 橙 — PR
    "RequisitionItem":     "#fbbf24",   # 浅橙 — PR 行项目
    "PurchaseOrder":       "#3b82f6",   # 蓝 — PO
    "PurchaseOrderItem":   "#60a5fa",   # 浅蓝 — PO 行项目
    "GoodsReceipt":        "#10b981",   # 绿 — GR
    "GoodsReceiptItem":    "#34d399",   # 浅绿 — GR 行项目
    "Supplier":            "#8b5cf6",   # 紫 — 供应商
    "PurchasingOrg":       "#a78bfa",   # 浅紫 — 采购组织
    "PurchasingGroup":     "#c4b5fd",   # 更浅紫 — 采购组
    "Plant":               "#0ea5e9",   # 天蓝 — 工厂
    "StorageLocation":     "#06b6d4",   # 青 — 库存地点
    "Material":            "#f97316",   # 橙红 — 物料
    "SourceList":          "#d946ef",   # 品红 — 货源清单
    "InfoRecord":          "#ec4899",   # 粉 — 信息记录
    "KBDoc":               "#64748b",   # 灰 — 知识库
}


# 实体类型中文含义 (给前端 / 终端用户看)
ENTITY_LABELS_CN: dict[str, str] = {
    "PurchaseRequisition": "采购申请(PR)",
    "RequisitionItem":     "PR 行项目",
    "PurchaseOrder":       "采购订单(PO)",
    "PurchaseOrderItem":   "PO 行项目",
    "GoodsReceipt":        "采购收货(GR)",
    "GoodsReceiptItem":    "GR 行项目",
    "Supplier":            "供应商",
    "PurchasingOrg":       "采购组织",
    "PurchasingGroup":     "采购组",
    "Plant":               "工厂",
    "StorageLocation":     "库存地点",
    "Material":            "物料",
    "SourceList":          "货源清单",
    "InfoRecord":          "信息记录",
    "KBDoc":               "知识库文档",
}


# 关系类型中文含义
RELATION_LABELS_CN: dict[str, str] = {
    "has_item":              "包含行项目",
    "converts_to":           "转成采购订单",
    "has_po_item":           "包含订单行",
    "receipt_of":            "收货对应订单",
    "receipt_item_of":       "收货行对应订单行",
    "belongs_to_org":        "归属于采购组织",
    "belongs_to_group":      "归属于采购组",
    "belongs_to_plant":      "收货/需求工厂",
    "has_location":          "工厂拥有库位",
    "stored_at":             "入库至库位",
    "supplies":              "供应商供货",
    "preferred_source":      "首选货源",
    "priced_by":             "价格取自信息记录",
    "source_by":             "货源来自货源清单",
    "sourced_from":          "货源指向供应商",
    "po_targets_vendor":     "订单指定供应商",
    "po_item_targets_material": "订单行指定物料",
    "task_targets_pr":       "SOP 适用于 PR",
    "task_targets_po":       "SOP 适用于 PO",
    "requires_role":         "需要角色审批",
    "at_risk_of_delay":      "存在延期风险",
}
