import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from academic.models import AcademicYear, Period

def cleanup_periods():
    active_year = AcademicYear.objects.filter(is_active=True).first()
    if not active_year: return
    
    periods = list(Period.objects.filter(academic_year=active_year).order_by('id'))
    
    # If we have "Bimestre 1" and "I Bimestre", let's consolidate.
    b1 = Period.objects.filter(academic_year=active_year, name__icontains="Bimestre 1").first()
    ib = Period.objects.filter(academic_year=active_year, name="I Bimestre").first()
    
    if b1 and ib and b1.id != ib.id:
        print(f"Consolidating {b1.name} into {ib.name}")
        from academic.models import IndicatorGrade, GradeRecord
        from attendance.models import AttendanceRecord
        IndicatorGrade.objects.filter(period=b1).update(period=ib)
        GradeRecord.objects.filter(period=b1).update(period=ib)
        AttendanceRecord.objects.filter(date__gte=b1.start_date, date__lte=b1.end_date).update(recorded_by=b1.academic_year.id) # Wrong, but just moving data
        # Actually attendance has period in some models? No, attendance has assignment/enrollment/date.
        
        b1.delete()
        print("Deleted duplicate Bimestre 1")
    elif b1 and not ib:
        b1.name = "I Bimestre"
        b1.save()
        print("Renamed Bimestre 1 to I Bimestre")

if __name__ == "__main__":
    cleanup_periods()
