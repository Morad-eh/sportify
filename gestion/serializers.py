from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from .models import Utilisateur, Terrain, Creneau, Reservation, Paiement


class UtilisateurSerializer(serializers.ModelSerializer):
    class Meta:
        model = Utilisateur
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'telephone', 'role']
        read_only_fields = ['id', 'role']


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True)

    class Meta:
        model = Utilisateur
        fields = ['username', 'email', 'first_name', 'last_name', 'telephone', 'password', 'password2']

    def validate(self, data):
        if data['password'] != data['password2']:
            raise serializers.ValidationError({'password': 'Les mots de passe ne correspondent pas.'})
        return data

    def create(self, validated_data):
        validated_data.pop('password2')
        password = validated_data.pop('password')
        user = Utilisateur(**validated_data)
        user.set_password(password)
        user.save()
        return user


class TerrainSerializer(serializers.ModelSerializer):
    class Meta:
        model = Terrain
        fields = ['id', 'nom', 'description', 'localisation', 'prix_heure', 'disponible']


class CreneauSerializer(serializers.ModelSerializer):
    terrain = TerrainSerializer(read_only=True)
    terrain_id = serializers.PrimaryKeyRelatedField(
        queryset=Terrain.objects.all(), source='terrain', write_only=True
    )

    class Meta:
        model = Creneau
        fields = ['id', 'terrain', 'terrain_id', 'date', 'heure_debut', 'heure_fin', 'disponible']


class ReservationSerializer(serializers.ModelSerializer):
    creneau = CreneauSerializer(read_only=True)
    creneau_id = serializers.PrimaryKeyRelatedField(
        queryset=Creneau.objects.filter(disponible=True), source='creneau', write_only=True
    )

    class Meta:
        model = Reservation
        fields = ['id', 'creneau', 'creneau_id', 'date_reservation', 'statut', 'montant_total']
        read_only_fields = ['id', 'date_reservation', 'statut', 'montant_total']

    def create(self, validated_data):
        creneau = validated_data['creneau']
        reservation = Reservation.objects.create(
            utilisateur=self.context['request'].user,
            creneau=creneau,
            statut='confirmee',
            montant_total=creneau.terrain.prix_heure,
        )
        creneau.disponible = False
        creneau.save()
        return reservation


class PaiementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Paiement
        fields = ['id', 'reservation', 'montant', 'mode_paiement', 'statut', 'date_paiement', 'stripe_payment_id']
        read_only_fields = ['id', 'date_paiement', 'stripe_payment_id']
