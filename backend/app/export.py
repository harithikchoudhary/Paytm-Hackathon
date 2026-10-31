import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from .samples import detailed_pdf
from .policies import POLICY_ID, CLAUSES
from .customer import policy_context
from . import object_store


def packet(app):
    context = policy_context(app)
    line_items = [
        item
        for doc in app.get('documents', [])
        for item in doc.get('line_items', [])
    ]
    eligibility = app.get('eligibility') or {}
    risk = app.get('risk_assessment') or {}
    fields = app.get('fields') or {}
    docs = app.get('documents') or []
    policy_checks = eligibility.get('checks') or []
    source_lines = []
    for key, field in fields.items():
        if not field.get('value'):
            continue
        sources = field.get('sources') or []
        evidence = ', '.join(f"{s.get('document_name', 'document')} p.{s.get('page', '?')}" for s in sources) or 'user-confirmed'
        quote = next((str(s.get('quote', '')).strip() for s in sources if s.get('quote')), '')
        source_lines.append(f"{field.get('label', key)}: {field['value']} (source: {evidence}{'; evidence: ' + quote if quote else ''})")
    document_lines = [
        f"{d.get('name', d.get('kind', 'Document'))} · {d.get('kind', 'unknown')} · {len(d.get('extracted', []))} extracted fields"
        for d in docs
    ]
    item_lines = [
        f"{item.get('description', 'Item')}: INR {item.get('amount', 0)} · {item.get('result', item.get('status', 'review_required'))} · {item.get('reason', 'No explanation recorded.') }"
        for item in line_items
    ]
    check_lines = [
        f"{check.get('id', 'check')}: {check.get('result', 'unknown')} · clause {check.get('clause_id', 'not recorded')} · {check.get('explanation', '')}"
        for check in policy_checks
    ]
    issue_lines = [
        f"{issue.get('severity', 'finding').upper()}: {issue.get('message', 'Validation finding')}"
        for issue in app.get('issues', [])
    ]
    sections = [
        ('What this packet contains', [
            'This ZIP contains a reviewed reimbursement claim summary, the saved claim data or policy reference, and the uploaded source documents available to OneFlow at packet preparation time.',
            'It is a preparation aid. It does not establish coverage, payable amount, insurer approval, or settlement.',
        ]),
        ('Application and review', [
            f"Application: {app.get('title', 'Not available')}", f"Application ID: {app.get('id', 'Not available')}",
            f"Policy reference: {context.get('id', 'Not available')}", f"Reviewed at: {app.get('reviewed_at', 'Not available')}",
            f"Packet prepared at: {app.get('packet_generated_at', 'Not available')}",
            f"Workflow status: {app.get('status', 'Not available')} · revision {app.get('revision', 'Not available')}",
        ]),
        ('Documents included', document_lines),
        ('Captured claim information and evidence', source_lines),
        ('Itemized bill assessment', item_lines or ['No itemized bill lines were extracted from the uploaded evidence.']),
        ('Amount summary', [
            f"Total bill: INR {eligibility.get('bill_total', 'Not available')}",
            f"Indicative eligible amount: INR {eligibility.get('eligible_amount', 'Not available')}",
            f"Needs insurer review: INR {eligibility.get('review_amount', 'Not available')}",
            f"Indicative payable amount: INR {eligibility.get('indicative_payable_amount', 'Not available')}",
            eligibility.get('explanation', 'No eligibility explanation was recorded.'),
        ]),
        ('Policy and validation checks', check_lines or ['No policy-specific checks were available.'],
        ),
        ('Risk assessment', [
            f"Risk level: {risk.get('level', 'not available')}",
            risk.get('explanation', 'No risk explanation was recorded.'),
            f"Signals recorded: {', '.join(str(s) for s in (risk.get('reasons') or [])) or 'None recorded'}",
        ]),
        ('Open findings and next steps', issue_lines or ['No blocking validation findings remain in the saved review.'],),
        ('Submission note', [
            'Submission requires separate explicit user authorization. If submitted through the local workflow, any acknowledgement and insurer event are clearly marked simulated and must not be treated as a real insurer decision.',
        ]),
    ]
    summary = detailed_pdf('Reviewed preliminary reimbursement packet' if app.get('issued_policy') else 'Reviewed reimbursement packet', sections)
    body = BytesIO()
    with ZipFile(body, 'w', ZIP_DEFLATED) as z:
        z.writestr('claim-summary.pdf', summary)
        z.writestr('README.txt', '\n'.join([
            'ONEFLOW CLAIM PACKET',
            '',
            'This packet was assembled from the saved OneFlow application record after review confirmation.',
            'claim-summary.pdf explains the captured evidence, itemized assessment, policy checks, validation findings, risk signals, and next steps.',
            'The included JSON is an audit-friendly machine-readable copy of the same record.',
            'Any submission, acknowledgement, authorization, or settlement in this local workflow is simulated unless an external insurer integration explicitly says otherwise.',
        ]))
        z.writestr('claim-review.json', json.dumps({
            'application_id': app.get('id'),
            'reviewed_at': app.get('reviewed_at'),
            'packet_generated_at': app.get('packet_generated_at'),
            'status': app.get('status'),
            'fields': app.get('fields', {}),
            'documents': [{k: v for k, v in d.items() if k not in ('path', 'pages')} for d in docs],
            'eligibility': eligibility,
            'risk_assessment': risk,
            'validation_findings': app.get('issues', []),
        }, indent=2))
        if app.get('issued_policy'):
            z.writestr('policy-source-reference.json', json.dumps(context, indent=2))
        else:
            z.writestr('claim-data.json', json.dumps({
                'id': app['id'], 'reviewed_at': app['reviewed_at'], 'revision': app['revision'],
                'policy_id': context['id'], 'issued_policy': app.get('issued_policy'), 'fields': app['fields'], 'claim_details': app.get('claim_details', {}), 'reviewer_notes': app['issues'],
                'audit': app['audit'], 'clauses': context['clauses'], 'eligibility': eligibility,
                'risk_assessment': risk, 'line_items': line_items,
            }, indent=2))
        for doc in app['documents']:
            # Storage paths are generated by the server, never derived from user filenames.
            suffix = Path(doc.get('path') or doc.get('name', '')).suffix or '.pdf'
            z.writestr(f"documents/{doc['kind']}-{doc['id']}{suffix}", object_store.read(doc))
    return body.getvalue()
