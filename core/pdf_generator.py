"""
PDF Export helper for CoParent
Generates PDF from messages and events
"""

from io import BytesIO
from datetime import datetime
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib import colors


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
    story.append(Paragraph(f"<b>Conversa:</b> #{conversation_id}", meta_style))
    story.append(Paragraph(f"<b>Gerado em:</b> {datetime.now().strftime('%d/%m/%Y às %H:%M')}", meta_style))
    story.append(Spacer(1, 0.3*inch))
    
    # Messages Section
    if messages:
        story.append(Paragraph("Mensagens", styles['Heading2']))
        story.append(Spacer(1, 0.2*inch))
        
        for msg in messages[:100]:  # Limit to 100 messages
            sender = msg.sender.first_name or msg.sender.username
            timestamp = msg.created_at.strftime('%d/%m/%Y %H:%M')
            
            # Check if read
            read_status = "Lido"
            if msg.messageread_set.exists():
                read_at = msg.messageread_set.first().read_at.strftime('%H:%M')
                read_status = f"Lido às {read_at}"
            else:
                read_status = "Entregue"
            
            msg_text = f"""
            <b>{sender}</b> — {timestamp}<br/>
            {msg.content[:200]}...<br/>
            <i style="color: #999">{read_status}</i>
            <br/><br/>
            """
            story.append(Paragraph(msg_text, styles['Normal']))
        
        story.append(PageBreak())
    
    # Events Section
    if events:
        story.append(Paragraph("Eventos", styles['Heading2']))
        story.append(Spacer(1, 0.2*inch))
        
        for event in events[:50]:  # Limit to 50 events
            creator = event.created_by.first_name or event.created_by.username
            event_date = event.event_date.strftime('%d/%m/%Y %H:%M')
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
        "Este documento é um registro oficial mantido por CoParent Lite.<br/>"
        "Não pode ser editado. Data: " + datetime.now().strftime('%d/%m/%Y'),
        footer_style
    ))
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    
    return buffer
