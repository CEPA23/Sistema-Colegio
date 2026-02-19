from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import landscape
from reportlab.lib.units import mm
from reportlab.lib import colors
from django.conf import settings
import os

def generate_payment_receipt(payment):
    buffer = BytesIO()
    # Medidas: 210mm x 100mm
    width = 210 * mm
    height = 100 * mm
    
    p = canvas.Canvas(buffer, pagesize=(width, height))
    
    school = payment.fee.enrollment.academic_year.school
    student = payment.fee.enrollment.student
    
    # Dibujar borde decorativo
    p.setStrokeColor(colors.HexColor('#d7e1ee'))
    p.roundRect(5*mm, 5*mm, width - 10*mm, height - 10*mm, 3*mm, stroke=1, fill=0)
    
    # Logo del colegio (si existe)
    if school.logo:
        try:
            logo_path = school.logo.path
            if os.path.exists(logo_path):
                p.drawImage(logo_path, 15*mm, height - 25*mm, width=20*mm, height=15*mm, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass

    # Cabecera - Nombre del Colegio y RUC
    p.setFont("Helvetica-Bold", 16)
    p.drawCentredString(width/2, height - 15*mm, school.name.upper())
    
    p.setFont("Helvetica", 10)
    if school.ruc:
        p.drawCentredString(width/2, height - 20*mm, f"RUC: {school.ruc}")
    
    p.drawCentredString(width/2, height - 25*mm, school.address[:80])
    
    # Linea separadora
    p.setStrokeColor(colors.lightgrey)
    p.line(10*mm, height - 32*mm, width - 10*mm, height - 32*mm)
    
    # Titulo del documento
    p.setFont("Helvetica-Bold", 14)
    p.drawString(15*mm, height - 42*mm, "BOLETA DE PAGO ELECTRÓNICA")
    p.setFont("Helvetica", 12)
    p.drawRightString(width - 15*mm, height - 42*mm, f"N° 001 - {str(payment.id).zfill(6)}")
    
    # Información del Alumno y Fecha
    p.setFont("Helvetica-Bold", 10)
    p.drawString(15*mm, height - 55*mm, "ALUMNO:")
    p.setFont("Helvetica", 10)
    p.drawString(35*mm, height - 55*mm, f"{student.last_name}, {student.first_name}")
    
    p.setFont("Helvetica-Bold", 10)
    p.drawString(15*mm, height - 62*mm, "CONCEPTO:")
    p.setFont("Helvetica", 10)
    concept_display = f"{payment.fee.get_concept_display()}"
    if payment.fee.concept == 'pension':
        concept_display += f" - {payment.fee.get_pension_month_display()}"
    elif payment.fee.concept == 'libro' and payment.fee.course:
        concept_display += f": {payment.fee.course.name}"
    p.drawString(38*mm, height - 62*mm, concept_display)
    
    p.setFont("Helvetica-Bold", 10)
    p.drawRightString(width - 40*mm, height - 55*mm, "FECHA:")
    p.setFont("Helvetica", 10)
    p.drawString(width - 38*mm, height - 55*mm, payment.payment_date.strftime("%d/%m/%Y"))
    
    # Comentario
    if payment.comment:
        p.setFont("Helvetica-Oblique", 9)
        p.drawString(15*mm, height - 72*mm, f"Nota: {payment.comment}")
    
    # Recuadro de Monto Total
    p.setFillColor(colors.HexColor('#f8fafc'))
    p.rect(width - 60*mm, 15*mm, 45*mm, 15*mm, fill=1, stroke=0)
    p.setFillColor(colors.black)
    p.setFont("Helvetica-Bold", 12)
    p.drawString(width - 55*mm, 21*mm, "TOTAL:")
    p.drawRightString(width - 20*mm, 21*mm, f"S/ {payment.amount:.2f}")
    
    p.setFont("Helvetica-Oblique", 8)
    p.drawCentredString(width/2, 10*mm, "Gracias por su pago. Este documento es un comprobante de operacion interna.")
    
    p.showPage()
    p.save()
    
    buffer.seek(0)
    return buffer
