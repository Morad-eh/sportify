from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Utilisateur, Terrain, Creneau, Reservation, Paiement, Notification


@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'is_staff')
    list_filter = ('role', 'is_staff', 'is_active')
    fieldsets = UserAdmin.fieldsets + (
        ('Informations Sportify', {'fields': ('telephone', 'role')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Informations Sportify', {'fields': ('email', 'first_name', 'last_name', 'telephone', 'role')}),
    )


@admin.register(Terrain)
class TerrainAdmin(admin.ModelAdmin):
    list_display = ('nom', 'localisation', 'prix_heure', 'disponible')
    list_filter = ('disponible',)
    search_fields = ('nom', 'localisation')
    list_editable = ('disponible',)


@admin.register(Creneau)
class CreneauAdmin(admin.ModelAdmin):
    list_display = ('terrain', 'date', 'heure_debut', 'heure_fin', 'disponible')
    list_filter = ('disponible', 'terrain', 'date')
    list_editable = ('disponible',)
    date_hierarchy = 'date'


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ('id', 'utilisateur', 'get_terrain', 'get_date', 'statut', 'montant_total', 'date_reservation')
    list_filter = ('statut',)
    search_fields = ('utilisateur__username', 'creneau__terrain__nom')

    def get_terrain(self, obj):
        return obj.creneau.terrain.nom
    get_terrain.short_description = 'Terrain'

    def get_date(self, obj):
        return obj.creneau.date
    get_date.short_description = 'Date'


@admin.register(Paiement)
class PaiementAdmin(admin.ModelAdmin):
    list_display = ('id', 'reservation', 'montant', 'mode_paiement', 'statut', 'date_paiement')
    list_filter = ('statut', 'mode_paiement')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('utilisateur', 'message', 'date_envoi', 'lu')
    list_filter = ('lu',)
