import { useEffect, useMemo, useState } from 'react';
import { api } from './api';
import './intake.css';

type Screen = 'incidents' | 'analytics' | 'postmortem' | 'status';
type Action = { id?: number; action: string; outcome: 'successful' | 'failed' | 'inconclusive'; notes: string; created_at?: string };
type Incident = { id: string; title: string; timestamp: string; service: string; severity: string; symptoms: string[]; error_signatures: string[]; deployment: string; configuration_context: string; status: string; actions: Action[]; confirmed_root_cause?: string; resolution?: string; resolution_minutes?: number };
type Evidence = { incident_id: string; date?: string; service: string; text: string; relevance?: number; metadata?: Record<string, string> };
type SimilarIncident = { incident_id: string; memory_id?: string; date?: string; service: string; deployment_context: string; symptoms: string; error_signals: string; actions_and_outcomes: string; confirmed_root_cause: string; resolution: string; similarity_terms: string[]; differences: string[]; why_relevant: string; relevance?: number };
type Recommendation = { summary: string; hypotheses: { cause: string; confidence: number; rationale: string; classification: 'FACT' | 'HYPOTHESIS' }[]; recommended_steps: { step: string; priority: string; expected_observation: string; safety_note: string; evidence_ids: string[] }[]; safety_notes: string[]; evidence_memory_ids: string[]; memory_evidence: { incident_id: string; reason: string; outcome_summary: string }[]; unknowns: string[] };
type Analysis = { incident: Incident; recommendation: Recommendation; evidence: Evidence[]; similar_incidents: SimilarIncident[]; memory_stats: { recalled: number; selected_for_reasoning: number; llm_payload_characters: number }; analysis_id: number };
type Health = { status: string; hindsight_configured: boolean; llm_configured: boolean; synthetic_data_only: boolean };
type PostmortemDraft = { id: number; incident_id: string; report: Record<string, unknown>; markdown: string; finalized: boolean; retained_at?: string; updated_at: string };
type AnalyticsData = { measured_from: string; incident_count: number; investigation_count: number; investigations_with_recalled_results: number; recommendations_with_citations: number; citation_validity: number | null; valid_citations: number; citation_count: number; successful_hindsight_retains: number; distinct_incidents_with_retained_outcomes: number; action_outcomes: Record<string, number>; recommendation_feedback: { accepted: number; rejected: number; recorded: number }; latest_evaluation?: { id: number; status: string; created_at: string; result: EvaluationResult } | null };
type EvaluationResult = { evaluation_mode: string; baseline: { mode: string; retrieved_relevant: number; expected_relevant_in_completed_cases: number; note: string }; memory_assisted: { completed_cases: number; failed_cases: number; retrieval_recall: number | null; retrieval_recall_hits: number; retrieval_recall_expected: number; selected_precision: number | null; selected_precision_relevant: number; selected_precision_count: number; unmatched_cases_with_results: number; unmatched_cases: number }; metric_definitions: Record<string, string>; cases: { case_id: string; status: string; error_type?: string; recalled_ids: string[]; selected_ids: string[]; relevant_recalled_ids?: string[] }[] };

const compactEvidence = (text: string) => { const value = text.replace(/\s+/g, ' ').trim(); return value.length > 320 ? `${value.slice(0, 319)}…` : value; };
const fmt = (value: number | null | undefined, digits = 0) => value == null ? 'Not measured' : `${(value * (digits ? 100 : 1)).toFixed(digits || 0)}${digits ? '%' : ''}`;

function AnalyticsDashboard() {
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const refresh = async () => { try { setData(await api<AnalyticsData>('/api/analytics')); setError(''); } catch (e) { setError(e instanceof Error ? e.message : String(e)); } };
  useEffect(() => { void refresh(); }, []);
  const runEvaluation = async () => {
    setBusy(true); setError('');
    try { await api('/api/evaluations/run', { method: 'POST' }); await refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  };
  const evaluation = data?.latest_evaluation?.result;
  return <section className="page-stack">
    <div className="page-heading"><div><div className="eyebrow">MEASURED APPLICATION DATA</div><h2>Memory and evaluation analytics</h2><p>{data?.measured_from || 'Loading application records…'}</p></div><button className="button secondary" onClick={() => void refresh()}>↻ Refresh</button></div>
    {error && <div className="notice error">{error}</div>}
    {!data ? <div className="card">Loading metrics…</div> : <>
      <div className="kpi-grid">
        <Metric label="Incidents" value={data.incident_count}/><Metric label="Investigations" value={data.investigation_count}/>
        <Metric label="With recall results" value={data.investigations_with_recalled_results}/><Metric label="Hindsight retain calls" value={data.successful_hindsight_retains}/>
        <Metric label="Incidents with retained outcomes" value={data.distinct_incidents_with_retained_outcomes}/><Metric label="Recommendations with citations" value={data.recommendations_with_citations}/>
      </div>
      <div className="card"><div className="tag-title">RECORDED ENGINEER OUTCOMES</div><div className="metric-row">{Object.entries(data.action_outcomes).map(([name, value]) => <Metric key={name} label={name} value={value}/>)}</div></div>
      <div className="card"><div className="tag-title">RECOMMENDATION FEEDBACK</div><p className="muted">Latest accepted/rejected decision per analyzed recommendation. No feedback is inferred when none was recorded.</p><div className="metric-row"><Metric label="Accepted" value={data.recommendation_feedback.accepted}/><Metric label="Rejected" value={data.recommendation_feedback.rejected}/><Metric label="Recorded" value={data.recommendation_feedback.recorded}/><Metric label="Citation validity" value={data.citation_validity == null ? 'Not measured' : fmt(data.citation_validity, 1)}/></div></div>
      <div className="card"><div className="page-heading"><div><div className="tag-title">REPEATABLE HINDSIGHT EVALUATION</div><p>Calls real Hindsight recall for labeled synthetic cases. No LLM calls are made.</p></div><button className="button primary" disabled={busy} onClick={() => void runEvaluation()}>{busy ? 'Running…' : 'Run evaluation'}</button></div>
        {!evaluation ? <p className="muted">No evaluation run has been recorded.</p> : <EvaluationSummary evaluation={evaluation} status={data.latest_evaluation?.status || ''}/>}
      </div>
    </>}
  </section>;
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return <div className="metric"><span>{label}</span><b>{value}</b></div>;
}

function EvaluationSummary({ evaluation, status }: { evaluation: EvaluationResult; status: string }) {
  return <div className="evaluation-result">
    <div className="metric-row"><Metric label="Status" value={status}/><Metric label="Retrieval recall" value={evaluation.memory_assisted.retrieval_recall == null ? 'Not measured' : fmt(evaluation.memory_assisted.retrieval_recall, 1)}/><Metric label="Selected precision" value={evaluation.memory_assisted.selected_precision == null ? 'Not measured' : fmt(evaluation.memory_assisted.selected_precision, 1)}/><Metric label="Cases completed / failed" value={`${evaluation.memory_assisted.completed_cases} / ${evaluation.memory_assisted.failed_cases}`}/></div>
    <p className="muted">{evaluation.baseline.note}</p>
    <p className="muted">Evaluation mode: {evaluation.evaluation_mode}. Scope: retrieval and six-memory selection; not recommendation quality or incident resolution.</p>
    <details><summary>Scenario results</summary>{evaluation.cases.map(item => <div className="evaluation-case" key={item.case_id}><b>{item.case_id}</b><span>{item.status}{item.error_type ? ` · ${item.error_type}` : ''}</span><small>Recalled: {item.recalled_ids.join(', ') || 'none'} · Selected: {item.selected_ids.join(', ') || 'none'}</small></div>)}</details>
    <details><summary>Metric definitions</summary>{Object.entries(evaluation.metric_definitions).map(([key, value]) => <p key={key}><b>{key}</b>: {value}</p>)}</details>
  </div>;
}

function PostmortemPanel({ incidentId }: { incidentId: string }) {
  const [draft, setDraft] = useState<PostmortemDraft | null>(null);
  const [markdown, setMarkdown] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  useEffect(() => {
    setDraft(null); setMarkdown(''); setError(''); setMessage('');
    if (!incidentId) return;
    api<PostmortemDraft>(`/api/incidents/${incidentId}/postmortem`).then(value => { setDraft(value); setMarkdown(value.markdown); })
      .catch(e => { if (!(e instanceof Error) || !e.message.includes('Postmortem draft not found')) setError(e instanceof Error ? e.message : String(e)); });
  }, [incidentId]);
  const run = async (operation: () => Promise<PostmortemDraft>, success: string) => {
    setBusy(true); setError(''); setMessage('');
    try { const value = await operation(); setDraft(value); setMarkdown(value.markdown); setMessage(success); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  };
  if (!incidentId) return <div className="card">Select an incident before drafting a postmortem.</div>;
  const download = () => { const url = URL.createObjectURL(new Blob([markdown], { type: 'text/markdown;charset=utf-8' })); const anchor = document.createElement('a'); anchor.href = url; anchor.download = `${incidentId}-postmortem.md`; anchor.click(); URL.revokeObjectURL(url); };
  const report = draft?.report || {};
  return <section className="page-stack">
    <div className="page-heading"><div><div className="eyebrow">REVIEW BEFORE RETAINING</div><h2>Incident postmortem</h2><p>{incidentId} · Drafts use recorded incident, action, analysis, and Hindsight citation data.</p></div><button className="button secondary" disabled={busy} onClick={() => void run(() => api<PostmortemDraft>(`/api/incidents/${incidentId}/postmortem/generate`, { method: 'POST' }), 'Draft generated from recorded data.')}>Generate draft</button></div>
    {error && <div className="notice error">{error}</div>}{message && <div className="notice">{message}</div>}
    {!draft ? <div className="card">Generate a draft to review recorded facts and unknowns.</div> : <>
      <div className="card"><div className="tag-title">STRUCTURED REPORT</div><div className="postmortem-facts">
        <p><b>Summary</b> · {String(report.summary || '')}</p><p><b>Impact</b> · {String(report.impact || '')}</p><p><b>Confirmed root cause</b> · {String(report.confirmed_root_cause || '')}</p><p><b>Resolution</b> · {String(report.resolution_status || '')}: {String(report.resolution || '')}</p>
        <details><summary>Timeline, contributing factors, actions, lessons, and evidence</summary><pre>{JSON.stringify({ timeline: report.timeline, contributing_factors: report.contributing_factors, actions: report.actions, lessons_learned: report.lessons_learned, follow_up_recommendations: report.follow_up_recommendations, memories_informed: report.memories_informed }, null, 2)}</pre></details>
      </div></div>
      <div className="card"><div className="tag-title">EDITABLE MARKDOWN</div><textarea className="postmortem-editor" value={markdown} onChange={e => setMarkdown(e.target.value)} aria-label="Edit postmortem Markdown"/><div className="button-row">
        <button className="button secondary" disabled={busy || markdown.trim().length < 20} onClick={() => void run(() => api<PostmortemDraft>(`/api/incidents/${incidentId}/postmortem`, { method: 'PUT', body: JSON.stringify({ markdown }) }), 'Draft saved.')}>Save edits</button>
        <button className="button secondary" onClick={download} disabled={!markdown.trim()}>Export Markdown</button>
        <button className="button primary" disabled={busy || draft.finalized && draft.markdown === markdown} onClick={() => { if (window.confirm('Finalize this postmortem and retain the incident outcome in Hindsight?')) void run(() => api<PostmortemDraft>(`/api/incidents/${incidentId}/postmortem/finalize`, { method: 'POST', body: JSON.stringify({ markdown }) }), 'Postmortem finalized and incident knowledge retained.'); }}>Finalize + retain in Hindsight</button>
      </div><small className="muted">{draft.finalized ? `Finalized${draft.retained_at ? ` · retained ${new Date(draft.retained_at).toLocaleString()}` : ''}` : 'Draft · not finalized'}</small></div>
    </>}
  </section>;
}

function IntegrationStatus({ health }: { health: Health | null }) {
  return <section className="page-stack"><div className="page-heading"><div><div className="eyebrow">APPLICATION STATUS</div><h2>Integration configuration</h2><p>This page reports configured credentials; it does not probe remote services.</p></div></div>
    <div className="card"><div className="tag-title">BACKEND STATUS</div><div className="metric-row"><Metric label="API" value={health?.status || 'Loading'}/><Metric label="Synthetic data only" value={health ? String(health.synthetic_data_only) : 'Loading'}/><Metric label="Hindsight credentials" value={health ? health.hindsight_configured ? 'Configured' : 'Missing' : 'Loading'}/><Metric label="LLM credentials" value={health ? health.llm_configured ? 'Configured' : 'Missing' : 'Loading'}/></div><p className="muted">The health endpoint checks configuration presence only. Live Hindsight calls occur during analysis, retain, and evaluation; Groq is called during recommendation generation.</p></div>
    <div className="card"><div className="tag-title">SAFETY BOUNDARY</div><p>Recommendations are advisory. The application does not connect to production telemetry or execute remediation.</p></div>
  </section>;
}

export default function App() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [current, setCurrent] = useState('');
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [screen, setScreen] = useState<Screen>('incidents');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [health, setHealth] = useState<Health | null>(null);
  const [action, setAction] = useState('');
  const [outcome, setOutcome] = useState<Action['outcome']>('inconclusive');
  const [notes, setNotes] = useState('');
  const [actionSubmissionId, setActionSubmissionId] = useState(() => crypto.randomUUID());
  const [cause, setCause] = useState('');
  const [resolution, setResolution] = useState('');
  const [minutes, setMinutes] = useState('');
  const [intakeOpen, setIntakeOpen] = useState(false);
  const [intakeTitle, setIntakeTitle] = useState('');
  const [intakeSymptoms, setIntakeSymptoms] = useState('');
  const [intakeDeployment, setIntakeDeployment] = useState('');
  const [feedback, setFeedback] = useState<Record<number, boolean>>({});
  const selected = useMemo(() => incidents.find(item => item.id === current), [incidents, current]);
  const actions = selected?.actions || [];

  const refresh = async () => { const rows = await api<Incident[]>('/api/incidents'); setIncidents(rows); if (!current && rows[0]) setCurrent(rows[0].id); };
  useEffect(() => { void refresh().catch(e => setError(e.message)); void api<Health>('/api/health').then(setHealth).catch(() => {}); }, []);
  const run = async <T,>(operation: () => Promise<T>) => { setBusy(true); setError(''); setMessage(''); try { return await operation(); } catch (e) { setError(e instanceof Error ? e.message : String(e)); return undefined; } finally { setBusy(false); } };
  const createFirst = () => run(async () => { const item = await api<Incident>('/api/demo/first', { method: 'POST' }); await refresh(); setCurrent(item.id); setAnalysis(null); setMessage('First incident created. Analyze now to see the no-history baseline.'); });
  const analyze = () => run(async () => { if (!current) return; const result = await api<Analysis>(`/api/incidents/${current}/analyze`, { method: 'POST' }); setAnalysis(result); setMessage('Analysis complete using current evidence and Hindsight recall.'); await refresh(); });
  const seed = () => run(async () => { if (!window.confirm('Retain the four synthetic checkout incidents in the configured Hindsight bank?')) return; const result = await api<{ seeded: number }>('/api/demo/seed-hindsight', { method: 'POST' }); setMessage(`${result.seeded} synthetic historical incidents retained into Hindsight.`); });
  const recordAction = () => run(async () => {
    if (!current || !action.trim()) return;
    if (!window.confirm(`Record this ${outcome} outcome and retain the updated incident in Hindsight?`)) return;
    await api(`/api/incidents/${current}/actions`, { method: 'POST', body: JSON.stringify({ action, outcome, notes, submission_id: actionSubmissionId }) });
    await api(`/api/incidents/${current}/retain`, { method: 'POST' });
    setAction(''); setNotes(''); setActionSubmissionId(crypto.randomUUID()); await refresh();
    setMessage('Engineer outcome recorded and incident memory updated in Hindsight.');
  });
  const resolve = () => run(async () => { if (!current || !window.confirm('Mark this incident resolved and retain its final outcome in Hindsight?')) return; const result = await api<{ learning: { retained: boolean } }>(`/api/incidents/${current}/resolve`, { method: 'POST', body: JSON.stringify({ confirmed_root_cause: cause, resolution, resolution_minutes: Number(minutes) }) }); await refresh(); setMessage(result.learning.retained ? 'Incident resolved and its outcome retained in Hindsight.' : 'Incident resolved; memory retention needs attention.'); });
  const laterSimilar = () => run(async () => { const item = await api<Incident>('/api/incidents', { method: 'POST', body: JSON.stringify({ title: 'Later checkout timeout after traffic ramp', service: 'checkout-api', severity: 'SEV-2', symptoms: ['checkout requests timing out', 'database connection acquisition wait elevated'], error_signatures: ['TimeoutError: acquiring connection from pool exceeded 5s'], deployment: 'checkout-2.19.2', configuration_context: 'Traffic ramped to 2.7x normal; pool metrics not yet confirmed.' }) }); await refresh(); setCurrent(item.id); setAnalysis(null); setMessage('Later incident created. Analyze it to recall the newly retained outcome.'); });
  const createManual = () => run(async () => { const item = await api<Incident>('/api/incidents', { method: 'POST', body: JSON.stringify({ title: intakeTitle, service: 'checkout-api', severity: 'SEV-2', symptoms: intakeSymptoms.split('\n').map(value => value.trim()).filter(Boolean), deployment: intakeDeployment || 'unknown', configuration_context: 'Engineer supplied incident intake.' }) }); await refresh(); setCurrent(item.id); setAnalysis(null); setIntakeOpen(false); setIntakeTitle(''); setIntakeSymptoms(''); setIntakeDeployment(''); setMessage('Incident created. Run analysis to recall historical outcomes.'); });
  const recordFeedback = (accepted: boolean) => run(async () => { if (!analysis) return; await api(`/api/analyses/${analysis.analysis_id}/feedback`, { method: 'POST', body: JSON.stringify({ accepted }) }); setFeedback(previous => ({ ...previous, [analysis.analysis_id]: accepted })); setMessage(accepted ? 'Recommendation marked useful.' : 'Recommendation marked not useful.'); });
  const changeIncident = (id: string) => { setCurrent(id); setAnalysis(null); setMessage(''); setScreen('incidents'); };

  return <div className="shell">
    <header className="topbar"><div className="brand"><div className="brandmark">IQ</div><div><strong>IncidentIQ</strong><span>Incident intelligence & memory</span></div></div><div className="top-meta"><span className="synthetic"><i/> SYNTHETIC DEMO DATA</span><span className="connection">Hindsight {health?.hindsight_configured ? 'configured' : 'needs key'} <i className={health?.hindsight_configured ? 'on' : ''}/></span></div></header>
    <aside className="rail"><div className="rail-label">WORKSPACE</div><div className="rail-foot">DEMO · CHECKOUT</div></aside>
    <main className="main">
      <div className="page-head"><div><div className="eyebrow">INCIDENT INTELLIGENCE / CHECKOUT</div><h1>IncidentIQ workspace</h1><p>Investigate with persistent incident outcomes and explicit evidence.</p></div><button className="button secondary" onClick={() => void run(refresh)} disabled={busy}>↻ Refresh</button></div>
      <nav className="screen-nav" aria-label="IncidentIQ screens">{([['incidents', 'Incidents'], ['analytics', 'Memory analytics'], ['postmortem', 'Postmortem'], ['status', 'Integration status']] as [Screen, string][]).map(([value, label]) => <button key={value} className={`button ${screen === value ? 'primary' : 'secondary'}`} onClick={() => setScreen(value)}>{label}</button>)}</nav>
      {(error || message) && <div className={`notice ${error ? 'error' : ''}`}>{error || message}<button onClick={() => { setError(''); setMessage(''); }}>×</button></div>}
      {screen === 'analytics' ? <AnalyticsDashboard/> : screen === 'postmortem' ? <PostmortemPanel incidentId={current}/> : screen === 'status' ? <IntegrationStatus health={health}/> : <div className="layout">
        <section className="center-col">
          <div className="card incident-card"><div className="card-top"><div><div className="eyebrow">ACTIVE INCIDENT</div><h2>{selected?.title || 'No incident selected'}</h2></div><span className="pill sev">{selected?.severity || '—'}</span></div>
            <div className="selector-row"><label htmlFor="incident">Incident</label><select id="incident" value={current} onChange={event => changeIncident(event.target.value)}><option value="">Select incident</option>{incidents.map(item => <option key={item.id} value={item.id}>{item.id} · {item.title}</option>)}</select><button onClick={() => setIntakeOpen(value => !value)} disabled={busy} className="button secondary">＋ New intake</button><button onClick={() => void createFirst()} disabled={busy} className="button secondary">First demo</button></div>
            {intakeOpen && <div className="intake-panel"><div className="tag-title">NEW INCIDENT INTAKE <span>synthetic/demo workflow</span></div><div className="form-grid"><label className="full">Incident title<input value={intakeTitle} onChange={event => setIntakeTitle(event.target.value)} placeholder="e.g. Checkout latency after traffic ramp"/></label><label className="full">Symptoms<textarea value={intakeSymptoms} onChange={event => setIntakeSymptoms(event.target.value)} placeholder="One symptom per line"/></label><label className="full">Deployment/version<input value={intakeDeployment} onChange={event => setIntakeDeployment(event.target.value)} placeholder="checkout-2.19.0"/></label></div><button className="button primary" onClick={() => void createManual()} disabled={busy || !intakeTitle.trim() || !intakeSymptoms.trim()}>Create incident</button></div>}
            {selected && <><div className="facts"><div><span className="label">SERVICE</span><b>{selected.service}</b></div><div><span className="label">DEPLOYMENT</span><b>{selected.deployment}</b></div><div><span className="label">OPENED</span><b>{new Date(selected.timestamp).toLocaleString()}</b></div><div><span className="label">STATUS</span><b className="status-text">{selected.status}</b></div></div><div className="divider"/><div className="tag-title">FACT <span>Reported signals and context</span></div><div className="fact-list">{selected.symptoms.map(symptom => <div className="fact-row" key={symptom}><span className="bullet"/>{symptom}</div>)}</div><div className="context-line"><span>ERROR SIGNATURE</span>{selected.error_signatures.join(' · ') || 'Not supplied'}</div><div className="context-line"><span>CONFIGURATION</span>{selected.configuration_context}</div></>}
          </div>
          <div className="analysis-head"><div><div className="eyebrow">AGENT ANALYSIS</div><h2>Investigation plan</h2></div><button className="button primary" onClick={() => void analyze()} disabled={busy || !current}>{busy ? 'Working…' : '✦ Analyze incident'}</button></div>
          {!analysis ? <div className="empty-card"><div className="empty-icon">✧</div><h3>Ready to investigate</h3><p>Run analysis to recall related incidents and generate evidence-backed next steps.</p><div className="empty-actions"><button className="button primary" onClick={() => void analyze()} disabled={busy || !current}>Analyze with memory</button><button className="button secondary" onClick={() => void seed()} disabled={busy}>Seed historical incidents</button></div><small>For the walkthrough, analyze the first incident before seeding history.</small></div> : <>
            <div className="card summary"><div className="tag-title">SUMMARY</div><p>{analysis.recommendation.summary}</p></div>
            {analysis.similar_incidents.length > 0 && <div className="card"><div className="tag-title">SIMILAR INCIDENT COMPARISON <span>Hindsight evidence · not root-cause equivalence</span></div>{analysis.similar_incidents.map(item => <article className="comparison-card" key={item.incident_id || item.memory_id}><div className="comparison-heading"><b>{item.incident_id || 'Hindsight memory'}</b><span>{item.date ? new Date(item.date).toLocaleDateString() : 'Date unavailable'} · {item.service}</span></div><p><b>Why returned:</b> {item.why_relevant}</p><p><b>Shared terms:</b> {item.similarity_terms.join(', ') || 'No direct term overlap detected'}</p><p><b>Historical context:</b> {item.deployment_context}</p><p><b>Symptoms / errors:</b> {[item.symptoms, item.error_signals].filter(Boolean).join(' · ') || 'Not supplied'}</p><p><b>Actions and outcomes:</b> {item.actions_and_outcomes}</p><p><b>Confirmed cause in that incident:</b> {item.confirmed_root_cause}</p><p><b>Resolution:</b> {item.resolution}</p><small>Memory ID: {item.memory_id || 'Not returned'}</small></article>)}</div>}
            <div className="card"><div className="tag-title">HYPOTHESES <span>Possible explanations, not confirmed facts</span></div>{analysis.recommendation.hypotheses.length ? analysis.recommendation.hypotheses.map((hypothesis, index) => <div className="hypothesis" key={hypothesis.cause}><div className="rank">0{index + 1}</div><div className="hypo-copy"><div className="hypo-name">{hypothesis.cause}<span className="confidence">{Math.round(hypothesis.confidence * 100)}% confidence</span></div><p>{hypothesis.rationale}</p></div><span className={`pill ${hypothesis.classification === 'FACT' ? 'fact-pill' : 'hypo-pill'}`}>{hypothesis.classification}</span></div>) : <p className="muted">No hypotheses returned.</p>}</div>
            <div className="card"><div className="tag-title">RECOMMENDATION <span>Safe investigation steps</span></div>{analysis.recommendation.recommended_steps.map((step, index) => <div className="step" key={step.step}><div className="step-num">{index + 1}</div><div className="step-copy"><div className="step-line"><b>{step.step}</b><span className={`priority ${step.priority}`}>{step.priority}</span></div><p><b>Expected observation</b> · {step.expected_observation}</p><p className="safety"><b>Safety</b> · {step.safety_note}</p>{step.evidence_ids.length > 0 && <div className="evidence-link">Evidence used: {step.evidence_ids.join(', ')}</div>}</div></div>)}<div className="button-row"><button className="button secondary" disabled={busy || feedback[analysis.analysis_id] !== undefined} onClick={() => void recordFeedback(true)}>Useful</button><button className="button secondary" disabled={busy || feedback[analysis.analysis_id] !== undefined} onClick={() => void recordFeedback(false)}>Not useful</button>{feedback[analysis.analysis_id] !== undefined && <small>Feedback recorded: {feedback[analysis.analysis_id] ? 'useful' : 'not useful'}</small>}</div></div>
            {analysis.recommendation.unknowns.length > 0 && <div className="card unknown"><div className="tag-title">UNKNOWN <span>Resolve these gaps as you investigate</span></div><ul>{analysis.recommendation.unknowns.map(item => <li key={item}>{item}</li>)}</ul></div>}
            <div className="card capture"><div className="tag-title">ENGINEER ACTION / OUTCOME</div><p className="muted">Record what was actually tried. Failed and inconclusive actions are retained too.</p><div className="form-grid"><label>Action attempted<input value={action} onChange={event => setAction(event.target.value)} placeholder="e.g. Check pool utilization"/></label><label>Outcome<select value={outcome} onChange={event => setOutcome(event.target.value as Action['outcome'])}><option value="successful">Successful</option><option value="failed">Failed</option><option value="inconclusive">Inconclusive</option></select></label><label className="full">Notes<textarea value={notes} onChange={event => setNotes(event.target.value)} placeholder="Observation or outcome details"/></label></div><button className="button primary" onClick={() => void recordAction()} disabled={busy || !action.trim()}>Record outcome + retain memory</button>{actions.length > 0 && <div className="action-history">{actions.map((item, index) => <div key={item.id || index}><span className={`outcome ${item.outcome}`}>{item.outcome}</span><b>{item.action}</b><small>{item.notes}</small></div>)}</div>}</div>
            <div className="card resolve"><div className="tag-title">RESOLUTION</div><div className="form-grid"><label>Confirmed root cause<input value={cause} onChange={event => setCause(event.target.value)} placeholder="Confirmed cause"/></label><label>Resolution time (minutes)<input type="number" value={minutes} onChange={event => setMinutes(event.target.value)} placeholder="27"/></label><label className="full">Resolution<textarea value={resolution} onChange={event => setResolution(event.target.value)} placeholder="What resolved the incident?"/></label></div><button className="button secondary" onClick={() => void resolve()} disabled={busy || !cause || !resolution || !minutes}>Resolve + retain final outcome</button>{selected?.status === 'resolved' && <span className="learning">✓ Outcome retained into Hindsight</span>}</div>
            <div className="demo-next"><div><b>Continue the learning loop</b><span>Create a later similar incident to check whether this result is recalled.</span></div><button className="button secondary" onClick={() => void laterSimilar()} disabled={busy}>＋ Later similar incident</button><button className="button secondary" onClick={() => setScreen('postmortem')} disabled={busy}>Draft postmortem</button></div>
          </>}
        </section>
        <aside className="evidence-col"><div className="evidence-sticky"><div className="evidence-header"><div className="memory-icon">◉</div><div><div className="eyebrow">PERSISTENT MEMORY</div><h2>Hindsight evidence</h2></div></div><div className="memory-status"><span className={health?.hindsight_configured ? 'dot green' : 'dot amber'}/>{health?.hindsight_configured ? 'Hindsight credentials configured' : 'Configure HINDSIGHT_API_KEY'}</div>
          {!analysis ? <div className="memory-placeholder"><div className="placeholder-orbit">◉</div><b>Memory evidence appears here</b><p>Analyze an incident to query Hindsight. Each result shown here comes from its recall response.</p></div> : <>
            <div className="recall-count">{analysis.memory_stats.recalled} recalled · {analysis.memory_stats.selected_for_reasoning} selected for reasoning <span>{analysis.recommendation.evidence_memory_ids.length} cited</span></div>
            {analysis.evidence.length === 0 ? <div className="no-memory"><div>⌕</div><b>No useful history found</b><p>Recommendations use current incident facts only. Seed synthetic history after the baseline walkthrough.</p></div> : analysis.evidence.map((memory, index) => <div className="memory-card" key={`${memory.incident_id}-${index}`}><div className="memory-card-top"><span className="memory-id">{memory.incident_id || 'Hindsight memory'}</span><span className="relevance">{memory.relevance != null ? `${Number(memory.relevance).toFixed(2)} relevance` : 'recalled'}</span></div><div className="memory-meta">{memory.date ? new Date(memory.date).toLocaleDateString() : ''} · {memory.service}</div><p>{memory.text}</p><div className="outcomes"><b>Interventions in source</b>{/successful/i.test(memory.text) && <span className="success">✓ Successful intervention described</span>}{/failed/i.test(memory.text) && <span className="failed">× Failed intervention described</span>}</div></div>)}
            <div className="used-evidence"><div className="tag-title">USED IN RECOMMENDATION <span>{analysis.recommendation.evidence_memory_ids.length} cited</span></div>{analysis.recommendation.evidence_memory_ids.length ? <><p>Based on recalled Hindsight memory:</p>{analysis.recommendation.evidence_memory_ids.map(id => { const memory = analysis.evidence.find(item => item.incident_id === id); const citation = analysis.recommendation.memory_evidence.find(item => item.incident_id === id); const text = memory?.text || citation?.outcome_summary || ''; return <div className="used-row" key={id}><b>• {id}</b>{citation?.reason && <small>{citation.reason}</small>}<small>{compactEvidence(text) || 'Selected Hindsight memory; no display text was returned.'}</small></div>; })}</> : <p className="muted">No recalled memory was cited by the recommendation.</p>}</div>
          </>}
          <div className="memory-loop"><div className="loop-title">THE LEARNING LOOP</div><div className="loop"><span className="loop-done">RETAIN</span><i>→</i><span className={analysis ? 'loop-done' : ''}>RECALL</span><i>→</i><span>REASON</span><i>→</i><span>OUTCOME</span><i>→</i><span>RETAIN</span></div></div>
        </div></aside>
      </div>}
      <footer>INCIDENTIQ · SYNTHETIC DATA ONLY <span>Recommendations support engineer judgment. No production systems connected.</span></footer>
    </main>
  </div>;
}
