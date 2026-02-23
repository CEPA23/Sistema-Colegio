from academic.models import Period, AcademicYear
active_year = AcademicYear.objects.filter(is_active=True).first()
print(f"Active Year: {active_year}")
if active_year:
    periods = Period.objects.filter(academic_year=active_year)
    print(f"Total periods in DB for this year: {periods.count()}")
    for p in periods:
        print(f"- {p.name} (id: {p.id})")
else:
    print("No active academic year found.")
