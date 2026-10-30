import type { IssuedPolicy } from './api'

export type DemoApplicant = {
  id: string
  password: string
  profile: { id: string; name: string; email: string; mobile: string; address: string; date_of_birth: string; occupation: string; kyc_status: string; notice: string }
  policies: IssuedPolicy[]
}

const policy = (id: string, number: string, holder: string, memberId: string, sum_insured: number): IssuedPolicy => ({
  id, number, insurer: 'OneFlow Health Insurance', product: 'Care Plus Health Plan', uin: `DEMO-${id.toUpperCase()}`,
  start_date: '2026-01-01', end_date: '2026-12-31', sum_insured, holder, is_demo: true,
  notice: 'Example policy for this workspace. It is not issued by a real insurer.', wording_url: '',
  members: [{ id: memberId, name: holder, relationship: 'Self', age: 30 }],
})

export const DEMO_APPLICANTS: DemoApplicant[] = [
  { id: 'applicant-priya', password: 'Priya@123', profile: { id: 'applicant-priya', name: 'Priya Sharma', email: 'priya@example.com', mobile: '+91 90000 10001', address: 'Bengaluru, Karnataka', date_of_birth: '1994-06-12', occupation: 'Software engineer', kyc_status: 'Verified', notice: 'Applicant record for this workspace.' }, policies: [policy('priya-care', 'DEMO-PR-1001', 'Priya Sharma', 'priya-self', 500000)] },
  { id: 'applicant-rohan', password: 'Rohan@123', profile: { id: 'applicant-rohan', name: 'Rohan Mehta', email: 'rohan@example.com', mobile: '+91 90000 10002', address: 'Mumbai, Maharashtra', date_of_birth: '1988-02-25', occupation: 'Business owner', kyc_status: 'Verified', notice: 'Applicant record for this workspace.' }, policies: [policy('rohan-care', 'DEMO-RM-1002', 'Rohan Mehta', 'rohan-self', 750000)] },
  { id: 'applicant-ananya', password: 'Ananya@123', profile: { id: 'applicant-ananya', name: 'Ananya Iyer', email: 'ananya@example.com', mobile: '+91 90000 10003', address: 'Chennai, Tamil Nadu', date_of_birth: '1991-11-03', occupation: 'Teacher', kyc_status: 'Verified', notice: 'Applicant record for this workspace.' }, policies: [policy('ananya-care', 'DEMO-AI-1003', 'Ananya Iyer', 'ananya-self', 400000)] },
  { id: 'applicant-vikram', password: 'Vikram@123', profile: { id: 'applicant-vikram', name: 'Vikram Singh', email: 'vikram@example.com', mobile: '+91 90000 10004', address: 'New Delhi, Delhi', date_of_birth: '1985-08-19', occupation: 'Consultant', kyc_status: 'Verified', notice: 'Applicant record for this workspace.' }, policies: [policy('vikram-care', 'DEMO-VS-1004', 'Vikram Singh', 'vikram-self', 1000000)] },
  { id: 'applicant-neha', password: 'Neha@123', profile: { id: 'applicant-neha', name: 'Neha Patel', email: 'neha@example.com', mobile: '+91 90000 10005', address: 'Ahmedabad, Gujarat', date_of_birth: '1997-04-07', occupation: 'Designer', kyc_status: 'Verified', notice: 'Applicant record for this workspace.' }, policies: [policy('neha-care', 'DEMO-NP-1005', 'Neha Patel', 'neha-self', 600000)] },
]
