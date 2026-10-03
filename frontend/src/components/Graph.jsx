import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY } from "d3-force";
import { useMemo, useRef, useState } from "react";

const R = { user: 18, upi: 9, name: 9, device: 7, location: 7 };

/** Static force layout (computed once per data set) rendered as SVG with pan / zoom / select. */
export default function Graph({ data, selected, onSelect, highlightCycles }) {
  const [view, setView] = useState({ x: 0, y: 0, k: 1 });
  const drag = useRef(null);
  const W = 900, H = 560;

  const layout = useMemo(() => {
    const nodes = data.nodes.map((n) => ({ ...n }));
    const ids = new Set(nodes.map((n) => n.id));
    const links = data.edges.filter((e) => ids.has(e.source) && ids.has(e.target)).map((e) => ({ ...e }));
    const sim = forceSimulation(nodes)
      .force("link", forceLink(links).id((d) => d.id).distance((l) => (l.kind === "OBSERVED_FLOW" ? 70 : 90)).strength(0.6))
      .force("charge", forceManyBody().strength(-260))
      .force("x", forceX(0).strength(0.05))
      .force("y", forceY(0).strength(0.07))
      .force("collide", forceCollide((d) => (R[d.kind] || 8) + 14))
      .stop();
    const you = nodes.find((n) => n.id === "you");
    if (you) { you.fx = 0; you.fy = 0; }
    for (let i = 0; i < 300; i++) sim.tick();
    // fit the viewBox to the laid-out graph (plus room for labels)
    const xs = nodes.map((n) => n.x), ys = nodes.map((n) => n.y);
    const pad = 60;
    const box = nodes.length
      ? { x: Math.min(...xs) - pad, y: Math.min(...ys) - pad, w: Math.max(...xs) - Math.min(...xs) + pad * 2, h: Math.max(...ys) - Math.min(...ys) + pad * 2 }
      : { x: -W / 2, y: -H / 2, w: W, h: H };
    // keep the canvas aspect ratio so the SVG fills its frame
    const ratio = W / H;
    if (box.w / box.h > ratio) { const h = box.w / ratio; box.y -= (h - box.h) / 2; box.h = h; }
    else { const w = box.h * ratio; box.x -= (w - box.w) / 2; box.w = w; }
    return { nodes, links, box };
  }, [data]);

  const cycleEdges = useMemo(() => {
    const s = new Set();
    for (const c of data.cycles || []) c.forEach((id, i) => s.add(id + "→" + c[(i + 1) % c.length]));
    return s;
  }, [data]);

  const onWheel = (e) => {
    const k = Math.min(4, Math.max(0.3, view.k * (e.deltaY < 0 ? 1.15 : 1 / 1.15)));
    setView({ ...view, k });
  };
  const onDown = (e) => {
    if (e.target.closest(".g-node")) return;
    drag.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onMove = (e) => {
    if (!drag.current) return;
    setView({ ...view, x: drag.current.vx + (e.clientX - drag.current.x), y: drag.current.vy + (e.clientY - drag.current.y) });
  };
  const onUp = () => { drag.current = null; };

  return (
    <div className="graph-wrap">
      <div className="graph-tools" role="group" aria-label="Zoom">
        <button type="button" className="ghost small" onClick={() => setView({ ...view, k: Math.min(4, view.k * 1.25) })} aria-label="Zoom in">+</button>
        <button type="button" className="ghost small" onClick={() => setView({ ...view, k: Math.max(0.3, view.k / 1.25) })} aria-label="Zoom out">−</button>
        <button type="button" className="ghost small" onClick={() => setView({ x: 0, y: 0, k: 1 })}>Reset</button>
      </div>
      <svg className="graph" viewBox={`${layout.box.x} ${layout.box.y} ${layout.box.w} ${layout.box.h}`} role="img"
           aria-label={`Relationship graph with ${data.nodes.length} entities`}
           onWheel={onWheel} onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerLeave={onUp}>
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" className="g-arrow" />
          </marker>
        </defs>
        <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
          {layout.links.map((l, i) => {
            const s = l.source, t = l.target;
            const hot = highlightCycles && cycleEdges.has(s.id + "→" + t.id);
            const sel = selected && (s.id === selected || t.id === selected);
            const money = ["SENT", "RECEIVED", "OBSERVED_FLOW"].includes(l.kind);
            return (
              <line key={i} x1={s.x} y1={s.y} x2={t.x} y2={t.y}
                    className={`g-edge ${l.kind.toLowerCase()} ${l.risk || ""} ${hot ? "hot" : ""} ${sel ? "sel" : ""} ${l.synthetic ? "synthetic" : ""}`}
                    strokeWidth={money ? Math.min(6, 1 + Math.log10(1 + l.total / 1000)) : 1}
                    markerEnd={money ? "url(#arrow)" : undefined} />
            );
          })}
          {layout.nodes.map((n) => {
            const r = R[n.kind] || 8;
            const label = n.kind === "user" ? "You" : n.label.length > 22 ? n.label.slice(0, 21) + "…" : n.label;
            // label only what matters, so busy graphs stay readable; every node still has a tooltip and aria-label
            const showLabel = n.kind === "user" || n.suspicious || selected === n.id || layout.nodes.length <= 14;
            return (
              <g key={n.id} className={`g-node ${n.kind} ${n.risk || "none"} ${n.suspicious ? "suspicious" : ""} ${selected === n.id ? "selected" : ""}`}
                 transform={`translate(${n.x} ${n.y})`} tabIndex={0} role="button"
                 aria-label={`${n.kind} ${n.label}${n.risk ? `, ${n.risk} risk` : ""}${n.suspicious ? ", flagged" : ""}`}
                 onClick={() => onSelect(n)} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onSelect(n)}>
                {n.kind === "device" ? <rect x={-r} y={-r} width={r * 2} height={r * 2} />
                  : n.kind === "location" ? <path d={`M0,${-r} L${r},0 L0,${r} L${-r},0 Z`} />
                  : <circle r={r} />}
                <title>{n.label}</title>
                {n.suspicious && <circle r={r + 4} className="g-ring" />}
                {showLabel && <text y={r + 13} textAnchor="middle">{label}</text>}
                {n.risk === "high" && <text y={4} textAnchor="middle" className="g-glyph">!</text>}
              </g>
            );
          })}
        </g>
      </svg>
      <ul className="legend" aria-label="Legend">
        <li><span className="lg circle" /> UPI ID / person</li>
        <li><span className="lg square" /> Device</li>
        <li><span className="lg diamond" /> Location</li>
        <li><span className="lg ring" /> Flagged entity</li>
        <li><span className="lg hot" /> Circular money flow</li>
        <li><span className="lg dashed" /> Synthetic observed flow</li>
      </ul>
    </div>
  );
}
