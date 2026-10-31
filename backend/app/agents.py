"""LangGraph claim agents.

These graphs provide the conversational assistant with an explicit, inspectable
state machine and a small tool surface. Tools call existing OneFlow services;
the model layer may choose a next step, but it never receives direct database
access and cannot bypass validation.
"""
from typing import TypedDict, Literal
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from . import store, cashless
from .workflow import run


class AgentState(TypedDict):
    application: dict
    user_message: str
    stage: str
    next_step: str
    details: dict


@tool
def verify_claim_intake(application: dict) -> dict:
    """Verify that the selected policy and insured member can be used for a claim."""
    policy = application.get('issued_policy') or {}
    member_id = application.get('member_id')
    members = policy.get('members', [])
    member = next((m for m in members if m.get('id') == member_id), None)
    return {'verified': bool(policy and member), 'policy_number': policy.get('number'),
            'member': member, 'missing': [] if policy and member else ['policy or insured member']}


@tool
def inspect_claim_documents(application: dict) -> dict:
    """Inspect uploaded documents and report extraction/evidence coverage."""
    required = ('policy', 'bill', 'discharge', 'bank_proof')
    docs = application.get('documents', [])
    present = {d.get('kind') for d in docs}
    return {'documents': [{'kind': d.get('kind'), 'name': d.get('name'), 'fields': len(d.get('extracted', [])), 'provider': d.get('provider')} for d in docs],
            'missing': [kind for kind in required if kind not in present], 'complete': all(kind in present for kind in required)}


@tool
def compare_claim_evidence(application: dict) -> dict:
    """Run the existing cross-document consistency and eligibility checks."""
    updated = run(application)
    errors = [issue for issue in updated.get('issues', []) if issue.get('severity') == 'error']
    return {'application': updated, 'issues': updated.get('issues', []), 'blocking': errors,
            'eligibility': updated.get('eligibility'), 'risk_assessment': updated.get('risk_assessment'),
            'ready_for_review': not errors}


@tool
def resolve_claim_next_step(application: dict) -> dict:
    """Choose the next user-facing reimbursement step from persisted state."""
    missing = inspect_claim_documents.invoke({'application': application})
    if missing['missing']:
        return {'next_step': 'upload_document', 'document_kind': missing['missing'][0], 'missing': missing['missing']}
    errors = [i for i in application.get('issues', []) if i.get('severity') == 'error']
    if errors:
        return {'next_step': 'resolve_issue', 'issue': errors[0]}
    if not application.get('reviewed_at'):
        return {'next_step': 'confirm_review'}
    if not application.get('packet_generated_at'):
        return {'next_step': 'prepare_packet'}
    if not store.get_claim(application['id']):
        return {'next_step': 'confirm_submission'}
    return {'next_step': 'track_claim'}


@tool
def prepare_claim_packet(application: dict) -> dict:
    """Record packet readiness after review and validation have passed."""
    if application.get('status') != 'ready' or not application.get('reviewed_at'):
        return {'prepared': False, 'reason': 'Review and blocking issues must be complete first.'}
    application['packet_generated_at'] = application.get('packet_generated_at') or store.now()
    application['audit'].append({'at': store.now(), 'event': 'claim_packet_generated', 'details': {'agent': 'reimbursement'}})
    store.save(application)
    return {'prepared': True, 'packet_generated_at': application['packet_generated_at']}


@tool
def inspect_cashless_preparation(application: dict) -> dict:
    """Validate cashless admission details and handoff documents."""
    updated = run(application)
    return {'application': updated, 'issues': updated.get('issues', []), 'cashless': updated.get('cashless'),
            'ready': not updated.get('issues')}


@tool
def advance_cashless_stage(application: dict, requested_stage: str) -> dict:
    """Describe the permitted next cashless stage without executing insurer actions."""
    allowed = {'draft': 'collect admission details and upload admission advice/cost estimate',
               'submitted': 'wait for preauthorization response or clarification',
               'information_required': 'answer the clarification and resubmit',
               'resubmitted': 'wait for the authorization decision',
               'authorized': 'upload final bill and discharge summary',
               'discharge_review': 'review the final bill before settlement',
               'settled': 'view the settlement timeline'}
    status = (application.get('cashless') or {}).get('status', 'draft')
    return {'stage': status, 'next_step': allowed.get(status, 'review cashless details'), 'requested_stage': requested_stage}


def _reimbursement_intake(state):
    state['stage'] = 'intake'
    state['details'] = verify_claim_intake.invoke({'application': state['application']})
    return state


def _reimbursement_documents(state):
    state['stage'] = 'documents'
    state['details'] = inspect_claim_documents.invoke({'application': state['application']})
    return state


def _reimbursement_compare(state):
    state['stage'] = 'consistency'
    state['details'] = compare_claim_evidence.invoke({'application': state['application']})
    return state


def _reimbursement_next(state):
    state['details'] = {**state.get('details', {}), **resolve_claim_next_step.invoke({'application': state['application']})}
    state['next_step'] = state['details']['next_step']
    return state


def _cashless_intake(state):
    state['stage'] = 'cashless_intake'
    state['details'] = inspect_cashless_preparation.invoke({'application': state['application']})
    return state


def _cashless_next(state):
    state['details'] = {**state.get('details', {}), **advance_cashless_stage.invoke({'application': state['application'], 'requested_stage': state.get('user_message', '')})}
    state['next_step'] = state['details']['next_step']
    return state


def _build_reimbursement():
    graph = StateGraph(AgentState)
    graph.add_node('intake', _reimbursement_intake)
    graph.add_node('documents', _reimbursement_documents)
    graph.add_node('compare', _reimbursement_compare)
    graph.add_node('next_step', _reimbursement_next)
    graph.add_edge(START, 'intake'); graph.add_edge('intake', 'documents'); graph.add_edge('documents', 'compare'); graph.add_edge('compare', 'next_step'); graph.add_edge('next_step', END)
    return graph.compile()


def _build_cashless():
    graph = StateGraph(AgentState)
    graph.add_node('intake', _cashless_intake)
    graph.add_node('next_step', _cashless_next)
    graph.add_edge(START, 'intake'); graph.add_edge('intake', 'next_step'); graph.add_edge('next_step', END)
    return graph.compile()


reimbursement_agent = _build_reimbursement()
cashless_agent = _build_cashless()


def run_agent(application: dict, user_message: str = '', journey: Literal['reimbursement', 'cashless'] | None = None) -> dict:
    """Run the journey-specific graph and return its inspectable checkpoint."""
    selected = journey or application.get('journey', 'reimbursement')
    graph = cashless_agent if selected == 'cashless' else reimbursement_agent
    return graph.invoke({'application': application, 'user_message': user_message, 'stage': '', 'next_step': '', 'details': {}})
