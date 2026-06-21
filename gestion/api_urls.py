from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from . import api_views

urlpatterns = [
    # Terrains
    path('terrains/', api_views.TerrainListCreateView.as_view(), name='api_terrains'),
    path('terrains/<int:pk>/', api_views.TerrainDetailView.as_view(), name='api_terrain_detail'),

    # Créneaux
    path('creneaux/', api_views.CreneauListCreateView.as_view(), name='api_creneaux'),

    # Réservations
    path('reservations/', api_views.ReservationListCreateView.as_view(), name='api_reservations'),
    path('reservations/<int:pk>/', api_views.ReservationDetailView.as_view(), name='api_reservation_detail'),

    # Auth
    path('auth/register/', api_views.RegisterView.as_view(), name='api_register'),
    path('auth/login/', api_views.LoginView.as_view(), name='api_login'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='api_token_refresh'),

    # Utilisateur connecté
    path('users/me/', api_views.MeView.as_view(), name='api_me'),

    # Paiements
    path('paiements/', api_views.PaiementListCreateView.as_view(), name='api_paiements'),
    path('paiements/<int:pk>/', api_views.PaiementDetailView.as_view(), name='api_paiement_detail'),

    # Documentation Swagger
    path('schema/', SpectacularAPIView.as_view(), name='api_schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='api_schema'), name='api_docs'),
]
