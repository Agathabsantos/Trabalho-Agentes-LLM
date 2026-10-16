"""Confere os nos e arestas do grafo de producao, sem montar outro grafo."""

from src.graph import fechar_graph, get_graph


def main() -> None:
    graph = get_graph()
    snapshot = graph.get_graph()
    print("NOS")
    for name in sorted(node for node in snapshot.nodes if node not in {"__start__", "__end__"}):
        print(name)
    print("ARESTAS")
    for edge in sorted(snapshot.edges, key=lambda item: (item.source, item.target)):
        source = edge.source.removeprefix("__start__").removeprefix("__end__") or "START"
        target = edge.target.removeprefix("__start__").removeprefix("__end__") or "END"
        conditional = " [condicional]" if edge.conditional else ""
        print(f"{source} -> {target}{conditional}")
    fechar_graph()


if __name__ == "__main__":
    main()
