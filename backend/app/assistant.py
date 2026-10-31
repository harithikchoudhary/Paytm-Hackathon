"""Safe conversational routing for OneFlow.

The assistant may explain information, but every claim action is executed by
this module against the existing workflow and persistence services.  The LLM
is never given database access and cannot report an action as successful unless
the corresponding backend operation succeeded.
"""
from datetime import datetime, timezone, timedelta
import re
from uuid import uuid4
from difflib import SequenceMatcher
from .config import settings
from . import store, providers
from .workflow import run
from .policies import retrieve
from .customer import policy_context, HOSPITALS
from .customer import customer_policy_document, ISSUED_POLICY
from .models import FIELDS
from .insurer import simulated_insurer, utc_now
from .agents import run_agent
from . import cashless
from .date_utils import parse_document_date


def _now():
    return datetime.now(timezone.utc).isoformat()


def classify(text: str):
    value = text.strip().casefold()
    if any(word in value for word in ('hello', 'hi', 'hey', 'thanks', 'thank you', 'good morning', 'good evening')):
        return 'general_chat', {}
    if any(word in value for word in ('status', 'track', 'where is my claim', 'what is pending')):
        return 'get_claim_status', {}
    if any(word in value for word in ('claim details', 'show my claim', 'application details', 'my details')):
        return 'get_claim_details', {}
    if any(word in value for word in ('clarification', 'additional document', 'respond to query', 'insurer asked')):
        return 'respond_to_clarification', {}
    if any(word in value for word in ('submit claim', 'submit my claim', 'send claim', 'send my claim', 'submit this')):
        return 'submit_claim', {}
    if any(word in value for word in ('prepare packet', 'prepare my packet', 'claim packet', 'download packet')):
        return 'prepare_packet', {}
    if any(word in value for word in ('confirm review', 'confirm the review', 'review is correct', 'everything is correct', 'looks correct')):
        return 'confirm_review', {}
    if any(word in value for word in ('review my claim', 'review claim', 'check uploaded', 'check my documents', 'validate my claim')):
        return 'get_validation_issues', {}
    if any(word in value for word in ('missing document', 'which document', 'what documents', 'upload', 'replace document')):
        return 'upload_document_guidance', {}
    if any(word in value for word in ('validation', 'why was', 'flagged', 'issue', 'error')):
        return 'get_validation_issues', {}
    if any(word in value for word in ('change ', 'update ', 'correct ', 'set ')):
        fields = _field_update(text)
        return ('update_claim_field', fields) if fields else ('general_chat', {})
    if any(word in value for word in ('apply for', 'start claim', 'file a claim', 'start reimbursement', 'start cashless', 'need cashless treatment', 'cashless assistance')):
        return 'start_claim', {'journey': 'cashless' if 'cashless' in value else 'reimbursement'}
    if any(word in value for word in ('policy', 'coverage', 'covered', 'waiting period', 'exclusion', 'deductible', 'copay', 'co-pay', 'room rent', 'premium', 'sublimit')):
        return 'policy_question', {}
    return 'general_chat', {}


def _field_update(text: str):
    value = text.casefold()
    aliases = {label.casefold(): key for key, label in FIELDS.items()}
    for label, key in aliases.items():
        if label in value:
            start = value.index(label) + len(label)
            tail = text[start:].strip(' :="')
            if tail.casefold().startswith('to '):
                tail = tail[3:]
            return {'field': key, 'value': tail.strip(' .')}
    return {}


def _message(record, text, answer, citations=None):
    record['messages'].extend([
        {'id': str(uuid4()), 'role': 'user', 'text': text, 'at': store.now(), 'citations': []},
        {'id': str(uuid4()), 'role': 'assistant', 'text': answer, 'at': store.now(), 'citations': citations or []},
    ])


def _missing(record):
    if record.get('journey') == 'cashless':
        required = ('admission_advice', 'cost_estimate')
    else:
        required = ('policy', 'bill', 'discharge', 'bank_proof')
    return [kind for kind in required if not any(d.get('kind') == kind for d in record.get('documents', []))]


def _affirmative_document_follow_up(text, history, record):
    """Treat a short confirmation after claim start as document flow consent."""
    if record.get('journey') != 'reimbursement' or not _missing(record):
        return False
    value = text.strip().casefold().rstrip('!.')
    if value not in {'sure', 'yes', 'okay', 'ok', 'alright', 'go ahead', 'continue', 'proceed'}:
        return False
    previous = next((message.get('text', '').casefold() for message in reversed(history) if message.get('role') == 'assistant'), '')
    return 'claim' in previous and ('current application' in previous or 'one step' in previous or 'missing' in previous)


def _cashless_hospital_candidates(text):
    value = text.casefold()
    candidates = []
    for hospital in HOSPITALS:
        tokens = [hospital['name'].casefold(), hospital['name'].split()[0].casefold(), hospital['area'].casefold(), hospital['city'].casefold()]
        if hospital['name'].casefold() in value or (tokens[1] in value and (tokens[2] in value or tokens[3] in value)):
            candidates.append(hospital)
    # A fuzzy first-token match helps conversational names such as “Sunrise
    # Hospital” while the directory remains the source of truth.
    if not candidates:
        words = re.findall(r'[a-z]+', value)
        for hospital in HOSPITALS:
            score = SequenceMatcher(None, ' '.join(words), hospital['name'].casefold()).ratio()
            if score >= 0.68:
                candidates.append(hospital)
    return list({hospital['id']: hospital for hospital in candidates}.values())


def _normalise_relative_date(text):
    value = text.casefold()
    local_today = datetime.now().astimezone().date()
    if 'day after tomorrow' in value:
        return (local_today + timedelta(days=2)).isoformat()
    if re.search(r'\btomorrow\b', value):
        return (local_today + timedelta(days=1)).isoformat()
    if re.search(r'\btoday\b', value):
        return local_today.isoformat()
    match = re.search(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b|\b\d{4}-\d{1,2}-\d{1,2}\b', text)
    parsed = parse_document_date(match.group(0)) if match else None
    return parsed.isoformat() if parsed else None


def _extract_cashless_details(text, record):
    """Extract only explicit cashless intake values from one user message."""
    value = text.strip()
    lower = value.casefold()
    details = {}
    candidates = _cashless_hospital_candidates(value)
    if len(candidates) == 1:
        details['hospital_id'] = candidates[0]['id']
        details['hospital_name'] = candidates[0]['name']
        details['hospital_branch'] = f"{candidates[0]['area']}, {candidates[0]['city']}"
    elif len(candidates) > 1:
        details['hospital_ambiguous'] = True
    if 'emergency' in lower:
        details['admission_type'] = 'emergency'
    elif any(term in lower for term in ('planned', 'scheduled', 'elective')):
        details['admission_type'] = 'planned'
    admission_date = _normalise_relative_date(value)
    if admission_date:
        details['admission_date'] = admission_date
    amount = re.search(r'(?:estimated(?:\s+(?:cost|amount))?|cost|amount|₹|inr|rs\.?)[\s:=₹]*([\d,]+(?:\.\d{1,2})?)', value, re.I)
    if amount:
        details['estimated_amount'] = amount.group(1).replace(',', '')
    treatment = re.search(r'\b(?:treatment|reason|procedure)\s*(?:is|:|-)?\s*([^,.;]+)', value, re.I)
    if treatment:
        details['treatment_summary'] = treatment.group(1).strip()
    elif re.search(r'\bfor\s+[^,.;]+', value, re.I):
        candidate = re.search(r'\bfor\s+([^,.;]+)', value, re.I).group(1).strip()
        if not re.search(r'claim|cashless|assistance', candidate, re.I):
            details['treatment_summary'] = candidate
    previous = next((message.get('text', '').casefold() for message in reversed(record.get('messages', [])) if message.get('role') == 'assistant'), '')
    if value.casefold().rstrip('!.') in {'yes', 'yes, available', 'available', 'ready'} and 'identity' in previous:
        details['identity_ready'] = True
    elif 'identity' in lower and any(term in lower for term in ('available', 'ready', 'have')):
        details['identity_ready'] = True
    return details


def _cashless_missing(details):
    required = [('hospital_id', 'hospital'), ('admission_type', 'admission type'), ('admission_date', 'admission date'),
                ('treatment_summary', 'treatment description'), ('estimated_amount', 'estimated cost')]
    return [label for key, label in required if not details.get(key)]


def _cashless_summary(details):
    labels = [('hospital_name', 'Hospital'), ('hospital_branch', 'Branch'), ('admission_type', 'Admission'),
              ('admission_date', 'Date'), ('treatment_summary', 'Treatment'), ('estimated_amount', 'Estimated cost')]
    return '\n'.join(f"• {label}: {details[key]}" for key, label in labels if details.get(key))


def handle(record, text, confirmation=False, parameters=None):
    fallback_intent, fallback_parameters = classify(text)
    history = [
        {'role': message.get('role', 'assistant'), 'text': message.get('text', '')}
        for message in record.get('messages', [])[-6:]
    ]
    # A short numeric reply is meaningful only in the context of the
    # preceding assistant question. Preserve that context even if the model
    # is unavailable or returns an overly broad policy intent.
    bank_digits_reply = bool(re.fullmatch(r'\d{4}', text.strip())) and any(
        message['role'] == 'assistant' and 'bank account' in message['text'].casefold() and 'last 4' in message['text'].casefold()
        for message in history
    )
    if bank_digits_reply:
        fallback_intent, fallback_parameters = 'update_claim_field', {'field': 'bank_account_last4', 'value': text.strip()}
    model_decision = providers.classify_intent(text, {
        'journey': record.get('journey'),
        'status': record.get('status'),
        'missing_documents': _missing(record),
        'issues': record.get('issues', []),
        'has_submitted_claim': bool(store.get_claim(record['id'])),
    }, {'intent': fallback_intent, 'parameters': fallback_parameters}, history=history)
    intent = model_decision.get('intent', fallback_intent) if model_decision else fallback_intent
    # Preserve safe lexical parameters when the model omits optional values
    # such as reimbursement vs cashless journey.
    inferred = {**fallback_parameters, **(model_decision.get('parameters', {}) if model_decision else {})}
    parameters = {**inferred, **(parameters or {})}
    if bank_digits_reply:
        intent = 'update_claim_field'
        parameters.update({'field': 'bank_account_last4', 'value': text.strip()})
    # A confirmation after “your application is open” is consent to continue
    # the claim workflow, not a request to manually re-enter hospital fields.
    # Let the existing document guidance action identify the next real upload.
    if _affirmative_document_follow_up(text, history, record):
        intent = 'upload_document_guidance'
        parameters = {**parameters, 'journey': 'reimbursement'}
    cashless_extracted = _extract_cashless_details(text, record) if record.get('journey') == 'cashless' else {}
    if cashless_extracted:
        intent = 'update_cashless_details'
        parameters['cashless_details'] = cashless_extracted
    parameters.setdefault('journey', 'cashless' if 'cashless' in text.casefold() else 'reimbursement')
    result = {'intent': intent, 'action': None, 'needs_confirmation': False, 'suggested_questions': []}
    # Run the journey-specific LangGraph checkpoint before handling the turn.
    # Its tools inspect the current persisted state; action execution below
    # still performs the final validation and mutation.
    try:
        checkpoint = run_agent(record, text, 'cashless' if record.get('journey') == 'cashless' else 'reimbursement')
        checkpoint_details = dict(checkpoint.get('details') or {})
        checkpoint_details.pop('application', None)
        result['agent'] = {'journey': record.get('journey', 'reimbursement'), 'stage': checkpoint.get('stage'),
                           'next_step': checkpoint.get('next_step'), 'details': checkpoint_details}
    except Exception as error:
        providers.logger.warning('LangGraph agent checkpoint failed: %s', error)
    answer = ''

    if intent == 'update_cashless_details':
        existing = dict((record.get('cashless') or {}).get('details') or {})
        extracted = dict(parameters.get('cashless_details') or {})
        ambiguous = bool(extracted.pop('hospital_ambiguous', False))
        extracted.setdefault('member_id', record.get('member_id'))
        extracted.pop('hospital_name', None)
        extracted.pop('hospital_branch', None)
        merged = {**existing, **extracted}
        # Persist explicit values through the same cashless service used by
        # the existing form. A directory match is required before checking
        # network status; ambiguous branches are held until the user gives a
        # location.
        if extracted:
            cashless.save_details(record, {**extracted, '_source': 'assistant'})
            record = run(record)
            store.save(record)
        display = {**merged}
        if display.get('hospital_id'):
            hospital = next((item for item in HOSPITALS if item['id'] == display['hospital_id']), None)
            if hospital:
                display.update({'hospital_name': hospital['name'], 'hospital_branch': f"{hospital['area']}, {hospital['city']}"})
        if ambiguous or not display.get('hospital_id'):
            answer = ('I captured the other cashless details. Which hospital branch or city should I use? '
                      'I will check the directory only after the location is clear.')
            result['action'] = 'update_cashless_details'
            result['cashless_details'] = display
        else:
            result['action'] = 'update_cashless_details'
            result['cashless_details'] = display
            hospital = next(item for item in HOSPITALS if item['id'] == display['hospital_id'])
            network = 'sample network' if hospital['network'] == 'sample_network' else 'unverified arrangement'
            missing_details = _cashless_missing(display)
            if missing_details:
                answer = 'Captured details:\n' + _cashless_summary(display) + f"\n\nNext: please provide your {missing_details[0]}."
            elif not display.get('identity_ready'):
                answer = 'Captured details:\n' + _cashless_summary(display) + '\n\nNext: confirm that the patient identity and policy details are available for the hospital desk.'
            else:
                documents = _missing(record)
                answer = 'Captured details:\n' + _cashless_summary(display) + f"\n\nDirectory status: {network}. This is a simulated network check.\n\nNext: upload your hospital admission advice."
                result['document_kind'] = documents[0] if documents and documents[0] in ('admission_advice', 'cost_estimate') else 'admission_advice'
                result['missing_documents'] = documents
                result['action'] = 'upload_document_guidance'
    elif intent in ('general_chat', 'policy_question'):
        # Every conversational turn goes through the configured LLM. Only
        # explicit policy questions retrieve clauses; greetings, thanks and
        # general insurance education stay ungrounded and do not get forced
        # into unrelated policy citations.
        clauses = retrieve(text, corpus=policy_context(record)['clauses']) if intent == 'policy_question' else []
        answer_data = providers.explain(text, clauses, {'issues': record.get('issues', []), 'status': record.get('status'), 'journey': record.get('journey'), 'cashless': record.get('cashless'), 'fields': {k: v.get('value') for k, v in record.get('fields', {}).items()}}, history=history)
        answer = answer_data['answer']
        result['citations'] = [c for c in clauses if c['id'] in answer_data.get('clause_ids', [])]
    elif intent == 'start_claim':
        answer = ('I can guide you through a reimbursement claim one step at a time.' if parameters['journey'] == 'reimbursement' else 'I can guide you through cashless preauthorization one step at a time.')
        if record and record.get('journey') != parameters['journey'] and record.get('issued_policy'):
            # Keep each journey independently persisted while reusing the
            # selected policy and insured member from the user's workspace.
            record = store.create(
                'My ' + ('cashless assistance' if parameters['journey'] == 'cashless' else 'reimbursement claim'),
                parameters['journey'], record.get('issued_policy'), record.get('member_id', 'aarav'), record.get('owner_id', 'demo-user'))
            # Carry the selected policy schedule into the new journey so
            # policy/member fields remain available to validation immediately.
            policy = record.get('issued_policy')
            if policy and policy.get('id') == ISSUED_POLICY['id']:
                _, extracted = customer_policy_document(policy, record.get('member_id', 'aarav'))
            else:
                member = next((m for m in policy.get('members', []) if m.get('id') == record.get('member_id')), policy.get('members', [{}])[0])
                extracted = [{'key': 'full_name', 'value': member.get('name', policy.get('holder', '')), 'page': 1, 'quote': 'Insured: ' + member.get('name', policy.get('holder', ''))},
                             {'key': 'policy_number', 'value': policy.get('number', ''), 'page': 1, 'quote': 'Policy number: ' + policy.get('number', '')},
                             {'key': 'policy_start', 'value': policy.get('start_date', ''), 'page': 1, 'quote': 'Start date: ' + policy.get('start_date', '')},
                             {'key': 'policy_end', 'value': policy.get('end_date', ''), 'page': 1, 'quote': 'End date: ' + policy.get('end_date', '')}]
            record['documents'].append({'id': str(uuid4()), 'name': 'existing-policy-schedule.pdf', 'kind': 'policy', 'mime': 'application/pdf', 'size': 0, 'page_count': 1, 'path': '', 'pages': [], 'extracted': extracted, 'storage_uri': None, 'provider': 'Customer policy schedule', 'uploaded_at': store.now(), 'preloaded': True})
            store.save(record)
            result['action'] = 'start_claim'
            answer += ' I started a new application using your selected policy and insured member.'
        elif record:
            result['action'] = 'resume_claim'
            answer += ' Your current application is open. You can upload your claim documents here instead of entering every hospital detail manually. I will extract the fields, compare the documents, and then tell you what details are missing or inconsistent.'
        else:
            answer += ' Select your policy and the insured member in the claim workspace to begin.'
        if record and parameters['journey'] == 'reimbursement':
            missing = _missing(record)
            result['missing_documents'] = missing
            if missing:
                result['document_kind'] = missing[0]
                if result['action'] == 'start_claim':
                    answer += ' You can upload the documents here; I will extract the details before asking for anything that is still missing.'
        result['suggested_questions'] = ['Which documents are needed?', 'Show my claim status']
    elif intent == 'get_claim_status':
        claim = store.get_claim(record['id'])
        if claim:
            answer = f"Your claim is currently **{claim.get('status', 'unknown').replace('_', ' ')}**. The latest update is {claim.get('updated_at', 'not available')}."
            result['claim'] = claim
            result['action'] = 'get_claim_status'
        else:
            answer = 'There is no submitted claim for this application yet. I can help you complete the preparation first.'
    elif intent == 'get_claim_details':
        answer = 'Here are the details currently saved for this application.'
        result['action'] = 'get_claim_details'
        result['claim_details'] = record.get('claim_details', {})
    elif intent == 'upload_document_guidance':
        missing = _missing(record)
        if any(term in text.casefold() for term in ('multiple', 'more than one', 'several', 'many documents')):
            answer = 'Yes. You can add multiple documents of the same type, such as several hospital bills. Upload them one at a time using the document button; each file will be checked and kept as evidence.'
        elif missing:
            readable = ', '.join(kind.replace('_', ' ') for kind in missing)
            answer = 'The next document to add is your ' + missing[0].replace('_', ' ') + '. You can upload it here and I will extract the important details, compare it with the other documents, and point out any missing fields or discrepancies. I will apply policy checks when the relevant policy document is available. The checklist still needs: ' + readable + '.'
            result['document_kind'] = missing[0]
        else:
            answer = 'All required documents are present. I will now check the extracted details and show you anything that needs attention.'
        result['action'] = 'upload_document_guidance'
        result['missing_documents'] = missing
    elif intent == 'get_validation_issues':
        record = run(record)
        issues = record.get('issues', [])
        answer = ('There are no blocking issues right now. You can review the extracted details.' if not issues else 'I found these items to check:\n' + '\n'.join('• ' + issue['message'] for issue in issues))
        result['action'] = 'get_validation_issues'
        result['issues'] = issues
    elif intent == 'update_claim_field':
        field, value = parameters.get('field'), parameters.get('value', '').strip()
        if field not in FIELDS or not value:
            answer = 'Tell me the field and new value, for example: “Change hospital name to City Hospital”.'
        elif store.get_claim(record['id']) and store.get_claim(record['id']).get('status') not in ('clarification_requested',):
            answer = 'This submitted claim is locked. If the insurer asked for clarification, upload the requested information through the clarification step.'
        else:
            record['corrections'][field] = value
            store.mutate(record, 'field_confirmed', {'field': field, 'value': value, 'source': 'assistant'})
            record = run(record)
            answer = f"I updated {FIELDS[field].lower()} to “{value}” and rechecked the application."
            result['action'] = 'update_claim_field'
            result['field'] = field
    elif intent == 'confirm_review':
        record = run(record)
        if any(i['severity'] == 'error' for i in record.get('issues', [])):
            answer = 'I cannot confirm the review yet. Please resolve the blocking items shown in Review details.'
        elif not confirmation:
            answer = 'Please confirm that the extracted claim details are correct. This confirmation records your review.'
            result['needs_confirmation'] = True
        else:
            record['reviewed_at'] = store.now()
            record['audit'].append({'at': store.now(), 'event': 'review_confirmed', 'details': {'source': 'assistant'}})
            answer = 'Your review is confirmed. The claim packet can now be prepared.'
            result['action'] = 'confirm_review'
    elif intent == 'prepare_packet':
        record = run(record)
        if record.get('status') != 'ready' or not record.get('reviewed_at'):
            answer = 'Finish the review and resolve all blocking items before I prepare the packet.'
        elif not confirmation:
            answer = 'Would you like me to prepare the claim packet from these reviewed documents?'
            result['needs_confirmation'] = True
        else:
            record['packet_generated_at'] = record.get('packet_generated_at') or utc_now()
            record['revision'] += 1
            record['audit'].append({'at': utc_now(), 'event': 'claim_packet_generated', 'details': {'source': 'assistant'}})
            answer = 'The claim packet is ready. You can download it or submit the claim with your explicit consent.'
            result['action'] = 'prepare_packet'
    elif intent == 'submit_claim':
        existing = store.get_claim(record['id'])
        if existing:
            answer = 'This claim has already been submitted. I can show you its acknowledgement and current status.'
            result['claim'] = existing
        elif record.get('journey') == 'cashless':
            answer = 'Cashless requests use preauthorization. I can continue the cashless preparation flow from this application.'
        elif not confirmation:
            answer = 'Your claim will be sent to the simulated insurer after you explicitly confirm. Do you want to submit it?'
            result['needs_confirmation'] = True
        else:
            record = run(record)
            if record.get('status') != 'ready' or not record.get('packet_generated_at'):
                answer = 'The claim must be reviewed and the packet prepared before submission.'
            else:
                amount = record['fields'].get('bill_total', {}).get('value', '0').replace(',', '') or '0'
                claim = {'application_id': record['id'], 'claim_id': 'CLM-' + uuid4().hex[:12].upper(), 'status': 'draft', 'submitted_at': None, 'updated_at': utc_now(), 'claim_amount': amount, 'approved_amount': None, 'explanation': '', 'settlement': None, 'timeline': [], 'packet_generated_at': record.get('packet_generated_at'), 'document_count': len(record['documents']), 'claim_details': record.get('claim_details', {})}
                claim = simulated_insurer.submit(record, claim)
                record['status'] = 'submitted'
                store.mutate(record, 'claim_submitted', {'claim_id': claim['claim_id'], 'acknowledgement_id': claim['acknowledgement_id'], 'source': 'assistant'})
                store.save_claim(claim)
                answer = f"Your claim was submitted to the simulated insurer. Acknowledgement ID: {claim['acknowledgement_id']}."
                result['action'] = 'submit_claim'
                result['claim'] = claim
    elif intent == 'respond_to_clarification':
        claim = store.get_claim(record['id'])
        if not claim or claim.get('status') != 'clarification_requested':
            answer = 'There is no open clarification request for this application.'
        elif len(text.strip()) < 10:
            answer = 'Please tell me the requested information or upload the additional document, using at least a few words.'
        else:
            claim = simulated_insurer.event(record, claim, 'resubmit', {'explanation': text.strip()})
            record['status'] = 'claim_resubmitted'
            store.mutate(record, 'claim_clarification_resubmitted', {'claim_id': claim['claim_id'], 'source': 'assistant'})
            answer = 'I sent your clarification to the simulated insurer. You can track the updated status here.'
            result['action'] = 'respond_to_clarification'
            result['claim'] = claim

    # Workflow responses come from the actual backend result. Do not send
    # workflow turns through policy retrieval: that made document/status/action
    # questions repeatedly return policy clauses instead of doing the work.
    # Policy citations are reserved for the explicit policy_question branch.
    state = record.setdefault('assistant_state', {})
    claim = store.get_claim(record['id'])
    state.update({'active_application_id': record['id'], 'claim_id': claim.get('claim_id') if claim else state.get('claim_id'),
                  'claim_type': record.get('journey', 'reimbursement'), 'last_confirmation': bool(confirmation)})
    if result.get('action') in ('start_claim', 'resume_claim'):
        state['stage'] = 'documents' if _missing(record) else 'review'
    elif result.get('action') == 'upload_document_guidance':
        state['stage'] = 'documents'
    elif result.get('action') == 'get_validation_issues':
        state['stage'] = 'review'
    elif result.get('action') == 'confirm_review':
        state['stage'] = 'packet'
    elif result.get('action') == 'prepare_packet':
        state['stage'] = 'submission'
    elif result.get('action') in ('submit_claim', 'respond_to_clarification'):
        state['stage'] = 'tracking'
    elif result.get('action') == 'get_claim_status':
        state['stage'] = 'tracking'
    state['pending_action'] = 'confirmation' if result.get('needs_confirmation') else None
    result['conversation_state'] = dict(state)
    _message(record, text, answer, result.get('citations'))
    updated = run(record)
    # The normal workflow derives preparation status; once an insurer claim
    # exists, preserve the persisted submission/decision state instead of
    # turning it back into "review" on the final checkpoint.
    claim = store.get_claim(record['id'])
    if claim and record.get('journey') != 'cashless':
        updated['status'] = 'claim_' + claim.get('status', 'submitted')
    result['application'] = store.save(updated)
    return result
