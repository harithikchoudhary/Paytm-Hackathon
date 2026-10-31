import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { ArrowUp, BookOpen, Bot, Check, CheckCircle2, CircleHelp, FileText, Landmark, LoaderCircle, Mic, Plus, ShieldCheck, Sparkles, Square, Upload, UserRound, Volume2 } from 'lucide-react'
import type { Application, IssuedPolicy, Kind } from './api'
import { api, apiAudio, labels } from './api'
import { prepareSpeechRecording } from './voice'

type GuidedStep = 'idle' | 'policy' | 'member' | 'documents' | 'review'
type ChatLine = { id: string; role: 'assistant' | 'user'; text: string }
type AssistantReply = { assistant?: { action?: string | null; document_kind?: Kind; missing_documents?: Kind[]; intent?: string; suggested_questions?: string[] }; replyText?: string }

const required: Kind[] = ['policy', 'bill', 'discharge', 'bank_proof']
const cleanAssistantText = (text: string) => text.replace(/\\\*\\\*/g, '').replace(/\*\*/g, '').trim()

export function GuidedAssistant({ embedded = false, application, policies, busy, messages, onClose: _onClose, onAsk, onStartClaim, onUpload, onReviewAndSubmit, onPolicy, onNavigate, onClearChat }: {
  embedded?: boolean
  application: Application
  policies: IssuedPolicy[]
  busy: string
  messages: Application['messages']
  onClose: () => void
  onAsk: (text: string) => Promise<AssistantReply>
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
  const [requestedUploadKind, setRequestedUploadKind] = useState<Kind | null>(null)
  const [voiceState, setVoiceState] = useState<'idle' | 'recording' | 'transcribing' | 'speaking'>('idle')
  const [voiceError, setVoiceError] = useState('')
  const [voiceLanguage, setVoiceLanguage] = useState('en-IN')
  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const audioUrlRef = useRef<string | null>(null)
  const recordingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const policy = policies.find(item => item.id === selectedPolicy)
  const missing = useMemo(() => required.find(kind => !application.documents.some(doc => doc.kind === kind)), [application.documents])
  // Typed LLM turns do not rely on the legacy local step state. Once the user
  // has started a conversation, expose the real upload control whenever the
  // persisted application is missing a required document.
  // The upload control is rendered only when the assistant explicitly asks
  // for a document. A missing document alone is not enough: users may be
  // asking a general question, and the next response may not require upload.
  const showUploadControl = !!missing && requestedUploadKind === missing
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

  useEffect(() => () => {
    if (recordingTimerRef.current) clearTimeout(recordingTimerRef.current)
    if (recorderRef.current) {
      recorderRef.current.onstop = null
      if (recorderRef.current.state === 'recording') recorderRef.current.stop()
    }
    streamRef.current?.getTracks().forEach(track => track.stop())
    audioRef.current?.pause()
    if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current)
  }, [])

  async function playSpeech(text: string, language = voiceLanguage) {
    if (audioRef.current) audioRef.current.pause()
    if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current)
    setVoiceError('')
    setVoiceState('speaking')
    try {
      const blob = await apiAudio('/assistant/speech', { method: 'POST', body: JSON.stringify({ application_id: application.id, text: cleanAssistantText(text).slice(0, 2500), language_code: language }) })
      const url = URL.createObjectURL(blob)
      audioUrlRef.current = url
      const audio = new Audio(url)
      audioRef.current = audio
      audio.onended = () => setVoiceState('idle')
      audio.onerror = () => { setVoiceError('Could not play this reply.'); setVoiceState('idle') }
      await audio.play()
    } catch (error) {
      setVoiceError(error instanceof Error ? error.message : 'Could not play this reply.')
      setVoiceState('idle')
    }
  }

  function stopSpeech() {
    audioRef.current?.pause()
    audioRef.current = null
    if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current)
    audioUrlRef.current = null
    setVoiceState('idle')
  }

  async function startRecording() {
    setVoiceError('')
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setVoiceError('Microphone recording is unavailable in this browser. Please type your message.')
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg'].find(type => MediaRecorder.isTypeSupported(type))
      const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
      recorderRef.current = recorder
      const chunks: BlobPart[] = []
      recorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data) }
      recorder.onstop = async () => {
        if (recordingTimerRef.current) clearTimeout(recordingTimerRef.current)
        stream.getTracks().forEach(track => track.stop())
        streamRef.current = null
        setVoiceState('transcribing')
        try {
          const recording = await prepareSpeechRecording(new Blob(chunks, { type: recorder.mimeType || 'audio/webm' }))
          const form = new FormData()
          form.append('file', recording, 'oneflow-recording.wav')
          form.append('application_id', application.id)
          const result = await api<{ transcript: string; language_code?: string }>('/assistant/transcribe', { method: 'POST', body: form })
          const transcript = result.transcript.trim()
          setInput(transcript)
          if (result.language_code) setVoiceLanguage(result.language_code)
          setVoiceState('idle')
          if (transcript) {
            setInput('')
            const reply = await onAsk(transcript)
            const meta = reply?.assistant
            setRequestedUploadKind(meta && ['upload_document_guidance', 'start_claim', 'resume_claim'].includes(meta.action || '') && meta.document_kind ? meta.document_kind : null)
            if (reply.replyText) await playSpeech(reply.replyText, result.language_code || 'en-IN')
          }
        } catch (error) {
          setVoiceError(error instanceof Error ? error.message : 'Could not transcribe the recording.')
          setVoiceState('idle')
        }
      }
      recorder.start()
      setVoiceState('recording')
      recordingTimerRef.current = setTimeout(() => recorder.state === 'recording' && recorder.stop(), 25000)
    } catch (error) {
      streamRef.current?.getTracks().forEach(track => track.stop())
      setVoiceError(error instanceof Error ? error.message : 'Microphone access was denied.')
      setVoiceState('idle')
    }
  }

  function stopRecording() {
    if (recorderRef.current?.state === 'recording') recorderRef.current.stop()
  }

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
    void onAsk(text).then(reply => {
      const meta = reply?.assistant
      setRequestedUploadKind(meta && ['upload_document_guidance', 'start_claim', 'resume_claim'].includes(meta.action || '') && meta.document_kind ? meta.document_kind : null)
    })
  }

  function askQuickAction(text: string) {
    void onAsk(text).then(reply => {
      const meta = reply?.assistant
      setRequestedUploadKind(meta && ['upload_document_guidance', 'start_claim', 'resume_claim'].includes(meta.action || '') && meta.document_kind ? meta.document_kind : null)
    })
  }

  function choosePolicy(id: string) {
    setSelectedPolicy(id)
    const chosen = policies.find(item => item.id === id)
    setShowPolicyChoices(false)
    setStep('member')
    add('assistant', `I’ll use ${chosen?.product || 'this policy'}. Who needs treatment?`)
  }

  function renderMessage(role: ChatLine['role'], text: string, id: string, citations: Application['messages'][number]['citations'] = []) {
    const assistant = role === 'assistant'
    return <div className={`chat-message-row ${assistant ? 'assistant' : 'user'}`} key={id}><span className={`chat-message-avatar ${assistant ? 'assistant' : 'user'}`} aria-hidden="true">{assistant ? <Bot size={17}/> : <UserRound size={16}/>}</span><div className={`chat-bubble ${role}`}><span className="message-role">{assistant ? 'ONEFLOW' : 'YOU'}</span><p>{cleanAssistantText(text)}</p>{assistant && <button className="chat-speak-button" type="button" onClick={() => void playSpeech(text)} aria-label="Listen to this reply" title="Listen to this reply"><Volume2 size={14}/> Listen</button>}{citations.length > 0 && <div className="message-citations">{citations.map(clause => <button key={clause.id} onClick={() => onPolicy(clause.id)}><BookOpen size={11}/>{clause.id} · p.{clause.page}</button>)}</div>}</div></div>
  }

  return <div className={`chat-workspace ${embedded ? 'chat-workspace-embedded' : ''}`}><aside className={`chat-panel guided-chat ${embedded ? 'guided-chat-embedded' : ''}`} aria-label="Paytm OneFlow AI claim assistant">
    <div className="chat-header"><span className="ai-icon"><Sparkles size={20}/></span><div><h2>Paytm OneFlow AI</h2><span>Your health insurance assistant</span></div><div className="chat-header-actions"><button className="chat-clear-button" disabled={!!busy || messages.length === 0 && lines.length === 0} onClick={async () => { setLines([]); await onClearChat() }}>New chat</button></div></div>
    <div className="chat-policy-bar"><ShieldCheck size={14}/> {application.policy_context?.name || 'Your policy'} · Guided claim help</div>
    <div className="chat-messages guided-messages">
      <div className="chat-message-row assistant"><span className="chat-message-avatar assistant" aria-hidden="true"><Bot size={17}/></span><div className="chat-bubble assistant"><strong>Hi, I’m Paytm OneFlow AI.</strong><p>Tell me what you want to do, for example: “I want to apply for a claim.” I’ll ask one question at a time.</p></div></div>
      {lines.map(line => renderMessage(line.role, line.text, line.id))}
      {messages.map(message => renderMessage(message.role === 'user' ? 'user' : 'assistant', message.text, message.id, message.citations))}
      {application.documents.length > 0 && <div className="chat-documents"><div className="chat-documents-heading"><FileText size={15}/><strong>Documents in this claim</strong><span>{application.documents.length}</span></div>{application.documents.map(document => <div className="chat-document-row" key={document.id}><span><b>{document.name}</b><small>{labels[document.kind]} · {document.page_count} page(s)</small></span><Check size={14}/></div>)}</div>}
      {busy && <div className="chat-thinking"><LoaderCircle size={15} className="spin"/> Working on your claim…</div>}
      {step === 'policy' && showPolicyChoices && <div className="guided-choice-list"><strong>Choose your policy</strong>{policies.map(item => <button key={item.id} onClick={() => choosePolicy(item.id)}><ShieldCheck size={16}/><span><b>{item.product}</b><small>{item.number} · ₹{item.sum_insured.toLocaleString('en-IN')} cover</small></span><Check size={15}/></button>)}</div>}
      {step === 'member' && policy && <div className="guided-choice-list"><strong>Who is the claim for?</strong>{policy.members.map(member => <button key={member.id} onClick={async () => { await onStartClaim(selectedPolicy, member.id); setStep('documents'); add('assistant', `${member.name} selected. Please upload your policy schedule first.`) }}><ShieldCheck size={16}/><span><b>{member.name}</b><small>{member.relationship} · age {member.age}</small></span><Check size={15}/></button>)}</div>}
      {showUploadControl && requestedUploadKind && <button className="guided-upload" onClick={() => { setRequestedUploadKind(null); onUpload(requestedUploadKind) }}><Upload size={17}/><span><b>Upload {labels[requestedUploadKind].toLowerCase()}</b><small>I’ll extract and check it against your claim.</small></span><Plus size={16}/></button>}
      {step === 'review' && <button className="guided-submit" disabled={!!busy || application.status !== 'ready'} onClick={() => void onReviewAndSubmit()}><CheckCircle2 size={17}/><span><b>{application.status === 'ready' ? 'Confirm and submit claim' : 'Review details first'}</b><small>{application.status === 'ready' ? 'You remain in control before anything is submitted.' : 'Resolve the highlighted details in Review details.'}</small></span></button>}
      <div className="guided-suggestions"><span>Suggested next questions</span>{suggestions.map(suggestion => <button key={suggestion} disabled={!!busy} onClick={() => void submitText(undefined, suggestion)}>{suggestion}<ArrowUp size={12}/></button>)}</div>
    </div>
    <div className="chat-compose"><div className="chat-quick-actions"><button disabled={!!busy} onClick={() => askQuickAction('I want to apply for a reimbursement claim')}>Start reimbursement</button><button disabled={!!busy} onClick={() => askQuickAction('I need cashless assistance')}>Cashless assistance</button><button disabled={!!busy} onClick={() => onNavigate('profile')}>View policy</button><button disabled={!!busy} onClick={() => onNavigate('tracking')}>Track claim</button><button disabled={!!busy} onClick={() => askQuickAction('What documents do I need?')}>Required documents</button></div><form onSubmit={submitText}><label htmlFor="guided-chat-input" className="sr-only">Tell OneFlow what you need</label><textarea id="guided-chat-input" placeholder="Say, for example, I want to apply for a claim…" value={input} maxLength={2000} onChange={event => setInput(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); submitText() } }}/><button type="button" className={`chat-mic-button ${voiceState === 'recording' ? 'recording' : ''}`} aria-label={voiceState === 'recording' ? 'Stop recording and send' : 'Record voice message'} title={voiceState === 'recording' ? 'Stop and send' : 'Speak to OneFlow'} disabled={!!busy || voiceState === 'transcribing' || voiceState === 'speaking'} onClick={() => voiceState === 'recording' ? stopRecording() : void startRecording()}>{voiceState === 'recording' ? <Square size={16}/> : voiceState === 'transcribing' ? <LoaderCircle size={17} className="spin"/> : <Mic size={18}/>}</button><button className="send-button" aria-label="Send message" disabled={!!busy || !input.trim() || voiceState === 'recording' || voiceState === 'transcribing'}><ArrowUp size={19}/></button></form>{voiceState === 'recording' && <small className="chat-voice-status">Listening… tap the square to send. Recording stops after 25 seconds.</small>}{voiceState === 'transcribing' && <small className="chat-voice-status">Transcribing your voice with Sarvam AI…</small>}{voiceState === 'speaking' && <button className="chat-stop-speech" type="button" onClick={stopSpeech}><Square size={12}/> Stop audio</button>}{voiceError && <small className="chat-voice-error" role="alert">{voiceError}</small>}<small>Answers are checked against your linked policy and claim documents.</small></div>
  </aside><aside className="chat-context-panel" aria-label="Paytm OneFlow AI quick actions"><section><h3>Quick actions</h3><button onClick={() => askQuickAction('I want to apply for a reimbursement claim')}><FileText size={17}/> File a claim</button><button onClick={() => askQuickAction('I need cashless assistance')}><Landmark size={17}/> Cashless assistance</button><button onClick={() => onNavigate('profile')}><ShieldCheck size={17}/> View my policy</button><button onClick={() => onNavigate('tracking')}><CircleHelp size={17}/> Track claim status</button></section><section><h3>Example questions</h3>{['What documents do I need?', 'Is this treatment covered?', 'What is my room rent limit?', 'Show my recent claims'].map(question => <button className="example-question" key={question} onClick={() => askQuickAction(question)}>{question}</button>)}</section></aside></div>
}
