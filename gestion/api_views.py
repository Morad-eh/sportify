from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiParameter

from .models import Terrain, Creneau, Reservation, Paiement
from .serializers import (
    TerrainSerializer, CreneauSerializer, ReservationSerializer,
    PaiementSerializer, RegisterSerializer, UtilisateurSerializer,
)


class IsAdminOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated and (request.user.is_staff or request.user.role in ('admin', 'proprio'))


# --- Terrains ---

@extend_schema(tags=['Terrains'])
class TerrainListCreateView(generics.ListCreateAPIView):
    serializer_class = TerrainSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        return Terrain.objects.filter(disponible=True)


@extend_schema(tags=['Terrains'])
class TerrainDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = TerrainSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        return Terrain.objects.all()


# --- Créneaux ---

@extend_schema(
    tags=['Créneaux'],
    parameters=[
        OpenApiParameter('terrain_id', int, description='Filtrer par terrain'),
        OpenApiParameter('date', str, description='Filtrer par date (YYYY-MM-DD)'),
    ]
)
class CreneauListCreateView(generics.ListCreateAPIView):
    serializer_class = CreneauSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        qs = Creneau.objects.filter(disponible=True, date__gte=timezone.now().date())
        terrain_id = self.request.query_params.get('terrain_id')
        date = self.request.query_params.get('date')
        if terrain_id:
            qs = qs.filter(terrain_id=terrain_id)
        if date:
            qs = qs.filter(date=date)
        return qs


# --- Réservations ---

@extend_schema(tags=['Réservations'])
class ReservationListCreateView(generics.ListCreateAPIView):
    serializer_class = ReservationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Reservation.objects.filter(utilisateur=self.request.user).select_related('creneau__terrain')


@extend_schema(tags=['Réservations'])
class ReservationDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ReservationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Reservation.objects.filter(utilisateur=self.request.user)

    def destroy(self, request, *args, **kwargs):
        reservation = self.get_object()
        if reservation.statut == 'confirmee' and reservation.creneau.date >= timezone.now().date():
            reservation.creneau.disponible = True
            reservation.creneau.save()
            reservation.statut = 'annulee'
            reservation.save()
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response({'detail': 'Cette réservation ne peut pas être annulée.'}, status=status.HTTP_400_BAD_REQUEST)


# --- Auth ---

@extend_schema(tags=['Authentification'])
class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            'user': UtilisateurSerializer(user).data,
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }, status=status.HTTP_201_CREATED)


@extend_schema(tags=['Authentification'])
class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        user = authenticate(username=username, password=password)
        if not user:
            return Response({'detail': 'Identifiants incorrects.'}, status=status.HTTP_401_UNAUTHORIZED)
        refresh = RefreshToken.for_user(user)
        return Response({
            'user': UtilisateurSerializer(user).data,
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        })


# --- Profil utilisateur ---

@extend_schema(tags=['Utilisateurs'])
class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UtilisateurSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


# --- Paiements ---

@extend_schema(tags=['Paiements'])
class PaiementListCreateView(generics.ListCreateAPIView):
    serializer_class = PaiementSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Paiement.objects.filter(reservation__utilisateur=self.request.user)


@extend_schema(tags=['Paiements'])
class PaiementDetailView(generics.RetrieveAPIView):
    serializer_class = PaiementSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Paiement.objects.filter(reservation__utilisateur=self.request.user)
