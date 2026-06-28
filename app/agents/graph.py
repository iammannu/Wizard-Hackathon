"""
Knowledge Graph Builder.
Extracts entities (companies, technologies, people, macro forces) and their
relationships from research findings. Forms the basis of the living knowledge graph.
"""
import json
from app.agents.base import llm_json


NODE_COLORS = {
    "company":    "#6c5ce7",
    "technology": "#00cba9",
    "sector":     "#fdcb6e",
    "macro":      "#fd79a8",
    "country":    "#74b9ff",
    "person":     "#a29bfe",
    "product":    "#55efc4",
    "concept":    "#b2bec3",
}


async def extract_knowledge_graph(state, evidence_text: str = "") -> dict:
    """Extract knowledge graph nodes and edges from research state."""
    agent_findings = []
    for name in state.active_agents:
        out = getattr(state, f"{name}_output", None)
        if out and out.get("key_finding"):
            agent_findings.append(f"[{name}]: {out['key_finding']}")

    raw = await llm_json(
        system="""You are a knowledge graph extraction specialist.
Extract entities and relationships from this investment research.
Focus on the most important and interconnected entities.

Node types: company, technology, sector, macro, country, person, product, concept

Return JSON (NOT wrapped):
{
  "nodes": [
    {"id": "n1", "label": "NVIDIA", "type": "company", "description": "GPU/AI compute leader"},
    {"id": "n2", "label": "H100", "type": "product", "description": "Flagship AI accelerator"}
  ],
  "edges": [
    {"source": "n1", "target": "n2", "relationship": "manufactures", "strength": 0.9}
  ]
}

Guidelines:
- Create 8-14 nodes covering the most relevant entities
- Create 8-14 edges showing the most important relationships
- Relationship examples: "competes with", "supplies to", "depends on", "benefits from", "threatened by", "partner of", "regulated by"
- Strength 0-1 indicates how strong/important the relationship is
- Keep labels short (1-3 words)""",
        user=f"""Query: {state.query}
Tickers: {state.tickers}

Agent findings:
{chr(10).join(agent_findings[:8])}

External research:
{evidence_text[:600]}""",
    )

    nodes = raw.get("nodes", [])
    edges = raw.get("edges", [])

    # Validate and colorize nodes
    valid_nodes = []
    node_ids = set()
    for node in nodes:
        if node.get("id") and node.get("label"):
            node["color"] = NODE_COLORS.get(node.get("type", "concept"), "#b2bec3")
            valid_nodes.append(node)
            node_ids.add(node["id"])

    # Validate edges (only keep edges where both nodes exist)
    valid_edges = [
        e for e in edges
        if e.get("source") in node_ids and e.get("target") in node_ids
    ]

    return {
        "nodes": valid_nodes,
        "edges": valid_edges,
        "node_count": len(valid_nodes),
        "edge_count": len(valid_edges),
    }
