from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from .models import Terrain, Creneau, Reservation
from .forms import InscriptionForm, ConnexionForm


def home(request):
    terrains = Terrain.objects.filter(disponible=True)[:6]
    return render(request, 'gestion/home.html', {'terrains': terrains})


def liste_terrains(request):
    terrains = Terrain.objects.filter(disponible=True)
    return render(request, 'gestion/terrains.html', {'terrains': terrains})


def detail_terrain(request, pk):
    terrain = get_object_or_404(Terrain, pk=pk, disponible=True)
    creneaux = terrain.creneaux.filter(
        disponible=True,
        date__gte=timezone.now().date(),
    ).order_by('date', 'heure_debut')
    return render(request, 'gestion/terrain_detail.html', {
        'terrain': terrain,
        'creneaux': creneaux,
    })


def inscription(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        form = InscriptionForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Inscription réussie ! Bienvenue sur Sportify.')
            return redirect('dashboard')
    else:
        form = InscriptionForm()
    return render(request, 'gestion/register.html', {'form': form})


def connexion(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        form = ConnexionForm(request.POST)
        if form.is_valid():
            user = authenticate(
                request,
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password'],
            )
            if user:
                login(request, user)
                next_url = request.GET.get('next', 'dashboard')
                return redirect(next_url)
            else:
                messages.error(request, 'Identifiants incorrects. Veuillez réessayer.')
    else:
        form = ConnexionForm()
    return render(request, 'gestion/login.html', {'form': form})


def deconnexion(request):
    logout(request)
    messages.info(request, 'Vous avez été déconnecté.')
    return redirect('home')


@login_required
def dashboard(request):
    reservations = Reservation.objects.filter(
        utilisateur=request.user
    ).select_related('creneau__terrain').order_by('-date_reservation')
    return render(request, 'gestion/dashboard.html', {'reservations': reservations})


@login_required
def reserver(request, creneau_id):
    creneau = get_object_or_404(Creneau, pk=creneau_id, disponible=True)
    if request.method == 'POST':
        Reservation.objects.create(
            utilisateur=request.user,
            creneau=creneau,
            statut='confirmee',
            montant_total=creneau.terrain.prix_heure,
        )
        creneau.disponible = False
        creneau.save()
        messages.success(request, f'Réservation confirmée ! Terrain : {creneau.terrain.nom}, le {creneau.date} à {creneau.heure_debut}.')
        return redirect('dashboard')
    return render(request, 'gestion/reservation_confirm.html', {'creneau': creneau})
