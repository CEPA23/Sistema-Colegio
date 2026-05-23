from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0003_alter_attendancerecord_options_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='attendancerecord',
            name='status',
            field=models.CharField(
                choices=[
                    ('present', 'Asistio'),
                    ('absent', 'Falto'),
                    ('tardy', 'Tardanza'),
                    ('justified', 'Justificado'),
                ],
                default='present',
                max_length=20,
            ),
        ),
    ]
