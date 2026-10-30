from typing import Literal
from pydantic import BaseModel, Field

DocumentKind = Literal['policy', 'bill', 'discharge', 'bank_proof', 'admission_advice', 'cost_estimate', 'clarification']
FIELDS = {
    'full_name': 'Patient name', 'policy_number': 'Policy number', 'sum_insured': 'Sum insured',
    'admission_date': 'Admission date', 'discharge_date': 'Discharge date',
    'bill_total': 'Hospital bill total', 'hospital_name': 'Hospital name',
    'bank_account_last4': 'Bank account (last 4 digits)',
    'policy_start': 'Policy start', 'policy_end': 'Policy end',
    'treatment_summary': 'Treatment / admission advice', 'estimated_amount': 'Estimated treatment cost',
    # Optional claim-form fields. They are extracted when present and never block a claim when absent.
    'insured_address': 'Primary insured address', 'insured_city': 'Primary insured city',
    'insured_state': 'Primary insured state', 'insured_pincode': 'Primary insured pincode',
    'insured_mobile': 'Primary insured mobile', 'insured_email': 'Primary insured email',
    'patient_dob': 'Patient date of birth', 'patient_age': 'Patient age',
    'patient_gender': 'Patient gender', 'patient_relationship': 'Patient relationship',
    'patient_occupation': 'Patient occupation', 'patient_address': 'Patient address',
    'admission_time': 'Admission time', 'discharge_time': 'Discharge time',
    'room_category': 'Room category', 'hospitalization_reason': 'Hospitalization reason',
    'injury_date': 'Injury or diagnosis date', 'injury_cause': 'Injury cause',
    'medico_legal': 'Medico-legal case', 'police_reported': 'Police report filed',
    'fir_number': 'FIR number', 'system_of_medicine': 'System of medicine',
    'diagnosis': 'Diagnosis', 'procedure_details': 'Procedure details',
    'preauthorization_number': 'Preauthorization number',
    'pre_hospitalization_expenses': 'Pre-hospitalization expenses',
    'hospitalization_expenses': 'Hospitalization expenses',
    'post_hospitalization_expenses': 'Post-hospitalization expenses',
    'ambulance_charges': 'Ambulance charges', 'pharmacy_expenses': 'Pharmacy expenses',
    'investigation_expenses': 'Investigation expenses', 'other_expenses': 'Other expenses',
    'domiciliary_hospitalization': 'Domiciliary hospitalization',
    'pan': 'PAN', 'bank_account_number': 'Bank account number', 'bank_name': 'Bank name',
    'bank_branch': 'Bank branch', 'ifsc_code': 'IFSC code', 'kyc_status': 'KYC status',
}


class CreateApplication(BaseModel):
    title: str = Field(default='My reimbursement claim', min_length=1, max_length=100)
    journey: Literal['reimbursement', 'cashless'] = 'reimbursement'
    issued_policy_id: str | None = None
    # Local demo applicants can provide their selected policy record from the
    # frontend; production integrations should replace this with a server-side
    # policy lookup.
    issued_policy: dict | None = None
    member_id: str = 'aarav'


class CashlessDetails(BaseModel):
    member_id: str
    hospital_id: str
    admission_type: Literal['planned', 'emergency']
    admission_date: str = Field(min_length=1, max_length=30)
    treatment_summary: str = Field(min_length=10, max_length=1500)
    estimated_amount: str = Field(min_length=1, max_length=15)
    identity_ready: bool = False


class SimulationAction(BaseModel):
    model_config = {'extra': 'forbid'}
    action: Literal['submit', 'request_information', 'resubmit', 'authorize', 'decline', 'discharge_review', 'settle']
    clarification: str = Field(default='', max_length=1500)


class SubmitClaim(BaseModel):
    consent: bool


class InsurerAction(BaseModel):
    action: Literal['request_information', 'approve', 'partial_approve', 'reject', 'settle']
    explanation: str = Field(default='', max_length=2000)
    approved_amount: str | None = Field(default=None, max_length=30)


class ClarificationResponse(BaseModel):
    response: str = Field(min_length=1, max_length=2000)


class Correction(BaseModel):
    value: str = Field(min_length=1, max_length=200)


class Message(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class DemoRequest(BaseModel):
    scenario: Literal['complete', 'missing', 'conflict'] = 'missing'


class ExtractedValue(BaseModel):
    key: str
    value: str
    page: int = Field(ge=1)
    quote: str


class Extraction(BaseModel):
    fields: list[ExtractedValue]


class GroundedAnswer(BaseModel):
    answer: str
    clause_ids: list[str]
