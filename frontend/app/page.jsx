"use client";
import { useEffect, useState } from "react";
import Markdown from "react-markdown";

const API = process.env.NEXT_PUBLIC_API || "http://localhost:8001";
const NODES = { supervisor: [70, 110], researcher: [250, 50], retriever: [250, 170], analyst: [450, 110], writer: [650, 110], reviewer: [830, 110] };
const EDGES = [["supervisor", "researcher"], ["supervisor", "retriever"], ["researcher", "analyst"], ["retriever", "analyst"], ["researcher", "retriever"], ["analyst", "writer"], ["writer", "reviewer"]];
const EXAMPLES = ["Compare LangGraph vs CrewAI for production agents", "Latest breakthroughs in solid-state batteries", "Summarize the key findings in my uploaded documents"];

function Graph({ steps, busy }) {
  const seen = steps.map((s) => s.split(":")[0]);
  const last = seen[seen.length - 1];
  const loops = seen.filter((a) => a === "writer").length > 1;
  const cls = (n) => (busy && n === last ? "active" : seen.includes(n) ? "done" : !busy && steps.length ? "skip" : "");
  return (
    <svg viewBox="0 0 900 220" width="100%">
      <defs><linearGradient id="g"><stop offset="0" stopColor="#22d3ee" /><stop offset="1" stopColor="#a78bfa" /></linearGradient></defs>
      {EDGES.map(([a, b]) => {
        const [x1, y1] = NODES[a], [x2, y2] = NODES[b];
        return <line key={a + b} className={`edge ${seen.includes(a) && seen.includes(b) ? "on" : ""}`} x1={x1} y1={y1} x2={x2} y2={y2} />;
      })}
      <path className={`edge ${loops ? "on" : ""}`} d="M830 80 C 790 10, 690 10, 650 80" />
      <text x="740" y="22" fill="#64748b" fontSize="11" textAnchor="middle">revise loop</text>
      {Object.entries(NODES).map(([n, [x, y]]) => (
        <g key={n} className={`node ${cls(n)}`}>
          <circle cx={x} cy={y} r="30" />
          <text x={x} y={y + 4} style={{ fontSize: 18, fontWeight: 800 }}>{n[0].toUpperCase()}</text>
          <text x={x} y={y + 50}>{n}</text>
        </g>
      ))}
    </svg>
  );
}

export default function Home() {
  const [q, setQ] = useState("");
  const [res, setRes] = useState(null);
  const [steps, setSteps] = useState([]);
  const [docs, setDocs] = useState({});
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [hl, setHl] = useState(null);
  const [up, setUp] = useState(null);
  const [t0, setT0] = useState(0);
  const [now, setNow] = useState(0);

  const loadDocs = () => fetch(`${API}/documents`).then((r) => r.json()).then(setDocs).catch(() => {});
  useEffect(() => { loadDocs(); }, []);
  useEffect(() => { if (!busy) return; const i = setInterval(() => setNow(Date.now()), 100); return () => clearInterval(i); }, [busy]);

  async function upload(e) {
    const fd = new FormData();
    [...e.target.files].forEach((f) => fd.append("files", f));
    const names = [...e.target.files].map((f) => f.name).join(", ");
    e.target.value = "";
    setUp({ busy: true, text: `Uploading & indexing ${names}...` });
    try {
      const r = await fetch(`${API}/upload`, { method: "POST", body: fd });
      if (!r.ok) throw new Error(`Server error ${r.status}`);
      const out = Object.entries(await r.json());
      const bad = out.filter(([, v]) => v.error);
      setUp({ ok: !bad.length, text: out.map(([n, v]) => v.error ? `${n}: failed - ${v.error}` : `${n}: uploaded (${v.chunks} chunks)`).join(" | ") });
    } catch (err) {
      setUp({ ok: false, text: `Cannot reach backend at ${API}. Is it running? (${err.message})` });
    }
    loadDocs();
  }

  async function ask(query = q) {
    if (!query || busy) return;
    setQ(query); setBusy(true); setRes(null); setSteps([]); setMsg(""); setT0(Date.now()); setNow(Date.now());
    try {
      const r = await fetch(`${API}/research/stream`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query }) });
      const reader = r.body.getReader(), dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const lines = buf.split("\n"); buf = lines.pop();
        for (const l of lines.filter(Boolean)) {
          const m = JSON.parse(l);
          if (m.step) setSteps((s) => [...s, m.step]);
          if (m.final) setRes(m.final);
          if (m.error) setMsg(m.error);
        }
      }
    } catch (e) { setMsg(String(e)); }
    setBusy(false);
  }

  const cite = (n) => { setHl(n); document.getElementById(`src-${n}`)?.scrollIntoView({ behavior: "smooth", block: "center" }); };
  const report = res?.report.replace(/\[(\d+(?:\s*,\s*\d+)*)\]/g, (_, ns) => ns.split(/\s*,\s*/).map((n) => `[${n}](#src-${n})`).join(""));
  const download = () => { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([res.report])); a.download = "yuva-report.md"; a.click(); };
  const elapsed = res ? res.latency : busy ? ((now - t0) / 1000).toFixed(1) : "-";

  return (
    <div className="app">
      <div className="col">
        <div className="panel">
          <div className="logo">YUVA AI</div>
          <p className="sub" style={{ marginTop: 4 }}>Multi-agent research intelligence</p>
        </div>
        <div className="panel">
          <p className="sub">Knowledge base</p>
          <label className="drop">+ Upload PDF / TXT / MD<input type="file" multiple accept=".pdf,.txt,.md" onChange={upload} hidden disabled={up?.busy} /></label>
          {up && <div className="doc" style={{ color: up.busy ? "#22d3ee" : up.ok ? "#34d399" : "#f87171", display: "block" }}>{up.text}</div>}
          {!Object.keys(docs).length && !up && <div className="doc" style={{ color: "#64748b" }}>No documents yet</div>}
          {Object.entries(docs).map(([n, c]) => <div className="doc" key={n}><span>{n}</span><span style={{ color: "#64748b" }}>{c}</span></div>)}
          {Object.keys(docs).length > 0 && <button className="ghost" style={{ marginTop: 10 }} onClick={() => fetch(`${API}/documents`, { method: "DELETE" }).then(loadDocs)}>Clear all</button>}
        </div>
        <div className="panel" style={{ flex: 1 }}>
          <p className="sub">Try a mission</p>
          {EXAMPLES.map((e) => <button key={e} className="chip" onClick={() => ask(e)}>{e}</button>)}
        </div>
      </div>

      <div className="col">
        <div className="cmd">
          <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && ask()} placeholder="Launch a research mission..." />
          <button className="btn" onClick={() => ask()} disabled={busy || !q}>{busy ? "Agents working..." : "Launch"}</button>
        </div>
        <div className="panel"><p className="sub">Agent orchestration</p><Graph steps={steps} busy={busy} /></div>
        {msg && <div className="err">{msg}</div>}
        <div className="panel" style={{ flex: 1 }}>
          {res ? (
            <>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <p className="sub" style={{ margin: 0 }}>Intelligence report</p>
                <button className="ghost" onClick={download}>Export .md</button>
              </div>
              <div className="report">
                <Markdown components={{ a: ({ href, children }) => href?.startsWith("#src-")
                  ? <a className="cite" onClick={(e) => { e.preventDefault(); cite(+href.slice(5)); }}>{children}</a>
                  : <a href={href} target="_blank">{children}</a> }}>{report}</Markdown>
              </div>
            </>
          ) : (
            <div className="log">
              <p className="sub">Live agent feed</p>
              {steps.length ? steps.map((s, i) => { const [a, ...r] = s.split(":"); return <div key={i}><b>{a}</b>{r.join(":")}</div>; })
                : <div style={{ color: "#475569" }}>Awaiting mission...</div>}
            </div>
          )}
        </div>
      </div>

      <div className="col">
        <div className="panel">
          <p className="sub">Mission metrics</p>
          <div className="stats">
            <div className="stat"><b>{elapsed}s</b><span>Latency</span></div>
            <div className="stat"><b>{res?.sources.length ?? "-"}</b><span>Sources</span></div>
            <div className="stat"><b>{steps.length || "-"}</b><span>Agent steps</span></div>
            <div className="stat"><b>{res?.revisions ?? "-"}</b><span>Reviews</span></div>
          </div>
          {res && <div style={{ marginTop: 12 }}><span className="badge" style={{ background: res.approved ? "rgba(52,211,153,.15)" : "rgba(248,113,113,.15)", color: res.approved ? "#34d399" : "#f87171" }}>
            {res.approved ? "Claims verified" : "Partially verified"}</span></div>}
        </div>
        <div className="panel" style={{ flex: 1 }}>
          <p className="sub">Evidence ({res?.sources.length ?? 0})</p>
          {res?.sources.map((s) => (
            <div key={s.id} id={`src-${s.id}`} className={`src ${hl === s.id ? "hl" : ""}`}>
              <span className="n">[{s.id}]</span>
              {s.source.startsWith("http") ? <a href={s.source} target="_blank">{s.title}</a> : s.source}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
