"""
采购场景规则层 (Business Reasoning Rules + Engine)
==================================================
8 条规则:

查询类 (5 条 - 智能体编排):
  R1_source_recommendation      根据物料+工厂推荐合格供应商 (SourceList 寻源)
  R2_plan_pr_creation           编排采购申请创建 (物料/工厂/库位/供应商/数量校验)
  R3_approve_pr                 审批 PR (校验供应商资质 + 价格合理性)
  R4_pr_to_po                   PR→PO 智能编排 (按供应商归集 + 继承价格/MOQ/提前期)
  R5_approve_po                 审批 PO (校验合同金额 + 付款条款 + 国际贸易条款)

预警类 (2 条):
  R6_detect_price_deviation     检测采购价格偏离 (当前 vs 信息记录 ±10%)
  R7_track_delivery_overdue     追踪交货逾期 (delivery_date 早于今天 + 未全交)

物化类 (1 条):
  M1_materialize_pending_pr     把"审批中 + 申请时间 > 30天" 的 PR 物化为 at_risk_of_delay

复用全局 rules.Rule / RuleEngine, 不修改 rules.py。
"""
from __future__ import annotations

import os, sys
_HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from dataclasses import dataclass
from typing import Any

from ontology import KnowledgeGraph
from rules import Rule, RuleEngine  # noqa: E402


# --------------------------------------------------------------------------- #
# 辅助函数
# --------------------------------------------------------------------------- #
def _label(kg: KnowledgeGraph, eid: str) -> str:
    e = kg.get_entity(eid)
    return e.label if e else eid


def _today_iso() -> str:
    """取当前日期 (ISO), 可被规则用于比较。"""
    from datetime import date
    return date.today().isoformat()


def _days_between(d1: str, d2: str) -> int:
    """两个 ISO 日期相差天数 (d2 - d1)。"""
    from datetime import date
    try:
        a = date.fromisoformat(d1)
        b = date.fromisoformat(d2)
        return (b - a).days
    except Exception:
        return 0


# --------------------------------------------------------------------------- #
# 规则实现
# --------------------------------------------------------------------------- #
def rule_source_recommendation(kg: KnowledgeGraph, material: str,
                               plant: str | None = None) -> dict:
    """R1: 根据物料+工厂查询货源清单,推荐合格供应商"""
    kg.mark_focus(material, note="推理起点: 待寻源物料")
    mat_ent = kg.get_entity(material)
    if not mat_ent or mat_ent.etype != "Material":
        return {"material": material, "candidates": [], "recommendations": []}

    candidates = []
    # 遍历货源清单
    for src in kg.list_entities("SourceList"):
        if src.attrs.get("material_id") != mat_ent.attrs.get("material_id"):
            continue
        if plant and src.attrs.get("plant_id") != kg.get_entity(plant).attrs.get("plant_id"):
            continue
        # 校验有效期
        today = _today_iso()
        vfrom = src.attrs.get("valid_from", "1970-01-01")
        vto = src.attrs.get("valid_to", "9999-12-31")
        if not (vfrom <= today <= vto):
            kg.mark_hop(material, "source_by", src.eid,
                        reason=f"货源 {src.eid} 已过期, 跳过")
            continue

        vendor_id = src.attrs.get("vendor_id", "").upper()
        vendor_ent = None
        # 找供应商实体
        for v in kg.list_entities("Supplier"):
            if v.attrs.get("vendor_id", "").upper() == vendor_id:
                vendor_ent = v
                break

        if not vendor_ent:
            continue

        rating = vendor_ent.attrs.get("rating", "Z")
        fixed = bool(src.attrs.get("fixed_flag", False))
        mrp = bool(src.attrs.get("mrp_flag", False))

        kg.mark_hop(material, "source_by", src.eid,
                    reason=f"候选货源 {src.attrs['source_id']} → {vendor_ent.label} "
                          f"(rating={rating}, fixed={fixed}, mrp={mrp})")

        candidates.append({
            "source": src.eid,
            "vendor": vendor_ent.eid,
            "vendor_id": vendor_id,
            "vendor_name": vendor_ent.attrs.get("name"),
            "rating": rating,
            "fixed": fixed,
            "mrp": mrp,
            "score": (4 - ord(rating[0]) + ord("A")) * 10 + (20 if fixed else 0) + (10 if mrp else 0),
        })

    # 按评分降序
    candidates.sort(key=lambda x: -x["score"])
    if candidates:
        top = candidates[0]
        kg.mark_focus(top["vendor"], note=f"结论: 推荐供应商 {top['vendor_name']} "
                                          f"(rating={top['rating']}, fixed={top['fixed']})")

    return {
        "material": material,
        "plant": plant,
        "candidates": candidates,
        "recommendations": [candidates[0]] if candidates else [],
    }


def rule_plan_pr_creation(kg: KnowledgeGraph, material: str, quantity: int,
                          plant: str | None = None) -> dict:
    """R2: 编排采购申请创建 (校验物料/工厂/库位/供应商/数量)"""
    kg.mark_focus(material, note="推理起点: 待创建 PR")
    steps = []

    # Step 1: 校验物料存在
    mat_ent = kg.get_entity(material)
    if not mat_ent or mat_ent.etype != "Material":
        return {"material": material, "steps": [], "fallback": "物料不存在"}
    steps.append({"step": 1, "phase": "物料校验", "result": "✓"})

    # Step 2: 选工厂 (未指定则取默认第一个)
    chosen_plant = plant
    if not chosen_plant:
        plants = kg.list_entities("Plant")
        chosen_plant = plants[0].eid if plants else None
    if chosen_plant:
        kg.mark_hop(material, "belongs_to_plant", chosen_plant,
                    reason=f"目标工厂 {_label(kg, chosen_plant)}")
        steps.append({"step": 2, "phase": "工厂路由", "result": _label(kg, chosen_plant)})

    # Step 3: 推荐库位 (按工厂查 StorageLocation)
    chosen_loc = None
    plant_id = kg.get_entity(chosen_plant).attrs.get("plant_id") if chosen_plant else ""
    for loc in kg.list_entities("StorageLocation"):
        if loc.attrs.get("plant_id") == plant_id and loc.attrs.get("status") == "active":
            chosen_loc = loc.eid
            break
    if chosen_loc:
        steps.append({"step": 3, "phase": "库位匹配", "result": _label(kg, chosen_loc)})
    else:
        steps.append({"step": 3, "phase": "库位匹配", "result": "无活跃库位"})

    # Step 4: 复用 R1 推荐供应商
    src_plan = rule_source_recommendation(kg, material, chosen_plant)
    chosen_vendor = src_plan["recommendations"][0]["vendor"] if src_plan["recommendations"] else None
    if chosen_vendor:
        steps.append({"step": 4, "phase": "供应商寻源",
                      "result": _label(kg, chosen_vendor),
                      "score": src_plan["recommendations"][0]["score"]})

    # Step 5: 价格校验 (取信息记录价格作为 PR 预估单价)
    ir_price = None
    for ir in kg.out(material, "priced_by"):
        ir_ent = kg.get_entity(ir.obj)
        if ir_ent:
            ir_price = ir_ent.attrs.get("net_price")
            break
    if ir_price is None:
        steps.append({"step": 5, "phase": "价格校验", "result": "无信息记录价格"})
    else:
        steps.append({"step": 5, "phase": "价格校验",
                      "result": f"信息记录价 ¥{ir_price}"})
        kg.mark_hop(material, "priced_by", material,
                    reason=f"价格参考 ¥{ir_ent.attrs.get('net_price')}")

    # Step 6: 异常兜底
    fallback = None
    if not chosen_vendor:
        fallback = "无可用货源 → 需采购临时寻源或新建信息记录"
    elif not chosen_loc:
        fallback = "无活跃库位 → 工厂维护库存地点"

    return {
        "material": material,
        "quantity": quantity,
        "plant": chosen_plant,
        "location": chosen_loc,
        "vendor": chosen_vendor,
        "unit_price": ir_price,
        "steps": steps,
        "fallback": fallback,
    }


def rule_approve_pr(kg: KnowledgeGraph, pr: str, decision: str = "approve") -> dict:
    """R3: 审批 PR (校验供应商资质 + 价格合理性, 支持同意/驳回/转审)"""
    kg.mark_focus(pr, note=f"推理起点: 审批 PR")
    pr_ent = kg.get_entity(pr)
    if not pr_ent or pr_ent.etype != "PurchaseRequisition":
        return {"pr": pr, "checks": [], "decision": "invalid"}

    checks = []
    items = [r.obj for r in kg.out(pr, "has_item")]

    # 校验 1: 供应商资质 (信息记录是否存在)
    for it in items:
        for r in kg.out(it, "belongs_to_plant"):
            pass
        ir_price = None
        for r in kg.out(it, "priced_by"):
            ir_ent = kg.get_entity(r.obj)
            if ir_ent:
                ir_price = ir_ent.attrs.get("net_price")
                break

        vendor_id = kg.get_entity(it).attrs.get("vendor_id", "").upper()
        vendor_ent = None
        for v in kg.list_entities("Supplier"):
            if v.attrs.get("vendor_id", "").upper() == vendor_id:
                vendor_ent = v
                break
        if vendor_ent:
            kg.mark_hop(it, "priced_by", it,
                        reason=f"供应商 {vendor_ent.label} (rating={vendor_ent.attrs.get('rating')}) 存在")
            checks.append({"item": it, "vendor_ok": True,
                           "vendor_rating": vendor_ent.attrs.get("rating")})

    # 校验 2: 价格偏离 (当前 PR 单价 vs 信息记录价)
    price_alerts = []
    for it in items:
        it_ent = kg.get_entity(it)
        pr_price = it_ent.attrs.get("unit_price")
        # 找信息记录价 (通过 priced_by)
        ir_price = None
        for r in kg.out(it_ent.attrs.get("material_id", ""), "priced_by"):
            ir_ent = kg.get_entity(r.obj)
            if ir_ent and ir_ent.attrs.get("vendor_id") == it_ent.attrs.get("vendor_id"):
                ir_price = ir_ent.attrs.get("net_price")
                break
        if pr_price and ir_price:
            deviation = abs(pr_price - ir_price) / ir_price
            if deviation > 0.20:
                price_alerts.append({"item": it, "deviation": round(deviation, 2),
                                    "level": "high",
                                    "msg": f"偏离 ±20% ({pr_price} vs 信息记录 {ir_price})"})
            elif deviation > 0.10:
                price_alerts.append({"item": it, "deviation": round(deviation, 2),
                                    "level": "medium",
                                    "msg": f"偏离 ±10% ({pr_price} vs 信息记录 {ir_price})"})

    # 校验 3: 行项目数 + 总金额
    total = pr_ent.attrs.get("total_amount", 0)
    kg.mark_focus(pr, note=f"PR {pr_ent.attrs['pr_id']} 共 {len(items)} 行项目, 总金额 ¥{total}")

    # 综合决策
    final_decision = decision
    reasons = []
    if price_alerts:
        high = [a for a in price_alerts if a["level"] == "high"]
        if high and decision == "approve":
            final_decision = "conditional_approve"
            reasons.append(f"{len(high)} 条价格严重偏离, 需主管复核")

    return {
        "pr": pr,
        "decision": final_decision,
        "checks": checks,
        "price_alerts": price_alerts,
        "item_count": len(items),
        "total": total,
        "reasons": reasons,
    }


def rule_pr_to_po(kg: KnowledgeGraph, pr: str) -> dict:
    """R4: PR→PO 智能编排 (按供应商归集行项目 + 继承价格/MOQ/提前期)"""
    kg.mark_focus(pr, note="推理起点: PR 转 PO")
    pr_ent = kg.get_entity(pr)
    if not pr_ent or pr_ent.etype != "PurchaseRequisition":
        return {"pr": pr, "groups": [], "fallback": "PR 不存在"}

    items = [r.obj for r in kg.out(pr, "has_item")]
    if not items:
        return {"pr": pr, "groups": [], "fallback": "PR 无明细行"}

    # 按供应商归集
    by_vendor: dict[str, list[str]] = {}
    for it in items:
        it_ent = kg.get_entity(it)
        vendor_id = it_ent.attrs.get("vendor_id", "").upper()
        by_vendor.setdefault(vendor_id, []).append(it)

    groups = []
    for vendor_id, its in by_vendor.items():
        # 找供应商实体
        vendor_ent = None
        for v in kg.list_entities("Supplier"):
            if v.attrs.get("vendor_id", "").upper() == vendor_id:
                vendor_ent = v
                break
        if not vendor_ent:
            continue

        # 取最长提前期 + 总金额
        max_lead = 0
        total_amount = 0
        for it in its:
            it_ent = kg.get_entity(it)
            qty = int(it_ent.attrs.get("quantity", 0))
            price = int(it_ent.attrs.get("unit_price", 0))
            total_amount += qty * price
            # 从 supplier -> material -> material_id 反查 supplies 的 lead_time
            mat_id = it_ent.attrs.get("material_id", "")
            for v_mat in kg.out(vendor_ent.eid, "supplies"):
                if kg.get_entity(v_mat.obj).attrs.get("material_id") == mat_id:
                    max_lead = max(max_lead, int(v_mat.edge.get("lead_time_days", 0)))

        # 校验 MOQ
        moq_violations = []
        for it in its:
            it_ent = kg.get_entity(it)
            qty = int(it_ent.attrs.get("quantity", 0))
            mat_id = it_ent.attrs.get("material_id", "")
            for v_mat in kg.out(vendor_ent.eid, "supplies"):
                if kg.get_entity(v_mat.obj).attrs.get("material_id") == mat_id:
                    moq = int(v_mat.edge.get("min_order_qty", 0))
                    if qty < moq:
                        moq_violations.append({
                            "item": it, "material": mat_id,
                            "qty": qty, "moq": moq,
                        })
                    break

        kg.mark_hop(pr, "converts_to", pr,
                    reason=f"按供应商 {vendor_ent.label} 归集 {len(its)} 行, "
                          f"总金额 ¥{total_amount}, 最长提前期 {max_lead} 天")

        groups.append({
            "vendor": vendor_ent.eid,
            "vendor_id": vendor_id,
            "vendor_name": vendor_ent.attrs.get("name"),
            "items": its,
            "item_count": len(its),
            "total_amount": total_amount,
            "lead_time": max_lead,
            "moq_violations": moq_violations,
        })

    return {
        "pr": pr,
        "groups": groups,
        "fallback": None if groups else "无可归集行项目",
    }


def rule_approve_po(kg: KnowledgeGraph, po: str) -> dict:
    """R5: 审批 PO (校验合同金额 + 付款条款 + 国际贸易条款)"""
    kg.mark_focus(po, note="推理起点: 审批 PO")
    po_ent = kg.get_entity(po)
    if not po_ent or po_ent.etype != "PurchaseOrder":
        return {"po": po, "checks": [], "decision": "invalid"}

    checks = []
    amount = po_ent.attrs.get("contract_amount", 0)
    pay = po_ent.attrs.get("payment_terms", "")
    inco = po_ent.attrs.get("incoterms", "")
    curr = po_ent.attrs.get("currency", "")

    # 校验 1: 大额合同 (>= 50000 需主管审批)
    if amount >= 50000:
        checks.append({"type": "amount", "level": "high",
                       "msg": f"合同金额 ¥{amount} ≥ 50000, 需主管审批"})
        kg.mark_focus(po, note=f"大额合同 ¥{amount}, 触发主管复核")

    # 校验 2: 付款条款
    if "Net60" in pay and amount > 100000:
        checks.append({"type": "payment", "level": "medium",
                       "msg": f"长账期 {pay} + 大额, 财务复核"})
    elif pay not in ("Net30", "Net45", "Net60"):
        checks.append({"type": "payment", "level": "high",
                       "msg": f"非标准账期 {pay}"})

    # 校验 3: 国际贸易条款 (CIF/FOB/EXW/DDP)
    if inco not in ("FOB", "CIF", "EXW", "DDP"):
        checks.append({"type": "incoterms", "level": "high",
                       "msg": f"非常用贸易条款 {inco}"})

    # 校验 4: 外币合同
    if curr != "CNY":
        checks.append({"type": "currency", "level": "medium",
                       "msg": f"外币合同 {curr}, 汇率风险"})

    return {
        "po": po,
        "decision": "approve" if not [c for c in checks if c["level"] == "high"] else "conditional_approve",
        "checks": checks,
        "amount": amount,
    }


def rule_detect_price_deviation(kg: KnowledgeGraph, threshold: float = 0.10) -> dict:
    """R6: 检测采购价格偏离 (PO 单价 vs 信息记录 net_price, 偏离 > ±10% 触发预警)"""
    findings = []
    for po_item in kg.list_entities("PurchaseOrderItem"):
        mat_id = po_item.attrs.get("material_id")
        po_price = int(po_item.attrs.get("unit_price", 0))

        # 找信息记录 (按 material + vendor)
        po = None
        for r in kg.inn(po_item.eid, "has_po_item"):
            po = r.subject
            break
        vendor_id = kg.get_entity(po).attrs.get("vendor_id", "").upper() if po else ""

        ir_price = None
        for ir in kg.list_entities("InfoRecord"):
            if (ir.attrs.get("material_id") == mat_id and
                    ir.attrs.get("vendor_id", "").upper() == vendor_id):
                ir_price = int(ir.attrs.get("net_price", 0))
                break

        if not ir_price or not po_price:
            continue

        deviation = abs(po_price - ir_price) / ir_price
        if deviation > threshold:
            level = "high" if deviation > 0.20 else "medium"
            findings.append({
                "po_item": po_item.eid,
                "material": mat_id,
                "po": po,
                "po_price": po_price,
                "ir_price": ir_price,
                "deviation": round(deviation, 3),
                "level": level,
            })
            kg.mark_focus(po_item.eid, note=f"价格偏离 {deviation*100:.1f}% "
                                            f"(PO ¥{po_price} vs 信息记录 ¥{ir_price})")
            kg.mark_hop(mat_id, "priced_by", po_item.eid,
                        reason=f"价格偏离 {level}: {deviation*100:.1f}%")

    findings.sort(key=lambda x: -x["deviation"])
    return {"threshold": threshold, "count": len(findings), "findings": findings}


def rule_track_delivery_overdue(kg: KnowledgeGraph) -> dict:
    """R7: 追踪交货逾期 (delivery_date < 今天 + delivered_qty < quantity)"""
    today = _today_iso()
    overdue = []
    for poi in kg.list_entities("PurchaseOrderItem"):
        delivery = poi.attrs.get("delivery_date", "")
        qty = int(poi.attrs.get("quantity", 0))
        dq = int(poi.attrs.get("delivered_qty", 0))
        if delivery < today and dq < qty:
            days_overdue = _days_between(delivery, today)
            overdue.append({
                "po_item": poi.eid,
                "material": poi.attrs.get("material_id"),
                "delivery_date": delivery,
                "ordered_qty": qty,
                "delivered_qty": dq,
                "remaining": qty - dq,
                "days_overdue": days_overdue,
            })
            kg.mark_focus(poi.eid, note=f"逾期 {days_overdue} 天, 剩余 {qty - dq}")

    overdue.sort(key=lambda x: -x["days_overdue"])
    return {"today": today, "count": len(overdue), "overdue": overdue}


def _materialize_pending_pr(kg: KnowledgeGraph, threshold_days: int = 30) -> int:
    """M1: 把"审批中 + 申请时间 > 30天" 的 PR 物化为 at_risk_of_delay"""
    today = _today_iso()
    n = 0
    for pr in kg.list_entities("PurchaseRequisition"):
        if pr.attrs.get("pr_status") != "pending_approval":
            continue
        days = _days_between(pr.attrs.get("doc_date", ""), today)
        if days < threshold_days:
            continue
        severity = "high" if days > 60 else "medium"
        if kg.add_inferred(pr.eid, "at_risk_of_delay", pr.eid,
                           days_pending=days, severity=severity):
            n += 1
            kg.mark_focus(pr.eid, note=f"物化: 审批中超过 {days} 天 ({severity})")
    return n


# --------------------------------------------------------------------------- #
# 默认规则集
# --------------------------------------------------------------------------- #
def build_procurement_rules() -> list[Rule]:
    return [
        Rule("R1_source_recommendation",
             "根据物料+工厂查询货源清单, 推荐合格供应商",
             "SourceList(?s) material_id=Material(?m).material_id ∧ "
             "valid_from ≤ today ≤ valid_to → Supplier(?v)",
             "query", 10,
             lambda kg, material, plant=None: rule_source_recommendation(kg, material, plant)),
        Rule("R2_plan_pr_creation",
             "编排采购申请创建 (物料/工厂/库位/供应商/数量校验)",
             "Material(?m); Plant + StorageLocation 匹配; R1 → vendor; "
             "InfoRecord → unit_price",
             "query", 20,
             lambda kg, material, quantity=100, plant=None:
                 rule_plan_pr_creation(kg, material, quantity, plant)),
        Rule("R3_approve_pr",
             "审批 PR (校验供应商资质 + 价格合理性)",
             "PurchaseRequisition(?p) has_item RequisitionItem(?i); "
             "priced_by InfoRecord; deviation > 10% → alert",
             "query", 30,
             lambda kg, pr, decision="approve":
                 rule_approve_pr(kg, pr, decision)),
        Rule("R4_pr_to_po",
             "PR→PO 智能编排 (按供应商归集 + 继承价格/MOQ/提前期)",
             "PurchaseRequisition(?p) has_item {?i}; group by vendor_id; "
             "supplies lead_time_days + min_order_qty",
             "query", 40,
             lambda kg, pr: rule_pr_to_po(kg, pr)),
        Rule("R5_approve_po",
             "审批 PO (校验合同金额 + 付款条款 + 国际贸易条款)",
             "PurchaseOrder(?p) contract_amount, payment_terms, incoterms; "
             "rules: amount ≥ 50k → 主管审批; 非标准 → 警示",
             "query", 50,
             lambda kg, po: rule_approve_po(kg, po)),
        Rule("R6_detect_price_deviation",
             "检测采购价格偏离 (PO 单价 vs 信息记录 net_price ±10%)",
             "PurchaseOrderItem(?i).unit_price vs InfoRecord(?r).net_price; "
             "|deviation| > 0.10 → alert",
             "query", 60,
             lambda kg, threshold=0.10: rule_detect_price_deviation(kg, threshold)),
        Rule("R7_track_delivery_overdue",
             "追踪交货逾期 (delivery_date 早于今天 + 未全交)",
             "PurchaseOrderItem(?i) delivery_date < today ∧ delivered_qty < quantity → overdue",
             "query", 70,
             lambda kg: rule_track_delivery_overdue(kg)),
        Rule("M1_materialize_pending_pr",
             "[物化] 审批中 > 30天 的 PR 写入 at_risk_of_delay",
             "PurchaseRequisition(?p) pr_status=pending_approval ∧ "
             "doc_date + 30d < today → at_risk_of_delay",
             "materialize", 5,
             lambda kg, threshold_days=30: _materialize_pending_pr(kg, threshold_days)),
    ]
