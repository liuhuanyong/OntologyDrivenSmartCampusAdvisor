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
from __future__ import annotations

import os
import re
import asyncio
from typing import Any, AsyncGenerator

# AgentScope 核心
from agentscope.agent import Agent
from agentscope.model import DeepSeekChatModel
from agentscope.credential import DeepSeekCredential
from agentscope.tool import Toolkit, ToolBase, ToolChunk
from agentscope.message import Msg, TextBlock, UserMsg
from agentscope.permission import PermissionContext, PermissionDecision, PermissionBehavior

# 从 .env 读取 API Key
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

# System Prompt for Procurement Agent
SYSTEM_PROMPT = """你是 SAP 采购管理智能体，负责处理采购申请(PR)、采购订单(PO)、供应商管理、交货跟踪等 Source-to-Award 端到端业务。

你有以下工具可以使用:
- create_pr: 创建采购申请 (需要物料代码和数量)
- query_pr: 查询 PR 状态 (需要 PR 编号如 PR-2026-00001)
- approve_pr: 审批 PR (需要 PR 编号)
- pr_to_po: 将 PR 转成 PO (需要 PR 编号)
- query_po: 查询 PO 状态 (需要 PO 编号如 PO-2026-00789)
- approve_po: 审批 PO (需要 PO 编号)
- delivery_status: 查询交货状态/逾期 (可选 PO 编号)
- source_recommendation: 货源推荐 (需要物料代码)

请根据用户的问题，选择合适的工具来回答。

注意:
- 物料代码格式如 M1001, M1002
- PR 编号格式如 PR-2026-00001
- PO 编号格式如 PO-2026-00789
- 如果用户没有提供具体编号，先查询列表再选择
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
        return PermissionDecision(behavior=PermissionBehavior.ALLOW)


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
            "quantity": {"type": "integer", "description": "采购数量"},
            "plant": {"type": "string", "description": "工厂代码(可选)"},
        },
        "required": ["material_code", "quantity"],
    }
    is_read_only = False

    async def call(self, material_code: str, quantity: int, plant: str = None) -> ToolChunk:
        from scenarios.procurement.advisor import answer_create_pr

        # 解析物料
        material = None
        for m in self.kg.list_entities("Material"):
            if m.attrs.get("material_id", "").upper() == material_code.upper():
                material = m.eid
                break

        if not material:
            return ToolChunk(content=[TextBlock(text=f"未找到物料 {material_code}，请检查物料代码是否正确")])

        result = answer_create_pr(
            self.kg, self.engine,
            material=material,
            quantity=quantity,
            plant=plant
        )

        answer = result.get("answer", "处理完成")
        return ToolChunk(content=[TextBlock(text=answer)])


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

    async def call(self, pr_id: str = None) -> ToolChunk:
        from scenarios.procurement.advisor import answer_query_pr

        # 解析 PR
        pr = None
        if pr_id:
            for p in self.kg.list_entities("PurchaseRequisition"):
                if p.attrs.get("pr_id", "").upper() == pr_id.upper():
                    pr = p.eid
                    break

        result = answer_query_pr(self.kg, self.engine, pr=pr)
        answer = result.get("answer", "处理完成")
        return ToolChunk(content=[TextBlock(text=answer)])


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

    async def call(self, pr_id: str = None) -> ToolChunk:
        from scenarios.procurement.advisor import answer_approve_pr

        # 解析 PR
        pr = None
        if pr_id:
            for p in self.kg.list_entities("PurchaseRequisition"):
                if p.attrs.get("pr_id", "").upper() == pr_id.upper():
                    pr = p.eid
                    break

        result = answer_approve_pr(self.kg, self.engine, pr=pr)
        answer = result.get("answer", "处理完成")
        return ToolChunk(content=[TextBlock(text=answer)])


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

    async def call(self, pr_id: str = None) -> ToolChunk:
        from scenarios.procurement.advisor import answer_pr_to_po

        # 解析 PR
        pr = None
        if pr_id:
            for p in self.kg.list_entities("PurchaseRequisition"):
                if p.attrs.get("pr_id", "").upper() == pr_id.upper():
                    pr = p.eid
                    break

        result = answer_pr_to_po(self.kg, self.engine, pr=pr)
        answer = result.get("answer", "处理完成")
        return ToolChunk(content=[TextBlock(text=answer)])


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

    async def call(self, po_id: str = None) -> ToolChunk:
        from scenarios.procurement.advisor import answer_query_po

        # 解析 PO
        po = None
        if po_id:
            for p in self.kg.list_entities("PurchaseOrder"):
                if p.attrs.get("po_id", "").upper() == po_id.upper():
                    po = p.eid
                    break

        result = answer_query_po(self.kg, self.engine, po=po)
        answer = result.get("answer", "处理完成")
        return ToolChunk(content=[TextBlock(text=answer)])


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

    async def call(self, po_id: str = None) -> ToolChunk:
        from scenarios.procurement.advisor import answer_approve_po

        # 解析 PO
        po = None
        if po_id:
            for p in self.kg.list_entities("PurchaseOrder"):
                if p.attrs.get("po_id", "").upper() == po_id.upper():
                    po = p.eid
                    break

        result = answer_approve_po(self.kg, self.engine, po=po)
        answer = result.get("answer", "处理完成")
        return ToolChunk(content=[TextBlock(text=answer)])


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

    async def call(self, po_id: str = None) -> ToolChunk:
        from scenarios.procurement.advisor import answer_delivery_status

        # 解析 PO
        po = None
        if po_id:
            for p in self.kg.list_entities("PurchaseOrder"):
                if p.attrs.get("po_id", "").upper() == po_id.upper():
                    po = p.eid
                    break

        result = answer_delivery_status(self.kg, self.engine, po=po)
        answer = result.get("answer", "处理完成")
        return ToolChunk(content=[TextBlock(text=answer)])


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

    async def call(self, material_code: str, plant: str = None) -> ToolChunk:
        from scenarios.procurement.advisor import answer_source_recommendation

        # 解析物料
        material = None
        for m in self.kg.list_entities("Material"):
            if m.attrs.get("material_id", "").upper() == material_code.upper():
                material = m.eid
                break

        if not material:
            return ToolChunk(content=[TextBlock(text=f"未找到物料 {material_code}，请检查物料代码是否正确")])

        # 解析工厂
        plant_ent = None
        if plant:
            for p in self.kg.list_entities("Plant"):
                if p.attrs.get("plant_id", "").upper() == plant.upper():
                    plant_ent = p.eid
                    break

        result = answer_source_recommendation(
            self.kg, self.engine,
            material=material,
            plant=plant_ent
        )
        answer = result.get("answer", "处理完成")
        return ToolChunk(content=[TextBlock(text=answer)])


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

    async for event in agent.reply_stream(msg):
        yield {
            "type": event.__class__.__name__,
            "data": _serialize_event(event),
        }


def _serialize_event(event: Any) -> dict:
    """将 AgentEvent 序列化为字典"""
    result = {"class": event.__class__.__name__}

    # 根据事件类型提取相关字段
    if hasattr(event, "delta"):
        result["delta"] = event.delta
    if hasattr(event, "content"):
        result["content"] = event.content
    if hasattr(event, "tool_calls"):
        result["tool_calls"] = [
            {
                "id": tc.id,
                "name": tc.name,
                "input": tc.input,
            }
            for tc in event.tool_calls
        ]
    if hasattr(event, "reply_id"):
        result["reply_id"] = event.reply_id

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
