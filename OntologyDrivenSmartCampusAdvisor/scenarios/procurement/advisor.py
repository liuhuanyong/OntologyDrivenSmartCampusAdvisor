"""
采购场景 NLQ 路由 (Advisor)
===========================
复用全局 ontology.KnowledgeGraph / scenarios.procurement.rules.RuleEngine,
不修改全局 advisor.py。

意图 (7 种):
  create_pr        创建 PR / 请购
  query_pr         查询 PR 状态 / 列表
  approve_pr       审批 PR
  pr_to_po         PR 转 PO
  query_po         查询 PO 状态 / 列表
  approve_po       审批 PO
  delivery_status  交货跟踪 / 逾期
"""
from __future__ import annotations

import os, sys
import re
_HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from ontology import KnowledgeGraph
from rules import _label
from scenarios.procurement.rules import RuleEngine


# --------------------------------------------------------------------------- #
# 意图 + 关键词
# --------------------------------------------------------------------------- #
INTENT_KEYWORDS: dict[str, list[str]] = {
    "create_pr":       ["创建申请", "请购", "发起采购", "新增 PR", "提个申请",
                         "要采购", "帮我买", "需要买", "做个申请", "申请购买",
                         "创建一个采购申请", "帮我创建一个"],
    "query_pr":        ["查申请", "哪些申请", "我的 PR", "采购申请",
                         "哪些 PR", "PR 列表", "查询 PR", "PR 状态",
                         "申请单状态", "申请状态", "还在审批",
                         "最优供应商", "谁能供", "谁能提供", "找供应商",
                         "供应商推荐", "哪家能供", "谁供应",
                         "找哪家", "哪家供应商", "哪家供", "应该找哪家",
                         "找哪个供应商", "推荐供应商",
                         "现在到哪一步", "到哪一步了", "哪一步了",
                         "到哪一步了"],
    "approve_pr":      ["审批申请", "通过申请", "驳回申请", "批准 PR",
                         "审核 PR", "处理 PR", "审批一下", "审批 PR",
                         "帮我审批"],
    "pr_to_po":        ["转订单", "转成采购单", "生成 PO", "转 PO",
                         "转成 PO", "转采购订单", "转成采购订单",
                         "帮我转", "帮我生成"],
    "query_po":        ["采购单", "哪些订单", "查订单",
                         "查询 PO", "PO 列表", "订单状态", "现在什么状态",
                         "PO 现在", "订单进度", "什么状态",
                         "PO 状态", "现在状态", "订单状态如何"],
    "approve_po":      ["审批订单", "通过订单", "批准 PO", "审核 PO",
                         "审批 PO", "帮我审批订单", "审批采购订单"],
    "delivery_status": ["交货", "到货", "收货", "逾期", "跟踪", "进度",
                         "什么时候到", "到货状态", "已逾期"],
}


# 各意图的规则编排
RULE_FLOWS: dict[str, list[dict]] = {
    "create_pr": [
        {"rule": "R1_source_recommendation", "depends_on": [],
         "chinese": "按物料 + 工厂查询货源清单, 推荐合格供应商",
         "why": "SourceList 是采购寻源的合规依据, 优先 fixed_flag=True 的货源"},
        {"rule": "R2_plan_pr_creation", "depends_on": ["R1_source_recommendation"],
         "chinese": "编排 PR 创建全流程 (物料 → 工厂 → 库位 → 供应商 → 价格)",
         "why": "区别于固定流程 RPA, 智能体自动校验 MOQ / 提前期 / 信息记录价格"},
    ],
    "query_pr": [
        {"rule": "M1_materialize_pending_pr", "depends_on": [],
         "chinese": "物化审批中超过 30 天的 PR (at_risk_of_delay)",
         "why": "对悬而未决的 PR 自动标记延期风险, 推送给采购主管"},
        {"rule": "R3_approve_pr", "depends_on": [],
         "chinese": "对查询到的 PR 做供应商资质 + 价格合理性体检",
         "why": "智能体主动识别风险, 不只是简单列表返回"},
    ],
    "approve_pr": [
        {"rule": "R3_approve_pr", "depends_on": [],
         "chinese": "校验供应商资质 + 信息记录价格 + 总金额 + 偏差",
         "why": "PR 审批需检查价格偏离 + 供应商 rating + 信息记录完整性"},
    ],
    "pr_to_po": [
        {"rule": "R4_pr_to_po", "depends_on": [],
         "chinese": "按供应商归集 PR 行项目, 校验 MOQ + 提前期",
         "why": "智能体自动按供应商拆单/合并 PO, 避免一个 PO 多供应商"},
        {"rule": "R6_detect_price_deviation", "depends_on": [],
         "chinese": "校验转 PO 后的单价是否偏离信息记录",
         "why": "防止采购员手动改价, 偏离 ±10% 触发复核"},
    ],
    "query_po": [
        {"rule": "R5_approve_po", "depends_on": [],
         "chinese": "对查询到的 PO 做金额 / 付款条款 / 国际贸易条款体检",
         "why": "智能体主动识别大额合同 + 外币风险 + 非常用条款"},
        {"rule": "R7_track_delivery_overdue", "depends_on": [],
         "chinese": "同步跟踪 PO 的交货进度, 标记逾期",
         "why": "交货逾期直接影响生产排程"},
    ],
    "approve_po": [
        {"rule": "R5_approve_po", "depends_on": [],
         "chinese": "校验合同金额 + 付款条款 + 国际贸易条款 + 货币",
         "why": "PO 是对外法律契约, 审批需严谨"},
        {"rule": "R6_detect_price_deviation", "depends_on": [],
         "chinese": "检查 PO 行项目单价 vs 信息记录价格偏离",
         "why": "防止价格操纵, 偏离 ±10% 触发预警"},
    ],
    "delivery_status": [
        {"rule": "R7_track_delivery_overdue", "depends_on": [],
         "chinese": "扫描所有 PO 行项目, 标记逾期",
         "why": "按 delivery_date 与当前日期比较 + delivered_qty 判断"},
        {"rule": "R5_approve_po", "depends_on": [],
         "chinese": "对未清的 PO 复检审批状态",
         "why": "未审批完成的 PO 即使发货也需先审批"},
    ],
}


# 规则的中文含义
RULE_MEANINGS: dict[str, str] = {
    "R1_source_recommendation": "遍历 SourceList 找物料+工厂匹配的有效货源, "
                                 "按 rating + fixed_flag + mrp_flag 计算评分, "
                                 "推荐评分最高的供应商。",
    "R2_plan_pr_creation": "智能体编排 PR 创建: 选工厂 (默认第一个) → 匹配活跃库位 → "
                            "复用 R1 选供应商 → 取信息记录 net_price 作为 PR 预估单价 → "
                            "输出完整 PR 草稿。",
    "R3_approve_pr": "审批 PR: 校验供应商资质 (信息记录存在) + 价格偏离 "
                     "(PR 单价 vs 信息记录 net_price, 偏离 ±10%/±20% 分级) → "
                     "输出最终决策 (approve / conditional_approve)。",
    "R4_pr_to_po": "PR 转 PO: 按供应商 ID 归集 PR 行项目, 每组生成一张 PO 草稿, "
                   "校验 MOQ (最小订单量) + 提前期 + 总金额。",
    "R5_approve_po": "审批 PO: 校验合同金额 (≥50000 需主管) + 付款条款 "
                     "(非标准账期) + 国际贸易条款 (FOB/CIF/EXW/DDP) + 货币 (外币风险)。",
    "R6_detect_price_deviation": "扫描所有 PO 行项目, 比较 unit_price 与对应信息记录 "
                                  "net_price, 偏离 >10% 触发 medium, >20% 触发 high。",
    "R7_track_delivery_overdue": "遍历 PO 行项目, 当 delivery_date < 今天 且 "
                                  "delivered_qty < quantity 时视为逾期, "
                                  "按逾期天数降序排列。",
    "M1_materialize_pending_pr": "把 pr_status=pending_approval 且 申请时间 > 30天 的 PR "
                                 "物化为 at_risk_of_delay 自环边, 含 days_pending + severity。",
}


EXAMPLE_QUESTIONS = [
    # 创建 PR
    "帮我创建一个采购申请: 电子元件-主控芯片 STM32 2000 个",
    "请购 1000 个 PCB 主板",
    "我要买 300 个精密轴承, 帮我发起采购",
    # 查询 PR
    "有哪些采购申请还在审批中？",
    "PR-2026-00001 现在到哪一步了？",
    "我提交的采购申请状态如何？",
    # 审批 PR
    "帮我审批一下 PR-2026-00001",
    "批准 PR-2026-00002",
    # PR 转 PO
    "把 PR-2026-00003 转成采购订单",
    "PR-2026-00003 帮我生成 PO",
    # 查询 PO
    "PO-2026-00789 现在什么状态？",
    "有哪些采购订单已下达？",
    # 审批 PO
    "审批 PO-2026-00789",
    "帮我看看 PO-2026-00792 能否通过",
    # 交货跟踪
    "哪些采购订单已逾期？",
    "PO-2026-00790 的交货进度？",
    "现在有哪些订单还没到货？",
    # 寻源推荐
    "M1001 的最优供应商是谁？",
    "物料 M1005 谁能供？",
]


# --------------------------------------------------------------------------- #
# 实体解析
# --------------------------------------------------------------------------- #
def _resolve_pr(kg: KnowledgeGraph, text: str) -> str | None:
    """解析 PR-YYYY-NNNNN"""
    m = re.search(r'\bPR-?(\d{4}-?\d{5})\b', text.upper())
    if m:
        pr_id = "PR-" + m.group(1).replace("-", "-")
        for pr in kg.list_entities("PurchaseRequisition"):
            if pr.attrs.get("pr_id", "").upper() == pr_id.upper():
                return pr.eid
    # 中文名子串
    for pr in kg.list_entities("PurchaseRequisition"):
        for it in [r.obj for r in kg.out(pr.eid, "has_item")]:
            mat = kg.get_entity(it)
            if mat:
                mat_ent_id = None
                for mi in kg.list_entities("Material"):
                    if mi.attrs.get("material_id") == mat.attrs.get("material_id"):
                        mat_ent_id = mi.eid
                        break
                if mat_ent_id and mat.attrs.get("material_id", "") in text:
                    return pr.eid
    return None


def _resolve_po(kg: KnowledgeGraph, text: str) -> str | None:
    """解析 PO-YYYY-NNNNN"""
    m = re.search(r'\bPO-?(\d{4}-?\d{5})\b', text.upper())
    if m:
        po_id = "PO-" + m.group(1).replace("-", "-")
        for po in kg.list_entities("PurchaseOrder"):
            if po.attrs.get("po_id", "").upper() == po_id.upper():
                return po.eid
    return None


def _resolve_material(kg: KnowledgeGraph, text: str) -> str | None:
    """物料代码 (M1001) + 中文名双向匹配"""
    m = re.search(r'\b(M\d{4})\b', text.upper())
    if m:
        mid = m.group(1)
        for mat in kg.list_entities("Material"):
            if mat.attrs.get("material_id", "").upper() == mid:
                return mat.eid
    def _match(name: str) -> bool:
        if not name:
            return False
        if name in text or text in name:
            return True
        for part in name.replace("-", " ").replace("-", " ").split():
            part = part.strip()
            if len(part) >= 3 and part in text:
                return True
        return False
    for mat in kg.list_entities("Material"):
        if _match(mat.attrs.get("name", "")):
            return mat.eid
    return None


def _resolve_supplier(kg: KnowledgeGraph, text: str) -> str | None:
    def _match(name: str) -> bool:
        if not name:
            return False
        if name in text or text in name:
            return True
        for part in name.replace("-", " ").replace(" ", " ").split():
            part = part.strip()
            if len(part) >= 3 and part in text:
                return True
        return False
    for v in kg.list_entities("Supplier"):
        if _match(v.attrs.get("name", "")):
            return v.eid
    return None


def _resolve_plant(kg: KnowledgeGraph, text: str) -> str | None:
    def _match(name: str) -> bool:
        if not name:
            return False
        if name in text or text in name:
            return True
        for part in name.replace("-", " ").split():
            part = part.strip()
            if len(part) >= 3 and part in text:
                return True
        return False
    for p in kg.list_entities("Plant"):
        if _match(p.attrs.get("name", "")):
            return p.eid
    return None


# --------------------------------------------------------------------------- #
# 答案生成器
# --------------------------------------------------------------------------- #
def _build_reasoning_block(kg: KnowledgeGraph, engine: RuleEngine,
                           rule_name: str, goal: str, conclusion: str,
                           traced_result: dict) -> dict:
    trace = traced_result["trace"]
    rule = engine.rules.get(rule_name)
    hops, focus = [], []
    for h in trace["hops"]:
        item = {
            "from": h["subject"],
            "from_label": _label(kg, h["subject"]),
            "predicate": h["predicate"],
            "to": h["object"],
            "to_label": _label(kg, h["object"]),
            "reason": h["reason"],
        }
        if h["predicate"] == "__focus__":
            focus.append({"id": h["subject"], "note": h["reason"]})
        else:
            hops.append(item)
    return {
        "rule": rule_name,
        "rule_desc": rule.description if rule else "",
        "rule_pattern": rule.pattern if rule else "",
        "rule_kind": rule.kind if rule else "query",
        "rule_priority": rule.priority if rule else 0,
        "rule_meaning": RULE_MEANINGS.get(rule_name, ""),
        "goal": goal,
        "hops": hops,
        "focus": focus,
        "conclusion": conclusion,
        "result": traced_result["result"],
    }


def answer_create_pr(kg: KnowledgeGraph, engine: RuleEngine,
                     material: str | None = None,
                     quantity: int | None = None,
                     plant: str | None = None) -> dict:
    """创建 PR"""
    # 默认挑第一个物料 + 数量 100
    if not material:
        materials = kg.list_entities("Material")
        material = materials[0].eid if materials else None
    if not quantity:
        quantity = 100
    if not plant:
        plants = kg.list_entities("Plant")
        plant = plants[0].eid if plants else None

    r1 = engine.query_traced("R1_source_recommendation", material=material, plant=plant)
    r2 = engine.query_traced("R2_plan_pr_creation", material=material,
                             quantity=quantity, plant=plant)
    plan = r2["result"]

    mat_name = kg.get_entity(material).attrs["name"] if material else "?"
    lines = [f"【PR 创建编排】物料 {mat_name} × {quantity}"]
    lines.append("步骤:")
    for s in plan.get("steps", []):
        line = f"  {s['step']}. {s['phase']} → {s.get('result', '?')}"
        if "score" in s:
            line += f" (评分 {s['score']})"
        lines.append(line)
    if plan.get("vendor"):
        lines.append(f"\n推荐供应商: {_label(kg, plan['vendor'])}")
    if plan.get("unit_price"):
        lines.append(f"预估单价: ¥{plan['unit_price']}")
        lines.append(f"预估总金额: ¥{plan['unit_price'] * quantity}")
    if plan.get("fallback"):
        lines.append(f"兜底方案: {plan['fallback']}")

    involved = r1["trace"]["involved_entities"] | r2["trace"]["involved_entities"]
    # mark_hop 不会触发 _record_walk, 因此 from/to 需要手工补到 involved
    for rb in [r1, r2]:
        for h in rb["trace"]["hops"]:
            involved.add(h["subject"])
            involved.add(h["object"])
    # 显式补齐关键主数据: 货源清单 / 信息记录 节点 (R1/R2 trace 已覆盖来源, 这里冗余保险)
    for src in kg.list_entities("SourceList"):
        if src.attrs.get("material_id") == kg.get_entity(material).attrs.get("material_id"):
            involved.add(src.eid)
    for ir in kg.list_entities("InfoRecord"):
        if ir.attrs.get("material_id") == kg.get_entity(material).attrs.get("material_id"):
            involved.add(ir.eid)
    reasoning = [
        _build_reasoning_block(kg, engine, "R1_source_recommendation",
            goal=f"为 {mat_name} 推荐合格供应商",
            conclusion=f"找到 {len(r1['result']['candidates'])} 个候选, "
                       f"最优 {_label(kg, r1['result']['recommendations'][0]['vendor']) if r1['result']['recommendations'] else '无'}",
            traced_result=r1),
        _build_reasoning_block(kg, engine, "R2_plan_pr_creation",
            goal=f"编排 {mat_name} 的 PR 创建",
            conclusion=f"供应商={_label(kg, plan['vendor']) if plan['vendor'] else '无'} "
                       f"工厂={_label(kg, plan['plant']) if plan['plant'] else '无'}",
            traced_result=r2),
    ]
    return {
        "answer": "\n".join(lines),
        "reasoning": reasoning,
        "involved": involved,
        "stages": [s.get("stage") for s in plan.get("steps", []) if s.get("stage")],
    }


def answer_source_recommendation(kg: KnowledgeGraph, engine: RuleEngine,
                                 material: str | None = None,
                                 plant: str | None = None) -> dict:
    """寻源推荐 — 物料 + 工厂 → 推荐合格供应商"""
    if not material:
        materials = kg.list_entities("Material")
        material = materials[0].eid if materials else None
    if not material:
        return {"answer": "无可推荐物料", "reasoning": [], "involved": set()}

    mat_name = kg.get_entity(material).attrs["name"]
    r1 = engine.query_traced("R1_source_recommendation", material=material, plant=plant)
    res = r1["result"]

    lines = [f"【寻源推荐】物料 {mat_name}"]
    if plant:
        lines.append(f"工厂: {_label(kg, plant)}")
    if res["candidates"]:
        lines.append(f"找到 {len(res['candidates'])} 个合格货源:")
        for i, c in enumerate(res["candidates"][:5], 1):
            lines.append(f"  {i}. {c['vendor_name']} (rating={c['rating']}, "
                        f"fixed={c['fixed']}, mrp={c['mrp']}, 评分={c['score']})")
        top = res["recommendations"][0]
        lines.append(f"\n推荐供应商: {top['vendor_name']} "
                    f"(评分 {top['score']})")
    else:
        lines.append("⚠️ 未找到有效货源 → 建议临时寻源或新建信息记录")

    involved = r1["trace"]["involved_entities"]
    reasoning = [
        _build_reasoning_block(kg, engine, "R1_source_recommendation",
            goal=f"为 {mat_name} 推荐合格供应商",
            conclusion=f"找到 {len(res['candidates'])} 个候选, "
                       f"最优 {_label(kg, res['recommendations'][0]['vendor']) if res['recommendations'] else '无'}",
            traced_result=r1),
    ]
    return {"answer": "\n".join(lines), "reasoning": reasoning, "involved": involved}


def answer_query_pr(kg: KnowledgeGraph, engine: RuleEngine,
                    pr: str | None = None) -> dict:
    """查询 PR"""
    # 物化
    materialize_count = engine.query_traced("M1_materialize_pending_pr",
                                            threshold_days=30)["result"]
    # 选取待审批 PR
    if not pr:
        for pr_ent in kg.list_entities("PurchaseRequisition"):
            if pr_ent.attrs.get("pr_status") == "pending_approval":
                pr = pr_ent.eid
                break
    if not pr:
        # 拿第一个
        all_prs = kg.list_entities("PurchaseRequisition")
        pr = all_prs[0].eid if all_prs else None
    if not pr:
        return {"answer": "没有可查询的 PR", "reasoning": [], "involved": set()}

    pr_ent = kg.get_entity(pr)
    r3 = engine.query_traced("R3_approve_pr", pr=pr, decision="approve")
    res = r3["result"]

    lines = [f"【PR 查询】{pr_ent.attrs.get('pr_id')}"]
    lines.append(f"状态: {pr_ent.attrs.get('pr_status')}")
    lines.append(f"申请人: {pr_ent.attrs.get('applicant')} ({pr_ent.attrs.get('dept')})")
    lines.append(f"申请日期: {pr_ent.attrs.get('doc_date')}")
    lines.append(f"优先级: {pr_ent.attrs.get('priority')}")
    lines.append(f"总金额: ¥{pr_ent.attrs.get('total_amount')}")
    lines.append(f"行项目数: {res['item_count']}")

    if res.get("price_alerts"):
        lines.append("\n价格预警:")
        for a in res["price_alerts"]:
            lines.append(f"  [{a['level']}] {a['msg']}")

    # 列出 PR 延期物化边
    inferred_delays = sum(1 for (s, _, o) in kg._inferred
                          if s == pr and o == pr)
    if inferred_delays > 0:
        lines.append(f"\n⚠️ 此 PR 存在延期风险 (at_risk_of_delay)")

    involved = r3["trace"]["involved_entities"]
    reasoning = [
        _build_reasoning_block(kg, engine, "M1_materialize_pending_pr",
            goal="物化审批中超过 30 天的 PR",
            conclusion=f"本次物化 {materialize_count} 条 at_risk_of_delay 边",
            traced_result=engine.query_traced("M1_materialize_pending_pr",
                                               threshold_days=30)),
        _build_reasoning_block(kg, engine, "R3_approve_pr",
            goal=f"体检 PR {pr_ent.attrs.get('pr_id')}",
            conclusion=f"决策={res['decision']}, 价格预警={len(res['price_alerts'])} 条",
            traced_result=r3),
    ]
    return {"answer": "\n".join(lines), "reasoning": reasoning, "involved": involved}


def answer_approve_pr(kg: KnowledgeGraph, engine: RuleEngine,
                      pr: str | None = None) -> dict:
    """审批 PR"""
    if not pr:
        for pr_ent in kg.list_entities("PurchaseRequisition"):
            if pr_ent.attrs.get("pr_status") == "pending_approval":
                pr = pr_ent.eid
                break
    if not pr:
        return {"answer": "没有待审批的 PR", "reasoning": [], "involved": set()}

    pr_ent = kg.get_entity(pr)
    r3 = engine.query_traced("R3_approve_pr", pr=pr, decision="approve")
    res = r3["result"]

    lines = [f"【PR 审批】{pr_ent.attrs.get('pr_id')}"]
    lines.append(f"决策: {res['decision']}")
    if res.get("reasons"):
        lines.append("理由:")
        for r in res["reasons"]:
            lines.append(f"  - {r}")
    if res.get("price_alerts"):
        lines.append("\n价格预警:")
        for a in res["price_alerts"]:
            lines.append(f"  [{a['level']}] {a['msg']}")
    if res.get("checks"):
        lines.append("\n供应商资质校验:")
        for c in res["checks"][:5]:
            lines.append(f"  - 行项目 {c['item']}: rating={c.get('vendor_rating', '?')}")

    involved = r3["trace"]["involved_entities"]
    reasoning = [
        _build_reasoning_block(kg, engine, "R3_approve_pr",
            goal=f"审批 PR {pr_ent.attrs.get('pr_id')}",
            conclusion=f"决策={res['decision']}, 警告={len(res['price_alerts'])}",
            traced_result=r3),
    ]
    return {"answer": "\n".join(lines), "reasoning": reasoning, "involved": involved}


def answer_pr_to_po(kg: KnowledgeGraph, engine: RuleEngine,
                    pr: str | None = None) -> dict:
    """PR 转 PO"""
    if not pr:
        for pr_ent in kg.list_entities("PurchaseRequisition"):
            if pr_ent.attrs.get("pr_status") == "approved":
                pr = pr_ent.eid
                break
    if not pr:
        # 兜底用 pending_approval
        for pr_ent in kg.list_entities("PurchaseRequisition"):
            if pr_ent.attrs.get("pr_status") == "pending_approval":
                pr = pr_ent.eid
                break
    if not pr:
        return {"answer": "没有可转 PO 的 PR", "reasoning": [], "involved": set()}

    pr_ent = kg.get_entity(pr)
    r4 = engine.query_traced("R4_pr_to_po", pr=pr)
    r6 = engine.query_traced("R6_detect_price_deviation")
    plan = r4["result"]

    lines = [f"【PR → PO 编排】{pr_ent.attrs.get('pr_id')}"]
    if plan.get("fallback"):
        lines.append(f"兜底: {plan['fallback']}")
        return {"answer": "\n".join(lines), "reasoning": [], "involved": set()}

    lines.append(f"按供应商归集, 共 {len(plan['groups'])} 张 PO 草稿:")
    for i, g in enumerate(plan["groups"], 1):
        lines.append(f"  PO 草稿 {i}: 供应商={g['vendor_name']} ({g['vendor_id']})")
        lines.append(f"    行项目: {g['item_count']} 条, 总金额 ¥{g['total_amount']:,}")
        lines.append(f"    最长提前期: {g['lead_time']} 天")
        if g.get("moq_violations"):
            lines.append(f"    ⚠️ MOQ 违反: {len(g['moq_violations'])} 条")

    price_dev = r6["result"]
    lines.append(f"\n价格偏离体检: {price_dev['count']} 条")
    if price_dev["findings"]:
        for f in price_dev["findings"][:5]:
            lines.append(f"  [{f['level']}] {f['material']}: "
                        f"PO ¥{f['po_price']} vs 信息记录 ¥{f['ir_price']} "
                        f"(偏离 {f['deviation']*100:.1f}%)")

    involved = r4["trace"]["involved_entities"] | r6["trace"]["involved_entities"]
    reasoning = [
        _build_reasoning_block(kg, engine, "R4_pr_to_po",
            goal=f"将 {pr_ent.attrs.get('pr_id')} 按供应商归集生成 PO",
            conclusion=f"生成 {len(plan['groups'])} 张 PO, 总金额 "
                       f"¥{sum(g['total_amount'] for g in plan['groups']):,}",
            traced_result=r4),
        _build_reasoning_block(kg, engine, "R6_detect_price_deviation",
            goal="体检转 PO 后的价格偏离",
            conclusion=f"{price_dev['count']} 条偏离",
            traced_result=r6),
    ]
    return {"answer": "\n".join(lines), "reasoning": reasoning, "involved": involved}


def answer_query_po(kg: KnowledgeGraph, engine: RuleEngine,
                    po: str | None = None) -> dict:
    """查询 PO"""
    if not po:
        all_pos = kg.list_entities("PurchaseOrder")
        po = all_pos[0].eid if all_pos else None
    if not po:
        return {"answer": "没有 PO", "reasoning": [], "involved": set()}

    po_ent = kg.get_entity(po)
    r5 = engine.query_traced("R5_approve_po", po=po)
    r7 = engine.query_traced("R7_track_delivery_overdue")
    res = r5["result"]

    lines = [f"【PO 查询】{po_ent.attrs.get('po_id')}"]
    lines.append(f"供应商: {po_ent.attrs.get('vendor_id')}")
    lines.append(f"类型: {po_ent.attrs.get('po_type')}, 状态: {po_ent.attrs.get('doc_status')}")
    lines.append(f"币种: {po_ent.attrs.get('currency')}, 付款条款: {po_ent.attrs.get('payment_terms')}")
    lines.append(f"贸易条款: {po_ent.attrs.get('incoterms')}")
    lines.append(f"合同金额: ¥{po_ent.attrs.get('contract_amount')}")
    lines.append(f"决策: {res['decision']}")
    if res.get("checks"):
        lines.append("\n体检项:")
        for c in res["checks"]:
            lines.append(f"  [{c['level']}] {c['type']}: {c['msg']}")

    # 关联的逾期
    overdue = [o for o in r7["result"]["overdue"]
               if po_ent.attrs.get("po_id") in
                  kg.get_entity(o["po_item"]).attrs.get("po_ref", "")
               or True]  # 简化为全部
    # 正确做法: 通过 has_po_item 反查
    po_overdue = []
    for r in kg.out(po, "has_po_item"):
        poi_id = r.obj
        for o in r7["result"]["overdue"]:
            if o["po_item"] == poi_id:
                po_overdue.append(o)
    if po_overdue:
        lines.append("\n⚠️ 含逾期行项目:")
        for o in po_overdue:
            lines.append(f"  - 物料 {o['material']}: 逾期 {o['days_overdue']} 天, "
                        f"剩余 {o['remaining']}")

    involved = r5["trace"]["involved_entities"] | r7["trace"]["involved_entities"]
    reasoning = [
        _build_reasoning_block(kg, engine, "R5_approve_po",
            goal=f"体检 PO {po_ent.attrs.get('po_id')}",
            conclusion=f"决策={res['decision']}, 警告={len(res['checks'])} 条",
            traced_result=r5),
        _build_reasoning_block(kg, engine, "R7_track_delivery_overdue",
            goal="扫描交货逾期",
            conclusion=f"{r7['result']['count']} 条逾期 (其中本 PO {len(po_overdue)} 条)",
            traced_result=r7),
    ]
    return {"answer": "\n".join(lines), "reasoning": reasoning, "involved": involved}


def answer_approve_po(kg: KnowledgeGraph, engine: RuleEngine,
                      po: str | None = None) -> dict:
    """审批 PO"""
    if not po:
        for po_ent in kg.list_entities("PurchaseOrder"):
            if po_ent.attrs.get("doc_status") == "pending_approval":
                po = po_ent.eid
                break
    if not po:
        return {"answer": "没有待审批的 PO", "reasoning": [], "involved": set()}

    po_ent = kg.get_entity(po)
    r5 = engine.query_traced("R5_approve_po", po=po)
    r6 = engine.query_traced("R6_detect_price_deviation")
    res = r5["result"]

    lines = [f"【PO 审批】{po_ent.attrs.get('po_id')}"]
    lines.append(f"合同金额: ¥{po_ent.attrs.get('contract_amount')}")
    lines.append(f"决策: {res['decision']}")
    if res.get("checks"):
        lines.append("体检项:")
        for c in res["checks"]:
            lines.append(f"  [{c['level']}] {c['type']}: {c['msg']}")

    # 该 PO 的价格偏离
    po_price_issues = []
    for r in kg.out(po, "has_po_item"):
        poi_id = r.obj
        for f in r6["result"]["findings"]:
            if f["po_item"] == poi_id:
                po_price_issues.append(f)
    if po_price_issues:
        lines.append("\n价格偏离:")
        for f in po_price_issues:
            lines.append(f"  [{f['level']}] {f['material']}: 偏离 {f['deviation']*100:.1f}%")

    involved = r5["trace"]["involved_entities"] | r6["trace"]["involved_entities"]
    reasoning = [
        _build_reasoning_block(kg, engine, "R5_approve_po",
            goal=f"审批 PO {po_ent.attrs.get('po_id')}",
            conclusion=f"决策={res['decision']}",
            traced_result=r5),
        _build_reasoning_block(kg, engine, "R6_detect_price_deviation",
            goal="体检价格偏离",
            conclusion=f"共 {r6['result']['count']} 条 (本 PO {len(po_price_issues)} 条)",
            traced_result=r6),
    ]
    return {"answer": "\n".join(lines), "reasoning": reasoning, "involved": involved}


def answer_delivery_status(kg: KnowledgeGraph, engine: RuleEngine,
                           po: str | None = None) -> dict:
    """交货跟踪 / 逾期"""
    r7 = engine.query_traced("R7_track_delivery_overdue")
    r5_res = None
    if po:
        r5_res = engine.query_traced("R5_approve_po", po=po)

    overdue = r7["result"]["overdue"]
    lines = [f"【交货跟踪】扫描时间 {r7['result']['today']}, 共发现 {len(overdue)} 条逾期"]
    if overdue:
        lines.append("\n逾期明细:")
        for o in overdue[:10]:
            lines.append(f"  - 物料 {o['material']}: 交货日期 {o['delivery_date']}, "
                        f"已交 {o['delivered_qty']}/{o['ordered_qty']}, "
                        f"逾期 {o['days_overdue']} 天")

    if po and r5_res:
        po_ent = kg.get_entity(po)
        lines.append(f"\n关联 PO: {po_ent.attrs.get('po_id')}")
        lines.append(f"  状态: {po_ent.attrs.get('doc_status')}")
        lines.append(f"  决策: {r5_res['result']['decision']}")

    # 物化边统计
    inferred_count = sum(1 for _ in kg._inferred)
    lines.append(f"\n物化边总数: {inferred_count}")

    involved = r7["trace"]["involved_entities"]
    reasoning = [
        _build_reasoning_block(kg, engine, "R7_track_delivery_overdue",
            goal="扫描所有 PO 行项目的交货状态",
            conclusion=f"识别 {len(overdue)} 条逾期",
            traced_result=r7),
    ]
    if po and r5_res:
        reasoning.append(
            _build_reasoning_block(kg, engine, "R5_approve_po",
                goal=f"复检 PO {kg.get_entity(po).attrs.get('po_id')}",
                conclusion=f"决策={r5_res['result']['decision']}",
                traced_result=r5_res),
        )
        involved |= r5_res["trace"]["involved_entities"]
    return {"answer": "\n".join(lines), "reasoning": reasoning, "involved": involved}


# --------------------------------------------------------------------------- #
# 8 阶段 Pipeline
# --------------------------------------------------------------------------- #
def parse_question(kg: KnowledgeGraph, question: str) -> tuple[dict | None, list[dict]]:
    q = question.strip()
    pipeline: list[dict] = []

    # 步骤 1: 意图识别
    pipeline.append({
        "step": 1, "phase": "NLU", "action": "意图识别",
        "method": "基于 INTENT_KEYWORDS 关键词词典匹配",
        "detail": f"候选意图: {list(INTENT_KEYWORDS)}",
    })
    intent = None
    matched_kw = None
    for it, keywords in INTENT_KEYWORDS.items():
        for kw in keywords:
            if kw in q:
                intent = it
                matched_kw = kw
                break
        if intent:
            break
    if not intent:
        pipeline[-1]["result"] = "❌ 未匹配到任何意图"
        return None, pipeline
    pipeline[-1]["result"] = f"✅ 识别意图 = {intent} (命中关键词 '{matched_kw}')"

    # 步骤 2: 实体解析
    pipeline.append({
        "step": 2, "phase": "NLU", "action": "实体解析",
        "method": "正则匹配 PR-/PO-/M[0-9]+ 代码 + 中文名子串双向匹配",
    })
    pr = _resolve_pr(kg, q)
    po = _resolve_po(kg, q)
    material = _resolve_material(kg, q)
    supplier = _resolve_supplier(kg, q)
    plant = _resolve_plant(kg, q)

    # 数量解析: 必须紧跟中文单位 (避免把 STM32 / M1001 / PO 编号误识为数量)
    qty_match = re.search(r"(\d+)\s*(?:个|件|箱|台|只|条|张|台套|EA|KG|kg|米|升|M|L|套|片|块)", q)
    qty = int(qty_match.group(1)) if qty_match else None
    if qty and qty >= 10000:
        qty = None

    parts = []
    if pr:
        parts.append(f"PR={pr} ({kg.get_entity(pr).attrs['pr_id']})")
    if po:
        parts.append(f"PO={po} ({kg.get_entity(po).attrs['po_id']})")
    if material:
        parts.append(f"物料={material} ({kg.get_entity(material).attrs['name']})")
    if supplier:
        parts.append(f"供应商={supplier} ({kg.get_entity(supplier).attrs['name']})")
    if plant:
        parts.append(f"工厂={plant} ({kg.get_entity(plant).attrs['name']})")
    if qty:
        parts.append(f"数量={qty}")
    pipeline[-1]["result"] = "✅ " + ("、".join(parts) if parts else "未识别到具体实体 (将使用默认)")

    return {
        "intent": intent,
        "pr": pr, "po": po,
        "material": material, "supplier": supplier, "plant": plant,
        "qty": qty,
    }, pipeline


def _extract_answer_nodes(reasoning: list[dict]) -> list[str]:
    seen = set()
    out = []
    for rb in reasoning:
        for f in rb.get("focus", []):
            note = f.get("note", "")
            if ("结论" in note or "推理结论" in note) and f["id"] not in seen:
                out.append(f["id"])
                seen.add(f["id"])
    return out


def ask(kg: KnowledgeGraph, engine: RuleEngine, question: str) -> dict:
    parsed, pipeline = parse_question(kg, question)
    if not parsed:
        pipeline.append({
            "step": 4, "phase": "FAIL", "action": "无法处理",
            "method": "意图识别失败",
            "result": "❌ 请换一种问法 (示例见 EXAMPLE_QUESTIONS)",
        })
        return {
            "question": question, "intent": "unknown",
            "answer": "抱歉,我无法理解你的问题。试试:\n  - " +
                      "\n  - ".join(EXAMPLE_QUESTIONS[:5]),
            "pipeline": pipeline,
            "reasoning": [], "involved": [], "subgraph": {"nodes": [], "edges": []},
            "answer_nodes": [], "rule_flow": [],
        }

    intent = parsed["intent"]
    pr = parsed["pr"]
    po = parsed["po"]
    material = parsed["material"]
    supplier = parsed["supplier"]
    plant = parsed["plant"]
    qty = parsed.get("qty")

    # 阶段2: 规则编排
    rule_flow = RULE_FLOWS.get(intent, [])
    pipeline.append({
        "step": 4, "phase": "Orchestration", "action": "规则编排",
        "method": f"根据意图 {intent} 查 RULE_FLOWS 表",
        "detail": " → ".join(
            f"{rf['rule']}" + (f"(依赖{rf['depends_on']})" if rf['depends_on'] else "")
            for rf in rule_flow),
        "result": f"✅ 编排出 {len(rule_flow)} 条规则: " + ", ".join(rf['rule'] for rf in rule_flow),
    })

    # 阶段3: 参数补全
    pipeline.append({
        "step": 5, "phase": "Param Resolution", "action": "参数补全",
        "method": "默认从挂起状态单据/第一个物料拣取",
        "result": f"pr={pr} po={po} material={material} supplier={supplier} plant={plant} qty={qty}",
    })

    # 阶段4: 执行规则链
    pipeline.append({
        "step": 6, "phase": "Reasoning", "action": "执行规则链",
        "method": "按编排顺序逐条调用规则, 开启 trace 记录图游走",
        "chain": [dict(rf) for rf in rule_flow],
        "result": f"开始执行 {len(rule_flow)} 条规则...",
    })

    if intent == "create_pr":
        result = answer_create_pr(kg, engine, material=material,
                                  quantity=qty or 100, plant=plant)
    elif intent == "query_pr":
        # 如果同时识别到物料 + 供应商关键词, 走 R1 货源推荐
        if material and ("供应商" in question or "货源" in question or "谁能供" in question or "推荐" in question):
            result = answer_source_recommendation(kg, engine, material=material, plant=plant)
        else:
            result = answer_query_pr(kg, engine, pr=pr)
    elif intent == "approve_pr":
        result = answer_approve_pr(kg, engine, pr=pr)
    elif intent == "pr_to_po":
        result = answer_pr_to_po(kg, engine, pr=pr)
    elif intent == "query_po":
        result = answer_query_po(kg, engine, po=po)
    elif intent == "approve_po":
        result = answer_approve_po(kg, engine, po=po)
    elif intent == "delivery_status":
        result = answer_delivery_status(kg, engine, po=po)
    else:
        result = None

    if result is None:
        pipeline.append({
            "step": 7, "phase": "FAIL", "action": "执行失败",
            "result": "❌ 规则执行返回 None",
        })
        return {
            "question": question, "intent": "error",
            "answer": "处理失败", "pipeline": pipeline,
            "reasoning": [], "involved": [], "subgraph": {"nodes": [], "edges": []},
            "answer_nodes": [], "rule_flow": [],
        }

    # 阶段5: 子图提取
    involved = set(result["involved"])
    # 把推理 hops 的 from/to 也纳入 (mark_hop 不会触发 _record_walk)
    for rb in result.get("reasoning", []):
        for h in rb.get("hops", []):
            involved.add(h["from"])
            involved.add(h["to"])
    for f in sum([rb.get("focus", []) for rb in result.get("reasoning", [])], []):
        involved.add(f.get("id"))
    for eid in list(involved):
        for r in kg.out(eid):
            involved.add(r.obj)
        for r in kg.inn(eid):
            involved.add(r.subject)
    pipeline.append({
        "step": 7, "phase": "Graph Extraction", "action": "提取推理子图",
        "method": "汇总涉及实体 + 1跳邻居, 调 subgraph_data 导出",
        "result": f"✅ 子图: {len(involved)} 节点",
    })

    # 阶段6: 答案生成
    answer_nodes = _extract_answer_nodes(result["reasoning"])
    pipeline.append({
        "step": 8, "phase": "Answer Generation", "action": "生成自然语言答案",
        "method": "汇总各规则结论, 提取 focus 标签中的答案节点",
        "result": f"✅ 答案生成完毕, 识别答案节点 {len(answer_nodes)} 个",
    })

    subgraph = kg.subgraph_data(involved)
    return {
        "question": question,
        "intent": intent,
        "answer": result["answer"],
        "pipeline": pipeline,
        "reasoning": result["reasoning"],
        "rule_flow": rule_flow,
        "answer_nodes": answer_nodes,
        "involved": list(involved),
        "subgraph": subgraph,
        "stages": result.get("stages", []),
    }


# --------------------------------------------------------------------------- #
# CLI 演示入口
# --------------------------------------------------------------------------- #
def _banner(title: str) -> None:
    print("\n" + "=" * 64)
    print(f"  {title}")
    print("=" * 64)


def main() -> None:
    from scenarios.procurement.knowledge_base import build_procurement_knowledge_base
    from scenarios.procurement.rules import build_procurement_rules

    _banner("Procurement Scenario · CLI 演示")
    kg = build_procurement_knowledge_base()
    print(f"  {kg}")
    engine = RuleEngine(kg)
    for r in build_procurement_rules():
        engine.register(r)
    added = engine.forward_chain()
    print(f"  物化: {added}")
    for r in sorted(engine.rules.values(), key=lambda x: x.priority):
        print(f"  [{r.kind:11}] {r.name:32} {r.description}")

    questions = [
        ("帮我创建一个采购申请: 电子元件-主控芯片 STM32 2000 个", "create_pr"),
        ("有哪些采购申请还在审批中？", "query_pr"),
        ("帮我审批一下 PR-2026-00001", "approve_pr"),
        ("把 PR-2026-00003 转成采购订单", "pr_to_po"),
        ("PO-2026-00789 现在什么状态？", "query_po"),
        ("审批 PO-2026-00792", "approve_po"),
        ("哪些采购订单已逾期？", "delivery_status"),
    ]
    for q, intent in questions:
        _banner(f"Q ({intent}): {q}")
        result = ask(kg, engine, q)
        print(result["answer"])
        print(f"\n  Pipeline 步骤数: {len(result['pipeline'])}")
        print(f"  Reasoning 规则数: {len(result['reasoning'])}")
        print(f"  Answer nodes: {result['answer_nodes']}")
    _banner("演示完成")


if __name__ == "__main__":
    main()
