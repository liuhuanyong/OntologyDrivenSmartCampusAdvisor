"""
仓库场景 ABox (实例数据)
========================
Smart Campus 场景的姊妹篇: Warehouse / SAP 操作自动化场景。

规模: 3 工厂 · 15 物料 · 8 供应商 · 6 客户 · 12 库位 · 22 库存 · 12 任务 · 8 文档
覆盖: 智能体编排(收料/发料/调拨/盘点/报表) + 跨部门交互 + 呆滞物化预警
"""
from __future__ import annotations

from ontology import KnowledgeGraph


def build_warehouse_knowledge_base() -> KnowledgeGraph:
    """构建仓库场景实例底座。

    Returns:
        KnowledgeGraph: 已加载实体 / 关系的 KG 实例。
    """
    kg = KnowledgeGraph()
    # 临时覆盖 schema —— 这样仓库专有类型可被 add_entity/add_relation 接受。
    # NOTE: KnowledgeGraph.add_entity/add_relation 会校验全局 schema,
    # 因此我们这里直接 monkey-patch 注入仓库专属 schema。
    from ontology import ENTITY_SCHEMAS, RELATION_SCHEMAS, ENTITY_COLORS
    from scenarios.warehouse.ontology import (
        WAREHOUSE_ENTITY_SCHEMAS, WAREHOUSE_RELATION_SCHEMAS, WAREHOUSE_ENTITY_COLORS,
    )
    ENTITY_SCHEMAS.update(WAREHOUSE_ENTITY_SCHEMAS)
    RELATION_SCHEMAS.update(WAREHOUSE_RELATION_SCHEMAS)
    ENTITY_COLORS.update(WAREHOUSE_ENTITY_COLORS)

    # ========================================================== #
    # 1. 工厂 Plant (3)
    # ========================================================== #
    plants = [
        ("plant:sh01", "SH01", "上海中央仓",  "华东", "DC"),
        ("plant:sz02", "SZ02", "深圳区域仓",  "华南", "Regional"),
        ("plant:cd03", "CD03", "成都区域仓",  "西南", "Regional"),
    ]
    for eid, code, name, region, pt in plants:
        kg.add_entity(eid, "Plant", code=code, name=name,
                      region=region, plant_type=pt)

    # ========================================================== #
    # 2. 物料 Material (15)
    # ========================================================== #
    materials = [
        # code, name, category, uom, perishable, hazardous
        ("mat:rm001",  "RM001",  "电子元件-主控芯片",       "原材料", "EA", False, False),
        ("mat:rm002",  "RM002",  "PCB 主板",              "原材料", "EA", False, False),
        ("mat:rm003",  "RM003",  "锂电池 18650",          "原材料", "EA", False, True),
        ("mat:rm004",  "RM004",  "ABS 塑胶粒",            "原材料", "KG", False, False),
        ("mat:sf001",  "SF001",  "半成品-外壳组件",        "半成品", "EA", False, False),
        ("mat:sf002",  "SF002",  "半成品-主板组件",        "半成品", "EA", False, False),
        ("mat:fg001",  "FG001",  "智能终端-A 型机",        "成品",   "EA", False, False),
        ("mat:fg002",  "FG002",  "智能终端-B 型机",        "成品",   "EA", False, False),
        ("mat:fg003",  "FG003",  "工业控制器",            "成品",   "EA", False, False),
        ("mat:sp001",  "SP001",  "电源适配器 65W",        "备件",   "EA", False, False),
        ("mat:sp002",  "SP002",  "散热风扇 40mm",         "备件",   "EA", False, False),
        ("mat:sp003",  "SP003",  "包装纸箱 5 层",          "备件",   "BOX", False, False),
        ("mat:rm005",  "RM005",  "生鲜原料-冷链物料 A",   "原材料", "KG", True,  False),
        ("mat:rm006",  "RM006",  "化工原料-粘合剂",       "原材料", "KG", False, True),
        ("mat:fg004",  "FG004",  "生鲜成品-预制菜",        "成品",   "KG", True,  False),
    ]
    for eid, code, name, cat, uom, per, haz in materials:
        kg.add_entity(eid, "Material", code=code, name=name, category=cat,
                      uom=uom, perishable=per, hazardous=haz)

    # 每个物料归属主工厂 (一个物料可跨工厂, 这里给每物料分配一个默认主工厂)
    mat_to_plant = [
        ("mat:rm001", "plant:sh01"), ("mat:rm002", "plant:sh01"),
        ("mat:rm003", "plant:sh01"), ("mat:rm004", "plant:sz02"),
        ("mat:sf001", "plant:sh01"), ("mat:sf002", "plant:sz02"),
        ("mat:fg001", "plant:sh01"), ("mat:fg002", "plant:sz02"),
        ("mat:fg003", "plant:cd03"), ("mat:sp001", "plant:sh01"),
        ("mat:sp002", "plant:sz02"), ("mat:sp003", "plant:cd03"),
        ("mat:rm005", "plant:sz02"), ("mat:rm006", "plant:cd03"),
        ("mat:fg004", "plant:sz02"),
    ]
    for mid, pid in mat_to_plant:
        kg.add_relation(mid, "belongs_to_plant", pid)

    # ========================================================== #
    # 3. 供应商 Supplier (8)
    # ========================================================== #
    suppliers = [
        ("sup:s01", "S01", "深圳芯联电子",  "A", "Net30"),
        ("sup:s02", "S02", "华强 PCB 厂",   "A", "Net30"),
        ("sup:s03", "S03", "宁德锂电",     "A", "Net60"),
        ("sup:s04", "S04", "中石化塑胶",   "B", "Net45"),
        ("sup:s05", "S05", "比亚迪精密",   "A", "Net30"),
        ("sup:s06", "S06", "富士康华东",   "B", "Net60"),
        ("sup:s07", "S07", "顺丰冷链",     "A", "Net15"),
        ("sup:s08", "S08", "万华化工",     "C", "Net45"),
    ]
    for eid, code, name, rating, terms in suppliers:
        kg.add_entity(eid, "Supplier", code=code, name=name,
                      rating=rating, payment_terms=terms)

    supplier_map = [
        ("sup:s01", "mat:rm001", 14, 500),
        ("sup:s02", "mat:rm002", 21, 200),
        ("sup:s03", "mat:rm003", 30, 1000),
        ("sup:s04", "mat:rm004", 7,  3000),
        ("sup:s05", "mat:sf001", 10, 200),
        ("sup:s06", "mat:sf002", 14, 200),
        ("sup:s03", "mat:rm003", 30, 1000),  # 双供应商示例
        ("sup:s07", "mat:rm005", 3,  500),
        ("sup:s08", "mat:rm006", 14, 1000),
        ("sup:s04", "mat:rm004", 7,  3000),
        ("sup:s05", "mat:sf001", 10, 200),
        ("sup:s06", "mat:sf002", 14, 200),
    ]
    for sid, mid, lead, moq in supplier_map:
        kg.add_relation(sid, "supplies_to", mid,
                        lead_time_days=lead, min_order_qty=moq)

    # ========================================================== #
    # 4. 客户/需求部门 Customer (6)
    # ========================================================== #
    customers = [
        ("cus:prod01", "C001", "总装车间",     "internal"),
        ("cus:prod02", "C002", "华南分厂",     "internal"),
        ("cus:aft01",  "C003", "客户服务中心", "internal"),
        ("cus:ext01",  "C004", "深圳电子市场", "external"),
        ("cus:ext02",  "C005", "杭州智能家居", "external"),
        ("cus:rnd01",  "C006", "研发中心",     "internal"),
    ]
    for eid, code, name, ct in customers:
        kg.add_entity(eid, "Customer", code=code, name=name, customer_type=ct)

    demand_map = [
        ("cus:prod01", "mat:rm001", 800),
        ("cus:prod01", "mat:rm002", 600),
        ("cus:prod01", "mat:sf001", 400),
        ("cus:prod01", "mat:fg003", 200),
        ("cus:prod02", "mat:rm004", 2500),
        ("cus:prod02", "mat:fg002", 300),
        ("cus:aft01",  "mat:sp001", 100),
        ("cus:aft01",  "mat:sp002", 200),
        ("cus:ext01",  "mat:fg001", 500),
        ("cus:ext01",  "mat:fg002", 400),
        ("cus:ext02",  "mat:fg001", 800),
        ("cus:ext02",  "mat:fg003", 250),
        ("cus:rnd01",  "mat:rm001", 100),
        ("cus:rnd01",  "mat:rm002", 50),
    ]
    for cid, mid, qty in demand_map:
        kg.add_relation(cid, "demands", mid, avg_monthly_qty=qty)

    # ========================================================== #
    # 5. 库位 StorageBin (12)
    # ========================================================== #
    bins = [
        # eid, bin_id, zone, capacity, location
        ("bin:sh-a01", "SH-A01", "A-常温",   2000, "上海仓 A 区 01 排"),
        ("bin:sh-a02", "SH-A02", "A-常温",   2000, "上海仓 A 区 02 排"),
        ("bin:sh-b01", "SH-B01", "B-冷藏",   500,  "上海仓 B 区 01 排"),
        ("bin:sh-d01", "SH-D01", "D-高架",   5000, "上海仓 D 区 01 排"),
        ("bin:sz-a01", "SZ-A01", "A-常温",   2000, "深圳仓 A 区 01 排"),
        ("bin:sz-a02", "SZ-A02", "A-常温",   2000, "深圳仓 A 区 02 排"),
        ("bin:sz-b01", "SZ-B01", "B-冷藏",   500,  "深圳仓 B 区 01 排"),
        ("bin:sz-c01", "SZ-C01", "C-危化品", 800,  "深圳仓 C 区 01 排"),
        ("bin:cd-a01", "CD-A01", "A-常温",   1500, "成都仓 A 区 01 排"),
        ("bin:cd-d01", "CD-D01", "D-高架",   5000, "成都仓 D 区 01 排"),
        ("bin:cd-c01", "CD-C01", "C-危化品", 600,  "成都仓 C 区 01 排"),
        ("bin:cd-qc",  "CD-QC",  "QC-待检",  500,  "成都仓 QC 暂存"),
    ]
    for eid, bid, zone, cap, loc in bins:
        kg.add_entity(eid, "StorageBin", bin_id=bid, zone=zone,
                      capacity=cap, location=loc)

    # ========================================================== #
    # 6. 库存记录 StockRecord (22)
    # ========================================================== #
    # 重点: days_idle 字段驱动呆滞料识别 (>180 天 即视为呆滞风险)
    stocks = [
        # eid, material, bin, qty, lot, last_movement, days_idle, status, safety_stock
        ("stk:0001", "mat:rm001", "bin:sh-a01", 3200, "L20240101", "2025-01-10", 45,  "normal",   500),
        ("stk:0002", "mat:rm002", "bin:sh-a01", 1500, "L20240115", "2024-08-15", 200, "obsolete", 200),
        ("stk:0003", "mat:rm003", "bin:sh-c01",  800, "L20240201", "2025-03-01", 30,  "normal",   300),
        ("stk:0004", "mat:rm004", "bin:sz-a02", 5800, "L20240220", "2024-05-20", 280, "obsolete", 500),
        ("stk:0005", "mat:sf001", "bin:sh-a02",  900, "L20240301", "2025-05-01", 5,   "normal",   200),
        ("stk:0006", "mat:sf002", "bin:sz-a01",  450, "L20240315", "2025-04-15", 20,  "normal",   200),
        ("stk:0007", "mat:fg001", "bin:sh-d01", 1200, "L20240401", "2024-09-01", 240, "obsolete", 300),
        ("stk:0008", "mat:fg002", "bin:sz-d01",  600, "L20240415", "2024-07-15", 260, "obsolete", 300),
        ("stk:0009", "mat:fg003", "bin:cd-d01",  400, "L20240501", "2025-06-01", 0,   "normal",   150),
        ("stk:0010", "mat:sp001", "bin:sh-a02",  150, "L20240510", "2025-05-10", 10,  "normal",   100),
        ("stk:0011", "mat:sp002", "bin:sz-a01",  280, "L20240520", "2024-10-20", 220, "obsolete", 100),
        ("stk:0012", "mat:sp003", "bin:cd-a01",  900, "L20240601", "2025-06-01", 0,   "normal",   200),
        ("stk:0013", "mat:rm005", "bin:sz-b01",  120, "L20240610", "2024-12-10", 130, "normal",   100),
        ("stk:0014", "mat:rm006", "bin:cd-c01",  450, "L20240615", "2024-06-15", 290, "obsolete", 100),
        ("stk:0015", "mat:fg004", "bin:sz-b01",   60, "L20240701", "2025-06-30", 1,   "normal",    50),
        # 冻结 / 异常状态
        ("stk:0016", "mat:rm003", "bin:sh-d01",  150, "L20240715", "2024-04-15", 320, "frozen",   0),
        ("stk:0017", "mat:rm001", "bin:sh-a02",  100, "L20240801", "2024-11-01", 180, "obsolete", 500),
        ("stk:0018", "mat:rm002", "bin:sz-a02",  300, "L20240815", "2025-04-15", 20,  "normal",   200),
        ("stk:0019", "mat:fg001", "bin:cd-d01",  250, "L20240901", "2024-09-01", 240, "obsolete", 300),
        ("stk:0020", "mat:fg002", "bin:cd-a01",  180, "L20240915", "2025-05-15", 10,  "normal",   300),
        ("stk:0021", "mat:sp001", "bin:sh-d01",  120, "L20241001", "2024-10-01", 270, "obsolete", 100),
        ("stk:0022", "mat:sf001", "bin:cd-a01",  220, "L20241015", "2024-11-15", 175, "normal",   200),
    ]
    for eid, mid, bid, qty, lot, lm, idle, status, ss in stocks:
        kg.add_entity(eid, "StockRecord", qty=qty, lot_no=lot,
                      last_movement=lm, days_idle=idle,
                      status=status, safety_stock=ss)
        kg.add_relation(eid, "stored_at", bid)
        # holds_stock 由 bin 反向视角提供 (qty + safety)
        kg.add_relation(bid, "holds_stock", mid, qty=qty, safety_stock=ss)

    # ========================================================== #
    # 7. 知识库文档 KBDoc (8) —— 基层员工 SOP + 培训
    # ========================================================== #
    kb_docs = [
        ("doc:sop-receipt", "SOP-WH-001 收料标准作业", "SOP",
         "1) 核对送货单与 PO 一致性; 2) 抽样质检; 3) 录入批次; 4) 上架至推荐库位; "
         "5) 更新 SAP MIGO 事务码; 6) 通知采购员收货确认。"),
        ("doc:sop-issue",   "SOP-WH-002 发料标准作业", "SOP",
         "1) 核对领料单; 2) 按 FIFO 原则拣选; 3) 复核数量与批次; 4) 扫描出库; "
         "5) SAP MB1A 事务码过账; 6) 通知需求部门取货。"),
        ("doc:sop-transfer", "SOP-WH-003 调拨标准作业", "SOP",
         "1) 确认调拨单; 2) 源库位下架; 3) 在途登记; 4) 目标库位收货确认; "
         "5) SAP MB1B 事务码; 6) 同步更新库存可见性。"),
        ("doc:sop-stocktake", "SOP-WH-004 盘点标准作业", "SOP",
         "1) 选择盘点策略 (ABC 分类); 2) 冻结库位; 3) 实物清点; 4) 与系统对比差异; "
         "5) 差异分析与责任判定; 6) SAP MI09 事务码调整。"),
        ("doc:kb-obsolete", "呆滞料识别与处理指南", "培训",
         "判定: 连续 180 天无移动 + 库存 > 安全库存; 措施: E&O 评审 → "
         "调拨/促销/报废; 责任部门: 计划 + 采购。"),
        ("doc:kb-handoff", "跨部门交接指引", "培训",
         "采购 → 仓储 → 计划 → 生产 → 售后: 各环节交接时限、责任人、SLA。"),
        ("doc:faq-lot", "批次冲突 FAQ", "FAQ",
         "Q: 同一物料多批次入库如何处理? A: 按入库时间排序, FIFO 出库, "
         "但冷链 / 危化品按专门策略。"),
        ("doc:kb-report", "库存报表生成指引", "政策",
         "日 / 周 / 月 报表模板; 自动生成 VS 人工介入阈值; 异常情况上报路径。"),
    ]
    for eid, title, cat, content in kb_docs:
        kg.add_entity(eid, "KBDoc", doc_id=eid.split(":")[1], title=title,
                      category=cat, content=content)

    # ========================================================== #
    # 8. 智能体任务 AgentTask (12)
    #    覆盖收料/发料/调拨/盘点/报表五大类, 含跨部门交互
    # ========================================================== #
    tasks = [
        # (eid, type, state, assignee, priority, created)
        ("task:t0001", "receipt",   "pending",  "采购员",  "urgent",  "2025-06-25"),
        ("task:t0002", "receipt",   "running",  "仓储员",  "standard","2025-06-26"),
        ("task:t0003", "issue",     "pending",  "计划员",  "standard","2025-06-26"),
        ("task:t0004", "issue",     "running",  "调度员",  "urgent",  "2025-06-27"),
        ("task:t0005", "transfer",  "pending",  "调度员",  "standard","2025-06-24"),
        ("task:t0006", "transfer",  "done",     "仓储员",  "standard","2025-06-20"),
        ("task:t0007", "stocktake", "pending",  "仓储员",  "standard","2025-06-25"),
        ("task:t0008", "stocktake", "done",     "仓储员",  "standard","2025-06-15"),
        ("task:t0009", "report",    "done",     "调度员",  "standard","2025-06-01"),
        ("task:t0010", "receipt",   "failed",   "采购员",  "return",  "2025-06-22"),
        ("task:t0011", "issue",     "pending",  "计划员",  "urgent",  "2025-06-28"),
        ("task:t0012", "report",    "running",  "调度员",  "standard","2025-06-27"),
    ]
    for eid, ttype, state, assignee, prio, created in tasks:
        kg.add_entity(eid, "AgentTask", task_id=eid.split(":")[1],
                      task_type=ttype, state=state, assignee=assignee,
                      priority=prio, created_at=created)

    # 任务 ↔ 物料 / 工厂 / 角色文档 的关联
    task_links = [
        ("task:t0001", "mat:rm001", "plant:sh01", "doc:sop-receipt", "采购员"),
        ("task:t0002", "mat:rm003", "plant:sh01", "doc:sop-receipt", "仓储员"),
        ("task:t0003", "mat:fg003", "plant:cd03", "doc:sop-issue",   "计划员"),
        ("task:t0004", "mat:fg001", "plant:sh01", "doc:sop-issue",   "调度员"),
        ("task:t0005", "mat:rm002", "plant:sz02", "doc:sop-transfer","调度员"),
        ("task:t0006", "mat:rm004", "plant:sz02", "doc:sop-transfer","仓储员"),
        ("task:t0007", "bin:sh-a01", "plant:sh01","doc:sop-stocktake","仓储员"),
        ("task:t0008", "bin:cd-a01", "plant:cd03","doc:sop-stocktake","仓储员"),
        ("task:t0009", "plant:sh01","plant:sh01", "doc:kb-report",   "调度员"),
        ("task:t0010", "mat:rm002", "plant:sh01", "doc:sop-receipt", "采购员"),
        ("task:t0011", "mat:fg002", "plant:sz02", "doc:sop-issue",   "计划员"),
        ("task:t0012", "plant:cd03","plant:cd03", "doc:kb-report",   "调度员"),
    ]
    for tid, mid, pid, did, role in task_links:
        kg.add_relation(tid, "task_targets_material", mid)
        kg.add_relation(tid, "task_in_plant", pid)
        kg.add_relation(tid, "requires_role", did, role=role)

    return kg


if __name__ == "__main__":
    kg = build_warehouse_knowledge_base()
    print(f"仓库场景 KG: {kg}")
    print(f"统计: {kg.stats()}")
    from collections import Counter
    dist = Counter(e.etype for e in kg.list_entities())
    print("实体分布:", dict(dist))