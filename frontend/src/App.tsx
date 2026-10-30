import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ArrowDownToLine, ArrowRight, ArrowUp, BadgeCheck, BookOpen, Check, CheckCheck, ChevronDown, ChevronRight, CircleHelp, Clock3, FileCheck2, FileText, FolderOpen, History, LayoutDashboard, LoaderCircle, MoreHorizontal, Plus, Search, ShieldCheck, Sparkles, Trash2, Upload, X, AlertCircle, ExternalLink, PanelLeftClose, Menu, Pencil, CheckCircle2, FlaskConical, Landmark, UserRound } from 'lucide-react'
import { api, labels, statusLabels, type Application, type Health, type Summary, type Kind, type Clause, type Field, type IssuedPolicy, type CashlessDetails } from './api'
import { JourneyStart, ExistingPolicyCard } from './JourneyStart'
import { CashlessJourney } from './CashlessJourney'
import { ClaimAcknowledgement, ClaimTracker } from './ClaimTracker'
import { EligibilityPanel } from './EligibilityPanel'
import { CustomerHub, type CustomerProfile } from './CustomerHub'
import { DEMO_APPLICANTS, type DemoApplicant } from './demoApplicants'

type View = 'profile' | 'overview' | 'documents' | 'review' | 'activity' | 'tracking'
type DemoIdentity = DemoApplicant
const descriptions: Record<Kind, string> = { policy: 'Your policy number and coverage period', bill: 'Itemized expenses from your hospital', discharge: 'Your treatment and hospital stay details', bank_proof: 'Account proof for reimbursement', admission_advice: 'Hospital admission advice and treatment details', cost_estimate: 'The hospital’s estimated treatment expenses', clarification: 'Additional information requested by the simulated insurer' }
const money = (v: string) => { const n = Number(v.replace(/,/g, '')); return v && Number.isFinite(n) ? new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(n) : '—' }

function Brand({ small = false }: { small?: boolean }) {
  return <div className={`brand ${small ? 'small' : ''}`}><div className="brand-symbol"><span/><span/></div><span>OneFlow<span className="brand-ai">AI</span></span></div>
}

function AuthScreen({ onSignIn }: { onSignIn: (user: DemoIdentity) => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  function submit(event: FormEvent) {
    event.preventDefault()
    const applicant = DEMO_APPLICANTS.find(item => item.profile.email.toLowerCase() === email.trim().toLowerCase() && item.password === password)
    if (!applicant) { setError('Use one of the applicant credentials below.'); return }
    onSignIn(applicant)
  }
  return <div className="modal-backdrop auth-backdrop"><section className="modal auth-card" role="dialog" aria-modal="true" aria-labelledby="auth-title">
    <Brand />
    <span className="eyebrow">YOUR INSURANCE ACCOUNT</span>
    <h2 id="auth-title">Welcome to your insurance space</h2>
    <p>Sign in as a sample applicant to view their saved profile and policy details. This is browser sign-in for this workspace only.</p>
    <form onSubmit={submit} className="auth-form">
      <label htmlFor="demo-email">Email address</label><input id="demo-email" type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="priya@example.com" autoComplete="email" />
      <label htmlFor="demo-password">Password</label><input id="demo-password" type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="Password" autoComplete="current-password" />
      {error && <p className="error-banner" role="alert">{error}</p>}
      <button className="button button-dark auth-submit" type="submit">Continue <ArrowRight size={16}/></button>
    </form>
    <small className="auth-note">Example sign-in for this workspace. No external account is created.</small>
    <div className="demo-credentials"><strong>Applicants</strong>{DEMO_APPLICANTS.map(item => <button key={item.id} type="button" onClick={() => { setEmail(item.profile.email); setPassword(item.password) }}>{item.profile.name} · {item.profile.email}</button>)}</div>
  </section></div>
}

export default function App() {
  const [signedInUser, setSignedInUser] = useState<DemoIdentity | null>(() => {
    try {
      const stored = JSON.parse(localStorage.getItem('oneflow-demo-user') || 'null')
      return stored?.profile && stored?.policies ? stored as DemoIdentity : null
    } catch { return null }
  })
  const [health, setHealth] = useState<Health | null>(null)
  const [application, setApplication] = useState<Application | null>(null)
  const [applications, setApplications] = useState<Summary[]>([])
  const [view, setView] = useState<View>('overview')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [chatOpen, setChatOpen] = useState(false)
  const [demoOpen, setDemoOpen] = useState(false)
  const [startOpen, setStartOpen] = useState(false)
  const [policies, setPolicies] = useState<IssuedPolicy[]>([])
  const [profile, setProfile] = useState<CustomerProfile | null>(null)
  const [policyOpen, setPolicyOpen] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [clauses, setClauses] = useState<Clause[]>([])
  const [activeClause, setActiveClause] = useState('')
  const [uploadKind, setUploadKind] = useState<Kind>('policy')
  const [replaceExisting, setReplaceExisting] = useState(false)
  const [confirmReview, setConfirmReview] = useState(false)
  const [question, setQuestion] = useState('')
  const [search, setSearch] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)
  const chatEnd = useRef<HTMLDivElement>(null)
  const initialized = useRef(false)

  async function refreshList() { setApplications(await api<Summary[]>('/applications')) }
  function apply(record: Application) {
    setApplication(record); localStorage.setItem('oneflow-application', record.id); setConfirmReview(false)
    if (record.policy_context) setClauses(record.policy_context.clauses)
    if (application?.id !== record.id) setUploadKind(record.journey === 'cashless' ? 'admission_advice' : record.issued_policy ? 'bill' : 'policy')
  }
  async function action(label: string, fn: () => Promise<void>) {
    if (busy) return
    setBusy(label); setError('')
    try { await fn() } catch (e) { setError(e instanceof Error ? e.message : 'Something went wrong. Please retry.') } finally { setBusy('') }
  }
  useEffect(() => {
    if (initialized.current) return
    if (!signedInUser) return
    initialized.current = true
    void action('Loading your workspace', async () => {
      const results = await Promise.allSettled([api<Health>('/health'), api<Summary[]>('/applications'), api<{ clauses: Clause[] }>('/policy'), api<{ policies: IssuedPolicy[] }>('/customer/policies'), api<{ profile: CustomerProfile }>('/customer/profile')])
      const healthResult = results[0]
      const applicationsResult = results[1]
      if (healthResult.status === 'rejected' || applicationsResult.status === 'rejected') throw new Error('The OneFlow service is unavailable. Please restart the local backend and try again.')
      const h = healthResult.value
      const list = applicationsResult.value
      const policy = results[2].status === 'fulfilled' ? results[2].value : { clauses: [] }
      const customer = results[3].status === 'fulfilled' ? results[3].value : { policies: [] }
      const profileResponse = results[4].status === 'fulfilled' ? results[4].value : { profile: signedInUser.profile }
      setHealth(h); setApplications(list); setClauses(policy.clauses); setPolicies(customer.policies)
      setPolicies(signedInUser.policies)
      setProfile({ ...profileResponse.profile, ...signedInUser.profile })
      const saved = localStorage.getItem('oneflow-application')
      const id = list.find(a => a.id === saved)?.id || list[0]?.id
      apply(id ? await api<Application>(`/applications/${id}`) : await api<Application>('/applications', { method: 'POST', body: JSON.stringify({ title: 'My reimbursement claim' }) }))
      if (!id) setView('profile')
      await refreshList()
    })
  }, [signedInUser])
  useEffect(() => { chatEnd.current?.scrollIntoView({ behavior: 'smooth' }) }, [application?.messages.length, chatOpen])
  useEffect(() => { if (notice) { const timer = setTimeout(() => setNotice(''), 5000); return () => clearTimeout(timer) } }, [notice])
  useEffect(() => {
    function escape(e: KeyboardEvent) { if (e.key === 'Escape') { setDemoOpen(false); setStartOpen(false); setPolicyOpen(false); setChatOpen(false); setSidebarOpen(false) } }
    window.addEventListener('keydown', escape); return () => window.removeEventListener('keydown', escape)
  }, [])

  const blockers = application?.issues.filter(i => i.severity === 'error') || []
  const warnings = application?.issues.filter(i => i.severity === 'warning') || []
  const isCashless = application?.journey === 'cashless'
  const kinds: Kind[] = isCashless ? ['admission_advice', 'cost_estimate', ...(['authorized', 'discharge_review'].includes(application?.cashless?.status || '') ? ['bill', 'discharge'] as Kind[] : [])] : ['policy', 'bill', 'discharge', 'bank_proof']
  const uploadKinds = kinds.filter(k => !(application?.issued_policy && k === 'policy'))
  const completedDocs = application?.documents.filter(d => kinds.includes(d.kind)).length || 0
  const firstName = application?.fields.full_name?.value.split(' ')[0]
  const missingKind = kinds.find(k => !application?.documents.some(d => d.kind === k))
  const isReady = application?.status === 'ready'
  const canReview = application && blockers.length === 0
  const docs = application?.documents.filter(d => (d.name + labels[d.kind]).toLowerCase().includes(search.toLowerCase())) || []
  const uploadedPolicy = application?.documents.find(d => d.kind === 'policy')

  async function newApplication() {
    setStartOpen(true); setSidebarOpen(false)
  }
  function signOut() {
    localStorage.removeItem('oneflow-demo-user')
    localStorage.removeItem('oneflow-application')
    initialized.current = false
    setApplication(null)
    setSignedInUser(null)
  }
  async function startJourney(journey: 'cashless' | 'reimbursement', policy: string, member: string) {
    await action('Loading your policy and starting the journey', async () => {
      const selectedPolicy = policies.find(item => item.id === policy)
      apply(await api<Application>('/applications', { method: 'POST', body: JSON.stringify({ title: journey === 'cashless' ? 'My cashless assistance' : 'My reimbursement claim', journey, issued_policy_id: selectedPolicy?.id, issued_policy: selectedPolicy, member_id: member }) }))
      await refreshList(); setView('overview'); setStartOpen(false); setNotice('Your existing policy is loaded. Let’s prepare the next step.')
    })
  }
  async function startPolicyUpload() {
    await action('Opening a policy upload journey', async () => {
      apply(await api<Application>('/applications', { method: 'POST', body: JSON.stringify({ title: 'Add a different policy', journey: 'reimbursement' }) }))
      await refreshList(); setView('documents'); setStartOpen(false); setNotice('Upload the policy schedule and claim documents for this separate journey.')
    })
  }
  async function saveCashlessDetails(details: CashlessDetails) {
    if (!application) return
    await action('Saving admission details', async () => {
      apply(await api<Application>(`/applications/${application.id}/cashless/details`, { method: 'PUT', body: JSON.stringify(details) })); await refreshList(); setNotice('Admission details saved. Preparation checks updated.')
    })
  }
  async function simulateCashless(actionName: string, clarification = '') {
    if (!application) return
    await action('Updating the cashless simulation', async () => {
      apply(await api<Application>(`/applications/${application.id}/cashless/simulate`, { method: 'POST', body: JSON.stringify({ action: actionName, clarification }) })); await refreshList(); setNotice('Simulation updated. No request was sent to an insurer.')
    })
  }
  async function loadDemo(scenario: string) {
    await action('Preparing sample case', async () => {
      let target = application
      if (!target || target.documents.length || Object.values(target.fields).some(f => f.confirmed)) target = await api<Application>('/applications', { method: 'POST', body: JSON.stringify({ title: `${scenario === 'complete' ? 'Complete' : scenario === 'conflict' ? 'Conflicting details' : 'Missing document'} · Sample claim` }) })
      apply(await api<Application>(`/applications/${target.id}/demo`, { method: 'POST', body: JSON.stringify({ scenario }) })); await refreshList(); setDemoOpen(false); setView('overview'); setNotice('Sample case loaded.')
    })
  }
  function chooseUpload(kind?: Kind, replace?: boolean) { if (replace !== undefined) setReplaceExisting(replace); setUploadKind(kind || missingKind || 'policy'); fileRef.current?.click() }
  async function uploadFile(file: File | undefined) {
    if (!file || !application) return
    await action('Reading and checking your document', async () => {
      const form = new FormData(); form.append('kind', uploadKind); form.append('replace', String(replaceExisting)); form.append('file', file)
      apply(await api<Application>(`/applications/${application.id}/documents`, { method: 'POST', body: form })); await refreshList(); setNotice(`${labels[uploadKind]} processed. Your checklist is up to date.`)
    })
    if (fileRef.current) fileRef.current.value = ''
  }
  async function correctField(key: string, value: string) {
    if (!application) return
    await action('Saving verified detail', async () => { apply(await api<Application>(`/applications/${application.id}/fields/${key}`, { method: 'PATCH', body: JSON.stringify({ value }) })); await refreshList(); setNotice('Detail confirmed. Validation has been rerun.') })
  }
  async function sendQuestion(text: string) {
    if (!text.trim() || !application) return
    setChatOpen(true)
    await action('Finding a grounded answer', async () => { apply(await api<Application>(`/applications/${application.id}/messages`, { method: 'POST', body: JSON.stringify({ text }) })); setQuestion('') })
  }
  function showClause(id?: string) { setActiveClause(id || ''); setPolicyOpen(true) }
  async function exportPacket() {
    if (!application) return
    await action('Preparing your packet', async () => {
      const response = await fetch(`/api/applications/${application.id}/export`)
      if (!response.ok) { const data = await response.json(); throw new Error(data.detail) }
      const url = URL.createObjectURL(await response.blob()); const link = document.createElement('a'); link.href = url; link.download = `oneflow-claim-${application.id.slice(0, 8)}.zip`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); apply(await api<Application>(`/applications/${application.id}`)); setNotice('Your reviewed claim packet has been downloaded.')
    })
  }
  async function submitClaim(consent: boolean) {
    if (!application) return
    await action('Submitting reviewed claim', async () => { apply(await api<Application>(`/applications/${application.id}/submit`, { method: 'POST', body: JSON.stringify({ consent }) })); await refreshList(); setView('tracking'); setNotice('Claim submitted to the simulated insurer. No real claim was sent.') })
  }
  async function respondClarification(response: string) {
    if (!application) return
    await action('Resubmitting clarification', async () => { apply(await api<Application>(`/applications/${application.id}/claim/clarification`, { method: 'POST', body: JSON.stringify({ response }) })); await refreshList(); setNotice('Clarification resubmitted to the simulated insurer.') })
  }

  if (!signedInUser) return <AuthScreen onSignIn={user => { localStorage.setItem('oneflow-demo-user', JSON.stringify(user)); setSignedInUser(user) }} />

  return <div className="app-shell">
    <input ref={fileRef} type="file" accept=".pdf,.png,.jpg,.jpeg" hidden onChange={e => void uploadFile(e.target.files?.[0])}/>
    {sidebarOpen && <div className="mobile-overlay" onClick={() => setSidebarOpen(false)}/>}
    <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
      <Brand/>
      <div className="workspace-selector"><div className="workspace-icon"><Landmark size={17}/></div><div><strong>My insurance</strong><span>Policies and claims</span></div><ChevronDown size={14}/></div>
      <span className="nav-label">WORKSPACE</span>
      <nav aria-label="Main navigation">
        {([{ id: 'profile', label: 'My profile & policies', icon: UserRound }, { id: 'overview', label: 'Current journey', icon: LayoutDashboard }, { id: 'documents', label: 'My documents', icon: FolderOpen }, { id: 'review', label: 'Review details', icon: FileCheck2 }, { id: 'tracking', label: 'Claim tracking', icon: ShieldCheck }, { id: 'activity', label: 'Activity', icon: History }] as const).filter(item => item.id === 'profile' || ((!isCashless || item.id !== 'review') && (!isCashless || item.id !== 'tracking' || !!application?.claim))).map(item => <button key={item.id} className={`nav-item ${view === item.id ? 'active' : ''}`} onClick={() => { setView(item.id); setSidebarOpen(false) }}><item.icon size={18}/>{item.label}{item.id === 'documents' && <span className="nav-count">{completedDocs}</span>}{item.id === 'review' && blockers.length > 0 && completedDocs > 0 && <span className="nav-dot"/>}</button>)}
      </nav>
      <div className="journeys-label"><span className="nav-label">YOUR JOURNEYS</span><button className="icon-button" aria-label="Create a new claim" onClick={() => void newApplication()} disabled={!!busy}><Plus size={15}/></button></div>
      <div className="journey-list">{applications.map(a => <button key={a.id} className={`journey-item ${application?.id === a.id ? 'selected' : ''}`} title={a.title} disabled={!!busy} onClick={() => void action('Opening claim', async () => { apply(await api<Application>(`/applications/${a.id}`)); setView('overview'); setSidebarOpen(false) })}><span className={`tiny-dot ${a.status === 'ready' ? 'green' : ''}`}/><span>{a.title}</span></button>)}</div>
      <button className="new-journey" onClick={() => void newApplication()} disabled={!!busy}><Plus size={16}/> Start claim</button>
      <div className="sidebar-bottom"><div className="support-card"><div className="support-icon"><Sparkles size={18}/></div><strong>A little clarity goes a long way.</strong><p>Understand the fine print. Take the next step with confidence.</p><button onClick={() => setChatOpen(true)}>Meet your assistant <ArrowRight size={14}/></button></div><button className="policy-nav" onClick={() => showClause()}><BookOpen size={17}/> Policy knowledge <ExternalLink size={13}/></button><div className="profile"><div className="avatar">{firstName?.[0] || signedInUser.profile.name[0] || 'Y'}</div><div><strong>{firstName ? `${firstName}'s workspace` : `${signedInUser.profile.name}'s workspace`}</strong><span>{signedInUser.profile.email}</span></div><ShieldCheck size={17}/></div><button className="policy-nav" onClick={signOut}>Sign out</button></div>
    </aside>

    <div className="main-column">
      <header className="topbar"><div className="breadcrumbs"><button className="mobile-menu icon-button" onClick={() => setSidebarOpen(true)} aria-label="Open navigation"><Menu size={20}/></button><span>My insurance</span><ChevronRight size={13}/><strong>Dashboard</strong></div><div className="topbar-right"><span className="saved-label"><span className="tiny-dot green"/>{busy ? 'Working on it…' : 'Saved'}</span><button className="icon-button help-button" onClick={() => setChatOpen(true)} aria-label="Ask for help"><CircleHelp size={20}/></button><div className="top-avatar">{firstName?.[0] || 'Y'}</div></div></header>
      <main>
        <div className="page-heading"><div><div className="eyebrow"><span/> YOUR HEALTH INSURANCE</div><h1>{view === 'overview' && isCashless ? 'A little less worry. A clearer next step.' : view === 'overview' ? (firstName ? `Let's take the next step, ${firstName}.` : 'A clearer path to your claim.') : view === 'documents' ? 'Your paperwork, in one place.' : view === 'review' ? 'Review your claim details' : 'Your health insurance'}</h1><p>{view === 'overview' && isCashless ? 'Prepare for hospital admission with your existing health policy.' : view === 'overview' ? 'From paperwork to prepared. We’ll guide you through the details.' : view === 'documents' ? 'Upload, check, and manage the documents behind your claim.' : view === 'review' ? 'Check extracted information against its source before you confirm.' : 'Manage your policy and claims in one place.'}</p></div></div>

        <div className="mode-banner"><div><FlaskConical size={15}/><span><strong>Your claim workspace</strong><span className="banner-divider">/</span>Policy and documents in one place</span></div><div className="mode-actions"><button className="upload-policy-action" title="Upload a policy" aria-label="Upload a policy" onClick={() => void startPolicyUpload()} disabled={!!busy}><Upload size={13}/> Upload policy</button>{uploadedPolicy && <button title="View uploaded policy" aria-label="View uploaded policy" onClick={() => showClause()}>View policy <ArrowRight size={13}/></button>}</div></div>
        {health?.mode === 'cloud' && !health.cloud_configured && <div className="error-banner"><AlertCircle size={18}/><span>Cloud setup incomplete: {health.missing_configuration.join(', ')}. See backend/.env.example.</span></div>}
        {error && <div role="alert" className="error-banner"><AlertCircle size={18}/><span>{error}</span><button className="icon-button" onClick={() => setError('')} aria-label="Dismiss error"><X size={16}/></button><button className="text-button" onClick={() => window.location.reload()}>Retry workspace</button></div>}

        {!application ? <div className="loading-state"><LoaderCircle className="spin" size={28}/><h3>Preparing your workspace</h3><p>{error ? 'Resolve the connection issue above to continue.' : 'Getting everything in place for your next step.'}</p></div> : <>
          {view === 'profile' && profile && <CustomerHub profile={profile} policies={policies} busy={!!busy} onStart={() => void newApplication()} onAddPolicy={() => void startPolicyUpload()} onViewPolicy={() => showClause()}/>} 
          {view !== 'profile' && application.issued_policy && <ExistingPolicyCard policy={application.issued_policy} memberId={application.member_id} onView={() => showClause()}/>}
          {!isCashless && view === 'review' && <EligibilityPanel eligibility={application.eligibility} onPolicy={showClause}/>} 
          {isCashless && application.claim && <ClaimAcknowledgement claim={application.claim}/>} 
          {!isCashless && view === 'review' && application.status === 'ready' && <ClaimTracker application={application} busy={!!busy} onSubmit={submitClaim} onUploadClarification={() => chooseUpload('clarification')} onRespond={respondClarification}/>} 
          {isCashless && (view === 'overview' || view === 'review') && <CashlessJourney key={application.id} application={application} busy={!!busy} onUpdate={saveCashlessDetails} onAction={simulateCashless} onUpload={chooseUpload} onPolicy={showClause} onAsk={text => void sendQuestion(text)}/>}
          {view === 'overview' && !isCashless && <>
            <section className="journey-card"><div className="journey-summary"><div className="claim-symbol"><ShieldCheck size={27}/></div><div className="claim-title"><div className="claim-type">HEALTH INSURANCE <span>REIMBURSEMENT</span></div><h2>{application.title}</h2><p>{application.fields.policy_number?.value || 'Policy not added yet'}<span>·</span>Individual claim</p></div><span className={`status-pill ${isReady ? 'ready' : ''}`}><span/>{statusLabels[application.status]}</span><button className="icon-button" aria-label="View claim activity" onClick={() => setView('activity')}><MoreHorizontal size={20}/></button></div>
              <div className="journey-progress"><div className="progress-heading"><span>Your journey to a prepared claim</span><strong>{application.progress}<span>% complete</span></strong></div><div className="progress-track"><div style={{ width: `${application.progress}%` }}/></div><div className="journey-steps">{[{ label: 'Get started', done: true }, { label: 'Add documents', done: completedDocs === 4 }, { label: 'Review details', done: isReady }, { label: 'Prepare packet', done: isReady }].map((s, i) => <div className={`journey-step ${s.done ? 'done' : ''} ${i === (completedDocs < 4 ? 1 : !isReady ? 2 : 3) ? 'current' : ''}`} key={s.label}><span>{s.done ? <Check size={12}/> : i + 1}</span>{s.label}</div>)}</div></div>
            </section>

            <div className="overview-grid"><div className="content-stack">
              <section className="next-step-card"><div className="next-step-top"><span className="section-kicker"><span className="pulse-dot"/> YOUR NEXT BEST STEP</span><span className="time-hint"><Clock3 size={13}/> About 2 minutes</span></div><div className="next-step-body"><div><h2>{missingKind ? `Add your ${labels[missingKind].toLowerCase()}` : blockers.length ? 'Let’s clear up a few details' : isReady ? 'Your claim packet is prepared' : 'Make it yours. Give it a final review.'}</h2><p>{missingKind ? descriptions[missingKind] + '. We’ll extract the important details and check them for you.' : blockers.length ? 'We spotted information that needs your attention. Compare the original sources and confirm the correct details.' : isReady ? 'Your details are reviewed and the checklist is complete. Download your packet for the next step with your insurer.' : 'Your documents are in place. Check the extracted details, then confirm to prepare your claim packet.'}</p><button className="button button-dark" disabled={!!busy} onClick={() => missingKind ? chooseUpload(missingKind) : isReady ? void exportPacket() : setView('review')}>{missingKind ? <Upload size={16}/> : isReady ? <ArrowDownToLine size={16}/> : <FileCheck2 size={16}/>}{missingKind ? 'Upload document' : isReady ? 'Download claim packet' : 'Review claim details'}<ArrowRight size={16}/></button></div><div className="document-illustration" aria-hidden="true"><div className="illustration-back"/><div className="illustration-paper"><div className="paper-icon"><FileText size={23}/></div><span/><span/><span/><div className="paper-stamp"><Check size={16}/></div></div><span className="illustration-spark">✦</span></div></div><div className="next-step-footer"><ShieldCheck size={14}/>{health?.mode === 'cloud' ? 'Your document details are ready to review'  : 'Your originals stay linked to every extracted detail'}</div></section>

              <section className="white-card documents-card"><div className="section-heading"><h2>Your documents <span className="counter">{completedDocs}/{kinds.length}</span></h2><button className="text-button" onClick={() => setView('documents')}>Manage documents <ArrowRight size={14}/></button></div><div className="document-checklist">{kinds.map(kind => { const doc = application.documents.find(d => d.kind === kind); return <div className={`checklist-row ${doc ? 'complete' : ''}`} key={kind}><div className={`doc-icon ${doc ? 'mint' : ''}`}><FileText size={19}/></div><div className="checklist-info"><strong>{labels[kind]}</strong><span>{doc ? `${doc.page_count} page${doc.page_count > 1 ? 's' : ''} · Details extracted` : descriptions[kind]}</span></div>{doc ? <><span className="document-done"><CheckCircle2 size={15}/> Added</span><button disabled={!!busy} className="small-upload" onClick={() => chooseUpload(kind, true)}><Upload size={13}/> Replace</button></> : <button disabled={!!busy} className="small-upload" onClick={() => chooseUpload(kind, false)}><Plus size={14}/> Add document</button>}</div> })}</div><div className="card-footnote"><CircleHelp size={13}/> PDF, JPG, or PNG · Up to 10 MB per document{health?.mode === 'demo' ? ' · Scanned images need cloud mode' : ''}</div></section>

              <section className="insight-strip"><div className="insight-icon"><BookOpen size={20}/></div><div><strong>A little understanding. A lot less uncertainty.</strong><p>Every requirement connects back to your policy. See the why behind each step.</p></div><button className="icon-button" onClick={() => showClause()} aria-label="Read the policy"><ArrowRight size={20}/></button></section>
            </div><div className="right-stack">
              <section className="assistant-card"><div className="assistant-heading"><span className="ai-icon"><Sparkles size={20}/></span><div><h2>Your OneFlow assistant</h2><span><span className="tiny-dot green"/> Here to help you move forward</span></div><span className="ai-badge">AI</span></div><div className="assistant-message"><p>{completedDocs ? `I've checked ${completedDocs} of your documents. ${missingKind ? `Next, we need your ${labels[missingKind].toLowerCase()}.` : blockers.length ? 'A few details need a second look.' : 'Everything on the checklist is accounted for.'}` : 'Hi there! I’m here to make your claim a little simpler.'}</p><p>{completedDocs ? 'You can ask me why a document is needed or what to do next.' : 'Add your documents, and I’ll help you understand what’s needed, spot missing details, and get your packet ready.'}</p><span className="grounded-label"><ShieldCheck size={12}/> Linked to this journey’s policy sources</span></div><div className="suggested-questions">{['What documents do I need?', 'How are my details checked?', 'What does packet ready mean?'].map(q => <button key={q} disabled={!!busy} onClick={() => void sendQuestion(q)}>{q}<ArrowUp size={13}/></button>)}</div><button className="assistant-input" onClick={() => setChatOpen(true)}><span>Ask anything about your claim…</span><span><ArrowUp size={16}/></span></button><p className="ai-footnote">AI can make mistakes. Always review important details.</p></section>
              <section className="snapshot-card"><div className="section-heading"><h2>At a glance</h2><span className="small-muted">THIS CLAIM</span></div><div className="snapshot-row"><span>Documents added</span><strong>{completedDocs} <span>/ {kinds.length}</span></strong></div><div className="snapshot-row"><span>Details extracted</span><strong>{Object.values(application.fields).filter(f => f.value).length}</strong></div><div className="snapshot-row"><span>Items to resolve</span><strong className={blockers.length ? 'amber-text' : 'teal-text'}>{blockers.length ? blockers.length : <><Check size={14}/> All clear</>}</strong></div><div className="snapshot-total"><span>Hospital bill total</span><strong>{money(application.fields.bill_total?.value || '')}</strong><small>Extracted amount · Subject to insurer review</small></div></section>
              <div className="trust-note"><ShieldCheck size={18}/><p><strong>You’re always in control.</strong><br/>Nothing is submitted to an insurer. Review and confirm before exporting.</p></div>
            </div></div>
          </>}

          {view === 'documents' && <><section className="white-card document-workspace"><div className="section-heading"><div><h2>Claim documents <span className="counter">{completedDocs}/{kinds.length}</span></h2><p className="muted">Add more than one document for each type when needed. New uploads stay with existing evidence unless you choose to replace them.</p></div><div className="upload-controls"><label className="sr-only" htmlFor="doc-kind">Document type</label><select id="doc-kind" value={uploadKind} onChange={e => setUploadKind(e.target.value as Kind)}>{uploadKinds.map(k => <option key={k} value={k}>{labels[k]}</option>)}</select><label className="replace-toggle"><input type="checkbox" checked={replaceExisting} onChange={e => setReplaceExisting(e.target.checked)}/> Replace all of this type</label><button className="button button-dark" disabled={!!busy} onClick={() => chooseUpload(uploadKind)}><Upload size={15}/> Upload</button></div></div><div className="dropzone" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); if (!busy) void uploadFile(e.dataTransfer.files[0]) }}><div className="upload-circle"><Upload size={25}/></div><h3>Drop your {labels[uploadKind].toLowerCase()} here</h3><p>or <button className="inline-link" disabled={!!busy} onClick={() => chooseUpload(uploadKind)}>browse files</button> on your device</p><span>PDF, JPG, PNG · Max 10 MB · {health?.mode === 'demo' ? 'Text-based PDF processing' : ('Read by ' + (health?.provider === 'sarvam' ? 'Sarvam AI' : 'Google Cloud'))}</span></div><div className="document-toolbar"><h3>Uploaded documents</h3><label className="search-field"><Search size={16}/><input placeholder="Find a document" value={search} onChange={e => setSearch(e.target.value)}/></label></div>{docs.length === 0 ? <div className="empty-state"><FolderOpen size={30}/><h3>{search ? 'No documents match your search' : 'A fresh start for your paperwork'}</h3><p>{search ? 'Try a different name or document type.' : 'Upload your first document above, or explore a sample case.'}</p></div> : docs.map(doc => <div className="file-row" key={doc.id}><div className="doc-icon mint"><FileText size={22}/></div><div className="file-details"><strong>{doc.name}</strong><span>{labels[doc.kind]} · {Math.max(1, Math.round(doc.size / 1024))} KB · {doc.page_count} page(s)</span><small>{doc.provider}</small></div><span className="document-done"><CheckCircle2 size={15}/> Extracted</span><a className="icon-button" href={`/api/applications/${application.id}/documents/${doc.id}/file`} target="_blank" rel="noreferrer" aria-label={`View ${doc.name}`}><ExternalLink size={17}/></a>{!doc.preloaded && <button className="icon-button delete-button" disabled={!!busy} aria-label={`Remove ${doc.name}`} onClick={() => void action('Removing document', async () => { apply(await api<Application>(`/applications/${application.id}/documents/${doc.id}`, { method: 'DELETE' })); await refreshList() })}><Trash2 size={17}/></button>}</div>)}</section><section className="sample-downloads"><div><FlaskConical size={20}/><div><h3>Need documents to try it out?</h3><p>Use example documents if you need help getting started.</p></div></div><div>{uploadKinds.map(k => <a href={`/api/samples/${k}`} key={k}><ArrowDownToLine size={13}/>{labels[k]}</a>)}</div></section></>}

          {view === 'review' && !isCashless && <div className="review-layout"><div className="content-stack"><section className="white-card"><div className="section-heading"><div><h2>Extracted claim details</h2><p className="muted">Open a field to compare evidence and confirm or correct its value.</p></div><BadgeCheck size={22} className="teal-text"/></div><div className="fields-list">{Object.values(application.fields).filter(field => !['estimated_amount', 'treatment_summary'].includes(field.key)).map(field => <FieldEditor key={`${application.id}-${field.key}-${field.value}-${field.confirmed}`} field={field} busy={!!busy} hasIssue={blockers.some(i => i.field === field.key)} onSave={value => void correctField(field.key, value)} readOnly={!!application.issued_policy && ['full_name', 'policy_number', 'policy_start', 'policy_end'].includes(field.key)} documentUrl={id => `/api/applications/${application.id}/documents/${id}/file`}/>)}</div></section><section className="white-card review-confirmation"><div className="review-icon"><ShieldCheck size={25}/></div><h2>{isReady ? 'Reviewed. Prepared. Ready for your next step.' : 'One last check, then you’re ready.'}</h2><p>Your preliminary packet includes a summary, original documents, field evidence, and review history. These checks cover the core preparation steps. Review the insurer’s full document list and conditional requirements before actual submission.</p>{isReady ? <><div className="reviewed-note"><CheckCheck size={16}/> Reviewed {new Date(application.reviewed_at!).toLocaleString('en-IN')}</div><button className="button button-dark" disabled={!!busy} onClick={() => void exportPacket()}><ArrowDownToLine size={17}/> Download claim packet</button></> : <><label className="review-checkbox"><input type="checkbox" checked={confirmReview} disabled={!canReview || !!busy} onChange={e => setConfirmReview(e.target.checked)}/><span>I have reviewed all details and any source discrepancies. I confirm the values shown are correct for this preparation packet.</span></label><button className="button button-dark" disabled={!canReview || !confirmReview || !!busy} onClick={() => void action('Confirming your review', async () => { apply(await api<Application>(`/applications/${application.id}/review`, { method: 'POST' })); await refreshList(); setNotice('Review confirmed. Your packet is ready to download.') })}><CheckCheck size={17}/> Confirm review & prepare packet</button>{!canReview && <span className="small-muted">Resolve the blocking items before confirming.</span>}</>}</section></div><aside className="review-issues"><section className="white-card"><div className="section-heading"><h2>Readiness checks</h2><span className="counter">{blockers.length}</span></div>{!blockers.length && <div className="all-clear"><CheckCircle2 size={28}/><h3>All checks passed</h3><p>The required documents and details are present.</p></div>}{blockers.map(i => <div className="issue" key={i.code}><AlertCircle size={17}/><div><strong>{i.message}</strong><button onClick={() => showClause(i.clause_id)}>Why is this needed? <ArrowRight size={12}/></button></div></div>)}{warnings.map(i => <div className="issue warning" key={i.code}><CircleHelp size={17}/><div><strong>{i.message}</strong><button onClick={() => showClause(i.clause_id)}>Review source rule <ArrowRight size={12}/></button></div></div>)}</section><div className="trust-note"><ShieldCheck size={18}/><p>Confirming a corrected value preserves the original sources and adds a review note to your export.</p></div></aside></div>}

          {view === 'activity' && <section className="white-card activity-card"><div className="section-heading"><h2>Your journey history</h2><span className="small-muted">REVISION {application.revision}</span></div>{!application.audit.length ? <div className="empty-state"><History size={30}/><h3>Your story starts here</h3><p>Add a document to see your journey take shape.</p></div> : <div className="timeline">{[...application.audit].reverse().map((event, i) => <div className="timeline-event" key={`${event.at}-${i}`}><div className="timeline-icon">{event.event === 'review_confirmed' ? <BadgeCheck size={17}/> : event.event === 'field_confirmed' ? <Pencil size={16}/> : <FileText size={17}/>}</div><div><h3>{event.event.startsWith('cashless_simulation_') ? 'Cashless simulation updated' : event.event === 'cashless_details_saved' ? 'Admission details saved' : event.event === 'existing_policy_loaded' ? 'Existing policy loaded' : event.event === 'document_uploaded' ? 'Document added and checked' : event.event === 'document_removed' ? 'Document removed' : event.event === 'field_confirmed' ? 'Detail confirmed by you' : 'Final review confirmed'}</h3><p>{event.event === 'field_confirmed' ? `${application.fields[String(event.details.field)]?.label}: ${String(event.details.value)}` : event.event === 'review_confirmed' ? `Application revision ${String(event.details.revision)} confirmed for packet preparation.` : String(event.details.message || event.details.policy || event.details.name || labels[event.details.kind as Kind] || '')}</p><time>{new Date(event.at).toLocaleString('en-IN')}</time></div><span className="audit-badge">{event.event === 'field_confirmed' || event.event === 'review_confirmed' ? 'YOU' : 'WORKFLOW'}</span></div>)}</div>}</section>}
          {view === 'tracking' && application.claim && <ClaimTracker application={application} busy={!!busy} onSubmit={submitClaim} onUploadClarification={() => chooseUpload('clarification')} onRespond={respondClarification}/>} 
          <footer className="page-footer"><Brand small/><span>Understand it. Complete it. Move forward.</span><span><ShieldCheck size={13}/> No insurer submission</span></footer>
        </>}
      </main>
    </div>

    {busy && <div className="working-indicator" role="status"><LoaderCircle className="spin" size={16}/>{busy}…</div>}
    {notice && <div className="toast" role="status"><CheckCircle2 size={18}/>{notice}<button className="icon-button" onClick={() => setNotice('')} aria-label="Dismiss notification"><X size={14}/></button></div>}
    {!chatOpen && <button className="floating-chat" onClick={() => setChatOpen(true)}><Sparkles size={19}/><span>Ask OneFlow</span></button>}

    {startOpen && <JourneyStart policies={policies} busy={!!busy} onClose={() => setStartOpen(false)} onCreate={(journey, policy, member) => void startJourney(journey, policy, member)} onAddPolicy={() => void startPolicyUpload()}/>} 
    {demoOpen && <div className="modal-backdrop" onClick={() => !busy && setDemoOpen(false)}><section className="modal demo-modal" role="dialog" aria-modal="true" aria-labelledby="demo-title" onClick={e => e.stopPropagation()}><button className="modal-close icon-button" onClick={() => setDemoOpen(false)} aria-label="Close sample cases"><X size={20}/></button><div className="modal-symbol"><FlaskConical size={25}/></div><span className="eyebrow">A SMALL PREVIEW OF WHAT’S POSSIBLE</span><h2 id="demo-title">Try a journey. See the difference.</h2><p>Three example cases, each with a different next step. Existing work is preserved in its own journey.</p>{health?.mode === 'cloud' ? <div className="cloud-demo-info"><p>Upload documents from My documents to process them and review the extracted details.</p><button className="button button-dark" onClick={() => { setDemoOpen(false); setView('documents') }}>Open documents <ArrowRight size={16}/></button></div> : <div className="scenario-list">{[{ id: 'missing', title: 'The missing piece', subtitle: 'Three documents added. Find what’s left.', icon: FolderOpen, tag: 'START HERE' }, { id: 'conflict', title: 'A detail worth a second look', subtitle: 'Spot a name mismatch across documents.', icon: Search, tag: 'CROSS-DOC CHECK' }, { id: 'complete', title: 'The clear path', subtitle: 'Review a complete case and export a packet.', icon: BadgeCheck, tag: 'FULL JOURNEY' }].map(s => <button key={s.id} disabled={!!busy} onClick={() => void loadDemo(s.id)}><div className="scenario-icon"><s.icon size={23}/></div><div><span>{s.tag}</span><h3>{s.title}</h3><p>{s.subtitle}</p></div><ArrowRight size={20}/></button>)}</div>}<div className="modal-footnote"><ShieldCheck size={14}/> Your policy. A clear workflow.</div></section></div>}

    {policyOpen && <div className="modal-backdrop" onClick={() => setPolicyOpen(false)}><section className="modal policy-modal" role="dialog" aria-modal="true" aria-labelledby="policy-title" onClick={e => e.stopPropagation()}><button className="modal-close icon-button" onClick={() => setPolicyOpen(false)} aria-label="Close policy"><X size={20}/></button><span className="eyebrow">THE EVIDENCE BEHIND THE GUIDANCE</span><h2 id="policy-title">Your policy, made clearer.</h2><p>{application?.policy_context?.name || 'Your policy'}<br/>{application?.issued_policy ? 'Official wording summaries and separate OneFlow workspace checks. The customer policy schedule.' : 'Upload your policy to use its own source rules.'}</p>{uploadedPolicy ? <a href={`/api/applications/${application?.id}/documents/${uploadedPolicy.id}/file`} className="button button-white" target="_blank" rel="noreferrer"><BookOpen size={16}/> Open uploaded policy <ExternalLink size={14}/></a> : <p className="muted">Upload your policy to view its source here.</p>}<div className="policy-clauses">{clauses.map(c => <article key={c.id} className={activeClause === c.id ? 'highlight' : ''}><div><span>{c.id}</span><small>PAGE {c.page}</small></div><h3>{c.section}</h3><p>{c.text}</p>{c.source_url && <a className="clause-source" href={c.source_url + (c.source_url.startsWith('https:') ? '#page=' + c.page : '')} target="_blank" rel="noreferrer">{c.source_name} · {c.summary ? 'Read original wording' : 'Read policy rule'} <ExternalLink size={12}/></a>}</article>)}</div></section></div>}

    {chatOpen && <aside className="chat-panel" aria-label="OneFlow assistant"><div className="chat-header"><span className="ai-icon"><Sparkles size={20}/></span><div><h2>OneFlow assistant</h2><span>Clarity for your next step</span></div><button className="icon-button" onClick={() => setChatOpen(false)} aria-label="Close assistant"><PanelLeftClose size={20}/></button></div><div className="chat-policy-bar"><ShieldCheck size={14}/> {health?.mode === 'cloud' ? 'Vertex AI ·' : 'Workspace responses ·'} Policy-linked process guidance</div><div className="chat-messages"><div className="chat-bubble assistant"><strong>A little less paperwork. A little more clarity.</strong><p>I can explain the required documents, help you understand a check, and guide your next step. What would you like to know?</p></div>{application?.messages.map(m => <div key={m.id} className={`chat-bubble ${m.role}`}><span className="message-role">{m.role === 'user' ? 'YOU' : 'ONEFLOW AI'}</span><p>{m.text}</p>{m.citations.length > 0 && <div className="message-citations">{m.citations.map(c => <button key={c.id} onClick={() => showClause(c.id)}><BookOpen size={11}/>{c.id} · p.{c.page}</button>)}</div>}</div>)}{busy === 'Finding a grounded answer' && <div className="chat-thinking"><LoaderCircle size={15} className="spin"/> Checking the policy…</div>}<div ref={chatEnd}/></div><div className="chat-compose"><div className="chat-quick-actions"><button disabled={!!busy} onClick={() => void sendQuestion('What documents do I need?')}>Required documents</button><button disabled={!!busy} onClick={() => void sendQuestion('What does packet ready mean?')}>Packet readiness</button></div><form onSubmit={(e: FormEvent) => { e.preventDefault(); void sendQuestion(question) }}><label htmlFor="chat-input" className="sr-only">Ask about your claim</label><textarea id="chat-input" placeholder="Ask about your claim…" value={question} maxLength={2000} onChange={e => setQuestion(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void sendQuestion(question) } }}/><button className="send-button" aria-label="Send message" disabled={!!busy || !question.trim() || !application}><ArrowUp size={19}/></button></form><small>Review AI answers against the linked source policy.</small></div></aside>}
  </div>
}

function FieldEditor({ field, busy, hasIssue, onSave, documentUrl, readOnly = false }: { field: Field; busy: boolean; hasIssue: boolean; onSave: (value: string) => void; documentUrl: (id: string) => string; readOnly?: boolean }) {
  const [open, setOpen] = useState(false)
  const [value, setValue] = useState(field.value)
  return <div className={`field-editor ${hasIssue ? 'has-issue' : ''}`}><button className="field-summary" onClick={() => setOpen(!open)} aria-expanded={open}><div><span>{field.label}</span><strong>{field.key === 'bill_total' && field.value ? money(field.value) : field.value || 'Not provided'}</strong></div><span className={`field-state ${field.confirmed ? 'confirmed' : hasIssue ? 'attention' : ''}`}>{field.confirmed ? <><CheckCheck size={13}/> Confirmed by you</> : hasIssue ? <><AlertCircle size={13}/> Check detail</> : <><FileText size={13}/> Source linked</>}</span><ChevronDown size={17} className={open ? 'rotated' : ''}/></button>{open && <div className="field-expanded">{field.sources.length ? <div className="field-sources">{field.sources.map((s, i) => <div className="source-card" key={i}><a href={documentUrl(s.document_id)} target="_blank" rel="noreferrer"><FileText size={13}/>{s.document_name} · p.{s.page}<ExternalLink size={11}/></a><strong>{s.value}</strong><blockquote>“{s.quote}”</blockquote></div>)}</div> : <p className="muted">No document evidence yet. Add the relevant document or enter a verified value.</p>}{readOnly ? <p className="field-note">Loaded from your existing customer policy. Start a new journey to change the patient, or replace conflicting claim evidence.</p> : <form onSubmit={e => { e.preventDefault(); onSave(value) }}><label htmlFor={`field-${field.key}`}>Confirm the correct value</label><div><input id={`field-${field.key}`} value={value} maxLength={200} onChange={e => setValue(e.target.value)} placeholder={field.key.includes('date') || field.key.startsWith('policy_') && field.key !== 'policy_number' ? 'Use the date as shown on the document' : field.label}/><button className="button button-dark" disabled={busy || !value.trim()}><Check size={15}/> Confirm</button></div></form>}<p className="field-note">Your confirmation is recorded alongside the original extraction. Replacing a document resets related confirmations.</p></div>}</div>
}
