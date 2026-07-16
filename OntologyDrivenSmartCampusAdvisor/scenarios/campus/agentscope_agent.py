"""
Campus AgentScope Agent
=======================
使用 AgentScope 2.0 ReAct Agent + DeepSeek 模型处理 Smart Campus 课程职业规划问题。
支持流式响应，实时推送推理过程给前端。
"""
import os
import asyncio
import time
from pathlib import Path
from typing import Any, AsyncGenerator

from agentscope.agent import Agent
from agentscope.model import DeepSeekChatModel
from agentscope.credential import DeepSeekCredential
from agentscope.tool import ToolBase, ToolChunk, Toolkit
from agentscope.message import Msg, TextBlock, UserMsg
from agentscope.permission import PermissionContext, PermissionDecision, PermissionBehavior

LOG_FILE = Path(__file__).parent.parent.parent.parent / "logs" / "agent.log"
LOG_FILE.parent.mkdir(exist_ok=True)

def _log(msg: str, level: str = "INFO"):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} [{level}] [campus] {msg}"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

# System Prompt for Campus Agent
SYSTEM_PROMPT = """你是 Smart Campus 课程职业规划顾问。基于校园本体知识图谱为学生提供选课建议和职业规划指导。

【本体模型 - 核心业务对象】
- Student: 学生 (id, name, grade, gpa)
- Course: 课程 (code, title, credits, difficulty, semester)
- Professor: 教授 (id, name, title, research_area)
- Department: 院系 (code, name)
- Major: 专业 (code, name, degree)
- Skill: 技能 (name, category)
- Career: 职业 (name, field, avg_salary, growth_rate)

【关系】
- offered_by: 课程→院系
- taught_by: 课程→教授
- teaches_skill: 课程→技能
- prerequisite_of: 课程→先修课程
- requires_course: 专业→要求课程
- leads_to: 专业→职业
- requires_skill: 职业→技能
- enrolled_in: 学生→专业
- takes: 学生→课程(含grade, status)
- has_skill: 学生→技能(含level)
- targets_career: 学生→职业目标
- eligible_for: 学生→适配职业(派生)

【工具】
使用 campus_query 工具查询学生档案、选课建议、资格检查等。
"""

class CampusToolBase(ToolBase):
    is_concurrency_safe = True
    is_read_only = True

    def __init__(self, kg: Any, engine: Any):
        self.kg = kg
        self.engine = engine

    async def check_permissions(self, tool_input: dict, context: PermissionContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ALLOW, message="")

    async def call(self, **kwargs) -> ToolChunk:
        try:
            result = await self._execute(**kwargs)
            return result
        except Exception as e:
            _log(f"工具异常: {e}", "ERROR")
            return ToolChunk(content=[TextBlock(text=f"查询出错: {e}")])

    async def _execute(self, **kwargs) -> ToolChunk:
        raise NotImplementedError


class CampusQueryTool(CampusToolBase):
    name = "campus_query"
    description = "查询学生档案和选课建议。参数: question(学生姓名+问题)"
    input_schema = {
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "学生姓名和问题，如 Alice 下学期该修什么课"},
        },
        "required": ["question"],
    }

    async def _execute(self, question: str) -> ToolChunk:
        from advisor import ask as campus_ask
        result = campus_ask(self.kg, self.engine, question)
        answer = result.get("answer", "处理完成")
        return ToolChunk(content=[TextBlock(text=answer)])


def create_campus_agent(kg: Any, engine: Any) -> Agent:
    model = DeepSeekChatModel(
        credential=DeepSeekCredential(api_key=DEEPSEEK_API_KEY),
        model="deepseek-v4-pro",
        stream=True,
    )
    toolkit = Toolkit(tools=[CampusQueryTool(kg, engine)])
    return Agent(
        name="campus_agent",
        system_prompt=SYSTEM_PROMPT,
        model=model,
        toolkit=toolkit,
    )


async def ask_with_agent_stream(question: str, kg: Any, engine: Any) -> AsyncGenerator[dict, None]:
    agent = create_campus_agent(kg, engine)
    msg = UserMsg(name="user", content=question)
    _log(f"Agent 开始处理: {question[:50]}")
    async for event in agent.reply_stream(msg):
        yield _serialize_event(event)


def _serialize_event(event: Any) -> dict:
    result = {"data": {}}
    event_name_map = {
        "ModelCallStartEvent": "ModelCallStartEvent",
        "ModelCallEndEvent": "ModelCallEndEvent",
        "TextBlockStartEvent": "TextStartEvent",
        "TextBlockEndEvent": "TextEndEvent",
        "TextBlockDeltaEvent": "TextDeltaEvent",
        "ThinkingBlockDeltaEvent": "ThinkingDeltaEvent",
        "ToolCallStartEvent": "ToolCallStartEvent",
        "ToolCallDeltaEvent": "ToolCallDeltaEvent",
        "ToolCallEndEvent": "ToolCallEndEvent",
        "ToolResultStartEvent": "ToolResultStartEvent",
        "ToolResultTextDeltaEvent": "ToolResultDeltaEvent",
        "ToolResultEndEvent": "ToolResultEndEvent",
        "ReplyStartEvent": "ReplyStartEvent",
        "ReplyEndEvent": "ReplyEndEvent",
    }
    original_name = event.__class__.__name__
    result["type"] = event_name_map.get(original_name, original_name)
    if hasattr(event, "delta"):
        result["data"]["delta"] = event.delta
    if hasattr(event, "content"):
        result["data"]["content"] = event.content
    if hasattr(event, "tool_calls"):
        result["data"]["tool_calls"] = [{"id": tc.id, "name": tc.name, "input": tc.input} for tc in event.tool_calls]
    if hasattr(event, "text"):
        result["data"]["text"] = event.text
    if hasattr(event, "reply_id"):
        result["reply_id"] = event.reply_id
    return result


def ask_with_agent_sync(question: str, kg: Any, engine: Any) -> Any:
    async def run():
        agent = create_campus_agent(kg, engine)
        msg = UserMsg(name="user", content=question)
        return await agent.reply(msg)
    return asyncio.run(run())
