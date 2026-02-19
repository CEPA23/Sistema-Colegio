from django.db import models

class Student(models.Model):
    dni = models.CharField(max_length=8, unique=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    birth_date = models.DateField()
    address = models.TextField()
    parent_name = models.CharField(max_length=150)
    parent_phone = models.CharField(max_length=15)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"
