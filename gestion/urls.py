from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('terrains/', views.liste_terrains, name='terrains'),
    path('terrains/<int:pk>/', views.detail_terrain, name='terrain_detail'),
    path('inscription/', views.inscription, name='inscription'),
    path('connexion/', views.connexion, name='connexion'),
    path('deconnexion/', views.deconnexion, name='deconnexion'),
    path('tableau-de-bord/', views.dashboard, name='dashboard'),
    path('reserver/<int:creneau_id>/', views.reserver, name='reserver'),
    path('profil/', views.profil, name='profil'),
    path('supprimer-compte/', views.supprimer_compte, name='supprimer_compte'),
    path('paiement/creer/<int:creneau_id>/', views.creer_paiement, name='creer_paiement'),
    path('paiement/succes/', views.paiement_succes, name='paiement_succes'),
    path('reservations/<int:reservation_id>/annuler/', views.annuler_reservation, name='annuler_reservation'),
    path('reservations/<int:reservation_id>/modifier/', views.modifier_reservation, name='modifier_reservation'),
]
