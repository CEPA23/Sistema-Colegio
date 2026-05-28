# Generated manually to scope indicators by unit.

import django.db.models.deletion
from django.db import migrations, models


def seed_units_and_attach_indicators(apps, schema_editor):
    TeacherCourseAssignment = apps.get_model('academic', 'TeacherCourseAssignment')
    Unit = apps.get_model('academic', 'Unit')
    Indicator = apps.get_model('academic', 'Indicator')

    assignments = TeacherCourseAssignment.objects.select_related(
        'course',
        'section__grade',
        'academic_year',
    ).all()

    for assignment in assignments:
        indicators = Indicator.objects.filter(competency__assignment_id=assignment.id)
        if not indicators.exists():
            continue

        unit, _ = Unit.objects.get_or_create(
            assignment_id=assignment.id,
            name='Unidad 1',
            defaults={'order': 1},
        )
        indicators.filter(unit__isnull=True).update(unit=unit)


class Migration(migrations.Migration):

    dependencies = [
        ('academic', '0018_competency_assignment'),
    ]

    operations = [
        migrations.CreateModel(
            name='Unit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('order', models.PositiveIntegerField(default=1)),
                ('assignment', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='units', to='academic.teachercourseassignment')),
            ],
            options={
                'ordering': ('order', 'id'),
                'unique_together': {('assignment', 'name')},
            },
        ),
        migrations.AddField(
            model_name='indicator',
            name='unit',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='indicators', to='academic.unit'),
        ),
        migrations.RunPython(seed_units_and_attach_indicators, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='indicator',
            name='unit',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='indicators', to='academic.unit'),
        ),
    ]
