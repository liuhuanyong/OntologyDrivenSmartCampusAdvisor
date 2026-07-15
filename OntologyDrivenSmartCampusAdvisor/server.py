"""
第 3 层(续): Web 服务器 (零依赖, 基于 http.server)
====================================================
多场景版: 在同一 Web 应用中并存两个场景
  - /                  Smart Campus 课程职业规划顾问
  - /warehouse         Warehouse SAP 操作自动化智能体

每个场景的 API 路径均带场景前缀:
  /api/campus/*        campus 场景
  /api/warehouse/*     warehouse 场景

启动后访问 http://localhost:8772
"""
from __future__ import annotations

import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler

from scenarios import load_scenario


# ---- 加载两个场景 ---- #
CAMPUS = load_scenario("campus")
WAREHOUSE = load_scenario("warehouse")
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

WAREHOUSE_EXAMPLES = [
    "RM001 怎么安排入库？",
    "锂电池 18650 现在收料走什么流程？",
    "上海仓来了一批 PCB 主板如何上架？",
    "总装车间要领 800 个主控芯片怎么发料？",
    "客户服务中心需要 100 个电源适配器如何安排？",
    "深圳电子市场订 500 台 A 型机怎么拣货？",
    "上海仓的 PCB 主板怎么调到深圳仓？",
    "原材料 ABS 塑胶粒在哪个工厂间调拨？",
    "上海仓怎么安排盘点？",
    "全部工厂的盘点策略是什么？",
    "现在有哪些呆滞料？",
    "识别高风险积压物料",
    "哪些库存需要预警？",
    "FG003 工业控制器如何入库？",
    "化工原料-粘合剂需要冷链吗？",
    "成都仓怎么安排盘点？",
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
        return {"campus": CAMPUS, "warehouse": WAREHOUSE}.get(name)

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
        examples = CAMPUS_EXAMPLES if scenario_name == "campus" else WAREHOUSE_EXAMPLES
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
    # 路由分发
    # ------------------------------------------------------------------ #
    def do_GET(self):
        path = self.path

        # 静态页面
        if path == "/" or path == "/index.html":
            self._send_file(os.path.join(STATIC_DIR, "index.html"), "text/html; charset=utf-8")
            return
        if path == "/warehouse" or path == "/warehouse.html":
            self._send_file(os.path.join(STATIC_DIR, "warehouse.html"), "text/html; charset=utf-8")
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

        # /api/<scenario>/ask
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
        pass  # 静默日志


class ReusableHTTPServer(HTTPServer):
    allow_reuse_address = True


def main():
    port = 8772
    server = ReusableHTTPServer(("0.0.0.0", port), Handler)
    print("  多场景 Web 服务已启动")
    print(f"  Campus  场景: {CAMPUS.kg}  规则 {len(CAMPUS.engine.rules)} 条")
    print(f"  访问: http://localhost:{port}/")
    print(f"  Warehouse 场景: {WAREHOUSE.kg}  规则 {len(WAREHOUSE.engine.rules)} 条")
    print(f"  访问: http://localhost:{port}/warehouse")
    print(f"  Ctrl+C 退出")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  服务已停止")
        server.server_close()


if __name__ == "__main__":
    main()