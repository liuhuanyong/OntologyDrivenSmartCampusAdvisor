"""
第 3 层(续)：Web 服务器 (零依赖，基于 http.server)
=====================================================
启动后访问 http://localhost:8769

API:
  GET  /                -> 问答界面 (index.html)
  GET  /api/graph       -> 完整知识图谱数据 (nodes + edges)
  GET  /api/rules       -> 规则列表
  GET  /api/stats       -> 图谱统计信息
  GET  /api/examples    -> 20 个复杂推理示例问题
  GET  /api/entities    -> 所有实体 (按类型分组, 含属性)
  GET  /api/relations   -> 所有关系 (含 schema 定义 + 实例列表)
  POST /api/ask         -> 问答接口 {question} -> {answer, reasoning, ...}
"""
from __future__ import annotations

import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler

from knowledge_base import build_knowledge_base
from ontology import ENTITY_COLORS, ENTITY_SCHEMAS, RELATION_SCHEMAS
from rules import RuleEngine, build_default_rules
from advisor import ask, RULE_MEANINGS


# ---- 初始化知识图谱 + 规则引擎 (全局单例) ---- #
KG = build_knowledge_base()
ENGINE = RuleEngine(KG)
for r in build_default_rules():
    ENGINE.register(r)
ENGINE.dump_rules_json("rules_store.json")
ENGINE.forward_chain()  # 执行正向链式，物化 eligible_for

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


# ---- 20 个复杂推理示例 ---- #
EXAMPLE_QUESTIONS = [
    # 课程推荐类 (R6 + R3)
    "Alice 下学期该修什么课？",
    "Dave 下学期该修什么课？",
    "Frank 选课建议",
    "Henry 该修哪些课？",
    # 职业适配类 (R5)
    "Eve 适合什么职业方向？",
    "Alice 适合什么职业方向？",
    "Bob 适合什么职业方向？",
    "Grace 就业方向如何？",
    # 技能缺口+补齐方案 (R4 + R7)
    "Carol 想成为数据科学家，还差什么？",
    "Bob 想成为机器学习工程师，怎么补？",
    "Dave 想做 NLP工程师，还差什么？",
    "Frank 想成为数据库工程师，目标怎么实现？",
    "Henry 想做数据分析师，还差什么？",
    # 选课资格检查 (R2)
    "Bob 能选 ML401 吗？",
    "Alice 能不能选 CS401 操作系统？",
    "Carol 可以直接选 ML402 深度学习吗？",
    "Eve 能修 NLP401 自然语言处理吗？",
    # 学生画像 (R6 + R3 + R5)
    "给我看看 Grace 的完整画像",
    "Alice 的完整档案",
    "Eve 的情况如何？",
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

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self._send_file(os.path.join(STATIC_DIR, "index.html"), "text/html; charset=utf-8")
        elif self.path == "/api/graph":
            self._send_json(KG.full_graph_data())
        elif self.path == "/api/rules":
            data = []
            for r in sorted(ENGINE.rules.values(), key=lambda r: r.priority):
                d = r.to_dict()
                d["meaning"] = RULE_MEANINGS.get(r.name, r.description)
                data.append(d)
            self._send_json(data)
        elif self.path == "/api/examples":
            self._send_json({"examples": EXAMPLE_QUESTIONS})
        elif self.path == "/api/entities":
            self._send_json(self._build_entities_data())
        elif self.path == "/api/relations":
            self._send_json(self._build_relations_data())
        elif self.path == "/api/stats":
            self._send_json({
                "kg": KG.stats(),
                "entity_types": list(ENTITY_SCHEMAS.keys()),
                "relation_types": list(RELATION_SCHEMAS.keys()),
                "colors": ENTITY_COLORS,
                "rules": len(ENGINE.rules),
            })
        elif self.path.startswith("/static/"):
            fname = self.path[8:]
            fpath = os.path.join(STATIC_DIR, fname)
            if os.path.exists(fpath):
                ct = "text/css; charset=utf-8" if fname.endswith(".css") else "application/javascript"
                self._send_file(fpath, ct)
            else:
                self.send_error(404)
        else:
            self.send_error(404)

    def _build_entities_data(self) -> dict:
        """构建实体 Tab 页数据: schema 定义 + 实例列表 (按类型分组)。"""
        # schema 定义
        schemas = {t: {"attrs": {k: v.__name__ for k, v in attrs.items()},
                        "color": ENTITY_COLORS.get(t, "#6b7280")}
                   for t, attrs in ENTITY_SCHEMAS.items()}
        # 实例 (按类型分组)
        instances = {}
        for etype in ENTITY_SCHEMAS:
            ents = KG.list_entities(etype)
            instances[etype] = [{
                "id": e.eid, "label": e.label, "attrs": e.attrs,
            } for e in ents]
        return {"schemas": schemas, "instances": instances,
                "total": sum(len(v) for v in instances.values())}

    def _build_relations_data(self) -> dict:
        """构建关系 Tab 页数据: schema 定义 + 实例三元组列表 (按关系分组)。"""
        # schema 定义 (注意: edge 中的值是 type 对象, 需转成字符串)
        schemas = {p: {"domain": s["domain"], "range": s["range"],
                        "edge": {k: v.__name__ for k, v in s.get("edge", {}).items()}}
                   for p, s in RELATION_SCHEMAS.items()}
        # 实例三元组 (按关系分组)
        instances = {}
        for subj, preds in KG._out.items():
            for pred, rels in preds.items():
                if pred not in instances:
                    instances[pred] = []
                for r in rels:
                    s_ent = KG.get_entity(r.subject)
                    o_ent = KG.get_entity(r.obj)
                    instances.setdefault(pred, []).append({
                        "from": r.subject, "from_label": s_ent.label if s_ent else r.subject,
                        "to": r.obj, "to_label": o_ent.label if o_ent else r.obj,
                        "edge": r.edge,
                        "inferred": (r.subject, r.predicate, r.obj) in KG._inferred,
                    })
        total = sum(len(v) for v in instances.values())
        return {"schemas": schemas, "instances": instances, "total": total}

    def do_POST(self):
        if self.path == "/api/ask":
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
            result = ask(KG, ENGINE, question)
            self._send_json(result)
        else:
            self.send_error(404)

    def log_message(self, *args):
        pass  # 静默日志


class ReusableHTTPServer(HTTPServer):
    allow_reuse_address = True


def main():
    port = 8772
    server = ReusableHTTPServer(("0.0.0.0", port), Handler)
    print(f"  Smart Campus Advisor 已启动")
    print(f"  知识图谱: {KG}")
    print(f"  规则数: {len(ENGINE.rules)}")
    print(f"  访问: http://localhost:{port}")
    print(f"  Ctrl+C 退出")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  服务已停止")
        server.server_close()

if __name__ == "__main__":
    main()
