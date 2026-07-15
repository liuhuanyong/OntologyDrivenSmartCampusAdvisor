"""
采购场景 ABox (实例数据)
========================
基于 p2pjh713.yaml 的 SAP-like P2P 业务对象图谱实例化。

规模: 4 工厂 · 6 供应商 · 3 采购组织 · 3 采购组 · 6 库位 · 15 物料 · 8 信息记录
      8 货源清单 · 5 PR · 10 PR 行 · 4 PO · 8 PO 行 · 3 GR · 6 GR 行 · 8 KB

覆盖: 完整采购到付款闭环 (Source → Award → Receipt)
"""
from __future__ import annotations

from ontology import KnowledgeGraph


def build_procurement_knowledge_base() -> KnowledgeGraph:
    """构建采购场景实例底座。

    Returns:
        KnowledgeGraph: 已加载实体 / 关系的 KG 实例。
    """
    kg = KnowledgeGraph()
    # 注入采购场景专属 schema (与全局 schema 合并)
    from ontology import ENTITY_SCHEMAS, RELATION_SCHEMAS, ENTITY_COLORS
    from scenarios.procurement.ontology import (
        PROCUREMENT_ENTITY_SCHEMAS, PROCUREMENT_RELATION_SCHEMAS,
        PROCUREMENT_ENTITY_COLORS,
    )
    ENTITY_SCHEMAS.update(PROCUREMENT_ENTITY_SCHEMAS)
    RELATION_SCHEMAS.update(PROCUREMENT_RELATION_SCHEMAS)
    ENTITY_COLORS.update(PROCUREMENT_ENTITY_COLORS)

    # ========================================================== #
    # 1. 工厂 Plant (4)
    # ========================================================== #
    plants = [
        ("plant:p100", "P100", "上海中央工厂",   "C100", "上海市浦东新区张江路 100 号", "上海"),
        ("plant:p200", "P200", "深圳南山分厂",   "C100", "深圳市南山区科技园路 1 号",  "深圳"),
        ("plant:p300", "P300", "成都高新分厂",   "C200", "成都市高新区天府大道 88 号",  "成都"),
        ("plant:p400", "P400", "苏州工业园",     "C100", "苏州市工业园区星湖街 328 号", "苏州"),
    ]
    for eid, pid, name, comp, addr, city in plants:
        kg.add_entity(eid, "Plant", plant_id=pid, name=name,
                      company_id=comp, address=addr, city=city)

    # ========================================================== #
    # 2. 库存地点 StorageLocation (6)
    # ========================================================== #
    locations = [
        ("loc:p100-rm",  "RM01", "P100", "原材料库", "active"),
        ("loc:p100-sf",  "SF01", "P100", "半成品库", "active"),
        ("loc:p100-fg",  "FG01", "P100", "成品库",   "active"),
        ("loc:p200-rm",  "RM02", "P200", "原材料库", "active"),
        ("loc:p200-fg",  "FG02", "P200", "成品库",   "active"),
        ("loc:p300-rm",  "RM03", "P300", "原材料库", "active"),
    ]
    for eid, lid, pid, name, status in locations:
        kg.add_entity(eid, "StorageLocation", location_id=lid, name=name,
                      plant_id=pid, status=status)

    # ========================================================== #
    # 3. 物料 Material (15)
    # ========================================================== #
    materials = [
        ("mat:m1001", "M1001", "电子元件-主控芯片 STM32",     "原材料",  "EA", 50,  10,  "ELEC"),
        ("mat:m1002", "M1002", "PCB 主板 双层 100x80mm",      "原材料",  "EA", 80,  20,  "ELEC"),
        ("mat:m1003", "M1003", "锂电池 18650 3000mAh",         "原材料",  "EA", 45,  15,  "BATT"),
        ("mat:m1004", "M1004", "ABS 塑胶粒 工业级",            "原材料",  "KG", 1000, 800, "PLAS"),
        ("mat:m1005", "M1005", "精密轴承 6204-2RS",            "设备配件","EA", 200, 50,  "MECH"),
        ("mat:m1006", "M1006", "液压阀 DN20 16MPa",            "设备配件","EA", 1500, 200,"MECH"),
        ("mat:m1007", "M1007", "工业仪表 PT100 温度传感器",     "设备配件","EA", 30,  10,  "INST"),
        ("mat:m1008", "M1008", "化工原料-环氧树脂",             "原材料",  "KG", 1100, 850,"CHEM"),
        ("mat:m1009", "M1009", "不锈钢管 DN50 304",            "原材料",  "M",  1500, 100,"METL"),
        ("mat:m1010", "M1010", "包装纸箱 5 层 KK 380*260*200",  "备件",    "BOX", 800, 1500,"PKG"),
        ("mat:m1011", "M1011", "冷却液乙二醇 工业级",          "原材料",  "L",  1100, 900,"CHEM"),
        ("mat:m1012", "M1012", "智能终端-A 型机",              "成品",    "EA", 1200, 1500,"PROD"),
        ("mat:m1013", "M1013", "工业控制器 PLC-S200",          "成品",    "EA", 800, 600,"PROD"),
        ("mat:m1014", "M1014", "设备维护服务包-季度",          "服务",    "EA", 0,   0,  "SERV"),
        ("mat:m1015", "M1015", "实验室校准服务",               "服务",    "EA", 0,   0,  "SERV"),
    ]
    for eid, mid, name, cat, unit, weight, vol, grp in materials:
        kg.add_entity(eid, "Material", material_id=mid, name=name,
                      category=cat, unit=unit, weight=weight,
                      volume=vol, mat_group=grp)

    # ========================================================== #
    # 4. 供应商 Supplier (6)
    # ========================================================== #
    suppliers = [
        ("sup:v001", "V001", "深圳芯联电子",      "CN", "深圳",  "张经理",   "13800001001", "sales@xinlian.cn",      "A", "Net30"),
        ("sup:v002", "V002", "华强 PCB 厂",       "CN", "深圳",  "李经理",   "13800001002", "order@huaqiangpcb.cn",  "A", "Net30"),
        ("sup:v003", "V003", "宁德时代锂电",      "CN", "宁德",  "王经理",   "13800001003", "b2b@catlbattery.cn",    "A", "Net60"),
        ("sup:v004", "V004", "中石化塑胶",        "CN", "上海",  "陈经理",   "13800001004", "plastic@sinopec.cn",    "B", "Net45"),
        ("sup:v005", "V005", "SKF 轴承直供",     "DE", "上海",  "Mr Schmidt","13800001005", "china@skf-direct.com",  "A", "Net30"),
        ("sup:v006", "V006", "万华化工",          "CN", "烟台",  "刘经理",   "13800001006", "epoxy@wanhua.cn",       "C", "Net45"),
    ]
    for eid, vid, name, country, city, contact, phone, email, rating, terms in suppliers:
        kg.add_entity(eid, "Supplier", vendor_id=vid, name=name, country=country,
                      city=city, contact=contact, phone=phone, email=email,
                      rating=rating, payment_terms=terms)

    # ========================================================== #
    # 5. 采购组织 / 采购组
    # ========================================================== #
    orgs = [
        ("porg:po100", "PO100", "上海采购中心", "C100", "上海总公司"),
        ("porg:po200", "PO200", "深圳采购部",   "C100", "上海总公司"),
        ("porg:po300", "PO300", "成都采购点",   "C200", "成都子公司"),
    ]
    for eid, oid, name, comp, cname in orgs:
        kg.add_entity(eid, "PurchasingOrg", org_id=oid, name=name,
                      company_id=comp, company_name=cname)

    groups = [
        ("pgrp:g01", "G01", "电子物料采购组",   "elec-procure@company.cn"),
        ("pgrp:g02", "G02", "机械配件采购组",   "mech-procure@company.cn"),
        ("pgrp:g03", "G03", "服务采购组",       "service-procure@company.cn"),
    ]
    for eid, gid, name, email in groups:
        kg.add_entity(eid, "PurchasingGroup", group_id=gid, name=name, email=email)

    # ========================================================== #
    # 6. 信息记录 InfoRecord (8) —— 价格主数据
    # ========================================================== #
    info_records = [
        ("ir:r01", "mat:m1001", "sup:v001",  28,   500, 14, "CNY"),
        ("ir:r02", "mat:m1002", "sup:v002",  35,   200, 21, "CNY"),
        ("ir:r03", "mat:m1003", "sup:v003",  12,  1000, 30, "CNY"),
        ("ir:r04", "mat:m1004", "sup:v004",  18,  3000,  7, "CNY"),
        ("ir:r05", "mat:m1005", "sup:v005",  85,   100, 20, "CNY"),
        ("ir:r06", "mat:m1008", "sup:v006",  42,   500, 14, "CNY"),
        ("ir:r07", "mat:m1009", "sup:v004",  55,   500, 10, "CNY"),
        ("ir:r08", "mat:m1011", "sup:v006",  18,  1000, 10, "CNY"),
    ]
    for eid, mid, vid, price, moq, lead, curr in info_records:
        kg.add_entity(eid, "InfoRecord", record_id=eid.split(":")[1],
                      material_id=mid.split(":")[1].upper(), vendor_id=vid.split(":")[1].upper(),
                      net_price=price,
                      moq=moq, lead_time=lead, currency=curr,
                      valid_from="2026-01-01", valid_to="2026-12-31")

    # 物料 -> 信息记录 (priced_by)
    for ir in info_records:
        kg.add_relation(ir[1], "priced_by", ir[0], net_price=ir[3])

    # ========================================================== #
    # 7. 货源清单 SourceList (8) —— 寻源主数据
    # ========================================================== #
    sources = [
        ("src:s01", "mat:m1001", "sup:v001", "plant:p100", "porg:po100", True,  True),
        ("src:s02", "mat:m1002", "sup:v002", "plant:p100", "porg:po100", True,  True),
        ("src:s03", "mat:m1003", "sup:v003", "plant:p100", "porg:po100", True,  True),
        ("src:s04", "mat:m1004", "sup:v004", "plant:p200", "porg:po200", False, True),
        ("src:s05", "mat:m1005", "sup:v005", "plant:p200", "porg:po200", True,  True),
        ("src:s06", "mat:m1008", "sup:v006", "plant:p300", "porg:po300", True,  False),
        ("src:s07", "mat:m1009", "sup:v004", "plant:p300", "porg:po300", False, True),
        ("src:s08", "mat:m1011", "sup:v006", "plant:p300", "porg:po300", True,  True),
    ]
    for eid, mid, vid, pid, oid, fixed, mrp in sources:
        kg.add_entity(eid, "SourceList", source_id=eid.split(":")[1],
                      material_id=mid.split(":")[1].upper(), vendor_id=vid.split(":")[1].upper(),
                      plant_id=pid.split(":")[1].upper(), org_id=oid.split(":")[1].upper(),
                      valid_from="2026-01-01",
                      valid_to="2026-12-31", fixed_flag=fixed, mrp_flag=mrp)
        kg.add_relation(mid, "source_by", eid, valid=True)

    # 供应商 -> 物料 (supplies, 反向)
    supplier_links = [
        ("sup:v001", "mat:m1001", 14, 500),
        ("sup:v002", "mat:m1002", 21, 200),
        ("sup:v003", "mat:m1003", 30, 1000),
        ("sup:v004", "mat:m1004",  7, 3000),
        ("sup:v005", "mat:m1005", 20, 100),
        ("sup:v006", "mat:m1008", 14,  500),
        ("sup:v004", "mat:m1009", 10,  500),
        ("sup:v006", "mat:m1011", 10, 1000),
        ("sup:v004", "mat:m1010",  5,  100),   # 包装纸箱 — 行政部采购
        ("sup:v005", "mat:m1014", 25,  10),    # 设备维护服务 — SK 直供
        ("sup:v006", "mat:m1015", 20,  10),    # 实验室校准服务 — 万华化工
    ]
    for sid, mid, lead, moq in supplier_links:
        kg.add_relation(sid, "supplies", mid, lead_time_days=lead, min_order_qty=moq)

    # ========================================================== #
    # 8. 采购申请 PR (5) + 行项目 (10)
    # ========================================================== #
    prs = [
        # eid, pr_id, type, status, doc_date, applicant, dept, priority, total
        ("pr:p0001", "PR-2026-00001", "standard", "pending_approval", "2026-06-01", "张工程师", "研发中心",   "urgent",  84000),
        ("pr:p0002", "PR-2026-00002", "standard", "pending_approval", "2026-06-15", "李技术员", "生产一部",   "normal",  35000),
        ("pr:p0003", "PR-2026-00003", "cost_center","approved",       "2026-05-20", "王主管",   "行政部",     "normal",  12000),
        ("pr:p0004", "PR-2026-00004", "service",   "pending_approval", "2026-05-10", "陈经理",   "设备维护部", "normal",  50000),
        ("pr:p0005", "PR-2026-00005", "standard", "rejected",         "2026-04-25", "孙工程师", "生产二部",   "urgent",  96000),
    ]
    for eid, prid, ptype, status, doc_date, applicant, dept, prio, total in prs:
        kg.add_entity(eid, "PurchaseRequisition", pr_id=prid, pr_type=ptype,
                      pr_status=status, doc_date=doc_date, applicant=applicant,
                      dept=dept, priority=prio, total_amount=total)

    pr_items = [
        # eid, parent_pr, mat, qty, unit, price, delivery, plant, loc, vendor, status, cost_center
        ("pri:0001", "pr:p0001", "mat:m1001", 2000, "EA", 28, "2026-07-15", "plant:p100", "loc:p100-rm", "sup:v001", "open", "CC-100"),
        ("pri:0002", "pr:p0001", "mat:m1002", 1000, "EA", 35, "2026-07-20", "plant:p100", "loc:p100-rm", "sup:v002", "open", "CC-100"),
        ("pri:0003", "pr:p0002", "mat:m1005",  300, "EA", 85, "2026-07-10", "plant:p200", "loc:p200-rm", "sup:v005", "open", "CC-200"),
        ("pri:0004", "pr:p0002", "mat:m1009",  200, "M",  55, "2026-07-08", "plant:p200", "loc:p200-rm", "sup:v004", "open", "CC-200"),
        ("pri:0005", "pr:p0003", "mat:m1010",  100, "BOX",12, "2026-06-10", "plant:p100", "loc:p100-fg", "sup:v004", "ordered", "CC-300"),
        ("pri:0006", "pr:p0004", "mat:m1014",   50, "EA",1000,"2026-07-01", "plant:p300", "loc:p300-rm", "sup:v005", "open", "CC-400"),
        ("pri:0007", "pr:p0004", "mat:m1015",   20, "EA",1500,"2026-07-01", "plant:p300", "loc:p300-rm", "sup:v006", "open", "CC-400"),
        ("pri:0008", "pr:p0005", "mat:m1003", 5000, "EA", 12, "2026-06-01", "plant:p100", "loc:p100-rm", "sup:v003", "closed", "CC-100"),
        ("pri:0009", "pr:p0005", "mat:m1008",  500, "KG", 42, "2026-05-30", "plant:p300", "loc:p300-rm", "sup:v006", "closed", "CC-300"),
        ("pri:0010", "pr:p0001", "mat:m1004", 1000, "KG", 18, "2026-07-25", "plant:p200", "loc:p200-rm", "sup:v004", "open", "CC-200"),
    ]
    for eid, pr_eid, mat, qty, unit, price, dl, pid, loc, vid, status, cc in pr_items:
        kg.add_entity(eid, "RequisitionItem", pr_item_id=eid.split(":")[1],
                      material_id=mat.split(":")[1].upper(),
                      quantity=qty, unit=unit, unit_price=price, delivery_date=dl,
                      plant_id=pid.split(":")[1], location_id=loc.split(":")[1],
                      vendor_id=vid.split(":")[1].upper(), item_status=status,
                      cost_center=cc)
        kg.add_relation(pr_eid, "has_item", eid)
        kg.add_relation(eid, "belongs_to_plant", pid)

    # ========================================================== #
    # 9. 采购订单 PO (4) + 行项目 (8)
    # ========================================================== #
    pos = [
        # eid, po_id, type, currency, payment, incoterms, status, doc_date, vendor, amount
        ("po:o0001", "PO-2026-00789", "standard",   "CNY", "Net30", "FOB", "approved",     "2026-06-05", "sup:v001",  56000),
        ("po:o0002", "PO-2026-00790", "urgent",     "CNY", "Net30", "CIF", "partial",      "2026-06-12", "sup:v005",  25500),
        ("po:o0003", "PO-2026-00791", "cost_center","CNY", "Net45", "EXW", "sent",         "2026-06-15", "sup:v004",  12000),
        ("po:o0004", "PO-2026-00792", "standard",   "USD", "Net60", "FOB", "pending_approval","2026-06-20", "sup:v005", 50000),
    ]
    for eid, poid, ptype, curr, pay, inco, status, doc_date, vid, amount in pos:
        kg.add_entity(eid, "PurchaseOrder", po_id=poid, po_type=ptype,
                      currency=curr, payment_terms=pay, incoterms=inco,
                      doc_status=status, doc_date=doc_date, vendor_id=vid.split(":")[1].upper(),
                      contract_amount=amount)
        kg.add_relation(eid, "po_targets_vendor", vid)
        kg.add_relation(eid, "belongs_to_org", "porg:po100" if vid.endswith("v001") or vid.endswith("v002") or vid.endswith("v003") else (
                                   "porg:po200" if vid.endswith("v005") else "porg:po300"))
        # 采购组分配 (按物料类型, 简化)
        if vid.endswith(("v001", "v002", "v003")):
            kg.add_relation(eid, "belongs_to_group", "pgrp:g01")
        elif vid.endswith(("v005",)):
            kg.add_relation(eid, "belongs_to_group", "pgrp:g02")
        else:
            kg.add_relation(eid, "belongs_to_group", "pgrp:g03")

    # PO 关联 PR (源单据)
    kg.add_relation("pr:p0003", "converts_to", "po:o0003",
                    convert_date="2026-06-15")

    po_items = [
        # eid, parent_po, mat, qty, unit_price, net_price, delivery, plant, loc, delivered, invoiced, pr_ref
        ("poi:i0001", "po:o0001", "mat:m1001", 2000, 32, 28, "2026-07-15", "plant:p100", "loc:p100-rm",  800, 800, "PR-2026-00001"),
        ("poi:i0002", "po:o0001", "mat:m1002", 1000, 40, 35, "2026-07-20", "plant:p100", "loc:p100-rm",    0,   0, "PR-2026-00001"),
        ("poi:i0003", "po:o0002", "mat:m1005",  300, 95, 85, "2026-07-10", "plant:p200", "loc:p200-rm",  100,  50, "PR-2026-00002"),
        ("poi:i0004", "po:o0002", "mat:m1009",  200, 60, 55, "2026-07-08", "plant:p200", "loc:p200-rm",  200, 150, "PR-2026-00002"),
        ("poi:i0005", "po:o0003", "mat:m1010",  100, 14, 12, "2026-06-10", "plant:p100", "loc:p100-fg",  100, 100, "PR-2026-00003"),
        ("poi:i0006", "po:o0004", "mat:m1006",  100,1500,1400,"2026-08-15", "plant:p200", "loc:p200-rm",    0,   0, ""),
        ("poi:i0007", "po:o0004", "mat:m1007",  500, 35, 30, "2026-08-15", "plant:p200", "loc:p200-rm",    0,   0, ""),
        ("poi:i0008", "po:o0004", "mat:m1014",   50,1100,1000,"2026-07-01", "plant:p300", "loc:p300-rm",    0,   0, "PR-2026-00004"),
    ]
    for eid, po_eid, mat, qty, uprice, nprice, dl, pid, loc, dq, iq, prref in po_items:
        kg.add_entity(eid, "PurchaseOrderItem", po_item_id=eid.split(":")[1],
                      material_id=mat.split(":")[1].upper(), quantity=qty,
                      unit_price=uprice, net_price=nprice, delivery_date=dl,
                      plant_id=pid.split(":")[1].upper(), location_id=loc.split(":")[1].upper(),
                      delivered_qty=dq, invoiced_qty=iq, pr_ref=prref)
        kg.add_relation(po_eid, "has_po_item", eid)
        kg.add_relation(eid, "po_item_targets_material", mat)

    # ========================================================== #
    # 10. 采购收货 GR (3) + 行项目 (6)
    # ========================================================== #
    grs = [
        ("gr:g0001", "GR-2026-05001", "2026-06-20", "sup:v001", "101", "po:o0001", "posted"),
        ("gr:g0002", "GR-2026-05002", "2026-06-22", "sup:v005", "101", "po:o0002", "posted"),
        ("gr:g0003", "GR-2026-05003", "2026-06-18", "sup:v004", "102", "po:o0003", "posted"),
    ]
    for eid, grid, grdate, vid, mtype, po_ref, status in grs:
        kg.add_entity(eid, "GoodsReceipt", gr_id=grid, gr_date=grdate,
                      vendor_id=vid.split(":")[1].upper(), movement_type=mtype,
                      po_ref=po_ref.split(":")[1].upper(), doc_status=status)
        kg.add_relation(eid, "receipt_of", po_ref)

    gr_items = [
        # eid, parent_gr, mat, qty, amount, batch, plant, loc, stock_qty
        ("gri:g0001", "gr:g0001", "mat:m1001", 800, 22400, "B20260620A", "plant:p100", "loc:p100-rm",  800),
        ("gri:g0002", "gr:g0001", "mat:m1002", 200,  7000, "B20260620B", "plant:p100", "loc:p100-rm",  200),
        ("gri:g0003", "gr:g0002", "mat:m1005", 100,  8500, "B20260622C", "plant:p200", "loc:p200-rm",  100),
        ("gri:g0004", "gr:g0002", "mat:m1009", 200, 11000, "B20260622D", "plant:p200", "loc:p200-rm",  200),
        ("gri:g0005", "gr:g0003", "mat:m1010",  20,   280, "B20260618E", "plant:p100", "loc:p100-fg",   80),
        ("gri:g0006", "gr:g0002", "mat:m1009",  50,  2750, "B20260622F", "plant:p200", "loc:p200-rm",  150),
    ]
    for eid, gr_eid, mat, qty, amount, batch, pid, loc, stock in gr_items:
        kg.add_entity(eid, "GoodsReceiptItem", gr_item_id=eid.split(":")[1],
                      material_id=mat.split(":")[1].upper(), quantity=qty, amount=amount,
                      batch_id=batch, plant_id=pid.split(":")[1].upper(),
                      location_id=loc.split(":")[1].upper(), stock_qty=stock)
        kg.add_relation(gr_eid, "receipt_item_of", eid)
        kg.add_relation(eid, "stored_at", loc)

    # ========================================================== #
    # 11. 知识库 KBDoc (8) —— 采购 SOP + 政策
    # ========================================================== #
    kb_docs = [
        ("doc:sop-pr",       "SOP-PROC-001 采购申请标准流程", "SOP",
         "1) 需求部门填写 PR 头 (申请人/部门/类型); 2) 添加物料明细 (工厂/库位/数量); "
         "3) 选择建议供应商或留空; 4) 提交审批。"),
        ("doc:sop-po",       "SOP-PROC-002 采购订单下达流程", "SOP",
         "1) PR 审批通过 → 转 PO 草稿; 2) 自动按供应商归集行项目; 3) 校验 MOQ 与提前期; "
         "4) 选择贸易条款 + 付款条件; 5) 审批下达 (邮件/EDI/SRM 门户)。"),
        ("doc:sop-gr",       "SOP-PROC-003 采购收货流程",   "SOP",
         "1) 到货预通知; 2) 实物验收 (数量/批次/质量); 3) 在系统中做 MIGO 101 收货; "
         "4) 触发三单匹配 (PO-收货-发票); 5) 上架至对应库位。"),
        ("doc:sop-source",   "SOP-PROC-004 寻源管理流程",   "SOP",
         "1) 新物料新增; 2) 通过信息记录维护价格/MOQ/提前期; 3) 通过货源清单设定 "
         "固定供应商 / MRP 自动货源; 4) 定期评估供应商绩效。"),
        ("doc:kb-source",    "货源确定策略指引", "培训",
         "优先级: 货源清单 fixed_flag=True > MRP 自动货源 > 临时寻源。"
         "冻结货源 (frozen_flag=True) 不允许采购, 即使信息记录存在。"),
        ("doc:kb-price",     "价格偏离判定标准", "政策",
         "PO 单价 vs 信息记录 net_price: 偏离 ±10% 触发价格复核; "
         "偏离 ±20% 需主管审批。"),
        ("doc:kb-delivery",  "交货逾期判定规则", "FAQ",
         "交货日期 < 当前日期 + 行项目 delivered_qty < quantity 视为逾期。"),
        ("doc:kb-audit",     "采购审计要点",   "政策",
         "三单匹配 / 价格波动监控 / 供应商集中度 / 紧急采购比例 / 库存呆滞关联。"),
    ]
    for eid, title, cat, content in kb_docs:
        kg.add_entity(eid, "KBDoc", doc_id=eid.split(":")[1], title=title,
                      category=cat, content=content)

    # KB 关联 PR / PO
    kb_links = [
        ("doc:sop-pr",     "pr:p0001", "需求方"),
        ("doc:sop-pr",     "pr:p0002", "需求方"),
        ("doc:sop-po",     "po:o0001", "采购员"),
        ("doc:sop-po",     "po:o0004", "采购员"),
        ("doc:sop-gr",     "po:o0001", "仓储员"),
        ("doc:sop-source", "po:o0004", "采购员"),
    ]
    for doc_eid, target_eid, role in kb_links:
        kg.add_relation(target_eid, "requires_role", doc_eid, role=role)
        # 反向 task_targets_*
        if target_eid.startswith("pr:"):
            kg.add_relation(doc_eid, "task_targets_pr", target_eid, role=role)
        else:
            kg.add_relation(doc_eid, "task_targets_po", target_eid, role=role)

    return kg


if __name__ == "__main__":
    kg = build_procurement_knowledge_base()
    print(f"采购场景 KG: {kg}")
    print(f"统计: {kg.stats()}")
    from collections import Counter
    dist = Counter(e.etype for e in kg.list_entities())
    print("实体分布:", dict(dist))
