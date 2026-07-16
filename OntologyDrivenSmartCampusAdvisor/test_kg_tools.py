import asyncio
import json
import unittest

from scenarios import load_scenario
from scenarios.campus.agentscope_agent import CampusGraphQueryTool, CampusReasonTool
from scenarios.procurement.agentscope_agent import ProcurementToolBase, SourceRecommendationTool


class CountingTool(ProcurementToolBase):
    name = "counting"
    description = "test"
    input_schema = {"type": "object", "properties": {}}
    calls = 0

    async def _execute(self, **kwargs):
        self.calls += 1
        return {"answer": "ok", "reasoning": [], "involved": set()}


class KGToolTest(unittest.TestCase):
    def test_tools_return_trace_and_execute_once(self):
        async def run():
            campus = load_scenario("campus")
            reason = await CampusReasonTool(campus.kg, campus.engine)(
                intent="recommend_courses", student="Alice",
            )
            reason_trace = json.loads(reason.content[0].text)["kg_trace"]
            self.assertTrue(reason_trace["rule_flow"])
            self.assertTrue(reason_trace["reasoning"])

            graph = await CampusGraphQueryTool(campus.kg, campus.engine)(
                query_type="list_entities", entity_type="Professor", limit=100,
            )
            graph_trace = json.loads(graph.content[0].text)["kg_trace"]
            self.assertEqual(graph_trace["status"], "success")
            self.assertTrue(graph_trace["reasoning"][0]["hops"])

            procurement = load_scenario("procurement")
            source = await SourceRecommendationTool(procurement.kg, procurement.engine)(
                material_code="M1001",
            )
            source_trace = json.loads(source.content[0].text)["kg_trace"]
            self.assertEqual(source_trace["tool_name"], "source_recommendation")
            self.assertTrue(source_trace["reasoning"])

            counting = CountingTool(procurement.kg, procurement.engine)
            await counting()
            self.assertEqual(counting.calls, 1)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
