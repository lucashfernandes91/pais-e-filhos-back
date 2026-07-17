"""
PDF Export helper for CoParent
Generates PDF from messages and events
"""

from io import BytesIO
from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib import colors

MESSAGE_EXCERPT_LENGTH = 500

ATTACHMENT_LABELS = {
    'image': 'Imagem',
    'pdf': 'PDF',
    'document': 'Documento',
}


def _local(dt):
    """Timestamps no fuso do projeto (hoje UTC; muda junto com o TIME_ZONE)."""
    return timezone.localtime(dt) if timezone.is_aware(dt) else dt


def generate_conversation_pdf(messages, events, conversation_id):
    """
    Generate PDF from messages and events
    
    Args:
        messages: QuerySet of Message objects
        events: QuerySet of Event objects
        conversation_id: ID of conversation
    
    Returns:
        BytesIO: PDF file as bytes
    """
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
    
    styles = getSampleStyleSheet()
    story = []
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1976D2'),
        spaceAfter=30,
    )
    story.append(Paragraph(f"CoParent — Registro Oficial", title_style))
    
    # Metadata
    meta_style = ParagraphStyle(
        'Meta',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#757575'),
        spaceAfter=20,
    )
    now_local = _local(timezone.now())
    story.append(Paragraph(f"<b>Conversa:</b> #{conversation_id}", meta_style))
    story.append(Paragraph(f"<b>Gerado em:</b> {now_local.strftime('%d/%m/%Y às %H:%M')}", meta_style))
    story.append(Spacer(1, 0.3*inch))

    # Messages Section — sem limite: o export é o registro completo.
    if messages:
        story.append(Paragraph("Mensagens", styles['Heading2']))
        story.append(Spacer(1, 0.2*inch))

        for msg in messages:
            sender = msg.sender.first_name or msg.sender.username
            timestamp = _local(msg.created_at).strftime('%d/%m/%Y %H:%M')

            first_read = msg.messageread_set.first()
            if first_read is not None:
                read_at = _local(first_read.read_at).strftime('%d/%m/%Y %H:%M')
                read_status = f"Lido às {read_at}"
            else:
                read_status = "Entregue"

            content = msg.content or ''
            if len(content) > MESSAGE_EXCERPT_LENGTH:
                content = content[:MESSAGE_EXCERPT_LENGTH] + '…'

            attachment_note = ''
            if msg.attachment:
                label = ATTACHMENT_LABELS.get(msg.attachment_type, 'Arquivo')
                attachment_note = f"<i>[Anexo: {label}]</i><br/>"

            msg_text = f"""
            <b>{sender}</b> — {timestamp}<br/>
            {content}<br/>
            {attachment_note}<i>{read_status}</i>
            <br/><br/>
            """
            story.append(Paragraph(msg_text, styles['Normal']))

        story.append(PageBreak())

    # Events Section — sem limite.
    if events:
        story.append(Paragraph("Eventos", styles['Heading2']))
        story.append(Spacer(1, 0.2*inch))

        for event in events:
            creator = event.created_by.first_name or event.created_by.username
            event_date = _local(event.event_date).strftime('%d/%m/%Y %H:%M')
            event_type = event.get_event_type_display()

            event_text = f"""
            <b>{event.title}</b> ({event_type})<br/>
            Data: {event_date}<br/>
            Criado por: {creator}<br/>
            Notas: {event.notes or 'Nenhuma'}<br/>
            <br/>
            """
            story.append(Paragraph(event_text, styles['Normal']))

        story.append(Spacer(1, 0.3*inch))

    # Footer
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#BDBDBD'),
        alignment=1,  # Center
    )
    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph(
        "Este documento é um registro mantido por CoParent Lite.<br/>"
        "Não pode ser editado. Data: " + now_local.strftime('%d/%m/%Y'),
        footer_style
    ))
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    
    return buffer
