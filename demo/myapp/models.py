from django.db import models
from django.utils import timezone
from encrypted_model_fields.fields import EncryptedCharField
from encrypted_model_fields.fields import EncryptedDateTimeField


class Dbbi(models.Model):
    # nom = models.CharField(max_length=255)
    # date = models.DateField()
    # entree = models.CharField(max_length=20, blank=True, null=True)  # Allow null
    # sortie = models.CharField(max_length=20, blank=True, null=True)  # Allow null
    # travail = models.CharField(max_length=20, blank=True, null=True)  # Allow null
    # travail_cumulee = models.CharField(max_length=50, blank=True, null=True)  # Allow null
    # created_at = models.DateTimeField(auto_now_add=True)

    nom = EncryptedCharField(max_length=255)
    date = EncryptedDateTimeField() 
    entree = EncryptedCharField(max_length=20, blank=True, null=True)  # <-- Add null=True
    sortie = EncryptedCharField(max_length=20, blank=True, null=True)   # <-- Add null=True
    travail = EncryptedCharField(max_length=20, blank=True, null=True)   # <-- Add null=True
    travail_cumulee = EncryptedCharField(max_length=50, blank=True, null=True)  # <-- Add null=True
    
    class Meta:
        unique_together = ['nom', 'date']
    
    def __str__(self):
        return f"{self.nom} - {self.date}"

class FunctionResult(models.Model):
    function_name = models.CharField(max_length=255)
    arguments = models.TextField(blank=True, null=True)
    result = models.TextField(blank=True, null=True)
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True, null=True)
    executed_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-executed_at']
    
    def __str__(self):
        return f"{self.function_name} - {self.executed_at}"