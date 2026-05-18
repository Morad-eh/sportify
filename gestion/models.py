from django.db import models
from django.contrib.auth.models import AbstractUser


class Utilisateur(AbstractUser):
    ROLE_CHOICES = [
        ('membre', 'Membre'),
        ('admin', 'Administrateur'),
        ('proprio', 'Propriétaire de terrain'),
    ]
    telephone = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='membre')

    def __str__(self):
        return self.get_full_name() or self.username


class Terrain(models.Model):
    nom = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    localisation = models.CharField(max_length=255)
    prix_heure = models.DecimalField(max_digits=10, decimal_places=2)
    disponible = models.BooleanField(default=True)
    proprietaire = models.ForeignKey(
        Utilisateur,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'role': 'proprio'},
        related_name='terrains',
    )

    def __str__(self):
        return self.nom


class Creneau(models.Model):
    terrain = models.ForeignKey(Terrain, on_delete=models.CASCADE, related_name='creneaux')
    date = models.DateField()
    heure_debut = models.TimeField()
    heure_fin = models.TimeField()
    disponible = models.BooleanField(default=True)

    class Meta:
        ordering = ['date', 'heure_debut']

    def __str__(self):
        return f"{self.terrain.nom} — {self.date} {self.heure_debut}–{self.heure_fin}"


class Reservation(models.Model):
    STATUT_CHOICES = [
        ('en_attente', 'En attente'),
        ('confirmee', 'Confirmée'),
        ('annulee', 'Annulée'),
        ('terminee', 'Terminée'),
    ]
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='reservations')
    creneau = models.ForeignKey(Creneau, on_delete=models.CASCADE, related_name='reservations')
    date_reservation = models.DateTimeField(auto_now_add=True)
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='en_attente')
    montant_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ['-date_reservation']

    def __str__(self):
        return f"Réservation #{self.id} — {self.utilisateur.username}"


class Paiement(models.Model):
    STATUT_CHOICES = [
        ('en_attente', 'En attente'),
        ('paye', 'Payé'),
        ('rembourse', 'Remboursé'),
        ('echoue', 'Échoué'),
    ]
    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE, related_name='paiements')
    montant = models.DecimalField(max_digits=10, decimal_places=2)
    mode_paiement = models.CharField(max_length=50, default='stripe')
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='en_attente')
    date_paiement = models.DateTimeField(auto_now_add=True)
    stripe_payment_id = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"Paiement #{self.id} — {self.statut}"


class Notification(models.Model):
    TYPE_CHOICES = [
        ('reservation', 'Réservation'),
        ('paiement', 'Paiement'),
        ('rappel', 'Rappel'),
        ('systeme', 'Système'),
    ]
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='notifications')
    titre = models.CharField(max_length=150)
    message = models.TextField()
    type_notification = models.CharField(max_length=20, choices=TYPE_CHOICES, default='systeme')
    date_envoi = models.DateTimeField(auto_now_add=True)
    lu = models.BooleanField(default=False)

    class Meta:
        ordering = ['-date_envoi']

    def __str__(self):
        return f"Notification #{self.id} — {self.utilisateur.username}"
