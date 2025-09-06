from rest_framework import serializers
from .models import Dbbi


class DbbiSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dbbi
        fields = ['id', 'nom', 'date', 'entree', 'sortie', 'travail', 'travail_cumulee']
