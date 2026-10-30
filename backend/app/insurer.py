"""Insurer boundary for the POC.

The adapter is deliberately small: a real insurer/TPA implementation can replace
SimulatedInsurer without changing the claim routes or the frontend contract.
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Protocol
from uuid import uuid4
from . import store


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class InsurerAdapter(Protocol):
    def submit(self, application: dict, claim: dict) -> dict: ...
    def event(self, application: dict, claim: dict, action: str, payload: dict) -> dict: ...


class SimulatedInsurer:
    name = 'OneFlow Simulated Insurer'

    def submit(self, application, claim):
        ack = f"SIM-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:10].upper()}"
        return self._transition(application, claim, 'submitted', {
            'acknowledgement_id': ack, 'claim_amount': claim['claim_amount'],
            'message': 'Simulated insurer received the claim. No real submission was made.'})

    def preauthorize(self, application, claim):
        ack = f"SIM-PREAUTH-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:8].upper()}"
        return self._transition(application, claim, 'submitted', {
            'acknowledgement_id': ack,
            'message': 'Simulated cashless preauthorization request received. No real request was made.'})

    def event(self, application, claim, action, payload):
        transitions = {
            'request_information': ('clarification_requested', 'Simulated insurer requested additional information.'),
            'resubmit': ('resubmitted', 'Clarification documents and information were resubmitted to the simulated insurer.'),
            'approve': ('approved', 'Simulated insurer approved the claim subject to final settlement.'),
            'partial_approve': ('partially_approved', 'Simulated insurer partially approved the claim after review.'),
            'reject': ('rejected', 'Simulated insurer rejected the claim in this simulation.'),
            'settle': ('settled', 'Simulated insurer marked the claim as settled. No funds were transferred.'),
        }
        if action not in transitions:
            raise ValueError('Unsupported simulated insurer action.')
        status, message = transitions[action]
        data = {'message': message, **payload}
        if action == 'approve':
            data['approved_amount'] = claim['claim_amount']
        if action == 'partial_approve':
            data['approved_amount'] = data.get('approved_amount') or str((Decimal(claim['claim_amount']) * Decimal('0.70')).quantize(Decimal('0.01')))
        if action == 'settle':
            data['settlement'] = {'settled_at': utc_now(), 'settled_amount': claim.get('approved_amount') or '0.00', 'reference': 'SIM-SET-' + uuid4().hex[:10].upper()}
        return self._transition(application, claim, status, data)

    def _transition(self, application, claim, status, data):
        at = utc_now()
        claim.update({k: v for k, v in data.items() if k in {'acknowledgement_id', 'claim_amount', 'approved_amount', 'settlement'}})
        if data.get('explanation'):
            claim['explanation'] = data['explanation']
        claim['status'] = status
        claim['updated_at'] = at
        if status == 'submitted' and not claim.get('submitted_at'):
            claim['submitted_at'] = at
        event = {'at': at, 'status': status, 'source': 'simulated_insurer', **data}
        claim.setdefault('timeline', []).append(event)
        store.save_claim(claim)
        store.add_insurer_event(application['id'], event)
        return claim


simulated_insurer = SimulatedInsurer()
