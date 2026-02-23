import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from academic.models import AcademicYear, Period

def check_system():
    active_year = AcademicYear.objects.filter(is_active=True).first()
    print(f"Active Year: {active_year}")
    
    if active_year:
        periods = Period.objects.filter(academic_year=active_year).order_by('start_date')
        print(f"Total periods for {active_year}: {periods.count()}")
        for p in periods:
            print(f"- {p.name} (ID: {p.id})")
        
        if periods.count() < 4:
            print("\nWARNING: Less than 4 bimestres found. Creating missing ones...")
            expected = ["I Bimestre", "II Bimestre", "III Bimestre", "IV Bimestre"]
            existing_names = [p.name for p in periods]
            
            from datetime import date
            # Dummy dates if missing
            dummy_dates = [
                (date(active_year.year, 3, 1), date(active_year.year, 5, 15)),
                (date(active_year.year, 5, 20), date(active_year.year, 7, 25)),
                (date(active_year.year, 8, 10), date(active_year.year, 10, 15)),
                (date(active_year.year, 10, 20), date(active_year.year, 12, 20)),
            ]
            
            for i, name in enumerate(expected):
                # Search for similar names or exact
                if not any(name.lower() in p.lower() or p.lower() in name.lower() for p in existing_names):
                    Period.objects.create(
                        name=name,
                        academic_year=active_year,
                        start_date=dummy_dates[i][0],
                        end_date=dummy_dates[i][1]
                    )
                    print(f"Created: {name}")

if __name__ == "__main__":
    check_system()
