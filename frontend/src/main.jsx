import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

function App() {
  const [candidates, setCandidates] = useState([]);
  const [selected, setSelected] = useState([]);
  const [question, setQuestion] = useState("What evidence supports RAG evaluation experience?");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetch("/api/candidates")
      .then(async r => { if (!r.ok) throw new Error("Start the API and ingest the dataset."); return r.json(); })
      .then(data => setCandidates(data.candidate_ids))
      .catch(e => setError(e.message));
  }, []);

  async function submit(mode) {
    setBusy(true); setError(""); setResult(null);
    try {
      const response = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: mode === "shortlist"
            ? "Suggest up to three candidates for human review against R1-R7, then P1-P4. Explain supporting evidence and unknowns."
            : question,
          candidate_ids: mode === "shortlist" ? [] : selected,
          mode,
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Request failed.");
      setResult(data);
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  return <main>
    <h1>Candidate Evidence Assistant</h1>
    <p>Compare resume evidence against the job description. A hiring manager makes the decision.</p>
    <p className="muted">Candidate IDs protect identity in model prompts. Match each ID to its local DOCX filename.</p>
    <fieldset disabled={busy}>
      <legend>Candidate scope</legend>
      <p>Choose candidates for a focused answer or comparison. With none selected, Q&amp;A searches globally.</p>
      <div className="choices">{candidates.map(id => <label key={id}>
        <input type="checkbox" checked={selected.includes(id)} onChange={e =>
          setSelected(e.target.checked ? [...selected, id] : selected.filter(x => x !== id))
        } />{id}
      </label>)}</div>
    </fieldset>
    <form onSubmit={e => { e.preventDefault(); submit("qa"); }}>
      <label htmlFor="question">Question</label>
      <textarea id="question" required minLength={3} maxLength={600}
        value={question} onChange={e => setQuestion(e.target.value)} disabled={busy} />
      <div className="actions">
        <button disabled={busy}>Ask / compare</button>
        <button type="button" disabled={busy} onClick={() => submit("shortlist")}>
          Suggest shortlist from all 15
        </button>
      </div>
    </form>
    {busy && <p role="status">Retrieving evidence and checking the answer...</p>}
    {error && <p role="alert" className="error">{error}</p>}
    {result && <section aria-live="polite">
      <h2>{result.status}</h2>
      <p>{result.message}</p>
      <p className="notice">{result.notice}</p>
      {result.shortlist.length > 0 && <p><strong>Suggested for review:</strong> {result.shortlist.join(", ")}</p>}
      {result.findings.map((f, i) => <article key={i}>
        <h3>{f.candidate_id} <small>{f.requirement_ids.join(", ")}</small></h3>
        <p>{f.text}</p>
        {f.citations.map((c, j) => {
          const source = result.evidence.find(e => e.id === c.chunk_id);
          return <blockquote key={j}>
            <p>{c.quote}</p>
            <footer>{source?.source_id} · {source?.section} · {source?.locator} · {c.chunk_id}</footer>
          </blockquote>;
        })}
      </article>)}
      {result.unknowns.length > 0 && <article><h3>Unknowns to verify</h3>
        <ul>{result.unknowns.map((u, i) =>
          <li key={i}>{u.candidate_id}: not found in retrieved evidence — {u.topic}</li>)}</ul>
        <p>Missing evidence does not establish that a candidate lacks the skill.</p>
      </article>}
      <details><summary>Job requirements</summary>
        {result.jd_criteria.map(c => <p key={c.id}><strong>{c.section}</strong>: {c.text} ({c.locator})</p>)}
      </details>
      <details><summary>Inspect retrieved evidence ({result.evidence.length} sections)</summary>
        <p>Strategy: {result.retrieval_strategy}</p>
        {result.evidence.map((e, i) => <article key={i}>
          <h4>{e.source_id} · {e.section} · {e.locator}</h4><p>{e.text}</p>
        </article>)}
      </details>
    </section>}
  </main>;
}

createRoot(document.getElementById("root")).render(<App />);