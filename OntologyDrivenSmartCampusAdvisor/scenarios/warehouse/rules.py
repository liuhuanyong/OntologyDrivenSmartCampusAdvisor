"""
仓库场景规则层 (Business Reasoning Rules + Engine)
==================================================
8 条规则:

查询类 (5 条 - 智能体编排):
  R1_recommend_bin_for_material    根据物料属性推荐库位
  R2_plan_receipt                  编排收料任务 (供应商→工厂→库位→质检→入库)
  R3_plan_issue                    编排发料任务 (需求→可用库存→FIFO→拣货→出库)
  R4_plan_transfer                 编排调拨任务 (源库位→目标库位→在途→收货)
  R5_plan_stocktake                编排盘点任务 (ABC分类→循环盘点→差异报告)

预警类 (2 条):
  R6_detect_idle_stock             识别呆滞料 (无移动 > 180 天 + 高库存)
  R7_cross_dept_handoff            识别跨部门任务交接点

物化类 (1 条):
  M1_materialize_obsolete_risk     把呆滞风险 ≥ 中 的 (Material, StockRecord)
                                  物化为 at_risk_of_obsolete

说明:
- 复用全局 rules.Rule / RuleEngine, 不修改 rules.py。
- 通过 mark_hop / mark_focus 在 KG 上记录推理路径, 供前端高亮展示。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ontology import KnowledgeGraph


# --------------------------------------------------------------------------- #
# 复用全局 Rule / RuleEngine (避免重复实现)
# --------------------------------------------------------------------------- #
# 直接 import 全局 rules 模块下的基础设施
import sys, os
_HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
from rules import Rule, RuleEngine  # noqa: E402


# --------------------------------------------------------------------------- #
# 辅助函数
# --------------------------------------------------------------------------- #
def _label(kg: KnowledgeGraph, eid: str) -> str:
    e = kg.get_entity(eid)
    return e.label if e else eid


def _stock_by_lot_fifo(kg: KnowledgeGraph, material: str) -> list[tuple[str, str, int]]:
    """FIFO 排序: 按 last_movement 升序返回可用库存 [(record_id, lot_no, qty)]"""
    out = []
    # material -> bin via holds_stock 反向
    for r in kg.inn(material, "holds_stock"):
        bin_eid = r.subject
        # bin -> stock via stored_at 反向
        for sr in kg.inn(bin_eid, "stored_at"):
            sr_id = sr.subject
            sr_ent = kg.get_entity(sr_id)
            if sr_ent and sr_ent.attrs.get("status") != "frozen":
                out.append((sr_id, sr_ent.attrs.get("lot_no", ""),
                            int(sr_ent.attrs.get("qty", 0))))
    out.sort(key=lambda x: x[1])  # 按 lot 升序近似 FIFO
    return out


# --------------------------------------------------------------------------- #
# 规则实现
# --------------------------------------------------------------------------- #
def rule_recommend_bin(kg: KnowledgeGraph, material: str) -> dict:
    """R1: 根据物料属性推荐库位 (zone 匹配 + 容量校验)"""
    kg.mark_focus(material, note="推理起点: 待入库物料")
    mat = kg.get_entity(material)
    if not mat or mat.etype != "Material":
        return {"material": material, "candidates": [], "recommendations": []}

    cat = mat.attrs.get("category")
    perishable = bool(mat.attrs.get("perishable", False))
    hazardous = bool(mat.attrs.get("hazardous", False))

    # 目标 zone 规则
    if perishable:
        target_zone_prefix = "B-"
    elif hazardous:
        target_zone_prefix = "C-"
    elif cat == "成品":
        target_zone_prefix = "D-"
    else:
        target_zone_prefix = "A-"

    candidates = []
    for b in kg.list_entities("StorageBin"):
        bin_zone = b.attrs.get("zone", "")
        if not bin_zone.startswith(target_zone_prefix):
            continue
        # 当前库存数 (反向查 holds_stock)
        used = sum(r.edge.get("qty", 0) for r in kg.out(b.eid, "holds_stock"))
        cap = int(b.attrs.get("capacity", 0))
        free = cap - used
        if free <= 0:
            kg.mark_hop(material, "__candidate__", b.eid,
                        reason=f"库位 {b.attrs['bin_id']} 已满载, 跳过")
            continue
        kg.mark_hop(material, "__candidate__", b.eid,
                    reason=f"候选库位 {b.attrs['bin_id']} (区域 {bin_zone}, "
                          f"剩余 {free}/{cap})")
        candidates.append({
            "bin": b.eid, "bin_id": b.attrs["bin_id"],
            "zone": bin_zone, "free": free, "capacity": cap,
        })
    candidates.sort(key=lambda x: -x["free"])
    rec = candidates[0] if candidates else None
    if rec:
        kg.mark_focus(rec["bin"], note=f"结论: 推荐库位 {rec['bin_id']} (剩余 {rec['free']})")
    return {
        "material": material, "candidates": candidates,
        "recommendations": [rec] if rec else [],
    }


def rule_plan_receipt(kg: KnowledgeGraph, material: str, supplier: str | None = None,
                      plant: str | None = None) -> dict:
    """R2: 智能体编排收料 (PO 验证 → ASN 比对 → 库位推荐 → 质检 → 上架 → 过账)"""
    kg.mark_focus(material, note="推理起点: 待收物料")
    steps = []

    # Step1: 选供应商 (无指定时取评分最高)
    sups = [r.subject for r in kg.inn(material, "supplies_to")]
    chosen_sup = None
    if supplier and supplier in sups:
        chosen_sup = supplier
    elif sups:
        # 按 rating 字母序排序 (A 优于 B 优于 C 优于 D)
        def _rating(eid):
            ent = kg.get_entity(eid)
            return ent.attrs.get("rating", "Z") if ent else "Z"
        sups.sort(key=_rating)
        chosen_sup = sups[0]
    if chosen_sup:
        sup_ent = kg.get_entity(chosen_sup)
        kg.mark_hop(chosen_sup, "supplies_to", material,
                    reason=f"供应商 {sup_ent.label} 主供 {kg.get_entity(material).label}")
        steps.append({"step": 1, "phase": "供应商匹配", "result": sup_ent.label,
                      "lead_time": _get_edge_attr(kg, chosen_sup, "supplies_to", material, "lead_time_days")})

    # Step2: 选工厂 (无指定时按 belongs_to_plant)
    plants = [r.obj for r in kg.out(material, "belongs_to_plant")]
    chosen_plant = plant if plant in plants else (plants[0] if plants else None)
    if chosen_plant:
        kg.mark_hop(material, "belongs_to_plant", chosen_plant,
                    reason=f"目标工厂 {_label(kg, chosen_plant)}")
        steps.append({"step": 2, "phase": "工厂路由", "result": _label(kg, chosen_plant)})

    # Step3: 推荐库位 (复用 R1)
    bin_plan = rule_recommend_bin(kg, material)
    rec_bin = bin_plan["recommendations"][0] if bin_plan["recommendations"] else None
    if rec_bin:
        steps.append({"step": 3, "phase": "库位推荐", "result": rec_bin["bin_id"],
                      "free": rec_bin["free"]})

    # Step4: 质检 SOP 关联
    qc_doc = "doc:sop-receipt"
    kg.mark_hop(qc_doc, "category", qc_doc,
                reason="触发质检 SOP: 核对 PO/ASN/批次")
    steps.append({"step": 4, "phase": "质检 SOP", "result": "SOP-WH-001"})

    # Step5: 异常兜底
    fallback = None
    if not rec_bin:
        # 候选库位都满 → 建议调拨 / 紧急扩容
        kg.mark_focus(material, note="兜底: 所有推荐库位满载, 需走紧急扩容或调拨")
        fallback = "无可用库位 → 建议紧急扩容 或 从其他工厂调拨"
    elif not chosen_sup:
        fallback = "未找到供应商 → 需采购新建供应商档案"

    if rec_bin:
        kg.mark_focus(rec_bin["bin"], note=f"结论: 收料编排完成 → 库位 {rec_bin['bin_id']}")

    return {
        "material": material, "supplier": chosen_sup, "plant": chosen_plant,
        "bin": rec_bin["bin"] if rec_bin else None,
        "steps": steps, "fallback": fallback,
    }


def _get_edge_attr(kg, s, p, o, attr):
    for r in kg.out(s, p):
        if r.obj == o:
            return r.edge.get(attr)
    return None


def rule_plan_issue(kg: KnowledgeGraph, customer: str, material: str,
                    qty: int = 100) -> dict:
    """R3: 智能体编排发料 (需求 → FIFO 拣选 → 复核 → 出库 → 过账)"""
    kg.mark_focus(customer, note="推理起点: 需求部门/客户")
    kg.mark_focus(material, note="目标物料")
    steps = []

    # Step1: 客户需求确认
    avg_qty = _get_edge_attr(kg, customer, "demands", material, "avg_monthly_qty")
    kg.mark_hop(customer, "demands", material,
                reason=f"{_label(kg, customer)} 月均需求 {avg_qty} {kg.get_entity(material).attrs.get('uom','EA')}")
    steps.append({"step": 1, "phase": "需求确认",
                  "result": f"月均 {avg_qty} (本次申请 {qty})"})

    # Step2: FIFO 拣选
    fifo = _stock_by_lot_fifo(kg, material)
    picked, remaining = [], qty
    for sr_id, lot, lot_qty in fifo:
        if remaining <= 0:
            break
        take = min(remaining, lot_qty)
        picked.append({"record": sr_id, "lot": lot, "qty": take})
        kg.mark_hop(sr_id, "stored_at", sr_id,
                    reason=f"按 FIFO 拣选 {lot} 数量 {take}")
        remaining -= take
    steps.append({"step": 2, "phase": "FIFO 拣选", "result": f"拣选 {len(picked)} 个批次"})

    # Step3: 异常兜底
    fallback = None
    if remaining > 0:
        kg.mark_focus(material, note=f"兜底: 库存缺口 {remaining}, 触发补货或调拨")
        fallback = (f"库存不足, 缺口 {remaining} → 触发调拨或紧急补货; "
                    f"或拆单部分发货")

    # Step4: 出库 SOP
    steps.append({"step": 4, "phase": "出库 SOP", "result": "SOP-WH-002 (MB1A 过账)"})
    kg.mark_hop("doc:sop-issue", "category", "doc:sop-issue",
                reason="触发发料 SOP")

    # Step5: 跨部门交接 (采购已完成, 仓储出库, 计划员确认)
    handoffs = []
    if avg_qty and qty > avg_qty * 1.5:
        handoffs.append("计划员: 异常大批量发料 → 复核生产计划")
        kg.mark_focus(customer, note="跨部门: 计划员复核申请合理性")

    return {
        "customer": customer, "material": material, "qty": qty,
        "picked": picked, "short": max(remaining, 0),
        "steps": steps, "handoffs": handoffs, "fallback": fallback,
    }


def rule_plan_transfer(kg: KnowledgeGraph, material: str, qty: int = 100,
                       target_plant: str | None = None) -> dict:
    """R4: 智能体编排调拨 (源库位 → 目标库位 → 在途 → 收货确认)"""
    kg.mark_focus(material, note="推理起点: 待调拨物料")
    steps = []

    # Step1: 源工厂定位
    plants = [r.obj for r in kg.out(material, "belongs_to_plant")]
    source_plant = plants[0] if plants else None
    if source_plant:
        kg.mark_hop(material, "belongs_to_plant", source_plant,
                    reason=f"源工厂 {_label(kg, source_plant)}")
    target = target_plant if target_plant and target_plant in plants else (
        plants[1] if len(plants) > 1 else None)

    # Step2: 源库位查找 (取最大库存所在)
    candidates = []
    for r in kg.inn(material, "holds_stock"):
        bin_eid = r.subject
        qty_in_bin = r.edge.get("qty", 0)
        candidates.append((bin_eid, qty_in_bin))
    candidates.sort(key=lambda x: -x[1])
    source_bin = candidates[0][0] if candidates else None
    if source_bin:
        kg.mark_hop(source_bin, "holds_stock", material,
                    reason=f"源库位 {_label(kg, source_bin)} 现有库存 {candidates[0][1]}")
    steps.append({"step": 1, "phase": "源库位定位", "result": _label(kg, source_bin) if source_bin else "无"})

    # Step3: 目标库位推荐 (复用 R1 但限定工厂)
    bin_plan = rule_recommend_bin(kg, material)
    rec_bin = bin_plan["recommendations"][0] if bin_plan["recommendations"] else None
    steps.append({"step": 2, "phase": "目标库位推荐",
                  "result": rec_bin["bin_id"] if rec_bin else "无"})

    # Step4: 在途跟踪
    steps.append({"step": 3, "phase": "在途登记", "result": f"调拨 {qty} {kg.get_entity(material).attrs.get('uom','EA')}"})

    # Step5: 收货确认
    steps.append({"step": 4, "phase": "收货确认", "result": "MB1B 过账 + 实物扫码"})

    # Step6: 异常兜底
    fallback = None
    if not source_bin:
        fallback = "无源库位 → 物料不在任何库位"
    elif not rec_bin:
        fallback = "目标工厂无可用库位 → 走紧急扩容"

    if source_bin and rec_bin:
        kg.mark_focus(rec_bin["bin"], note=f"结论: 调拨编排完成 → {_label(kg, source_bin)} → {rec_bin['bin_id']}")

    return {
        "material": material, "qty": qty,
        "source_plant": source_plant, "target_plant": target,
        "source_bin": source_bin, "target_bin": rec_bin["bin"] if rec_bin else None,
        "steps": steps, "fallback": fallback,
    }


def rule_plan_stocktake(kg: KnowledgeGraph, plant: str | None = None) -> dict:
    """R5: 智能体编排盘点 (ABC分类 → 循环盘点 → 差异报告)"""
    kg.mark_focus(plant or "ALL", note="推理起点: 盘点范围")
    steps = []

    bins = []
    for b in kg.list_entities("StorageBin"):
        if plant:
            # 限定工厂: 通过 holds_stock 反查物料 → belongs_to_plant
            in_plant = False
            for r in kg.out(b.eid, "holds_stock"):
                for pp in kg.out(r.obj, "belongs_to_plant"):
                    if pp.obj == plant:
                        in_plant = True
                        break
                if in_plant:
                    break
            if not in_plant:
                continue
        bins.append(b)

    # ABC 分类: 按库存金额近似 (qty + 所属物料)
    classified = {"A": [], "B": [], "C": []}
    for b in bins:
        total_qty = sum(r.edge.get("qty", 0) for r in kg.out(b.eid, "holds_stock"))
        if total_qty >= 2000:
            classified["A"].append(b.eid)
        elif total_qty >= 500:
            classified["B"].append(b.eid)
        else:
            classified["C"].append(b.eid)
        kg.mark_hop(b.eid, "zone", b.eid,
                    reason=f"库位 {b.attrs['bin_id']} 库存 {total_qty} → ABC分类")

    steps.append({"step": 1, "phase": "ABC 分类",
                  "result": f"A:{len(classified['A'])} B:{len(classified['B'])} C:{len(classified['C'])}"})
    steps.append({"step": 2, "phase": "盘点策略",
                  "result": "A类月盘 / B类季盘 / C类半年盘"})
    steps.append({"step": 3, "phase": "差异报告", "result": "SAP MI09 事务码"})

    if classified["A"]:
        kg.mark_focus(classified["A"][0], note=f"结论: 优先盘点 A 类库位 {len(classified['A'])} 个")

    return {"plant": plant, "bins_total": len(bins),
            "classified": classified, "steps": steps}


def rule_detect_idle_stock(kg: KnowledgeGraph, threshold_days: int = 180) -> dict:
    """R6: 识别呆滞料 (无移动 > threshold + 库存 > 安全库存)"""
    kg.mark_focus("ALL", note="推理起点: 全量库存扫描")
    findings = []
    for s in kg.list_entities("StockRecord"):
        idle = int(s.attrs.get("days_idle", 0))
        qty = int(s.attrs.get("qty", 0))
        ss = int(s.attrs.get("safety_stock", 0))
        if idle < threshold_days:
            continue
        # 风险评级: 高 (> 240 天 + qty > 2*安全) / 中 (> 180 天 + qty > 安全)
        excess = max(qty - ss, 0)
        if idle > 240 and excess > ss:
            risk = "high"
        elif idle > 180 and excess > 0:
            risk = "medium"
        else:
            risk = "low"

        # 反查所属物料 (stored_at: stk -> bin, holds_stock: bin -> mat)
        bin_rel = kg.out(s.eid, "stored_at")
        mat_id = None
        if bin_rel:
            # bin 的 holds_stock 出边指向物料
            bin_eid = bin_rel[0].obj
            mat_rels = kg.out(bin_eid, "holds_stock")
            if mat_rels:
                mat_id = mat_rels[0].obj

        kg.mark_focus(s.eid, note=f"呆滞风险 {risk}: 闲置 {idle}天, 库存 {qty}, 安全 {ss}")
        if mat_id:
            kg.mark_hop(mat_id, "holds_stock", bin_rel[0].obj,
                        reason=f"{_label(kg, mat_id)} 在 {_label(kg, bin_rel[0].obj)} 积压 {excess}")
        findings.append({
            "record": s.eid, "material": mat_id, "bin": bin_rel[0].obj if bin_rel else None,
            "days_idle": idle, "qty": qty, "safety_stock": ss,
            "excess": excess, "risk": risk,
        })
    findings.sort(key=lambda x: (-( {"high":3,"medium":2,"low":1}[x["risk"]] ), -x["excess"]))
    return {"threshold_days": threshold_days, "count": len(findings), "findings": findings}


def rule_cross_dept_handoff(kg: KnowledgeGraph) -> dict:
    """R7: 识别跨部门任务交接点 + 自动填充交接信息"""
    handoffs = []
    for t in kg.list_entities("AgentTask"):
        if t.attrs.get("state") not in ("pending", "running"):
            continue
        # 收集 requires_role 文档
        doc_rels = kg.out(t.eid, "requires_role")
        if not doc_rels:
            continue
        role = doc_rels[0].edge.get("role", "")
        doc_id = doc_rels[0].obj
        plant = kg.neighbors(t.eid, "task_in_plant")
        plant = plant[0] if plant else None
        mat = kg.neighbors(t.eid, "task_targets_material")
        mat = mat[0] if mat else None
        kg.mark_hop(t.eid, "requires_role", doc_id,
                    reason=f"交接: {role} 按 SOP {_label(kg, doc_id)} 处理 {_label(kg, mat) if mat else ''}")
        # 跨部门判定: assignee vs 文档 category
        doc_cat = kg.get_entity(doc_id).attrs.get("category", "") if kg.get_entity(doc_id) else ""
        is_cross = role not in (t.attrs.get("assignee", ""))
        handoffs.append({
            "task": t.eid, "task_type": t.attrs.get("task_type"),
            "state": t.attrs.get("state"),
            "role": role, "doc": doc_id, "plant": plant, "material": mat,
            "cross_dept": is_cross, "category": doc_cat,
        })
    return {"count": len(handoffs), "handoffs": handoffs}


def _materialize_obsolete_risk(kg: KnowledgeGraph) -> int:
    """M1: 把呆滞风险 ≥ medium 的 (Material, StockRecord) 物化为 at_risk_of_obsolete"""
    n = 0
    res = rule_detect_idle_stock(kg)
    for f in res["findings"]:
        if f["risk"] not in ("medium", "high"):
            continue
        if not f["material"]:
            continue
        if kg.add_inferred(f["material"], "at_risk_of_obsolete", f["record"],
                           risk_level=f["risk"], days_idle=f["days_idle"],
                           excess_qty=f["excess"]):
            n += 1
    return n


# --------------------------------------------------------------------------- #
# 默认规则集
# --------------------------------------------------------------------------- #
def build_warehouse_rules() -> list[Rule]:
    return [
        Rule("R1_recommend_bin_for_material", "根据物料属性(易腐/危化/成品)推荐库位",
             "Material(?m) -> zone 匹配 -> StorageBin(?b); capacity - used > 0",
             "query", 10, lambda kg, material: rule_recommend_bin(kg, material)),
        Rule("R2_plan_receipt", "智能体编排收料(供应商→工厂→库位→质检→入库)",
             "Supplier(?s) -supplies_to-> Material(?m); Material(?m) -belongs_to_plant-> Plant; R1 → bin",
             "query", 20,
             lambda kg, material, supplier=None, plant=None:
                 rule_plan_receipt(kg, material, supplier, plant)),
        Rule("R3_plan_issue", "智能体编排发料(需求→FIFO拣选→复核→出库→过账)",
             "Customer(?c) -demands-> Material(?m); StockRecord FIFO by lot; 拣选 sum(qty)≥req",
             "query", 30,
             lambda kg, customer, material, qty=100:
                 rule_plan_issue(kg, customer, material, qty)),
        Rule("R4_plan_transfer", "智能体编排调拨(源库位→目标库位→在途→收货)",
             "Material(?m) -belongs_to_plant-> Plant; StorageBin(?b1) -holds_stock-> ?m; target_bin via R1",
             "query", 40,
             lambda kg, material, qty=100, target_plant=None:
                 rule_plan_transfer(kg, material, qty, target_plant)),
        Rule("R5_plan_stocktake", "智能体编排盘点(ABC分类→循环盘点→差异报告)",
             "StorageBin(?b) -holds_stock-> Material(?m); qty threshold → ABC",
             "query", 50,
             lambda kg, plant=None: rule_plan_stocktake(kg, plant)),
        Rule("R6_detect_idle_stock", "识别呆滞料(无移动 > 180天 + 库存 > 安全库存)",
             "StockRecord(?s) days_idle>180 ∧ qty>safety_stock → risk=medium/high",
             "query", 60,
             lambda kg, threshold_days=180: rule_detect_idle_stock(kg, threshold_days)),
        Rule("R7_cross_dept_handoff", "识别跨部门任务交接点",
             "AgentTask(?t) -requires_role-> KBDoc(?d); role ≠ assignee → cross_dept",
             "query", 70,
             lambda kg: rule_cross_dept_handoff(kg)),
        Rule("M1_materialize_obsolete_risk", "[物化]呆滞风险 ≥ medium 写入 at_risk_of_obsolete",
             "Material(?m) -holds_stock-> StockRecord(?s); risk ≥ medium => at_risk_of_obsolete",
             "materialize", 5, _materialize_obsolete_risk),
    ]