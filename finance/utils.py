from decimal import Decimal
from io import BytesIO
import os

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def _normalize_payments(payment_or_payments):
    if isinstance(payment_or_payments, (list, tuple)):
        return list(payment_or_payments)
    return [payment_or_payments]


def generate_payment_receipt(payment_or_payments):
    payments = _normalize_payments(payment_or_payments)
    if not payments:
        raise ValueError("Se requiere al menos un pago para generar la boleta.")

    primary_payment = payments[0]
    is_batch = len(payments) > 1
    total_amount = sum((payment.amount for payment in payments), Decimal("0.00"))

    buffer = BytesIO()
    width = 210 * mm
    height = 120 * mm if is_batch else 100 * mm

    p = canvas.Canvas(buffer, pagesize=(width, height))

    school = primary_payment.fee.enrollment.academic_year.school
    student = primary_payment.fee.enrollment.student

    p.setStrokeColor(colors.HexColor("#d7e1ee"))
    p.roundRect(5 * mm, 5 * mm, width - 10 * mm, height - 10 * mm, 3 * mm, stroke=1, fill=0)

    if school.logo:
        try:
            logo_path = school.logo.path
            if os.path.exists(logo_path):
                p.drawImage(
                    logo_path,
                    15 * mm,
                    height - 25 * mm,
                    width=20 * mm,
                    height=15 * mm,
                    preserveAspectRatio=True,
                    mask="auto",
                )
        except Exception:
            pass

    p.setFont("Helvetica-Bold", 16)
    p.drawCentredString(width / 2, height - 15 * mm, school.name.upper())

    p.setFont("Helvetica", 10)
    if school.ruc:
        p.drawCentredString(width / 2, height - 20 * mm, f"RUC: {school.ruc}")

    p.drawCentredString(width / 2, height - 25 * mm, school.address[:80])

    p.setStrokeColor(colors.lightgrey)
    p.line(10 * mm, height - 32 * mm, width - 10 * mm, height - 32 * mm)

    p.setFont("Helvetica-Bold", 14)
    p.drawString(15 * mm, height - 42 * mm, "BOLETA DE PAGO ELECTRONICA")
    p.setFont("Helvetica", 12)
    p.drawRightString(width - 15 * mm, height - 42 * mm, f"N° 001 - {str(primary_payment.id).zfill(6)}")

    p.setFont("Helvetica-Bold", 10)
    p.drawString(15 * mm, height - 55 * mm, "ALUMNO:")
    p.setFont("Helvetica", 10)
    p.drawString(35 * mm, height - 55 * mm, f"{student.last_name}, {student.first_name}")

    p.setFont("Helvetica-Bold", 10)
    p.drawString(15 * mm, height - 62 * mm, "CONCEPTO:")
    p.setFont("Helvetica", 10)
    concept_display = f"{primary_payment.fee.get_concept_display()}"
    if is_batch and primary_payment.fee.concept == "pension":
        months = ", ".join(
            payment.fee.get_pension_month_display()
            for payment in payments
            if payment.fee.pension_month
        )
        concept_display += f" ({months})"
    elif primary_payment.fee.concept == "pension":
        concept_display += f" - {primary_payment.fee.get_pension_month_display()}"
    elif primary_payment.fee.concept == "libro" and primary_payment.fee.course:
        concept_display += f": {primary_payment.fee.course.name}"
    p.drawString(38 * mm, height - 62 * mm, concept_display[:90])

    p.setFont("Helvetica-Bold", 10)
    p.drawRightString(width - 40 * mm, height - 55 * mm, "FECHA:")
    p.setFont("Helvetica", 10)
    p.drawString(width - 38 * mm, height - 55 * mm, primary_payment.payment_date.strftime("%d/%m/%Y"))

    if is_batch:
        p.setFont("Helvetica-Bold", 10)
        p.drawString(15 * mm, height - 70 * mm, "DETALLE:")
        y = height - 76 * mm
        for payment in payments:
            month_label = (
                payment.fee.get_pension_month_display()
                if payment.fee.concept == "pension"
                else payment.fee.get_concept_display()
            )
            p.setFont("Helvetica", 9)
            p.drawString(18 * mm, y, f"- {month_label}: S/ {payment.amount:.2f}")
            y -= 6 * mm

    if primary_payment.comment:
        p.setFont("Helvetica-Oblique", 9)
        comment_y = 16 * mm if is_batch else height - 72 * mm
        p.drawString(15 * mm, comment_y, f"Nota: {primary_payment.comment}")

    p.setFillColor(colors.HexColor("#f8fafc"))
    p.rect(width - 60 * mm, 15 * mm, 45 * mm, 15 * mm, fill=1, stroke=0)
    p.setFillColor(colors.black)
    p.setFont("Helvetica-Bold", 12)
    p.drawString(width - 55 * mm, 21 * mm, "TOTAL:")
    p.drawRightString(width - 20 * mm, 21 * mm, f"S/ {total_amount:.2f}")

    p.setFont("Helvetica-Oblique", 8)
    p.drawCentredString(
        width / 2,
        10 * mm,
        "Gracias por su pago. Este documento es un comprobante de operacion interna.",
    )

    p.showPage()
    p.save()

    buffer.seek(0)
    return buffer
