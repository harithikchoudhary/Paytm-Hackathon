from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from .policies import CLAUSES

LABELS = {'policy': 'Policy schedule', 'bill': 'Hospital bill', 'discharge': 'Discharge summary', 'bank_proof': 'Bank account proof', 'admission_advice': 'Admission advice', 'cost_estimate': 'Hospital cost estimate'}


def pdf_bytes(title, lines):
    out = BytesIO()
    c = canvas.Canvas(out, pagesize=A4)
    c.setTitle(title)
    c.setFillColorRGB(.04, .14, .2)
    c.setFont('Helvetica-Bold', 23)
    c.drawString(48, 790, 'OneFlow AI')
    c.setFont('Helvetica', 11)
    c.drawString(48, 765, 'SYNTHETIC SAMPLE - NOT A REAL FINANCIAL DOCUMENT')
    c.setFont('Helvetica-Bold', 16)
    c.drawString(48, 720, title)
    y = 680
    import textwrap
    for line in lines:
        for wrapped in textwrap.wrap(str(line), width=85) or ['']:
            if y < 60:
                c.showPage()
                c.setFont('Helvetica', 11)
                y = 780
            c.setFont('Helvetica', 11)
            c.drawString(48, y, wrapped)
            y -= 20
        y -= 5
    c.save()
    return out.getvalue()


def detailed_pdf(title, sections, subtitle='Prepared from the saved OneFlow application record'):
    """Render a readable, evidence-oriented document for a downloaded workflow artifact.

    ``sections`` is a list of ``(heading, lines)`` pairs.  Keeping this renderer
    alongside the existing sample renderer means the API routes retain their
    current download contracts while the generated documents can explain the
    actual workflow state in enough detail for a customer or reviewer.
    """
    out = BytesIO()
    c = canvas.Canvas(out, pagesize=A4)
    c.setTitle(title)
    import textwrap

    def header():
        c.setFillColorRGB(.04, .14, .2)
        c.setFont('Helvetica-Bold', 20)
        c.drawString(48, 795, 'OneFlow AI')
        c.setFont('Helvetica', 9)
        c.setFillColorRGB(.28, .38, .46)
        c.drawString(48, 778, subtitle)
        c.setStrokeColorRGB(.78, .87, .92)
        c.line(48, 765, 547, 765)

    def footer():
        c.setStrokeColorRGB(.84, .89, .93)
        c.line(48, 42, 547, 42)
        c.setFillColorRGB(.38, .45, .5)
        c.setFont('Helvetica', 8)
        c.drawString(48, 28, 'OneFlow AI · Generated from saved application data')
        c.drawRightString(547, 28, f'Page {c.getPageNumber()}')

    header()
    c.setFillColorRGB(.04, .14, .2)
    c.setFont('Helvetica-Bold', 17)
    c.drawString(48, 735, title)
    y = 705
    for heading, lines in sections:
        if y < 105:
            footer(); c.showPage(); header(); y = 735
        c.setFillColorRGB(.02, .39, .7)
        c.setFont('Helvetica-Bold', 12)
        c.drawString(48, y, str(heading))
        y -= 21
        c.setFillColorRGB(.08, .16, .22)
        for line in lines or ['Not available']:
            wrapped_lines = textwrap.wrap(str(line), width=82) or ['']
            for wrapped in wrapped_lines:
                if y < 70:
                    footer(); c.showPage(); header(); y = 735
                c.setFont('Helvetica', 9.5)
                c.drawString(58, y, wrapped)
                y -= 15
            y -= 2
        y -= 9
    footer()
    c.save()
    return out.getvalue()


def sample(kind, conflict=False):
    name = 'Amulya' if kind in ('admission_advice', 'cost_estimate') else ('Aarav Shah' if kind == 'bill' and conflict else 'Aarav Sharma')
    common = [f'Patient name: {name}']
    lines = {
        'policy': common + ['Policy number: OF-2026-001', 'Policy start: 2026-01-01', 'Policy end: 2026-12-31', 'Sum insured INR: 500000'],
        'bill': common + ['Hospital name: Sunrise Care Hospital', 'Admission date: 2026-10-12', 'Discharge date: 2026-10-15',
                          'Room charges: INR 18000', 'Doctor consultation: INR 8500', 'Medicines: INR 7500',
                          'Diagnostics: INR 6500', 'Non-medical convenience: INR 1500', 'Nursing charges: INR 6500',
                          'Bill total INR: 48500'],
        'discharge': common + ['Hospital name: Sunrise Care Hospital', 'Admission date: 2026-10-12', 'Discharge date: 2026-10-15'],
        'bank_proof': common + ['Bank account last4: 4821', 'Bank name: Synthetic Demo Bank'],
        'admission_advice': common + ['Hospital name: Sunrise Care Hospital', 'Admission date: 2026-10-31', 'Treatment summary: Planned orthopaedic procedure advised by the treating doctor'],
        'cost_estimate': common + ['Hospital name: Sunrise Care Hospital', 'Estimated amount INR: 80000'],
    }[kind]
    return pdf_bytes(LABELS[kind], lines)


def issued_schedule(policy, member_id):
    member = next(m for m in policy['members'] if m['id'] == member_id)
    values = {'full_name': member['name'], 'policy_number': policy['number'], 'policy_start': policy['start_date'], 'policy_end': policy['end_date']}
    labels = {'full_name': 'Patient name', 'policy_number': 'Policy number', 'policy_start': 'Policy start', 'policy_end': 'Policy end'}
    extracted = [{'key': k, 'value': v, 'page': 1, 'quote': f'{labels[k]}: {v}'} for k, v in values.items()]
    content = pdf_bytes('Fictional issued policy schedule', [policy['notice'], f"Reference product: {policy['product']}",
        f"Reference insurer: {policy['insurer']}", f"Product UIN: {policy['uin']}",
        *[e['quote'] for e in extracted], f"Fictional sum insured INR: {policy['sum_insured']}",
        'Insured members: ' + ', '.join(m['name'] for m in policy['members']),
        'This demonstration schedule is generated by OneFlow, not issued by the insurer.'])
    return content, extracted


def policy_pdf():
    # Explicit page breaks match the stored clause page metadata.
    out = BytesIO()
    c = canvas.Canvas(out, pagesize=A4)
    import textwrap
    for page in (1, 2):
        c.setFont('Helvetica-Bold', 20)
        c.drawString(48, 790, 'Intentra Health - Health Policy Schedule')
        c.setFont('Helvetica', 10)
        c.drawString(48, 765, 'DEMONSTRATION ONLY - NOT AN INSURANCE PRODUCT')
        y = 710
        for clause in [x for x in CLAUSES if x['page'] == page]:
            c.setFont('Helvetica-Bold', 13)
            c.drawString(48, y, f"{clause['id']} | {clause['section']}")
            y -= 28
            c.setFont('Helvetica', 11)
            for line in textwrap.wrap(clause['text'], 85):
                c.drawString(48, y, line)
                y -= 19
            y -= 35
        c.showPage()
    c.save()
    return out.getvalue()
