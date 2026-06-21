import stripe
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from .models import Terrain, Creneau, Reservation, Paiement
from .forms import InscriptionForm, ConnexionForm, ProfilForm


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
def profil(request):
    if request.method == 'POST':
        form = ProfilForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profil mis à jour avec succès.')
            return redirect('profil')
    else:
        form = ProfilForm(instance=request.user)
    return render(request, 'gestion/profil.html', {'form': form})


@login_required
def supprimer_compte(request):
    if request.method == 'POST':
        request.user.delete()
        logout(request)
        messages.info(request, 'Votre compte a été supprimé.')
        return redirect('home')
    return render(request, 'gestion/supprimer_compte.html')


@login_required
def reserver(request, creneau_id):
    creneau = get_object_or_404(Creneau, pk=creneau_id, disponible=True)
    return render(request, 'gestion/reservation_confirm.html', {
        'creneau': creneau,
        'stripe_public_key': settings.STRIPE_PUBLIC_KEY,
    })


@login_required
def creer_paiement(request, creneau_id):
    creneau = get_object_or_404(Creneau, pk=creneau_id, disponible=True)
    stripe.api_key = settings.STRIPE_SECRET_KEY

    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price_data': {
                'currency': 'eur',
                'product_data': {
                    'name': f'Réservation — {creneau.terrain.nom}',
                    'description': f'{creneau.date} de {creneau.heure_debut} à {creneau.heure_fin}',
                },
                'unit_amount': int(creneau.terrain.prix_heure * 100),
            },
            'quantity': 1,
        }],
        mode='payment',
        success_url=request.scheme + '://' + request.get_host() + f'/paiement/succes/?session_id={{CHECKOUT_SESSION_ID}}&creneau_id={creneau_id}',
        cancel_url=request.scheme + '://' + request.get_host() + f'/reserver/{creneau_id}/',
        metadata={'creneau_id': creneau_id, 'user_id': request.user.id},
    )
    return redirect(session.url)


@login_required
def paiement_succes(request):
    session_id = request.GET.get('session_id')
    creneau_id = request.GET.get('creneau_id')

    if not session_id or not creneau_id:
        return redirect('home')

    stripe.api_key = settings.STRIPE_SECRET_KEY
    session = stripe.checkout.Session.retrieve(session_id)

    if session.payment_status == 'paid':
        creneau = get_object_or_404(Creneau, pk=creneau_id)
        if creneau.disponible:
            reservation = Reservation.objects.create(
                utilisateur=request.user,
                creneau=creneau,
                statut='confirmee',
                montant_total=creneau.terrain.prix_heure,
            )
            Paiement.objects.create(
                reservation=reservation,
                montant=creneau.terrain.prix_heure,
                mode_paiement='stripe',
                statut='paye',
                stripe_payment_id=session.payment_intent or '',
            )
            creneau.disponible = False
            creneau.save()
            messages.success(request, f'Paiement confirmé ! Terrain : {creneau.terrain.nom}, le {creneau.date}.')
        return render(request, 'gestion/paiement_succes.html', {'creneau': get_object_or_404(Creneau, pk=creneau_id)})

    return redirect('dashboard')
