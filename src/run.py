# run.py
import json
import sys
import traceback

from models import GraphState
from graph import build_graph, DummyLLM
from storage import SQLiteStore
from mcp_client import MCPClient

# NOTE:
# - 将之前的 dummy_platform.py 保存为 worldquant_platform_functions.py（或把其函数复制到该文件）。
# - MCPClient 会直接从 worldquant_platform_functions 模块调用工具，因此这里不再需要传入 runner。

def main():
    llm = DummyLLM()
    store = SQLiteStore("wq_graph.db")

    # 使用本地的 worldquant_platform_functions.py（可用 dummy implementation 进行测试）
    mcp = MCPClient()  # MCPClient 会反射调用 worldquant_platform_functions 中的工具

    app = build_graph(llm, mcp, store)

    init = GraphState(goal="Find robust alphas with low turnover and high stability.", max_rounds=5)

    try:
        final = app.invoke(init)
    except Exception as e:
        print("Graph invocation raised exception:", file=sys.stderr)
        traceback.print_exc()
        # 尝试把当前 init 状态持久化以便后续恢复（store 已被节点在运行时使用）
        try:
            store.save_snapshot(init.round_idx, init.dict())
            print("Saved snapshot of initial state for recovery.", file=sys.stderr)
        except Exception as se:
            print("Failed to save snapshot:", se, file=sys.stderr)
        raise

    print("Best candidate:")
    if final.best:
        print(json.dumps({
            "expr": final.best.expr,
            "score": final.best.score,
            "settings": final.best.settings,
            "rationale": getattr(final.best, "rationale", "")
        }, ensure_ascii=False, indent=2))
    else:
        print("No best candidate found.")
        print("History length:", len(final.history))

if __name__ == "__main__":
    main()
