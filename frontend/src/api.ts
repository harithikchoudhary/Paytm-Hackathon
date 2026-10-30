export type Kind = 'policy' | 'bill' | 'discharge' | 'bank_proof' | 'admission_advice' | 'cost_estimate' | 'clarification'
export type Clause = { id: string; section: string; page: number; text: string; source_url?: string; source_name?: string; summary?: boolean }
export type Source = { document_id: string; document_name: string; kind: Kind; value: string; page: number; quote: string }
export type Field = { key: string; label: string; value: string; confirmed: boolean; sources: Source[] }
export type Issue = { code: string; message: string; severity: 'error' | 'warning'; clause_id: string; field?: string }
export type Document = { id: string; name: string; kind: Kind; size: number; page_count: number; provider: string; preloaded?: boolean }
export type ChatMessage = { id: string; role: string; text: string; citations: Clause[]; at: string }
export type IssuedPolicy = { id: string; number: string; insurer: string; product: string; uin: string; start_date: string; end_date: string; sum_insured: number; holder: string; is_demo: boolean; notice: string; wording_url: string; members: { id: string; name: string; relationship: string; age: number }[] }
export type Hospital = { id: string; name: string; city: string; area: string; network: 'sample_network' | 'unverified'; specialties: string[]; is_demo: boolean }
export type CashlessDetails = { member_id: string; hospital_id: string; admission_type: 'planned' | 'emergency'; admission_date: string; treatment_summary: string; estimated_amount: string; identity_ready: boolean }
export type CashlessState = { simulation: boolean; status: string; details: Partial<CashlessDetails>; hospital?: Hospital; authorized_amount: string | null; timeline: { at: string; status: string; message: string; source: string }[] }
export type Claim = { application_id: string; claim_id: string; acknowledgement_id: string; status: string; submitted_at: string; updated_at: string; claim_amount: string; approved_amount?: string | null; explanation?: string; settlement?: { settled_at: string; settled_amount: string; reference: string } | null; timeline: { at: string; status: string; message: string; source: string; explanation?: string }[] }
export type Eligibility = { status: string; explanation: string; indicative_payable_amount?: string | null; checks: { id: string; result: string; clause_id: string; explanation: string }[] }
export type Application = { id: string; title: string; status: string; progress: number; documents: Document[]; fields: Record<string, Field>; issues: Issue[]; messages: ChatMessage[]; reviewed_at: string | null; packet_generated_at?: string | null; audit: { at: string; event: string; details: Record<string, unknown> }[]; revision: number; journey?: 'reimbursement' | 'cashless'; issued_policy?: IssuedPolicy; member_id?: string; cashless?: CashlessState; claim?: Claim | null; eligibility?: Eligibility; policy_context: { id: string; name: string; pdf_url: string; clauses: Clause[] } }
export type Summary = Pick<Application, 'id' | 'title' | 'status' | 'progress'>
export type Health = { mode: 'demo' | 'cloud'; cloud_configured: boolean; missing_configuration: string[]; model: string }

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch('/api' + path, { ...options, headers: options.body instanceof FormData ? undefined : { 'Content-Type': 'application/json', ...options.headers } })
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try { const data = await response.json(); message = typeof data.detail === 'string' ? data.detail : 'Please check the submitted information.' } catch { /* network or non-JSON response */ }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}
export const labels: Record<Kind, string> = { policy: 'Policy schedule', bill: 'Hospital bill', discharge: 'Discharge summary', bank_proof: 'Bank account proof', admission_advice: 'Admission advice', cost_estimate: 'Hospital cost estimate', clarification: 'Clarification document' }
export const statusLabels: Record<string, string> = { collecting: 'In progress', needs_attention: 'Needs attention', review: 'Ready for review', ready: 'Packet ready', submitted: 'Simulated · Submitted', claim_resubmitted: 'Simulated · Resubmitted', claim_clarification_requested: 'Action needed · Clarification', claim_approved: 'Simulated · Approved', claim_partially_approved: 'Simulated · Partially approved', claim_rejected: 'Simulated · Rejected', claim_settled: 'Simulated · Settled', cashless_draft: 'Prepare cashless request', cashless_submitted: 'Simulated · Submitted', cashless_information_required: 'Simulated · More information', cashless_resubmitted: 'Simulated · Resubmitted', cashless_authorized: 'Simulated · Authorized', cashless_declined: 'Simulated · Declined', cashless_discharge_review: 'Simulated · Discharge review', cashless_settled: 'Simulated · Settled' }
