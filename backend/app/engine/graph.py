"""Relationship graph built from a user's transactions (kept separate from the transaction classifier).

Nodes: you, counterparties (UPI ID or name), devices, locations.
Edges: SENT / RECEIVED (aggregated per counterparty), USED_DEVICE, AT_LOCATION, and, for the synthetic
demo dataset only, OBSERVED_FLOW between counterparties (third-party flows a real user can't see).

Analysis: fan-in / fan-out by degree, directed cycles (circular money movement), and suspicious
clusters = connected groups of risky nodes.
"""

from collections import defaultdict

from .simulator import DEMO_NETWORK

LEVELS = ["low", "medium", "high"]


def _max_level(a, b):
    if a is None:
        return b
    if b is None:
        return a
    return a if LEVELS.index(a) >= LEVELS.index(b) else b


def build(txs, reports: dict[str, int] | None = None, include_demo_flows: bool = True) -> dict:
    reports = reports or {}
    nodes, edges = {}, {}

    def node(nid, kind, label, **kw):
        n = nodes.setdefault(nid, {"id": nid, "kind": kind, "label": label, "risk": None, "transactions": 0,
                                   "total": 0.0, "synthetic": False, "reports": 0})
        n.update({k: v for k, v in kw.items() if v is not None})
        return n

    def edge(src, dst, kind, amount=0.0, risk=None, synthetic=False):
        e = edges.setdefault((src, dst, kind), {"source": src, "target": dst, "kind": kind, "count": 0,
                                                "total": 0.0, "risk": None, "synthetic": synthetic})
        e["count"] += 1
        e["total"] = round(e["total"] + amount, 2)
        e["risk"] = _max_level(e["risk"], risk)

    node("you", "user", "You")
    for t in txs:
        key = (t.counterparty_upi or t.counterparty_name or "").strip().lower()
        if not key:
            continue
        pid = f"party:{key}"
        n = node(pid, "upi" if t.counterparty_upi else "name", t.counterparty_upi or t.counterparty_name,
                 name=t.counterparty_name)
        n["transactions"] += 1
        n["total"] = round(n["total"] + t.amount, 2)
        n["risk"] = _max_level(n["risk"], t.risk_level)
        n["synthetic"] = n["synthetic"] or bool(t.is_synthetic)
        n["reports"] = reports.get(key, 0)
        if t.direction == "received":
            edge(pid, "you", "RECEIVED", t.amount, t.risk_level)
        else:
            edge("you", pid, "SENT", t.amount, t.risk_level)
        if t.device_id:
            did = f"device:{t.device_id}"
            node(did, "device", t.device_id)
            edge(did, pid, "USED_DEVICE", t.amount, t.risk_level)
        if t.location:
            lid = f"location:{t.location.lower()}"
            node(lid, "location", t.location)
            edge(pid, lid, "AT_LOCATION")

    if include_demo_flows:
        for a, b, amount in DEMO_NETWORK:
            pa, pb = f"party:{a}", f"party:{b}"
            if pa in nodes or pb in nodes:  # only around demo entities the user actually has
                node(pa, "upi", a, synthetic=True)
                node(pb, "upi", b, synthetic=True)
                edge(pa, pb, "OBSERVED_FLOW", amount, None, synthetic=True)

    # devices used for only one counterparty aren't interesting; keep devices shared or risky
    return analyze(nodes, list(edges.values()))


def analyze(nodes: dict, edges: list) -> dict:
    money = [e for e in edges if e["kind"] in ("SENT", "RECEIVED", "OBSERVED_FLOW")]
    out_deg, in_deg = defaultdict(set), defaultdict(set)
    adj = defaultdict(set)
    for e in money:
        out_deg[e["source"]].add(e["target"])
        in_deg[e["target"]].add(e["source"])
        adj[e["source"]].add(e["target"])

    flags = defaultdict(list)
    for nid, n in nodes.items():
        if n["kind"] in ("user", "device", "location"):
            continue
        if len(in_deg[nid]) >= 3:
            flags[nid].append(f"Fan-in: receives from {len(in_deg[nid])} sources")
        if len(out_deg[nid]) >= 3:
            flags[nid].append(f"Fan-out: sends to {len(out_deg[nid])} accounts")
        if n["reports"]:
            flags[nid].append(f"{n['reports']} unverified community report(s)")
    # devices used across several counterparties in risky transactions
    for e in edges:
        if e["kind"] == "USED_DEVICE" and e["risk"] in ("medium", "high"):
            flags[e["source"]].append("Device used in risky transactions")

    cycles = _cycles(adj, max_len=5)
    for c in cycles:
        for nid in c:
            if nid in nodes and nodes[nid]["kind"] != "user":
                flags[nid].append("Part of a circular money flow")

    suspicious = {nid for nid, n in nodes.items()
                  if n["kind"] not in ("user", "location") and (n["risk"] in ("medium", "high") or flags.get(nid))}
    for nid, n in nodes.items():
        n["flags"] = sorted(set(flags.get(nid, [])))
        n["suspicious"] = nid in suspicious
        n["degree"] = len(in_deg[nid] | out_deg[nid])

    clusters = _components(suspicious, edges)
    return {"nodes": list(nodes.values()), "edges": edges, "cycles": cycles,
            "clusters": [sorted(c) for c in clusters if len(c) >= 2],
            "stats": {"nodes": len(nodes), "edges": len(edges), "suspicious": len(suspicious), "cycles": len(cycles)}}


def _cycles(adj, max_len: int) -> list[list[str]]:
    """Simple directed cycles up to max_len, each reported once (rotation starting at its smallest id)."""
    found = set()
    for start in list(adj):
        stack = [(start, [start])]
        while stack:
            cur, path = stack.pop()
            for nxt in adj.get(cur, ()):
                if nxt == start and len(path) >= 2:
                    i = path.index(min(path))
                    found.add(tuple(path[i:] + path[:i]))
                elif nxt not in path and len(path) < max_len:
                    stack.append((nxt, path + [nxt]))
    return [list(c) for c in sorted(found)][:20]


def _components(ids: set, edges: list) -> list[set]:
    parent = {i: i for i in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in edges:
        a, b = e["source"], e["target"]
        if a in parent and b in parent:
            parent[find(a)] = find(b)
    groups = defaultdict(set)
    for i in ids:
        groups[find(i)].add(i)
    return list(groups.values())


def ego(graph: dict, center: str, depth: int = 2) -> dict:
    """Subgraph within `depth` hops of `center` (undirected)."""
    nbrs = defaultdict(set)
    for e in graph["edges"]:
        nbrs[e["source"]].add(e["target"])
        nbrs[e["target"]].add(e["source"])
    keep, frontier = {center}, {center}
    for _ in range(depth):
        frontier = {n for f in frontier for n in nbrs[f]} - keep
        keep |= frontier
    return {"nodes": [n for n in graph["nodes"] if n["id"] in keep],
            "edges": [e for e in graph["edges"] if e["source"] in keep and e["target"] in keep],
            "cycles": [c for c in graph["cycles"] if set(c) & keep],
            "clusters": [c for c in graph["clusters"] if set(c) & keep],
            "center": center}
