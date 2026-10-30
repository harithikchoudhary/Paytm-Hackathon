import { CircleHelp, CheckCircle2, ShieldCheck } from 'lucide-react'
import type { Eligibility } from './api'

export function EligibilityPanel({ eligibility, onPolicy }: { eligibility?: Eligibility; onPolicy: (id: string) => void }) {
  if (!eligibility) return null
  return <section className="white-card eligibility-panel"><div className="section-heading"><div><h2><ShieldCheck size={18}/> Policy eligibility assessment</h2><p className="muted">Evidence-based indicators from the supplied policy schedule.</p></div><span className="small-muted">{eligibility.status.replaceAll('_', ' ')}</span></div><p className="eligibility-explanation">{eligibility.explanation}</p>{eligibility.indicative_payable_amount && <div className="indicative-amount"><span>Indicative payable amount</span><strong>₹{Number(eligibility.indicative_payable_amount).toLocaleString('en-IN')}</strong><small>Estimate only; insurer adjudication and final bills control payment.</small></div>}<div className="eligibility-checks">{eligibility.checks.map(check => <div key={check.id}><span className={check.result === 'pass' ? 'check-pass' : 'check-uncertain'}>{check.result === 'pass' ? <CheckCircle2 size={15}/> : <CircleHelp size={15}/>}</span><p><strong>{check.explanation}</strong><button onClick={() => onPolicy(check.clause_id)}>View {check.clause_id}</button></p></div>)}</div></section>
}
