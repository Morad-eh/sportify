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
]
