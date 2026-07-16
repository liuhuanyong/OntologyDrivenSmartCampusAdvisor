"""
Campus AgentScope Agent
=======================
使用 AgentScope 2.0 ReAct Agent + DeepSeek 模型处理 Smart Campus 课程职业规划问题。
支持流式响应，实时推送推理过程给前端。
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
- 校园规则问题必须先调用 campus_reason，由模型填写 intent/student/course/career 参数。
- 实体列表、属性和一跳关系问题调用 campus_graph_query。
- 最终回答必须以工具返回的 KG 事实和推理证据为准；证据不足时明确说明，不得虚构。
- 不要向用户原样输出工具 JSON，只解释结论与关键依据。
"""

class CampusToolBase(ToolBase):
    is_concurrency_safe = True
    is_read_only = True

    def __init__(self, kg: Any, engine: Any):
        self.kg = kg
        self.engine = engine

    async def check_permissions(self, tool_input: dict, context: PermissionContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ALLOW, message="")

    async def __call__(self, **kwargs) -> ToolChunk:
        try:
            return await self._execute(**kwargs)
        except Exception as e:
            _log(f"工具异常: {e}", "ERROR")
            return self._trace_chunk({
                "intent": self.name,
                "answer": f"查询出错: {e}",
                "rule_flow": [], "reasoning": [], "answer_nodes": [],
                "subgraph": {"nodes": [], "edges": []},
            }, kwargs, "error")

    async def _execute(self, **kwargs) -> ToolChunk:
        raise NotImplementedError

    def _trace_chunk(self, result: dict, tool_input: dict, status: str = "success") -> ToolChunk:
        trace = {
            "schema_version": 1,
            "scenario": "campus",
            "tool_name": self.name,
            "tool_input": tool_input,
            "intent": result.get("intent", self.name),
            "status": status,
            "kg_answer": result.get("answer", ""),
            "rule_flow": result.get("rule_flow", []),
            "reasoning": result.get("reasoning", []),
            "answer_nodes": result.get("answer_nodes", []),
            "subgraph": _compact_subgraph(self.kg, result),
        }
        return ToolChunk(content=[TextBlock(text=json.dumps({
            "kg_answer": trace["kg_answer"],
            "kg_trace": trace,
        }, ensure_ascii=False, default=list))])


def _compact_subgraph(kg: Any, result: dict) -> dict:
    ids = set(result.get("answer_nodes", []))
    for block in result.get("reasoning", []):
        for hop in block.get("hops", []):
            ids.update((hop.get("from"), hop.get("to")))
        ids.update(f.get("id") for f in block.get("focus", []))
    ids.discard(None)
    return kg.subgraph_data(ids) if ids else result.get("subgraph", {"nodes": [], "edges": []})


class CampusReasonTool(CampusToolBase):
    name = "campus_reason"
    description = "按校园 KG 规则推理。先选择 intent，再填写学生及可选课程/职业参数。"
    input_schema = {
        "type": "object",
        "properties": {
            "intent": {"type": "string", "enum": ["recommend_courses", "career_advice", "skill_gap", "check_course", "student_profile"]},
            "student": {"type": "string", "description": "学生姓名，如 Alice"},
            "course": {"type": "string", "description": "课程代码或名称，check_course 时使用"},
            "career": {"type": "string", "description": "职业名称，skill_gap 时使用"},
        },
        "required": ["intent", "student"],
    }

    async def _execute(self, intent: str, student: str, course: str = None, career: str = None) -> ToolChunk:
        from advisor import ask as campus_ask

        student_entity = next((s for s in self.kg.list_entities("Student")
                               if student.lower() in {s.eid.lower(), s.attrs.get("name", "").lower()}), None)
        if not student_entity:
            raise ValueError(f"未找到学生 {student}")
        student = student_entity.attrs["name"]
        if intent == "check_course" and not course:
            raise ValueError("check_course 需要 course")
        if course and not any(course.lower() in {
            c.eid.lower(), str(c.attrs.get("code", "")).lower(), str(c.attrs.get("title", "")).lower()
        } for c in self.kg.list_entities("Course")):
            raise ValueError(f"未找到课程 {course}")
        if career and not any(career.lower() in {
            c.eid.lower(), str(c.attrs.get("name", "")).lower()
        } for c in self.kg.list_entities("Career")):
            raise ValueError(f"未找到职业 {career}")
        questions = {
            "recommend_courses": f"{student} 下学期该修什么课？",
            "career_advice": f"{student} 适合什么职业方向？",
            "skill_gap": f"{student} 想成为 {career or ''}，还差什么？",
            "check_course": f"{student} 能选 {course or ''} 吗？",
            "student_profile": f"给我看看 {student} 的完整画像",
        }
        result = campus_ask(self.kg, self.engine, questions[intent])
        return self._trace_chunk(result, {
            "intent": intent, "student": student, "course": course, "career": career,
        })


class CampusGraphQueryTool(CampusToolBase):
    name = "campus_graph_query"
    description = "通用只读 KG 查询：列出某类实体，或查询一个实体的一跳关系。"
    input_schema = {
        "type": "object",
        "properties": {
            "query_type": {"type": "string", "enum": ["list_entities", "entity_neighbors"]},
            "entity_type": {"type": "string", "description": "实体类型，如 Professor、Course"},
            "entity_id": {"type": "string", "description": "实体 ID、名称或代码"},
            "predicate": {"type": "string", "description": "可选关系类型"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50},
        },
        "required": ["query_type"],
    }

    async def _execute(self, query_type: str, entity_type: str = None,
                       entity_id: str = None, predicate: str = None,
                       limit: int = 50) -> ToolChunk:
        limit = max(1, min(limit, 100))
        if query_type == "list_entities":
            if not entity_type:
                raise ValueError("list_entities 需要 entity_type")
            entities = self.kg.list_entities(entity_type)[:limit]
            hops = [{
                "from": f"ontology:{entity_type}", "from_label": entity_type,
                "predicate": "has_instance", "to": e.eid, "to_label": e.label,
                "reason": f"{e.eid} 是 {entity_type} 实例",
            } for e in entities]
            answer = f"找到 {len(entities)} 个 {entity_type}: " + "、".join(e.label for e in entities)
            ids = {e.eid for e in entities}
            intent = "list_entities"
            conclusion = f"共 {len(entities)} 个 {entity_type}"
        else:
            entity = self.kg.get_entity(entity_id or "")
            if not entity:
                needle = (entity_id or "").lower()
                entity = next((e for e in self.kg.list_entities()
                               if needle in {e.eid.lower(), e.label.lower(),
                                             str(e.attrs.get('name', '')).lower(),
                                             str(e.attrs.get('code', '')).lower()}), None)
            if not entity:
                raise ValueError(f"未找到实体 {entity_id}")
            relations = (self.kg.out(entity.eid, predicate) + self.kg.inn(entity.eid, predicate))[:limit]
            hops = [{
                "from": r.subject, "from_label": self.kg.get_entity(r.subject).label,
                "predicate": r.predicate, "to": r.obj,
                "to_label": self.kg.get_entity(r.obj).label,
                "reason": "KG 一跳关系",
            } for r in relations]
            ids = {entity.eid} | {r.subject for r in relations} | {r.obj for r in relations}
            answer = f"{entity.label} 有 {len(relations)} 条匹配关系"
            intent = "entity_neighbors"
            conclusion = answer
        result = {
            "intent": intent,
            "answer": answer,
            "rule_flow": [{"rule": f"KG_{intent.upper()}", "depends_on": [], "chinese": "执行确定性图查询", "why": "从知识图谱读取事实"}],
            "reasoning": [{"rule": f"KG_{intent.upper()}", "rule_desc": "通用只读图查询", "goal": answer, "hops": hops, "focus": [], "conclusion": conclusion}],
            "answer_nodes": list(ids),
            "subgraph": self.kg.subgraph_data(ids),
        }
        return self._trace_chunk(result, {
            "query_type": query_type, "entity_type": entity_type,
            "entity_id": entity_id, "predicate": predicate, "limit": limit,
        })


def create_campus_agent(kg: Any, engine: Any) -> Agent:
    model = DeepSeekChatModel(
        credential=DeepSeekCredential(api_key=DEEPSEEK_API_KEY),
        model="deepseek-v4-pro",
        stream=True,
    )
    toolkit = Toolkit(tools=[CampusReasonTool(kg, engine), CampusGraphQueryTool(kg, engine)])
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
    tool_results: dict[str, str] = {}
    async for event in agent.reply_stream(msg):
        yield _serialize_event(event)
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
    if hasattr(event, "tool_call_id"):
        result["data"]["tool_call_id"] = event.tool_call_id
    if hasattr(event, "tool_call_name"):
        result["data"]["tool_call_name"] = event.tool_call_name
    return result


def ask_with_agent_sync(question: str, kg: Any, engine: Any) -> Any:
    async def run():
        agent = create_campus_agent(kg, engine)
        msg = UserMsg(name="user", content=question)
        return await agent.reply(msg)
    return asyncio.run(run())
