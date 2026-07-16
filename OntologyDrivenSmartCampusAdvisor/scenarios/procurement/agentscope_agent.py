"""
Procurement AgentScope Agent
============================
使用 AgentScope 2.0 ReAct Agent + DeepSeek 模型处理采购管理问题。
支持流式响应，实时推送推理过程给前端。

使用方式:
    from scenarios.procurement.agentscope_agent import create_procurement_agent, ask_with_agent_stream

    agent = create_procurement_agent(kg, engine)
    async for event in ask_with_agent_stream("帮我创建一个采购申请: M1001 1000个", kg, engine):
        print(event)
"""
import os
import asyncio
import json
import time
from pathlib import Path
from typing import Any, AsyncGenerator

from agentscope.agent import Agent
from agentscope.model import DeepSeekChatModel
from agentscope.credential import DeepSeekCredential
from agentscope.tool import Toolkit, ToolBase, ToolChunk
from agentscope.message import Msg, TextBlock, UserMsg
from agentscope.permission import PermissionContext, PermissionDecision, PermissionBehavior

LOG_FILE = Path(__file__).parent.parent.parent / "logs" / "agent.log"
LOG_FILE.parent.mkdir(exist_ok=True)

def _log(msg: str, level: str = "INFO"):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} [{level}] {msg}"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

# 从 .env 读取 API Key
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

# System Prompt for Procurement Agent (Ontology-Driven)
SYSTEM_PROMPT = """你是采购管理智能体。基于采购业务本体模型进行语义理解和知识图谱推理。

【本体模型 - 核心业务对象】
- 采购申请(PR): BO_PLAN_PR_HEAD (单头) + BO_PLAN_PR_INFO (明细)
  关键字段: PR_ID, PR_TYPE, PR_STATUS, MATERIAL_ID, QUANTITY, DELIVERY_DATE
- 采购订单(PO): PUR_PURORDER_HEAD (单头) + PUR_PURORDER_ITEM (明细)
  关键字段: PO_ID, VENDOR_ID, CONTRACT_AMOUNT, DOCUMENT_STATUS
- 供应商: BO_PLAN_MDM_GYS
  关键字段: VENDOR_ID, VENDOR_D, STATUS
- 物料: BO_PLAN_MDM_WL
  关键字段: MATERIAL_ID, MATERIAL_D, MATGROUP_ID
- 工厂: BO_PLAN_MDM_GC
  关键字段: FACTORY_ID, FACTORY_D

【本体关系 - 图谱推理依据】
- PR → PR_INFO: 一对多 (pr_head_pr_info)
- PR_INFO → Material: 一对一 (pr_info_mdm_wl)
- PO → PO_ITEM: 一对多 (pur_purorder_head_pur_purorder_item)
- 收货单 → PO: 一对一关联 (receipt_associated_po)

【支持的操作行为】
1. query_pr: 查询采购申请列表/详情
2. create_pr: 创建采购申请
3. approve_pr: 审批采购申请
4. pr_to_po: 采购申请转采购订单
5. query_po: 查询采购订单列表/详情
6. approve_po: 审批采购订单
7. delivery_status: 查询交货状态/逾期
8. source_recommendation: 货源推荐

【推理策略】
回答时需结合知识图谱进行多跳推理：
- 查询状态时，先找到相关单据节点，再顺着关系边查找关联信息
- 创建/审批时，验证业务规则约束（如 PR 需先审批才能转 PO）
- 追踪履约进度时，通过 receipt_associated_po 关系连接收货与订单

【编号格式】
- PR: PR-2026-XXXXX
- PO: PO-2026-XXXXX
- 物料: M1001, M1002

【工具使用约束】
- 采购事实和业务操作必须先调用对应 Typed Tool，由你填写单号、物料、数量、工厂等参数。
- 最终回答必须以工具返回的 KG 事实与规则证据为准，不得重复执行写操作。
- 不要向用户原样输出工具 JSON；证据不足时明确说明，不得虚构。
"""


# ============================================================================
# 工具基类
# ============================================================================

class ProcurementToolBase(ToolBase):
    """采购工具基类"""

    is_concurrency_safe = True
    is_read_only = False

    def __init__(self, kg: Any, engine: Any):
        self.kg = kg
        self.engine = engine

    async def check_permissions(self, tool_input: dict, context: PermissionContext) -> PermissionDecision:
        try:
            return PermissionDecision(behavior=PermissionBehavior.ALLOW, message="")
        except Exception:
            return PermissionDecision(behavior=PermissionBehavior.ALLOW, message="")

    async def __call__(self, **kwargs) -> ToolChunk:
        """包装所有工具调用，捕获异常"""
        try:
            _log(f"工具调用开始: {kwargs}")
            result = await self._execute(**kwargs)
            _log(f"工具调用成功")
            return self._trace_chunk(result, kwargs)
        except Exception as e:
            _log(f"工具调用异常: {e}", "ERROR")
            return self._trace_chunk({
                "answer": f"工具执行出错: {e}",
                "reasoning": [], "involved": set(),
            }, kwargs, "error")

    async def _execute(self, **kwargs) -> dict:
        raise NotImplementedError

    def _trace_chunk(self, result: dict, tool_input: dict, status: str = "success") -> ToolChunk:
        from scenarios.procurement.advisor import RULE_FLOWS, _extract_answer_nodes

        reasoning = result.get("reasoning", [])
        ids = set()
        for block in reasoning:
            for hop in block.get("hops", []):
                ids.update((hop.get("from"), hop.get("to")))
            ids.update(f.get("id") for f in block.get("focus", []))
        ids.discard(None)
        trace = {
            "schema_version": 1,
            "scenario": "procurement",
            "tool_name": self.name,
            "tool_input": tool_input,
            "intent": self.name,
            "status": status,
            "kg_answer": result.get("answer", ""),
            "rule_flow": RULE_FLOWS.get(self.name, []),
            "reasoning": reasoning,
            "answer_nodes": _extract_answer_nodes(reasoning),
            "subgraph": self.kg.subgraph_data(ids) if ids else {"nodes": [], "edges": []},
        }
        return ToolChunk(content=[TextBlock(text=json.dumps({
            "kg_answer": trace["kg_answer"],
            "kg_trace": trace,
        }, ensure_ascii=False, default=list))])

# ============================================================================
# 工具定义
# ============================================================================

class CreatePRTool(ProcurementToolBase):
    """创建采购申请"""

    name = "create_pr"
    description = "创建采购申请。需要物料代码(M开头)和数量。示例: create_pr(material_code='M1001', quantity=1000)"
    input_schema = {
        "type": "object",
        "properties": {
            "material_code": {"type": "string", "description": "物料代码，如 M1001"},
            "quantity": {"type": "integer", "minimum": 1, "description": "采购数量"},
            "plant": {"type": "string", "description": "工厂代码(可选)"},
        },
        "required": ["material_code", "quantity"],
    }
    is_read_only = False

    async def _execute(self, material_code: str, quantity: int, plant: str = None) -> dict:
        from scenarios.procurement.advisor import answer_create_pr

        # 解析物料
        material = None
        for m in self.kg.list_entities("Material"):
            if m.attrs.get("material_id", "").upper() == material_code.upper():
                material = m.eid
                break

        if not material:
            raise ValueError(f"未找到物料 {material_code}")
        if quantity < 1:
            raise ValueError("采购数量必须大于 0")

        plant_ent = None
        if plant:
            plant_ent = next((p.eid for p in self.kg.list_entities("Plant")
                              if plant.upper() in {p.eid.upper(), str(p.attrs.get("plant_id", "")).upper()}), None)
            if not plant_ent:
                raise ValueError(f"未找到工厂 {plant}")

        result = answer_create_pr(
            self.kg, self.engine,
            material=material,
            quantity=quantity,
            plant=plant_ent
        )
        return result


class QueryPRTool(ProcurementToolBase):
    """查询 PR 状态"""

    name = "query_pr"
    description = "查询采购申请(PR)的状态。示例: query_pr(pr_id='PR-2026-00001')"
    input_schema = {
        "type": "object",
        "properties": {
            "pr_id": {"type": "string", "description": "PR 编号，如 PR-2026-00001"},
        },
    }
    is_read_only = True

    async def _execute(self, pr_id: str = None) -> dict:
        from scenarios.procurement.advisor import answer_query_pr

        # 解析 PR
        pr = None
        if pr_id:
            for p in self.kg.list_entities("PurchaseRequisition"):
                if p.attrs.get("pr_id", "").upper() == pr_id.upper():
                    pr = p.eid
                    break
            if not pr:
                raise ValueError(f"未找到采购申请 {pr_id}")

        result = answer_query_pr(self.kg, self.engine, pr=pr)
        return result


class ApprovePRTool(ProcurementToolBase):
    """审批 PR"""

    name = "approve_pr"
    description = "审批采购申请(PR)。示例: approve_pr(pr_id='PR-2026-00001')"
    input_schema = {
        "type": "object",
        "properties": {
            "pr_id": {"type": "string", "description": "PR 编号，如 PR-2026-00001"},
        },
    }
    is_read_only = False

    async def _execute(self, pr_id: str = None) -> dict:
        from scenarios.procurement.advisor import answer_approve_pr

        # 解析 PR
        pr = None
        if pr_id:
            for p in self.kg.list_entities("PurchaseRequisition"):
                if p.attrs.get("pr_id", "").upper() == pr_id.upper():
                    pr = p.eid
                    break
            if not pr:
                raise ValueError(f"未找到采购申请 {pr_id}")

        result = answer_approve_pr(self.kg, self.engine, pr=pr)
        return result


class PRToPOTool(ProcurementToolBase):
    """PR 转 PO"""

    name = "pr_to_po"
    description = "将采购申请(PR)转成采购订单(PO)。示例: pr_to_po(pr_id='PR-2026-00003')"
    input_schema = {
        "type": "object",
        "properties": {
            "pr_id": {"type": "string", "description": "PR 编号，如 PR-2026-00003"},
        },
    }
    is_read_only = False

    async def _execute(self, pr_id: str = None) -> dict:
        from scenarios.procurement.advisor import answer_pr_to_po

        # 解析 PR
        pr = None
        if pr_id:
            for p in self.kg.list_entities("PurchaseRequisition"):
                if p.attrs.get("pr_id", "").upper() == pr_id.upper():
                    pr = p.eid
                    break
            if not pr:
                raise ValueError(f"未找到采购申请 {pr_id}")

        result = answer_pr_to_po(self.kg, self.engine, pr=pr)
        return result


class QueryPOTool(ProcurementToolBase):
    """查询 PO 状态"""

    name = "query_po"
    description = "查询采购订单(PO)的状态。示例: query_po(po_id='PO-2026-00789')"
    input_schema = {
        "type": "object",
        "properties": {
            "po_id": {"type": "string", "description": "PO 编号，如 PO-2026-00789"},
        },
    }
    is_read_only = True

    async def _execute(self, po_id: str = None) -> dict:
        from scenarios.procurement.advisor import answer_query_po

        # 解析 PO
        po = None
        if po_id:
            for p in self.kg.list_entities("PurchaseOrder"):
                if p.attrs.get("po_id", "").upper() == po_id.upper():
                    po = p.eid
                    break
            if not po:
                raise ValueError(f"未找到采购订单 {po_id}")

        result = answer_query_po(self.kg, self.engine, po=po)
        return result


class ApprovePOTool(ProcurementToolBase):
    """审批 PO"""

    name = "approve_po"
    description = "审批采购订单(PO)。示例: approve_po(po_id='PO-2026-00789')"
    input_schema = {
        "type": "object",
        "properties": {
            "po_id": {"type": "string", "description": "PO 编号，如 PO-2026-00789"},
        },
    }
    is_read_only = False

    async def _execute(self, po_id: str = None) -> dict:
        from scenarios.procurement.advisor import answer_approve_po

        # 解析 PO
        po = None
        if po_id:
            for p in self.kg.list_entities("PurchaseOrder"):
                if p.attrs.get("po_id", "").upper() == po_id.upper():
                    po = p.eid
                    break
            if not po:
                raise ValueError(f"未找到采购订单 {po_id}")

        result = answer_approve_po(self.kg, self.engine, po=po)
        return result


class DeliveryStatusTool(ProcurementToolBase):
    """交货跟踪"""

    name = "delivery_status"
    description = "查询交货状态/逾期。示例: delivery_status(po_id='PO-2026-00790') 或不传参数查看所有逾期"
    input_schema = {
        "type": "object",
        "properties": {
            "po_id": {"type": "string", "description": "PO 编号(可选)，如 PO-2026-00790"},
        },
    }
    is_read_only = True

    async def _execute(self, po_id: str = None) -> dict:
        from scenarios.procurement.advisor import answer_delivery_status

        # 解析 PO
        po = None
        if po_id:
            for p in self.kg.list_entities("PurchaseOrder"):
                if p.attrs.get("po_id", "").upper() == po_id.upper():
                    po = p.eid
                    break
            if not po:
                raise ValueError(f"未找到采购订单 {po_id}")

        result = answer_delivery_status(self.kg, self.engine, po=po)
        return result


class SourceRecommendationTool(ProcurementToolBase):
    """货源推荐"""

    name = "source_recommendation"
    description = "货源推荐，根据物料和工厂推荐合格供应商。示例: source_recommendation(material_code='M1001')"
    input_schema = {
        "type": "object",
        "properties": {
            "material_code": {"type": "string", "description": "物料代码，如 M1001"},
            "plant": {"type": "string", "description": "工厂代码(可选)"},
        },
        "required": ["material_code"],
    }
    is_read_only = True

    async def _execute(self, material_code: str, plant: str = None) -> dict:
        from scenarios.procurement.advisor import answer_source_recommendation

        # 解析物料
        material = None
        for m in self.kg.list_entities("Material"):
            if m.attrs.get("material_id", "").upper() == material_code.upper():
                material = m.eid
                break

        if not material:
            raise ValueError(f"未找到物料 {material_code}")

        # 解析工厂
        plant_ent = None
        if plant:
            for p in self.kg.list_entities("Plant"):
                if p.attrs.get("plant_id", "").upper() == plant.upper():
                    plant_ent = p.eid
                    break
            if not plant_ent:
                raise ValueError(f"未找到工厂 {plant}")

        result = answer_source_recommendation(
            self.kg, self.engine,
            material=material,
            plant=plant_ent
        )
        return result


# ============================================================================
# Agent 工厂函数
# ============================================================================

def create_procurement_agent(kg: Any, engine: Any) -> Agent:
    """创建采购管理 AgentScope Agent"""

    toolkit = Toolkit(tools=[
        CreatePRTool(kg, engine),
        QueryPRTool(kg, engine),
        ApprovePRTool(kg, engine),
        PRToPOTool(kg, engine),
        QueryPOTool(kg, engine),
        ApprovePOTool(kg, engine),
        DeliveryStatusTool(kg, engine),
        SourceRecommendationTool(kg, engine),
    ])

    # DeepSeek 模型配置
    model = DeepSeekChatModel(
        credential=DeepSeekCredential(api_key=DEEPSEEK_API_KEY),
        model="deepseek-v4-pro",
        stream=True,
    )

    return Agent(
        name="procurement_agent",
        system_prompt=SYSTEM_PROMPT,
        model=model,
        toolkit=toolkit,
    )


# ============================================================================
# 流式问答接口
# ============================================================================

async def ask_with_agent_stream(
    question: str,
    kg: Any,
    engine: Any
) -> AsyncGenerator[dict, None]:
    """
    流式问答接口，yield AgentEvent 字典

    Args:
        question: 用户问题
        kg: 知识图谱实例
        engine: 规则引擎实例

    Yields:
        dict: AgentEvent 事件字典，包含 type 和 data 字段
    """
    agent = create_procurement_agent(kg, engine)
    msg = UserMsg(name="user", content=question)
    _log(f"Agent 开始处理: {question[:50]}")
    tool_results: dict[str, str] = {}

    async for event in agent.reply_stream(msg):
        _log(f"Agent 收到事件: {event.__class__.__name__}", "DEBUG")
        serialized = _serialize_event(event)
        # 提取 type 字段作为事件类型，剩余内容作为 data
        event_type = serialized.pop("type", serialized.get("class", "UnknownEvent"))
        # 合并 class 字段到 data
        data = {k: v for k, v in serialized.items()}
        yield {
            "type": event_type,
            "data": data,
        }
        call_id = getattr(event, "tool_call_id", None)
        if event.__class__.__name__ == "ToolResultTextDeltaEvent":
            tool_results[call_id] = tool_results.get(call_id, "") + event.delta
        elif event.__class__.__name__ == "ToolResultEndEvent":
            try:
                trace = json.loads(tool_results.pop(call_id, ""))["kg_trace"]
                trace.update({"question": question, "tool_call_id": call_id})
                yield {"type": "KGTraceEvent", "data": trace}
            except (json.JSONDecodeError, KeyError, TypeError):
                pass
    _log("Agent 处理完成")


def _serialize_event(event: Any) -> dict:
    """将 AgentScope AgentEvent 序列化为前端友好的字典"""
    result = {"class": event.__class__.__name__}

    # AgentScope 2.0 事件类型映射到前端期望的名称
    event_name_map = {
        "ThinkingBlockDeltaEvent": "ReasoningDeltaEvent",
        "ThinkingBlockStartEvent": "ReasoningStartEvent",
        "ThinkingBlockEndEvent": "ReasoningEndEvent",
        "TextBlockDeltaEvent": "TextDeltaEvent",
        "TextBlockStartEvent": "TextStartEvent",
        "TextBlockEndEvent": "TextEndEvent",
        "ToolCallStartEvent": "ToolCallStartEvent",
        "ToolCallDeltaEvent": "ToolCallDeltaEvent",
        "ToolCallEndEvent": "ToolCallEndEvent",
        "ToolResultStartEvent": "ToolResultStartEvent",
        "ToolResultTextDeltaEvent": "ToolResultDeltaEvent",
        "ToolResultEndEvent": "ToolResultEndEvent",
        "ReplyStartEvent": "ReplyStartEvent",
        "ReplyEndEvent": "ReplyEndEvent",
    }

    # 映射事件类型
    original_name = event.__class__.__name__
    result["type"] = event_name_map.get(original_name, original_name)

    # 提取 delta (流式文本/推理)
    if hasattr(event, "delta"):
        result["delta"] = event.delta

    # 提取 content (文本块)
    if hasattr(event, "content"):
        result["content"] = event.content

    # 提取 thinking (推理块)
    if hasattr(event, "thinking"):
        result["thinking"] = event.thinking

    # 提取 tool_calls
    if hasattr(event, "tool_calls"):
        result["tool_calls"] = [
            {
                "id": tc.id,
                "name": tc.name,
                "input": tc.input,
            }
            for tc in event.tool_calls
        ]

    # 提取 tool_call (单个工具调用)
    if hasattr(event, "tool_call"):
        result["tool_call"] = {
            "id": event.tool_call.id,
            "name": event.tool_call.name,
            "input": event.tool_call.input,
        }

    # 提取 text (工具结果文本)
    if hasattr(event, "text"):
        result["text"] = event.text

    # 提取 reply_id
    if hasattr(event, "reply_id"):
        result["reply_id"] = event.reply_id

    if hasattr(event, "tool_call_id"):
        result["tool_call_id"] = event.tool_call_id

    if hasattr(event, "tool_call_name"):
        result["tool_call_name"] = event.tool_call_name

    _log(f"序列化事件: {original_name} -> {result.get('type', original_name)}", "DEBUG")
    return result


# ============================================================================
# 同步问答接口 (非流式)
# ============================================================================

def ask_with_agent_sync(question: str, kg: Any, engine: Any) -> dict:
    """
    同步问答接口 (非流式)

    Args:
        question: 用户问题
        kg: 知识图谱实例
        engine: 规则引擎实例

    Returns:
        dict: 最终回复内容
    """
    async def run():
        agent = create_procurement_agent(kg, engine)
        msg = UserMsg(name="user", content=question)
        return await agent.reply(msg)

    return asyncio.run(run())


# ============================================================================
# CLI 演示入口
# ============================================================================

def main() -> None:
    """CLI 演示"""
    from scenarios.procurement.knowledge_base import build_procurement_knowledge_base
    from scenarios.procurement.rules import build_procurement_rules

    print("\n" + "=" * 64)
    print("  Procurement AgentScope Agent · CLI 演示")
    print("=" * 64)

    # 检查 API Key
    if not DEEPSEEK_API_KEY:
        print("警告: DEEPSEEK_API_KEY 未设置，请在 .env 文件中配置")
        print("示例: DEEPSEEK_API_KEY=sk-xxxx...")
        return

    # 初始化 KG 和引擎
    kg = build_procurement_knowledge_base()
    print(f"  知识图谱: {kg}")

    from scenarios.procurement.rules import RuleEngine
    engine = RuleEngine(kg)
    for r in build_procurement_rules():
        engine.register(r)
    engine.forward_chain()
    print(f"  规则数: {len(engine.rules)}")

    # 演示问题
    questions = [
        "帮我创建一个采购申请: M1001 1000个",
        "有哪些采购申请还在审批中？",
        "帮我审批一下 PR-2026-00001",
        "PO-2026-00789 现在什么状态？",
        "哪些采购订单已逾期？",
        "M1001 的最优供应商是谁？",
    ]

    for q in questions:
        print(f"\n{'='*64}")
        print(f"Q: {q}")
        print("=" * 64)

        try:
            result = ask_with_agent_sync(q, kg, engine)
            print(result.get_text_content())
        except Exception as e:
            print(f"错误: {e}")


if __name__ == "__main__":
    main()
