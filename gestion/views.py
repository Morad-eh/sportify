import json
import stripe
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.core.mail import send_mail
from django.db.models import Sum, Count, Q
from .models import Terrain, Creneau, Reservation, Paiement, Utilisateur
from .forms import InscriptionForm, ConnexionForm, ProfilForm


def home(request):
    terrains = Terrain.objects.filter(disponible=True)[:6]
    return render(request, 'gestion/home.html', {'terrains': terrains})


def liste_terrains(request):
    terrains = Terrain.objects.filter(disponible=True)
    sport = request.GET.get('sport', '').strip()
    commune = request.GET.get('commune', '').strip()
    if sport:
        terrains = terrains.filter(nom__icontains=sport)
    if commune:
        terrains = terrains.filter(localisation__icontains=commune)
    return render(request, 'gestion/terrains.html', {
        'terrains': terrains,
        'sport_filtre': sport,
        'commune_filtre': commune,
    })


def detail_terrain(request, pk):
    from datetime import timedelta, date as date_type
    terrain = get_object_or_404(Terrain, pk=pk, disponible=True)
    today = timezone.now().date()

    date_str = request.GET.get('date')
    try:
        selected_date = date_type.fromisoformat(date_str) if date_str else today
        if selected_date < today:
            selected_date = today
    except (ValueError, TypeError):
        selected_date = today

    dates = [today + timedelta(days=i) for i in range(14)]

    creneaux = sorted(
        terrain.creneaux.filter(date=selected_date),
        key=lambda c: c.heure_debut.hour if c.heure_debut.hour >= 12 else c.heure_debut.hour + 24,
    )

    return render(request, 'gestion/terrain_detail.html', {
        'terrain': terrain,
        'creneaux': creneaux,
        'dates': dates,
        'selected_date': selected_date,
        'today': today,
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
    return render(request, 'gestion/dashboard.html', {
        'reservations': reservations,
        'today': timezone.now().date(),
    })


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
def annuler_reservation(request, reservation_id):
    reservation = get_object_or_404(Reservation, pk=reservation_id, utilisateur=request.user)
    if reservation.statut != 'confirmee' or reservation.creneau.date < timezone.now().date():
        messages.error(request, 'Cette réservation ne peut pas être annulée.')
        return redirect('dashboard')
    if request.method == 'POST':
        creneau = reservation.creneau
        reservation.statut = 'annulee'
        reservation.save()
        creneau.disponible = True
        creneau.save()
        messages.success(request, 'Votre réservation a été annulée.')
        return redirect('dashboard')
    return render(request, 'gestion/annuler_reservation.html', {'reservation': reservation})


def calendrier(request):
    from datetime import timedelta

    today = timezone.now().date()
    end_date = today + timedelta(days=30)

    terrains = Terrain.objects.filter(disponible=True).order_by('localisation', 'nom')

    # One query: which dates have at least 1 available slot per terrain
    available_qs = (
        Creneau.objects
        .filter(disponible=True, date__gte=today, date__lte=end_date)
        .values('terrain_id', 'date')
        .distinct()
    )
    dispo_summary = {}
    for item in available_qs:
        tid = str(item['terrain_id'])
        if tid not in dispo_summary:
            dispo_summary[tid] = []
        dispo_summary[tid].append(item['date'].isoformat())

    commune_order = ['Anderlecht', 'Forest', 'Molenbeek-Saint-Jean']
    complexes = {
        'Anderlecht': 'Royal Foot Indoor',
        'Forest': 'Fitfive Forest',
        'Molenbeek-Saint-Jean': 'City Five',
    }
    grouped = []
    for commune in commune_order:
        items = [t for t in terrains if t.localisation == commune]
        if items:
            grouped.append({'commune': commune, 'complexe': complexes.get(commune, commune), 'terrains': items})

    return render(request, 'gestion/calendrier.html', {
        'grouped': grouped,
        'dispo_json': json.dumps(dispo_summary),
        'today': today.isoformat(),
        'is_auth': request.user.is_authenticated,
    })


def api_creneaux(request):
    from datetime import date as date_type

    terrain_id = request.GET.get('terrain')
    date_str = request.GET.get('date')
    if not terrain_id or not date_str:
        return JsonResponse({'slots': []})

    terrain = get_object_or_404(Terrain, pk=terrain_id, disponible=True)
    try:
        d = date_type.fromisoformat(date_str)
    except (ValueError, TypeError):
        return JsonResponse({'slots': []})

    slot_hours = [12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 0]
    creneaux_map = {c.heure_debut.hour: c for c in terrain.creneaux.filter(date=d)}
    slots = []
    for h in slot_hours:
        c = creneaux_map.get(h)
        if c:
            slots.append({'id': c.id, 'label': f'{h:02d}:00', 'dispo': c.disponible})

    return JsonResponse({'slots': slots})


@login_required
def admin_dashboard(request):
    from datetime import timedelta

    if not request.user.is_staff:
        return redirect('home')

    today = timezone.now().date()
    month_start = today.replace(day=1)

    reservations_aujourd_hui = Reservation.objects.filter(
        creneau__date=today, statut='confirmee'
    ).count()

    revenue_today = Reservation.objects.filter(
        creneau__date=today, statut='confirmee'
    ).aggregate(total=Sum('montant_total'))['total'] or 0

    revenue_month = Reservation.objects.filter(
        creneau__date__gte=month_start, statut='confirmee'
    ).aggregate(total=Sum('montant_total'))['total'] or 0

    total_users = Utilisateur.objects.filter(is_staff=False).count()

    total_slots = Creneau.objects.filter(date=today).count()
    reserved_slots = Creneau.objects.filter(date=today, disponible=False).count()
    taux_occupation = round(reserved_slots / total_slots * 100) if total_slots > 0 else 0

    reservations_du_jour = Reservation.objects.filter(
        creneau__date=today
    ).select_related('creneau__terrain', 'utilisateur').order_by('creneau__heure_debut')

    top_terrains = Terrain.objects.annotate(
        nb_resa=Count('creneaux__reservations', filter=Q(creneaux__reservations__statut='confirmee'))
    ).order_by('-nb_resa')[:5]

    recent_users = Utilisateur.objects.filter(is_staff=False).order_by('-date_joined')[:5]

    max_commune = 0
    revenus_communes_raw = {}
    for commune in ['Anderlecht', 'Forest', 'Molenbeek-Saint-Jean']:
        r = float(Reservation.objects.filter(
            creneau__date__gte=month_start,
            statut='confirmee',
            creneau__terrain__localisation__icontains=commune,
        ).aggregate(total=Sum('montant_total'))['total'] or 0)
        revenus_communes_raw[commune] = r
        if r > max_commune:
            max_commune = r

    communes_data = [
        {'nom': k, 'total': v, 'pct': round(v / max_commune * 100) if max_commune > 0 else 0}
        for k, v in revenus_communes_raw.items()
    ]

    resa_football = Reservation.objects.filter(
        statut='confirmee', creneau__terrain__nom__icontains='Football'
    ).count()
    resa_padel = Reservation.objects.filter(
        statut='confirmee', creneau__terrain__nom__icontains='Padel'
    ).count()
    total_sport = resa_football + resa_padel
    pct_football = round(resa_football / total_sport * 100) if total_sport > 0 else 50
    pct_padel = 100 - pct_football

    revenus_7j = []
    max_rev = 0
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        r = float(Reservation.objects.filter(
            creneau__date=d, statut='confirmee'
        ).aggregate(total=Sum('montant_total'))['total'] or 0)
        revenus_7j.append({'date': d.strftime('%a'), 'total': r})
        if r > max_rev:
            max_rev = r
    for d in revenus_7j:
        d['pct'] = round(d['total'] / max_rev * 100) if max_rev > 0 else 0

    return render(request, 'gestion/admin_dashboard.html', {
        'reservations_aujourd_hui': reservations_aujourd_hui,
        'revenue_today': revenue_today,
        'revenue_month': revenue_month,
        'total_users': total_users,
        'taux_occupation': taux_occupation,
        'reserved_slots': reserved_slots,
        'total_slots': total_slots,
        'reservations_du_jour': reservations_du_jour,
        'top_terrains': top_terrains,
        'recent_users': recent_users,
        'communes_data': communes_data,
        'resa_football': resa_football,
        'resa_padel': resa_padel,
        'pct_football': pct_football,
        'pct_padel': pct_padel,
        'revenus_7j': revenus_7j,
        'today': today,
    })


@login_required
def telecharger_facture(request, reservation_id):
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from io import BytesIO

    reservation = get_object_or_404(Reservation, pk=reservation_id, utilisateur=request.user)

    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    w, h = A4

    # ── Fond header vert
    p.setFillColor(colors.HexColor('#0D2E1A'))
    p.rect(0, h - 110, w, 110, fill=1, stroke=0)

    # ── Logo Sportify
    p.setFont('Helvetica-Bold', 28)
    p.setFillColor(colors.HexColor('#1A8C4E'))
    p.drawString(50, h - 55, 'Sport')
    p.setFillColor(colors.HexColor('#F5A623'))
    p.drawString(50 + p.stringWidth('Sport', 'Helvetica-Bold', 28), h - 55, 'ify')

    p.setFont('Helvetica', 11)
    p.setFillColor(colors.HexColor('#8ab89a'))
    p.drawString(50, h - 78, 'Réservation de terrains sportifs — Bruxelles')

    # ── Numéro facture (droite)
    p.setFont('Helvetica-Bold', 13)
    p.setFillColor(colors.white)
    num = f'FACTURE #{reservation.id:04d}'
    p.drawRightString(w - 50, h - 55, num)
    p.setFont('Helvetica', 10)
    p.setFillColor(colors.HexColor('#8ab89a'))
    p.drawRightString(w - 50, h - 75, f'Émise le {reservation.date_reservation.strftime("%d/%m/%Y")}')

    # ── Section client
    y = h - 150
    p.setFont('Helvetica-Bold', 11)
    p.setFillColor(colors.HexColor('#0D2E1A'))
    p.drawString(50, y, 'CLIENT')
    p.setFont('Helvetica', 11)
    p.setFillColor(colors.HexColor('#1a1a1a'))
    nom = reservation.utilisateur.get_full_name() or reservation.utilisateur.username
    p.drawString(50, y - 18, nom)
    p.drawString(50, y - 36, reservation.utilisateur.email or '—')

    # ── Section détails réservation
    y2 = h - 150
    p.setFont('Helvetica-Bold', 11)
    p.setFillColor(colors.HexColor('#0D2E1A'))
    p.drawString(300, y2, 'RÉSERVATION')
    p.setFont('Helvetica', 11)
    p.setFillColor(colors.HexColor('#1a1a1a'))
    p.drawString(300, y2 - 18, f'#{reservation.id:04d} — {reservation.get_statut_display()}')
    p.drawString(300, y2 - 36, f'Payé le {reservation.date_reservation.strftime("%d/%m/%Y")}')

    # ── Séparateur
    y3 = h - 220
    p.setStrokeColor(colors.HexColor('#e8f0eb'))
    p.setLineWidth(1.5)
    p.line(50, y3, w - 50, y3)

    # ── Tableau détails
    y4 = y3 - 30
    p.setFillColor(colors.HexColor('#f4f6f4'))
    p.rect(50, y4 - 8, w - 100, 26, fill=1, stroke=0)
    p.setFont('Helvetica-Bold', 10)
    p.setFillColor(colors.HexColor('#6B7280'))
    p.drawString(60, y4 + 6, 'DESCRIPTION')
    p.drawRightString(w - 60, y4 + 6, 'MONTANT')

    rows = [
        ('Terrain', reservation.creneau.terrain.nom),
        ('Complexe / Commune', reservation.creneau.terrain.localisation),
        ('Date', reservation.creneau.date.strftime('%A %d %B %Y')),
        ('Horaire', f'{reservation.creneau.heure_debut.strftime("%H:%M")} → {reservation.creneau.heure_fin.strftime("%H:%M")}'),
        ('Mode de paiement', 'Carte bancaire (Stripe)'),
    ]

    y5 = y4 - 20
    for label, val in rows:
        p.setFont('Helvetica', 10)
        p.setFillColor(colors.HexColor('#6B7280'))
        p.drawString(60, y5, label)
        p.setFillColor(colors.HexColor('#1a1a1a'))
        p.drawString(200, y5, val)
        y5 -= 22

    # ── Ligne total
    p.setStrokeColor(colors.HexColor('#e8f0eb'))
    p.line(50, y5 - 6, w - 50, y5 - 6)
    y5 -= 28
    p.setFont('Helvetica-Bold', 13)
    p.setFillColor(colors.HexColor('#0D2E1A'))
    p.drawString(60, y5, 'TOTAL PAYÉ')
    p.setFillColor(colors.HexColor('#1A8C4E'))
    p.drawRightString(w - 60, y5, f'{reservation.montant_total} €')

    # ── Badge statut
    y5 -= 40
    p.setFillColor(colors.HexColor('#e8f5ed'))
    p.roundRect(60, y5 - 6, 120, 22, 4, fill=1, stroke=0)
    p.setFont('Helvetica-Bold', 10)
    p.setFillColor(colors.HexColor('#1a5c35'))
    p.drawString(70, y5 + 4, '✓ Paiement confirmé')

    # ── Footer
    p.setFillColor(colors.HexColor('#f4f6f4'))
    p.rect(0, 0, w, 60, fill=1, stroke=0)
    p.setFont('Helvetica', 9)
    p.setFillColor(colors.HexColor('#6B7280'))
    p.drawCentredString(w / 2, 36, 'Sportify — Réservation de terrains sportifs à Bruxelles')
    p.drawCentredString(w / 2, 20, 'Ce document fait office de reçu de paiement.')

    p.showPage()
    p.save()
    buffer.seek(0)

    from django.http import FileResponse
    filename = f'facture_sportify_{reservation.id:04d}.pdf'
    return FileResponse(buffer, as_attachment=True, filename=filename, content_type='application/pdf')


@login_required
def modifier_reservation(request, reservation_id):
    reservation = get_object_or_404(Reservation, pk=reservation_id, utilisateur=request.user)
    if reservation.statut != 'confirmee' or reservation.creneau.date < timezone.now().date():
        messages.error(request, 'Cette réservation ne peut pas être modifiée.')
        return redirect('dashboard')
    terrain = reservation.creneau.terrain
    creneaux = Creneau.objects.filter(
        terrain=terrain,
        disponible=True,
        date__gte=timezone.now().date(),
    ).exclude(pk=reservation.creneau.pk).order_by('date', 'heure_debut')
    if request.method == 'POST':
        nouveau_id = request.POST.get('creneau_id')
        nouveau_creneau = get_object_or_404(Creneau, pk=nouveau_id, terrain=terrain, disponible=True)
        ancien_creneau = reservation.creneau
        ancien_creneau.disponible = True
        ancien_creneau.save()
        nouveau_creneau.disponible = False
        nouveau_creneau.save()
        reservation.creneau = nouveau_creneau
        reservation.save()
        messages.success(request, f'Réservation modifiée : {nouveau_creneau.date} de {nouveau_creneau.heure_debut} à {nouveau_creneau.heure_fin}.')
        return redirect('dashboard')
    return render(request, 'gestion/reservation_modifier.html', {
        'reservation': reservation,
        'creneaux': creneaux,
        'terrain': terrain,
    })


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
            if request.user.email:
                try:
                    send_mail(
                        subject='✅ Confirmation de réservation — Sportify',
                        message=(
                            f'Bonjour {request.user.get_full_name() or request.user.username},\n\n'
                            f'Votre réservation est confirmée !\n\n'
                            f'📍 Terrain : {creneau.terrain.nom}\n'
                            f'🗓️  Date    : {creneau.date}\n'
                            f'🕐 Horaire : {creneau.heure_debut} – {creneau.heure_fin}\n'
                            f'💰 Montant : {creneau.terrain.prix_heure}€\n\n'
                            f'Merci de votre confiance.\n'
                            f"L'équipe Sportify 🏟️"
                        ),
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[request.user.email],
                        fail_silently=True,
                    )
                except Exception:
                    pass
        return render(request, 'gestion/paiement_succes.html', {'creneau': get_object_or_404(Creneau, pk=creneau_id)})

    return redirect('dashboard')
