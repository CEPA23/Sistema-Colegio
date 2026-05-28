# Generated manually to scope competencies by assignment.

import django.db.models.deletion
from django.db import migrations, models


def copy_competencies_to_assignments(apps, schema_editor):
    Competency = apps.get_model('academic', 'Competency')
    Indicator = apps.get_model('academic', 'Indicator')
    TeacherCourseAssignment = apps.get_model('academic', 'TeacherCourseAssignment')

    original_competencies = list(
        Competency.objects.select_related('course').prefetch_related('indicator_set').all()
    )
    original_competency_ids = [competency.id for competency in original_competencies]

    for competency in original_competencies:
        assignments = TeacherCourseAssignment.objects.filter(course_id=competency.course_id).order_by(
            'academic_year_id',
            'grade__name',
            'section__name',
            'teacher_id',
        )
        for assignment in assignments:
            copied_competency = Competency.objects.create(
                assignment_id=assignment.id,
                course_id=competency.course_id,
                name=competency.name,
                order=competency.order,
            )
            for indicator in competency.indicator_set.all():
                Indicator.objects.create(
                    competency_id=copied_competency.id,
                    name=indicator.name,
                    order=indicator.order,
                )

    Competency.objects.filter(id__in=original_competency_ids).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('academic', '0017_course_grades'),
    ]

    operations = [
        migrations.AddField(
            model_name='competency',
            name='assignment',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='competencies', to='academic.teachercourseassignment'),
        ),
        migrations.RunPython(copy_competencies_to_assignments, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='competency',
            name='course',
        ),
        migrations.AlterField(
            model_name='competency',
            name='assignment',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='competencies', to='academic.teachercourseassignment'),
        ),
    ]
