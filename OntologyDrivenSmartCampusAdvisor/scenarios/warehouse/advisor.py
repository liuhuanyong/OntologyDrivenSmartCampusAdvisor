"""
仓库场景 NLQ 路由 (Advisor)
===========================
复用全局 ontology.KnowledgeGraph / scenarios.warehouse.rules.RuleEngine,
不修改全局 advisor.py。

意图 (5 种):
  plan_receipt    收料 / 入库 / 到货 / 上架
  plan_issue      发料 / 出库 / 领料 / 拣货
  plan_transfer   调拨 / 移库 / 转储
  plan_stocktake  盘点 / 盘库 / 核对
  idle_stock_alert 呆滞 / 预警 / 风险 / 高库存
"""
from __future__ import annotations

import os, sys
_HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from ontology import KnowledgeGraph
from rules import _label
from scenarios.warehouse.rules import RuleEngine


# --------------------------------------------------------------------------- #
# 意图 + 关键词
# --------------------------------------------------------------------------- #
INTENT_KEYWORDS: dict[str, list[str]] = {
    "plan_receipt":     ["收料", "入库", "到货", "上架", "收货"],
    "plan_issue":       ["发料", "出库", "领料", "拣货", "发货"],
    "plan_transfer":    ["调拨", "移库", "转储", "调货", "调到", "调往"],
    "plan_stocktake":   ["盘点", "盘库", "核对", "盘存"],
    "idle_stock_alert": ["呆滞", "预警", "风险", "高库存", "积压"],
}


# 各意图的规则编排
RULE_FLOWS: dict[str, list[dict]] = {
    "plan_receipt": [
        {"rule": "R1_recommend_bin_for_material", "depends_on": [],
         "chinese": "先按物料属性匹配可用库位",
         "why": "易腐/危化/成品有专属区域, 先确定库位再编排收料"},
        {"rule": "R2_plan_receipt", "depends_on": ["R1_recommend_bin_for_material"],
         "chinese": "编排收料全流程 (供应商→工厂→库位→质检→上架→过账)",
         "why": "区别于固定流程 RPA, 智能体可根据 PO 类型 (标准/紧急/退货) 自动选路径"},
        {"rule": "R7_cross_dept_handoff", "depends_on": [],
         "chinese": "识别跨部门交接点 (采购员→仓储员→质检)",
         "why": "智能体自动标注每步交接的责任人 / SOP 文档"},
    ],
    "plan_issue": [
        {"rule": "R3_plan_issue", "depends_on": [],
         "chinese": "编排发料 (需求→FIFO拣选→复核→出库→过账)",
         "why": "智能体自动按 FIFO 选批次, 库存不足时输出兜底方案"},
        {"rule": "R7_cross_dept_handoff", "depends_on": [],
         "chinese": "跨部门交接 (计划员/调度员)",
         "why": "大批量发料时自动触发计划员复核"},
    ],
    "plan_transfer": [
        {"rule": "R1_recommend_bin_for_material", "depends_on": [],
         "chinese": "为目标库位推荐可用库位",
         "why": "调拨需先确定目标库位容量"},
        {"rule": "R4_plan_transfer", "depends_on": ["R1_recommend_bin_for_material"],
         "chinese": "编排调拨全流程 (源库位→在途→收货→过账)",
         "why": "智能体编排源库位选择 + 在途跟踪 + 收货确认"},
    ],
    "plan_stocktake": [
        {"rule": "R5_plan_stocktake", "depends_on": [],
         "chinese": "按 ABC 分类编排盘点",
         "why": "智能体根据库存量自动分类, 差异化盘点频率"},
        {"rule": "R6_detect_idle_stock", "depends_on": [],
         "chinese": "同时扫描呆滞料 (盘点重点)",
         "why": "呆滞料属于盘点重点, 一并识别"},
    ],
    "idle_stock_alert": [
        {"rule": "R6_detect_idle_stock", "depends_on": [],
         "chinese": "扫描呆滞料 + 风险评级",
         "why": "按 days_idle + 库存量 / 安全库存 评估风险等级"},
        {"rule": "R7_cross_dept_handoff", "depends_on": [],
         "chinese": "推送跨部门处理任务 (计划员+采购员)",
         "why": "呆滞料需跨部门评审 (调拨/促销/报废)"},
    ],
}


# 规则的中文含义
RULE_MEANINGS: dict[str, str] = {
    "R1_recommend_bin_for_material": "根据物料的易腐 / 危化 / 成品属性匹配目标 zone, "
                                   "再校验库位剩余容量, 选剩余容量最大的库位作为推荐。",
    "R2_plan_receipt": "智能体编排收料: 选供应商 (按 rating) → 路由目标工厂 → 复用 R1 推荐库位 "
                       "→ 关联质检 SOP → 上架 → 过账。异常时输出兜底方案。",
    "R3_plan_issue": "智能体编排发料: 按客户需求 → FIFO 拣选可用批次 → 复核 → 出库 SOP (MB1A 过账) "
                     "→ 跨部门交接。库存不足时拆单或触发补货 / 调拨。",
    "R4_plan_transfer": "智能体编排调拨: 选源工厂 → 找源库位 (取库存最大) → 复用 R1 推荐目标库位 → "
                        "在途登记 → 收货确认 → MB1B 过账。",
    "R5_plan_stocktake": "智能体编排盘点: 按库位库存量做 ABC 分类 → 差异化盘点频率 "
                         "(A 类月盘 / B 类季盘 / C 类半年盘) → MI09 过账差异。",
    "R6_detect_idle_stock": "扫描所有 StockRecord, days_idle > 180 天 且 qty > safety_stock 视为呆滞。"
                           "风险评级: high (idle>240 + excess>ss) / medium (idle>180 + excess>0)。",
    "R7_cross_dept_handoff": "遍历 AgentTask, 提取 requires_role 关联的角色 + SOP 文档, "
                            "对比 assignee 判断是否跨部门, 输出交接点清单。",
    "M1_materialize_obsolete_risk": "把 R6 中风险等级 ≥ medium 的 (Material, StockRecord) 物化"
                                   "为 at_risk_of_obsolete 边, 含 risk_level / days_idle / excess_qty 边属性。",
}


EXAMPLE_QUESTIONS = [
    # 收料
    "RM001 怎么安排入库？",
    "锂电池 18650 现在收料走什么流程？",
    "上海仓来了一批 PCB 主板如何上架？",
    # 发料
    "总装车间要领 800 个主控芯片怎么发料？",
    "客户服务中心需要 100 个电源适配器如何安排？",
    "深圳电子市场订 500 台 A 型机怎么拣货？",
    # 调拨
    "上海仓的 PCB 主板怎么调到深圳仓？",
    "原材料 ABS 塑胶粒在哪个工厂间调拨？",
    # 盘点
    "上海仓怎么安排盘点？",
    "全部工厂的盘点策略是什么？",
    # 呆滞预警
    "现在有哪些呆滞料？",
    "识别高风险积压物料",
    "哪些库存需要预警？",
]


# --------------------------------------------------------------------------- #
# 实体解析
# --------------------------------------------------------------------------- #
def _resolve_material(kg: KnowledgeGraph, text: str) -> str | None:
    # 1) 物料代码 (如 RM001, FG002)
    import re
    m = re.search(r'\b([A-Z]{2,4}\d{3})\b', text.upper())
    if m:
        code = m.group(1)
        for mat in kg.list_entities("Material"):
            if mat.attrs.get("code", "").upper() == code:
                return mat.eid
    # 2) 中文名子串匹配 (双向: text in name / name in text)
    def _match(name: str) -> bool:
        if not name:
            return False
        if name in text or text in name:
            return True
        # 模糊匹配: 取 name 中 - 之后的连续子片段 (>= 3 字), 看是否在 text 中
        for part in name.replace(" - ", "-").split("-"):
            part = part.strip()
            if len(part) >= 3 and part in text:
                return True
        return False
    for mat in kg.list_entities("Material"):
        if _match(mat.attrs.get("name", "")):
            return mat.eid
    for cus in kg.list_entities("Customer"):
        if _match(cus.attrs.get("name", "")):
            return cus.eid
    for p in kg.list_entities("Plant"):
        if _match(p.attrs.get("name", "")):
            return p.eid
    return None


def _resolve_customer(kg: KnowledgeGraph, text: str) -> str | None:
    def _match(name: str) -> bool:
        if not name:
            return False
        if name in text or text in name:
            return True
        for part in name.replace(" - ", "-").split("-"):
            part = part.strip()
            if len(part) >= 3 and part in text:
                return True
        return False
    for cus in kg.list_entities("Customer"):
        if _match(cus.attrs.get("name", "")):
            return cus.eid
    return None


def _resolve_plant(kg: KnowledgeGraph, text: str) -> str | None:
    def _match(name: str) -> bool:
        if not name:
            return False
        if name in text or text in name:
            return True
        for part in name.replace(" - ", "-").split("-"):
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
    """复用全局 advisor._build_reasoning_block 的语义, 这里本地实现以避免跨包导入。"""
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


def answer_plan_receipt(kg: KnowledgeGraph, engine: RuleEngine,
                        material: str | None = None,
                        supplier: str | None = None,
                        plant: str | None = None) -> dict:
    # 默认挑一个未完成的 receipt 任务关联物料
    if not material:
        for t in kg.list_entities("AgentTask"):
            if t.attrs.get("task_type") == "receipt" and t.attrs.get("state") in ("pending", "running"):
                mats = kg.neighbors(t.eid, "task_targets_material")
                if mats:
                    material = mats[0]
                    break
    if not material:
        material = "mat:rm001"  # 最终兜底

    mat_name = kg.get_entity(material).attrs["name"]
    r1 = engine.query_traced("R1_recommend_bin_for_material", material=material)
    r2 = engine.query_traced("R2_plan_receipt", material=material, supplier=supplier, plant=plant)
    r7 = engine.query_traced("R7_cross_dept_handoff")
    plan = r2["result"]

    lines = [f"【收料编排】物料 {mat_name}"]
    lines.append(f"步骤:")
    for s in plan.get("steps", []):
        lines.append(f"  {s['step']}. {s['phase']} → {s['result']}")
    if plan.get("fallback"):
        lines.append(f"兜底方案: {plan['fallback']}")

    cross = [h for h in r7["result"]["handoffs"]
             if h["task_type"] == "receipt" and h.get("cross_dept")]
    if cross:
        lines.append("跨部门交接:")
        for h in cross[:3]:
            lines.append(f"  - 任务 {h['task']} ({h['state']}) 角色: {h['role']} "
                         f"SOP: {_label(kg, h['doc'])}")

    involved = (r1["trace"]["involved_entities"]
                | r2["trace"]["involved_entities"]
                | r7["trace"]["involved_entities"])

    reasoning = [
        _build_reasoning_block(kg, engine, "R1_recommend_bin_for_material",
            goal=f"为 {mat_name} 推荐入库库位",
            conclusion=f"推荐 {len(r1['result']['candidates'])} 个候选, "
                       f"最优 {_label(kg, r1['result']['recommendations'][0]['bin']) if r1['result']['recommendations'] else '无'}",
            traced_result=r1),
        _build_reasoning_block(kg, engine, "R2_plan_receipt",
            goal=f"编排 {mat_name} 的收料任务",
            conclusion=f"供应商={_label(kg, plan['supplier']) if plan['supplier'] else '无'} "
                       f"工厂={_label(kg, plan['plant']) if plan['plant'] else '无'} "
                       f"库位={_label(kg, plan['bin']) if plan['bin'] else '无'}",
            traced_result=r2),
        _build_reasoning_block(kg, engine, "R7_cross_dept_handoff",
            goal="扫描跨部门交接点",
            conclusion=f"识别 {len(cross)} 个收料类跨部门交接",
            traced_result=r7),
    ]
    return {"answer": "\n".join(lines), "reasoning": reasoning, "involved": involved}


def answer_plan_issue(kg: KnowledgeGraph, engine: RuleEngine,
                      customer: str | None = None,
                      material: str | None = None,
                      qty: int = 100) -> dict:
    # 默认挑一个未完成的 issue 任务关联的 (物料, 客户)
    if not material or not customer:
        for t in kg.list_entities("AgentTask"):
            if t.attrs.get("task_type") == "issue" and t.attrs.get("state") in ("pending", "running"):
                mats = kg.neighbors(t.eid, "task_targets_material")
                if mats:
                    material = material or mats[0]
                    # 用需求部门推断 customer
                    for r in kg.inn(material, "demands"):
                        customer = customer or r.subject
                        break
                break
    if not material:
        material = "mat:fg001"
    if not customer:
        customer = "cus:ext01"

    cus_name = kg.get_entity(customer).attrs["name"]
    mat_name = kg.get_entity(material).attrs["name"]
    r3 = engine.query_traced("R3_plan_issue", customer=customer, material=material, qty=qty)
    r7 = engine.query_traced("R7_cross_dept_handoff")
    plan = r3["result"]

    lines = [f"【发料编排】{cus_name} 领 {qty} {kg.get_entity(material).attrs.get('uom','EA')} {mat_name}"]
    lines.append(f"步骤:")
    for s in plan.get("steps", []):
        lines.append(f"  {s['step']}. {s['phase']} → {s['result']}")
    if plan.get("picked"):
        lines.append(f"FIFO 拣选 ({len(plan['picked'])} 批次):")
        for p in plan["picked"]:
            lines.append(f"  - {p['lot']} × {p['qty']} (记录 {p['record']})")
    if plan.get("short", 0) > 0:
        lines.append(f"⚠️ 库存缺口: {plan['short']}")
    if plan.get("fallback"):
        lines.append(f"兜底方案: {plan['fallback']}")
    if plan.get("handoffs"):
        lines.append("跨部门交接:")
        for h in plan["handoffs"]:
            lines.append(f"  - {h}")

    involved = r3["trace"]["involved_entities"] | r7["trace"]["involved_entities"]
    reasoning = [
        _build_reasoning_block(kg, engine, "R3_plan_issue",
            goal=f"编排 {cus_name} 领 {mat_name}",
            conclusion=f"拣选 {len(plan.get('picked',[]))} 批次, 缺口 {plan.get('short',0)}",
            traced_result=r3),
        _build_reasoning_block(kg, engine, "R7_cross_dept_handoff",
            goal="扫描跨部门交接点",
            conclusion=f"识别 {r7['result']['count']} 个交接点",
            traced_result=r7),
    ]
    return {"answer": "\n".join(lines), "reasoning": reasoning, "involved": involved}


def answer_plan_transfer(kg: KnowledgeGraph, engine: RuleEngine,
                         material: str | None = None,
                         target_plant: str | None = None,
                         qty: int = 100) -> dict:
    if not material:
        for t in kg.list_entities("AgentTask"):
            if t.attrs.get("task_type") == "transfer" and t.attrs.get("state") == "pending":
                mats = kg.neighbors(t.eid, "task_targets_material")
                if mats:
                    material = mats[0]
                    break
    if not material:
        material = "mat:rm002"

    mat_name = kg.get_entity(material).attrs["name"]
    r1 = engine.query_traced("R1_recommend_bin_for_material", material=material)
    r4 = engine.query_traced("R4_plan_transfer", material=material, qty=qty, target_plant=target_plant)
    plan = r4["result"]

    lines = [f"【调拨编排】{mat_name} × {qty}"]
    lines.append(f"步骤:")
    for s in plan.get("steps", []):
        lines.append(f"  {s['step']}. {s['phase']} → {s['result']}")
    if plan.get("source_plant"):
        lines.append(f"源工厂: {_label(kg, plan['source_plant'])}")
    if plan.get("target_plant"):
        lines.append(f"目标工厂: {_label(kg, plan['target_plant'])}")
    if plan.get("source_bin"):
        lines.append(f"源库位: {_label(kg, plan['source_bin'])}")
    if plan.get("target_bin"):
        lines.append(f"目标库位: {_label(kg, plan['target_bin'])}")
    if plan.get("fallback"):
        lines.append(f"兜底方案: {plan['fallback']}")

    involved = r1["trace"]["involved_entities"] | r4["trace"]["involved_entities"]
    reasoning = [
        _build_reasoning_block(kg, engine, "R1_recommend_bin_for_material",
            goal=f"为 {mat_name} 推荐目标库位",
            conclusion=f"候选 {len(r1['result']['candidates'])} 个",
            traced_result=r1),
        _build_reasoning_block(kg, engine, "R4_plan_transfer",
            goal=f"编排 {mat_name} 的调拨任务",
            conclusion=f"源={_label(kg, plan['source_bin']) if plan['source_bin'] else '无'} "
                       f"目标={_label(kg, plan['target_bin']) if plan['target_bin'] else '无'}",
            traced_result=r4),
    ]
    return {"answer": "\n".join(lines), "reasoning": reasoning, "involved": involved}


def answer_plan_stocktake(kg: KnowledgeGraph, engine: RuleEngine,
                          plant: str | None = None) -> dict:
    r5 = engine.query_traced("R5_plan_stocktake", plant=plant)
    r6 = engine.query_traced("R6_detect_idle_stock")
    plan = r5["result"]

    lines = ["【盘点编排】"]
    if plan.get("plant"):
        lines.append(f"范围: {_label(kg, plan['plant'])}")
    else:
        lines.append(f"范围: 全工厂")
    lines.append(f"总库位: {plan['bins_total']}")
    cls = plan["classified"]
    lines.append(f"ABC 分类: A={len(cls['A'])} B={len(cls['B'])} C={len(cls['C'])}")
    lines.append("盘点策略: A类月盘 / B类季盘 / C类半年盘")
    idle = r6["result"]["findings"]
    lines.append(f"扫描到 {len(idle)} 条呆滞料 (重点盘点对象)")

    involved = r5["trace"]["involved_entities"] | r6["trace"]["involved_entities"]
    reasoning = [
        _build_reasoning_block(kg, engine, "R5_plan_stocktake",
            goal="按 ABC 分类编排盘点任务",
            conclusion=f"A:{len(cls['A'])} B:{len(cls['B'])} C:{len(cls['C'])}",
            traced_result=r5),
        _build_reasoning_block(kg, engine, "R6_detect_idle_stock",
            goal="扫描呆滞料 (盘点重点)",
            conclusion=f"识别 {len(idle)} 条呆滞料",
            traced_result=r6),
    ]
    return {"answer": "\n".join(lines), "reasoning": reasoning, "involved": involved}


def answer_idle_stock_alert(kg: KnowledgeGraph, engine: RuleEngine) -> dict:
    r6 = engine.query_traced("R6_detect_idle_stock")
    r7 = engine.query_traced("R7_cross_dept_handoff")
    findings = r6["result"]["findings"]

    lines = [f"【呆滞料预警】扫描阈值 {r6['result']['threshold_days']} 天, 识别 {len(findings)} 条"]
    high = [f for f in findings if f["risk"] == "high"]
    medium = [f for f in findings if f["risk"] == "medium"]
    low = [f for f in findings if f["risk"] == "low"]
    lines.append(f"  高风险: {len(high)} 条")
    lines.append(f"  中风险: {len(medium)} 条")
    lines.append(f"  低风险: {len(low)} 条")
    if high:
        lines.append("\n高风险明细:")
        for f in high[:5]:
            mat_name = kg.get_entity(f["material"]).attrs["name"] if f["material"] else "?"
            bin_name = kg.get_entity(f["bin"]).attrs["bin_id"] if f["bin"] else "?"
            lines.append(f"  - {mat_name} @ {bin_name}: 闲置 {f['days_idle']}天, "
                         f"库存 {f['qty']}, 超储 {f['excess']}")
    handoffs = [h for h in r7["result"]["handoffs"] if h["cross_dept"]]
    if handoffs:
        lines.append("\n推送跨部门处理:")
        for h in handoffs[:5]:
            lines.append(f"  - {h['role']} 接手 {_label(kg, h['task'])} ({h['task_type']})")

    # 物化边统计
    inferred_count = sum(1 for _ in kg._inferred)
    lines.append(f"\n物化边总数: {inferred_count} (at_risk_of_obsolete)")

    involved = r6["trace"]["involved_entities"] | r7["trace"]["involved_entities"]
    reasoning = [
        _build_reasoning_block(kg, engine, "R6_detect_idle_stock",
            goal="扫描呆滞料 + 风险评级",
            conclusion=f"高{len(high)} 中{len(medium)} 低{len(low)}",
            traced_result=r6),
        _build_reasoning_block(kg, engine, "R7_cross_dept_handoff",
            goal="推送跨部门评审",
            conclusion=f"{len(handoffs)} 个跨部门交接点",
            traced_result=r7),
    ]
    return {"answer": "\n".join(lines), "reasoning": reasoning, "involved": involved}


# --------------------------------------------------------------------------- #
# 8 阶段 Pipeline (复用全局 advisor 风格, 但场景定制)
# --------------------------------------------------------------------------- #
def parse_question(kg: KnowledgeGraph, question: str) -> tuple[dict | None, list[dict]]:
    q = question.strip()
    pipeline: list[dict] = []

    # 步骤1: 意图识别
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

    # 步骤2: 物料 / 客户 / 工厂实体解析
    pipeline.append({
        "step": 2, "phase": "NLU", "action": "物料/客户/工厂实体解析",
        "method": "正则匹配物料代码 + 中文名子串双向匹配",
    })
    material = _resolve_material(kg, q)
    customer = _resolve_customer(kg, q)
    plant = _resolve_plant(kg, q)

    # 数量提取 (如 "800 个", "100 EA")
    import re as _re
    qty_match = _re.search(r"(\d+)\s*(?:个|件|箱|EA|KG|kg|台|只)?", q)
    qty = int(qty_match.group(1)) if qty_match else None
    # 限定为 < 10000 才视为合理 qty (避免解析到年份等)
    if qty and qty >= 10000:
        qty = None

    parts = []
    if material:
        parts.append(f"物料={material} ({kg.get_entity(material).attrs['name']})")
    if customer:
        parts.append(f"客户={customer} ({kg.get_entity(customer).attrs['name']})")
    if plant:
        parts.append(f"工厂={plant} ({kg.get_entity(plant).attrs['name']})")
    if qty:
        parts.append(f"数量={qty}")
    pipeline[-1]["result"] = "✅ " + ("、".join(parts) if parts else "未识别到具体实体 (将使用默认任务/物料)")

    return {
        "intent": intent,
        "material": material,
        "customer": customer,
        "plant": plant,
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
            "answer": "抱歉，我无法理解你的问题。试试:\n  - " +
                      "\n  - ".join(EXAMPLE_QUESTIONS[:5]),
            "pipeline": pipeline,
            "reasoning": [], "involved": [], "subgraph": {"nodes": [], "edges": []},
            "answer_nodes": [], "rule_flow": [],
        }

    intent = parsed["intent"]
    material = parsed["material"]
    customer = parsed["customer"]
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

    # 阶段3: 参数补全 (略, 已在 parse 时尝试解析)
    pipeline.append({
        "step": 5, "phase": "Param Resolution", "action": "参数补全",
        "method": "默认从挂起任务关联实体中拣取",
        "result": f"material={material} customer={customer} plant={plant} qty={qty}",
    })

    # 阶段4: 执行规则链
    pipeline.append({
        "step": 6, "phase": "Reasoning", "action": "执行规则链",
        "method": "按编排顺序逐条调用规则, 开启 trace 记录图游走",
        "chain": [dict(rf) for rf in rule_flow],
        "result": f"开始执行 {len(rule_flow)} 条规则...",
    })

    if intent == "plan_receipt":
        result = answer_plan_receipt(kg, engine, material=material, plant=plant)
    elif intent == "plan_issue":
        result = answer_plan_issue(kg, engine, customer=customer, material=material, qty=qty or 100)
    elif intent == "plan_transfer":
        result = answer_plan_transfer(kg, engine, material=material, target_plant=plant, qty=qty or 100)
    elif intent == "plan_stocktake":
        result = answer_plan_stocktake(kg, engine, plant=plant)
    elif intent == "idle_stock_alert":
        result = answer_idle_stock_alert(kg, engine)
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
    for eid in list(result["involved"]):
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
    }


# --------------------------------------------------------------------------- #
# CLI 演示入口
# --------------------------------------------------------------------------- #
def _banner(title: str) -> None:
    print("\n" + "=" * 64)
    print(f"  {title}")
    print("=" * 64)


def main() -> None:
    from scenarios.warehouse.knowledge_base import build_warehouse_knowledge_base
    from scenarios.warehouse.rules import build_warehouse_rules

    _banner("Warehouse Scenario · CLI 演示")
    kg = build_warehouse_knowledge_base()
    print(f"  {kg}")
    engine = RuleEngine(kg)
    for r in build_warehouse_rules():
        engine.register(r)
    added = engine.forward_chain()
    print(f"  物化: {added}")
    for r in sorted(engine.rules.values(), key=lambda x: x.priority):
        print(f"  [{r.kind:11}] {r.name:32} {r.description}")

    questions = [
        ("RM001 怎么安排入库？", "plan_receipt"),
        ("总装车间要领 800 个主控芯片怎么发料？", "plan_issue"),
        ("上海仓的 PCB 主板怎么调到深圳仓？", "plan_transfer"),
        ("上海仓怎么安排盘点？", "plan_stocktake"),
        ("现在有哪些呆滞料？", "idle_stock_alert"),
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