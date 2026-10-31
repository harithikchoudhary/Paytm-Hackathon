import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { ArrowUp, BookOpen, Check, CheckCircle2, LoaderCircle, PanelLeftClose, Plus, ShieldCheck, Sparkles, Upload } from 'lucide-react'
import type { Application, IssuedPolicy, Kind } from './api'
import { labels } from './api'

type GuidedStep = 'idle' | 'policy' | 'member' | 'documents' | 'review'
type ChatLine = { id: string; role: 'assistant' | 'user'; text: string }

const required: Kind[] = ['policy', 'bill', 'discharge', 'bank_proof']
const cleanAssistantText = (text: string) => text.replace(/\\\*\\\*/g, '').replace(/\*\*/g, '').trim()

export function GuidedAssistant({ embedded = false, application, policies, busy, messages, onClose, onAsk, onStartClaim, onUpload, onReviewAndSubmit, onPolicy, onNavigate, onClearChat }: {
  embedded?: boolean
  application: Application
  policies: IssuedPolicy[]
  busy: string
  messages: Application['messages']
  onClose: () => void
  onAsk: (text: string) => Promise<void>
  onStartClaim: (policyId: string, memberId: string) => Promise<void>
  onUpload: (kind: Kind) => void
  onReviewAndSubmit: () => Promise<void>
  onPolicy: (id: string) => void
  onNavigate: (view: 'profile' | 'overview' | 'documents' | 'review' | 'activity' | 'tracking' | 'assistant') => void
  onClearChat: () => Promise<void>
}) {
  const [step, setStep] = useState<GuidedStep>('idle')
  const [lines, setLines] = useState<ChatLine[]>([])
  const [input, setInput] = useState('')
  const [selectedPolicy, setSelectedPolicy] = useState(policies[0]?.id || '')
  const [showPolicyChoices, setShowPolicyChoices] = useState(false)
  const policy = policies.find(item => item.id === selectedPolicy)
  const missing = useMemo(() => required.find(kind => !application.documents.some(doc => doc.kind === kind)), [application.documents])
  // Typed LLM turns do not rely on the legacy local step state. Once the user
  // has started a conversation, expose the real upload control whenever the
  // persisted application is missing a required document.
  const showUploadControl = !!missing && (step === 'documents' || messages.some(message => message.role === 'user'))
  const suggestions = useMemo(() => {
    const lastUser = [...messages].reverse().find(message => message.role === 'user')?.text.toLowerCase() || ''
    if (step === 'policy') return ['Which policy should I use?', 'What does my policy cover?']
    if (step === 'member') return ['Who is covered by this policy?', 'I need help choosing the patient']
    if (step === 'documents' && missing) return [`What is the ${labels[missing].toLowerCase()} for?`, 'Can I upload more than one document?', 'Why do you need this document?']
    if (step === 'review') return ['What still needs my review?', 'How much may be payable?', 'Submit this claim']
    if (lastUser.includes('cashless')) return ['What documents are needed for cashless?', 'How does cashless approval work?', 'Start cashless assistance']
    if (lastUser.includes('document') || lastUser.includes('upload')) return ['Which document should I upload next?', 'Why is this document needed?', 'Can I replace a document?']
    if (lastUser.includes('status') || lastUser.includes('track')) return ['What happens next?', 'When will the insurer respond?', 'Show my claim status']
    return ['I want to apply for a claim', 'What documents do I need?', 'How is my claim checked?']
  }, [messages, step, missing])
  const add = (role: ChatLine['role'], text: string) => setLines(previous => [...previous, { id: `${Date.now()}-${Math.random()}`, role, text }])

  useEffect(() => {
    if (step === 'documents' && !missing) {
      setStep('review')
      add('assistant', 'All four documents are here. I have extracted the claim details and checked them against the policy. Please review the summary below, then confirm if you want me to submit it.')
    }
  }, [step, missing])

  function submitText(event?: FormEvent, forcedText?: string) {
    event?.preventDefault()
    const text = (forcedText ?? input).trim()
    if (!text || busy) return
    setInput('')
    const lower = text.toLowerCase()
    if (step === 'review' && /(yes|submit|confirm|go ahead|correct)/.test(lower)) { add('user', text); void onReviewAndSubmit(); return }
    void onAsk(text)
  }

  function choosePolicy(id: string) {
    setSelectedPolicy(id)
    const chosen = policies.find(item => item.id === id)
    setShowPolicyChoices(false)
    setStep('member')
    add('assistant', `I’ll use ${chosen?.product || 'this policy'}. Who needs treatment?`)
  }

  return <aside className={`chat-panel guided-chat ${embedded ? 'guided-chat-embedded' : ''}`} aria-label="OneFlow claim assistant">
    <div className="chat-header"><span className="ai-icon"><Sparkles size={20}/></span><div><h2>OneFlow assistant</h2><span>Ask questions or complete a claim</span></div><div className="chat-header-actions"><button className="chat-clear-button" disabled={!!busy || messages.length === 0 && lines.length === 0} onClick={async () => { setLines([]); await onClearChat() }}>Clear chat</button><button className="icon-button" onClick={onClose} aria-label="Close assistant"><PanelLeftClose size={20}/></button></div></div>
    <div className="chat-policy-bar"><ShieldCheck size={14}/> {application.policy_context?.name || 'Your policy'} · Guided claim help</div>
    <div className="chat-messages guided-messages">
      <div className="chat-bubble assistant"><strong>Hi, I’m OneFlow.</strong><p>Tell me what you want to do, for example: “I want to apply for a claim.” I’ll ask one question at a time.</p></div>
      {lines.map(line => <div key={line.id} className={`chat-bubble ${line.role}`}><span className="message-role">{line.role === 'user' ? 'YOU' : 'ONEFLOW'}</span><p>{cleanAssistantText(line.text)}</p></div>)}
      {messages.map(message => <div key={message.id} className={`chat-bubble ${message.role}`}><span className="message-role">{message.role === 'user' ? 'YOU' : 'ONEFLOW'}</span><p>{cleanAssistantText(message.text)}</p>{message.citations.length > 0 && <div className="message-citations">{message.citations.map(clause => <button key={clause.id} onClick={() => onPolicy(clause.id)}><BookOpen size={11}/>{clause.id} · p.{clause.page}</button>)}</div>}</div>)}
      {busy && <div className="chat-thinking"><LoaderCircle size={15} className="spin"/> Working on your claim…</div>}
      {step === 'policy' && showPolicyChoices && <div className="guided-choice-list"><strong>Choose your policy</strong>{policies.map(item => <button key={item.id} onClick={() => choosePolicy(item.id)}><ShieldCheck size={16}/><span><b>{item.product}</b><small>{item.number} · ₹{item.sum_insured.toLocaleString('en-IN')} cover</small></span><Check size={15}/></button>)}</div>}
      {step === 'member' && policy && <div className="guided-choice-list"><strong>Who is the claim for?</strong>{policy.members.map(member => <button key={member.id} onClick={async () => { await onStartClaim(selectedPolicy, member.id); setStep('documents'); add('assistant', `${member.name} selected. Please upload your policy schedule first.`) }}><ShieldCheck size={16}/><span><b>{member.name}</b><small>{member.relationship} · age {member.age}</small></span><Check size={15}/></button>)}</div>}
      {showUploadControl && missing && <button className="guided-upload" onClick={() => onUpload(missing)}><Upload size={17}/><span><b>Upload {labels[missing].toLowerCase()}</b><small>I’ll extract and check it against your claim.</small></span><Plus size={16}/></button>}
      {step === 'review' && <button className="guided-submit" disabled={!!busy || application.status !== 'ready'} onClick={() => void onReviewAndSubmit()}><CheckCircle2 size={17}/><span><b>{application.status === 'ready' ? 'Confirm and submit claim' : 'Review details first'}</b><small>{application.status === 'ready' ? 'You remain in control before anything is submitted.' : 'Resolve the highlighted details in Review details.'}</small></span></button>}
      <div className="guided-suggestions"><span>Suggested next questions</span>{suggestions.map(suggestion => <button key={suggestion} disabled={!!busy} onClick={() => void submitText(undefined, suggestion)}>{suggestion}<ArrowUp size={12}/></button>)}</div>
    </div>
    <div className="chat-compose"><div className="chat-quick-actions"><button disabled={!!busy} onClick={() => { setStep('policy'); setShowPolicyChoices(true); add('assistant', 'Which policy should I use for this claim?') }}>Start reimbursement</button><button disabled={!!busy} onClick={() => void onAsk('I need cashless assistance')}>Cashless assistance</button><button disabled={!!busy} onClick={() => onNavigate('profile')}>View policy</button><button disabled={!!busy} onClick={() => onNavigate('tracking')}>Track claim</button><button disabled={!!busy} onClick={() => void onAsk('What documents do I need?')}>Required documents</button></div><form onSubmit={submitText}><label htmlFor="guided-chat-input" className="sr-only">Tell OneFlow what you need</label><textarea id="guided-chat-input" placeholder="Say, for example, I want to apply for a claim…" value={input} maxLength={2000} onChange={event => setInput(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); submitText() } }}/><button className="send-button" aria-label="Send message" disabled={!!busy || !input.trim()}><ArrowUp size={19}/></button></form><small>Answers are checked against your linked policy and claim documents.</small></div>
  </aside>
}
