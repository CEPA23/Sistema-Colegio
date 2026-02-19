from django.db import models

class School(models.Model):
    name = models.CharField(max_length=255)
    logo = models.FileField(upload_to='school_logos/', blank=True, null=True)
    address = models.TextField()
    phone = models.CharField(max_length=20)
    email = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
