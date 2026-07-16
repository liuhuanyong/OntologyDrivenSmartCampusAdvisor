"""
第 3 层(续): Web 服务器 (零依赖, 基于 http.server)
====================================================
多场景版: 在同一 Web 应用中并存三个场景
  - /                  Smart Campus 课程职业规划顾问
  - /warehouse         Warehouse SAP 操作自动化智能体
  - /procurement       Procurement SAP 采购管理智能体 (Source-to-Award)

每个场景的 API 路径均带场景前缀:
  /api/campus/*        campus 场景
  /api/warehouse/*     warehouse 场景
  /api/procurement/*   procurement 场景

支持 AgentScope SSE 流式路由:
  /api/procurement/ask/stream  流式问答 (AgentScope ReAct Agent)

启动后访问 http://localhost:8772
"""
from __future__ import annotations

import os
import sys
import json
import time
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

# 日志目录
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
_log_file = LOG_DIR / "server.log"

def _log(msg: str, level: str = "INFO"):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} [{level}] {msg}\n"
    with open(_log_file, "a", encoding="utf-8") as f:
        f.write(line)
    print(line, end="")  # 同时输出到终端

import asyncio
from urllib.parse import urlparse, parse_qs

from dotenv import load_dotenv

# 加载 .env 环境变量
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from scenarios import load_scenario


# ---- 加载两个场景 ---- #
CAMPUS = load_scenario("campus")
PROCUREMENT = load_scenario("procurement")
CAMPUS.engine.dump_rules_json("rules_store.json")

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


# ---- 20 个复杂推理示例 ---- #
CAMPUS_EXAMPLES = [
    "Alice 下学期该修什么课？",
    "Dave 下学期该修什么课？",
    "Frank 选课建议",
    "Henry 该修哪些课？",
    "Eve 适合什么职业方向？",
    "Alice 适合什么职业方向？",
    "Bob 适合什么职业方向？",
    "Grace 就业方向如何？",
    "Carol 想成为数据科学家，还差什么？",
    "Bob 想成为机器学习工程师，怎么补？",
    "Dave 想做 NLP工程师，还差什么？",
    "Frank 想成为数据库工程师，目标怎么实现？",
    "Henry 想做数据分析师，还差什么？",
    "Bob 能选 ML401 吗？",
    "Alice 能不能选 CS401 操作系统？",
    "Carol 可以直接选 ML402 深度学习吗？",
    "Eve 能修 NLP401 自然语言处理吗？",
    "给我看看 Grace 的完整画像",
    "Alice 的完整档案",
    "Eve 的情况如何？",
]

PROCUREMENT_EXAMPLES = [
    "帮我创建一个采购申请: 电子元件-主控芯片 STM32 2000 个",
    "请购 1000 个 PCB 主板",
    "有哪些采购申请还在审批中？",
    "PR-2026-00001 现在到哪一步了？",
    "帮我审批一下 PR-2026-00001",
    "把 PR-2026-00003 转成采购订单",
    "PO-2026-00789 现在什么状态？",
    "审批 PO-2026-00792",
    "哪些采购订单已逾期？",
    "PO-2026-00790 的交货进度？",
    "M1001 的最优供应商是谁？",
    "物料 M1005 谁能供？",
]


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False, default=list).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path, content_type):
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _scenario_for(self, name: str):
        return {"campus": CAMPUS, "procurement": PROCUREMENT}.get(name)

    def _send_404(self, msg: str = "Not Found"):
        self.send_error(404, msg)

    # ------------------------------------------------------------------ #
    # 场景分发工具
    # ------------------------------------------------------------------ #
    def _dispatch_graph(self, scenario_name: str):
        ctx = self._scenario_for(scenario_name)
        if not ctx:
            self._send_404()
            return
        self._send_json(ctx.kg.full_graph_data())

    def _dispatch_stats(self, scenario_name: str):
        ctx = self._scenario_for(scenario_name)
        if not ctx:
            self._send_404()
            return
        self._send_json({
            "scenario": scenario_name,
            "title": ctx.title,
            "kg": ctx.kg.stats(),
            "entity_types": list(ctx.entity_schemas.keys()),
            "relation_types": list(ctx.relation_schemas.keys()),
            "colors": ctx.entity_colors,
            "rules": len(ctx.engine.rules),
        })

    def _dispatch_entities(self, scenario_name: str):
        ctx = self._scenario_for(scenario_name)
        if not ctx:
            self._send_404()
            return
        schemas = {t: {"attrs": {k: v.__name__ for k, v in attrs.items()},
                        "color": ctx.entity_colors.get(t, "#6b7280")}
                   for t, attrs in ctx.entity_schemas.items()}
        instances = {}
        for etype in ctx.entity_schemas:
            ents = ctx.kg.list_entities(etype)
            instances[etype] = [{
                "id": e.eid, "label": e.label, "attrs": e.attrs,
            } for e in ents]
        self._send_json({
            "schemas": schemas,
            "instances": instances,
            "total": sum(len(v) for v in instances.values()),
        })

    def _dispatch_relations(self, scenario_name: str):
        ctx = self._scenario_for(scenario_name)
        if not ctx:
            self._send_404()
            return
        schemas = {p: {"domain": s["domain"], "range": s["range"],
                        "edge": {k: v.__name__ for k, v in s.get("edge", {}).items()}}
                   for p, s in ctx.relation_schemas.items()}
        instances = {}
        for subj, preds in ctx.kg._out.items():
            for pred, rels in preds.items():
                if pred not in instances:
                    instances[pred] = []
                for r in rels:
                    s_ent = ctx.kg.get_entity(r.subject)
                    o_ent = ctx.kg.get_entity(r.obj)
                    instances[pred].append({
                        "from": r.subject, "from_label": s_ent.label if s_ent else r.subject,
                        "to": r.obj, "to_label": o_ent.label if o_ent else r.obj,
                        "edge": r.edge,
                        "inferred": (r.subject, r.predicate, r.obj) in ctx.kg._inferred,
                    })
        total = sum(len(v) for v in instances.values())
        self._send_json({"schemas": schemas, "instances": instances, "total": total})

    def _dispatch_rules(self, scenario_name: str):
        ctx = self._scenario_for(scenario_name)
        if not ctx:
            self._send_404()
            return
        data = []
        for r in sorted(ctx.engine.rules.values(), key=lambda r: r.priority):
            d = r.to_dict()
            # 兼容两种 rule_meaning 来源
            meaning = (getattr(r, "description", "") or "")
            data.append(d)
        self._send_json(data)

    def _dispatch_examples(self, scenario_name: str):
        ctx = self._scenario_for(scenario_name)
        if not ctx:
            self._send_404()
            return
        if scenario_name == "campus":
            examples = CAMPUS_EXAMPLES
        elif scenario_name == "procurement":
            examples = PROCUREMENT_EXAMPLES
        else:
            examples = ctx.example_questions
        self._send_json({"examples": examples, "scenario": scenario_name})

    def _dispatch_ask(self, scenario_name: str, question: str):
        ctx = self._scenario_for(scenario_name)
        if not ctx:
            self._send_404()
            return
        result = ctx.ask(ctx.kg, ctx.engine, question)
        # 注入 scenario 标签 (方便前端展示)
        result["scenario"] = scenario_name
        result["scenario_title"] = ctx.title
        self._send_json(result)

    # ------------------------------------------------------------------ #
    # AgentScope SSE 流式路由
    # ------------------------------------------------------------------ #
    def _dispatch_ask_stream(self, scenario_name: str, question: str):
        """SSE 流式响应。"""
        _log(f"收到请求: scenario={scenario_name}, question={question[:50]}")
        ctx = self._scenario_for(scenario_name)
        if not ctx:
            self._send_404()
            return

        if not os.environ.get("DEEPSEEK_API_KEY"):
            _log("DEEPSEEK_API_KEY 未配置", "ERROR")
            self._send_json({"error": "DEEPSEEK_API_KEY 未配置，请在 .env 中设置"}, 500)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")  # 关闭 keep-alive
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        try:
            module = __import__(
                f"scenarios.{scenario_name}.agentscope_agent",
                fromlist=["ask_with_agent_stream"],
            )

            async def stream():
                async for event in module.ask_with_agent_stream(question, ctx.kg, ctx.engine):
                    data = json.dumps(event, ensure_ascii=False)
                    self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                    self.wfile.flush()

            asyncio.run(stream())
        except Exception as e:
            _log(f"Agent 执行失败: {e}", "ERROR")
            import traceback; _log(traceback.format_exc(), "ERROR")
            try:
                data = json.dumps({"type": "error", "data": {"message": str(e)}}, ensure_ascii=False)
                self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                self.wfile.flush()
            except (OSError, BrokenPipeError, ConnectionResetError):
                pass
        finally:
            try:
                self.wfile.write(b'data: {"type": "done", "data": {}}\n\n')
                self.wfile.flush()
            except (OSError, BrokenPipeError, ConnectionResetError):
                pass

    def do_GET(self):
        path = self.path

        # 静态页面
        if path == "/" or path == "/index.html":
            self._send_file(os.path.join(STATIC_DIR, "index.html"), "text/html; charset=utf-8")
            return
        if path == "/procurement" or path == "/procurement.html":
            self._send_file(os.path.join(STATIC_DIR, "procurement.html"), "text/html; charset=utf-8")
            return

        # 仪表盘页面 (新)
        if path == "/dashboard" or path == "/dashboard.html":
            self._send_file(os.path.join(STATIC_DIR, "dashboard.html"), "text/html; charset=utf-8")
            return
        if path.startswith("/dashboard/"):
            self._send_file(os.path.join(STATIC_DIR, "dashboard.html"), "text/html; charset=utf-8")
            return

        # /api/<scenario>/ask/stream - SSE 流式路由 (GET 方法)
        if path.startswith("/api/") and "/ask/stream" in path:
            parts = path[5:].split("/")
            scenario_name = parts[0]
            parsed_url = urlparse(path)
            query_params = parse_qs(parsed_url.query)
            question_list = query_params.get("question", [])
            question = question_list[0] if question_list else ""
            if not question:
                self._send_json({"error": "question 参数不能为空"}, 400)
                return
            self._dispatch_ask_stream(scenario_name, question)
            return

        # /api/<scenario>/<resource> 派发
        if path.startswith("/api/"):
            parts = path[5:].split("/")
            if len(parts) < 2:
                self._send_404()
                return
            scenario_name, resource = parts[0], "/".join(parts[1:])
            if resource == "graph":
                self._dispatch_graph(scenario_name)
                return
            if resource == "stats":
                self._dispatch_stats(scenario_name)
                return
            if resource == "entities":
                self._dispatch_entities(scenario_name)
                return
            if resource == "relations":
                self._dispatch_relations(scenario_name)
                return
            if resource == "rules":
                self._dispatch_rules(scenario_name)
                return
            if resource == "examples":
                self._dispatch_examples(scenario_name)
                return

        # 静态资源 (CSS/JS)
        if path.startswith("/static/"):
            fname = path[8:]
            fpath = os.path.join(STATIC_DIR, fname)
            if os.path.exists(fpath):
                ct = "text/css; charset=utf-8" if fname.endswith(".css") else "application/javascript"
                self._send_file(fpath, ct)
            else:
                self.send_error(404)
            return

        self._send_404()

    def do_POST(self):
        path = self.path
        # 兼容旧路径 (不带 scenario 前缀的 /api/ask 默认走 campus)
        if path == "/api/ask":
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw)
                question = payload.get("question", "").strip()
            except (json.JSONDecodeError, AttributeError):
                self._send_json({"error": "无效的 JSON"}, 400)
                return
            if not question:
                self._send_json({"error": "问题不能为空"}, 400)
                return
            self._dispatch_ask("campus", question)
            return

        # /api/<scenario>/ask - JSON 路由
        if path.startswith("/api/") and path.endswith("/ask"):
            scenario_name = path[5:-4]
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw)
                question = payload.get("question", "").strip()
            except (json.JSONDecodeError, AttributeError):
                self._send_json({"error": "无效的 JSON"}, 400)
                return
            if not question:
                self._send_json({"error": "问题不能为空"}, 400)
                return
            self._dispatch_ask(scenario_name, question)
            return

        self._send_404()

    def log_message(self, *args):
        pass  # 静默 HTTP 日志


class ReusableHTTPServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    _log("=== 服务启动 ===")
    port = 8772
    server = ReusableHTTPServer(("0.0.0.0", port), Handler)
    print("  多场景 Web 服务已启动")
    print(f"  Campus      场景: {CAMPUS.kg}  规则 {len(CAMPUS.engine.rules)} 条")
    print(f"  访问: http://localhost:{port}/")
    print(f"  访问 (新仪表盘): http://localhost:{port}/dashboard/campus")
    print(f"  Procurement 场景: {PROCUREMENT.kg}  规则 {len(PROCUREMENT.engine.rules)} 条")
    print(f"  访问: http://localhost:{port}/procurement")
    print(f"  访问 (新仪表盘): http://localhost:{port}/dashboard/procurement")
    print(f"  Ctrl+C 退出")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  服务已停止")
        server.server_close()


if __name__ == "__main__":
    main()
