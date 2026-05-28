# Generated manually to attach units to academic periods.

import django.db.models.deletion
from django.db import migrations, models


def attach_existing_units_to_first_period(apps, schema_editor):
    Unit = apps.get_model('academic', 'Unit')
    Period = apps.get_model('academic', 'Period')

    periods_by_year = {}
    for period in Period.objects.select_related('academic_year').order_by('academic_year_id', 'start_date', 'name'):
        periods_by_year.setdefault(period.academic_year_id, []).append(period)

    for unit in Unit.objects.select_related('assignment__academic_year').all():
        periods = periods_by_year.get(unit.assignment.academic_year_id, [])
        if not periods:
            continue
        first_period = periods[0]
        unit.period_id = first_period.id
        if unit.order is None or unit.order < 1:
            unit.order = 1
        if not unit.name:
            unit.name = f'Unidad {unit.order}'
        unit.save(update_fields=['period', 'order', 'name'])


class Migration(migrations.Migration):

    dependencies = [
        ('academic', '0019_unit_indicator_unit'),
    ]

    operations = [
        migrations.AddField(
            model_name='unit',
            name='period',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='units', to='academic.period'),
        ),
        migrations.RunPython(attach_existing_units_to_first_period, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='unit',
            name='period',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='units', to='academic.period'),
        ),
    ]
