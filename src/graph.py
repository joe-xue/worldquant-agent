# graph.py
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from models import GraphState
from nodes_author_risk import author_node, risk_node
from nodes_submit_poll import submit_node, poll_node
from nodes_analyze_decide import analyze_node, planner_node, decide_node

class DummyLLM:
    def generate(self, prompt: str) -> str:
        # 占位：可接入 Gemini 或其他 LLM
        if "EXPR:" in prompt:
            return "EXPR: ts_rank(winsorize(ts_delay(close, 1), std=4), 10)\nRATIONALE: Control turnover with delay and longer rank window."
        if "return updated settings" in prompt or "输出：给出修改后的 settings" in prompt:
            return '{"neutralization":"SECTOR","delay":1,"decay":1,"truncation":0.08,"region":"USA","universe":"TOP3000"}\nrationale: reduce turnover via decay'
        if "SCORE:" in prompt:
            return "SCORE: 1.2\nCOMMENT: Solid IR with moderate turnover.\nCONTINUE: Y"
        return ""

def build_graph(llm, mcp_client, store):
    graph = StateGraph(GraphState)
    # 绑定带依赖的包装节点
    def _planner(s): return planner_node(s, store=store)
    def _author(s): return author_node(s, llm=llm, lang="zh")
    def _risk(s): return risk_node(s, llm=llm, lang="zh")
    def _submit(s): return submit_node(s, mcp_client=mcp_client)
    def _poll(s): return poll_node(s, mcp_client=mcp_client, store=store)
    def _analyze(s): return analyze_node(s, llm=llm, store=store, lang="zh")
    def _decide(s): return decide_node(s)

    graph.add_node("planner", _planner)
    graph.add_node("author", _author)
    graph.add_node("risk", _risk)
    graph.add_node("submit", _submit)
    graph.add_node("poll", _poll)
    graph.add_node("analyze", _analyze)
    graph.add_node("decide", _decide)

    # 拓扑：planner → author → risk → submit → poll → analyze → decide → 循环或结束
    graph.add_edge("planner", "author")
    graph.add_edge("author", "risk")
    graph.add_edge("risk", "submit")
    graph.add_edge("submit", "poll")
    graph.add_edge("poll", "analyze")
    graph.add_edge("analyze", "decide")
    graph.add_conditional_edges("decide", lambda s: END if s.stop else "author")

    memory = MemorySaver()
    return graph.compile(checkpointer=memory)
