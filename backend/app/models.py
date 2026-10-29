from typing import Literal
from pydantic import BaseModel, Field

DocumentKind = Literal['policy', 'bill', 'discharge', 'bank_proof', 'admission_advice', 'cost_estimate']
FIELDS = {
    'full_name': 'Patient name', 'policy_number': 'Policy number',
    'admission_date': 'Admission date', 'discharge_date': 'Discharge date',
    'bill_total': 'Hospital bill total', 'hospital_name': 'Hospital name',
    'bank_account_last4': 'Bank account (last 4 digits)',
    'policy_start': 'Policy start', 'policy_end': 'Policy end',
    'treatment_summary': 'Treatment / admission advice', 'estimated_amount': 'Estimated treatment cost',
}


class CreateApplication(BaseModel):
    title: str = Field(default='My reimbursement claim', min_length=1, max_length=100)
    journey: Literal['reimbursement', 'cashless'] = 'reimbursement'
    issued_policy_id: str | None = None
    member_id: str = 'aarav'


class CashlessDetails(BaseModel):
    member_id: str
    hospital_id: str
    admission_type: Literal['planned', 'emergency']
    admission_date: str = Field(min_length=10, max_length=10)
    treatment_summary: str = Field(min_length=10, max_length=1500)
    estimated_amount: str = Field(min_length=1, max_length=15)
    identity_ready: bool = False


class SimulationAction(BaseModel):
    model_config = {'extra': 'forbid'}
    action: Literal['submit', 'request_information', 'resubmit', 'authorize', 'decline', 'discharge_review', 'settle']
    clarification: str = Field(default='', max_length=1500)


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
