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
    from datetime import timedelta

    terrain = get_object_or_404(Terrain, pk=pk, disponible=True)
    today = timezone.now().date()
    end_date = today + timedelta(days=30)

    dispo_dates = list(
        terrain.creneaux.filter(disponible=True, date__gte=today, date__lte=end_date)
        .values_list('date', flat=True).distinct()
    )
    dispo_json = json.dumps({str(terrain.id): [d.isoformat() for d in dispo_dates]})

    return render(request, 'gestion/terrain_detail.html', {
        'terrain': terrain,
        'dispo_json': dispo_json,
        'today': today.isoformat(),
        'is_auth': request.user.is_authenticated,
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
    if request.user.is_staff:
        messages.error(request, "Les administrateurs ne peuvent pas effectuer de réservations.")
        return redirect('terrains')
    creneau = get_object_or_404(Creneau, pk=creneau_id, disponible=True)
    return render(request, 'gestion/reservation_confirm.html', {
        'creneau': creneau,
        'stripe_public_key': settings.STRIPE_PUBLIC_KEY,
    })


@login_required
def creer_paiement(request, creneau_id):
    if request.user.is_staff:
        return redirect('terrains')
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
    from datetime import datetime as dt
    from zoneinfo import ZoneInfo

    reservation = get_object_or_404(Reservation, pk=reservation_id, utilisateur=request.user)
    if reservation.statut != 'confirmee' or reservation.creneau.date < timezone.now().date():
        messages.error(request, 'Cette réservation ne peut pas être annulée.')
        return redirect('dashboard')

    brussels = ZoneInfo('Europe/Brussels')
    now_brussels = timezone.now().astimezone(brussels)
    creneau_dt = dt.combine(reservation.creneau.date, reservation.creneau.heure_debut).replace(tzinfo=brussels)
    heures_avant = (creneau_dt - now_brussels).total_seconds() / 3600

    if heures_avant >= 48:
        pct_remboursement = 100
    elif heures_avant >= 24:
        pct_remboursement = 50
    else:
        pct_remboursement = 0

    montant_rembourse = round(float(reservation.montant_total) * pct_remboursement / 100, 2)

    if request.method == 'POST':
        creneau = reservation.creneau

        # Remboursement Stripe
        paiement = reservation.paiements.first()
        stripe_ok = False
        if paiement and paiement.stripe_payment_id and montant_rembourse > 0:
            try:
                stripe.api_key = settings.STRIPE_SECRET_KEY
                refund_kwargs = {'payment_intent': paiement.stripe_payment_id}
                if pct_remboursement < 100:
                    refund_kwargs['amount'] = int(montant_rembourse * 100)
                stripe.Refund.create(**refund_kwargs)
                paiement.statut = 'rembourse'
                paiement.save()
                stripe_ok = True
            except Exception:
                stripe_ok = False

        reservation.statut = 'annulee'
        reservation.save()
        creneau.disponible = True
        creneau.save()

        # Email client
        try:
            client_email = reservation.utilisateur.email
            if client_email:
                sujet_client = f"Annulation de votre réservation — {creneau.terrain.nom}"
                from django.template.loader import render_to_string
                corps_client = render_to_string('gestion/email_annulation_client.txt', {
                    'reservation': reservation,
                    'creneau': creneau,
                    'pct_remboursement': pct_remboursement,
                    'montant_rembourse': montant_rembourse,
                })
                send_mail(sujet_client, corps_client, settings.DEFAULT_FROM_EMAIL, [client_email])
        except Exception:
            pass

        # Email admin
        try:
            admin_email = settings.EMAIL_HOST_USER
            if admin_email:
                sujet_admin = f"[Sportify] Annulation — {reservation.utilisateur.username} — {creneau.terrain.nom}"
                from django.template.loader import render_to_string
                corps_admin = render_to_string('gestion/email_annulation_admin.txt', {
                    'reservation': reservation,
                    'creneau': creneau,
                    'pct_remboursement': pct_remboursement,
                    'montant_rembourse': montant_rembourse,
                })
                send_mail(sujet_admin, corps_admin, settings.DEFAULT_FROM_EMAIL, [admin_email])
        except Exception:
            pass

        messages.success(request, 'Annulation confirmée. Un email de confirmation vous a été envoyé.')
        return redirect('dashboard')

    return render(request, 'gestion/annuler_reservation.html', {
        'reservation': reservation,
        'pct_remboursement': pct_remboursement,
        'montant_rembourse': montant_rembourse,
        'heures_avant': int(heures_avant),
    })


def conditions(request):
    return render(request, 'gestion/conditions.html')


def confidentialite(request):
    return render(request, 'gestion/confidentialite.html')


def nos_complexes(request):
    complexes_info = [
        {
            'nom': 'Royal Foot Indoor',
            'commune': 'Anderlecht',
            'adresse': 'Anderlecht, 1070 Bruxelles',
            'emoji': '🏟️',
            'couleur': '#1A8C4E',
            'horaires': 'Lun–Ven : 10h–23h · Sam–Dim : 9h–23h',
            'sports': ['Football en salle'],
            'equipements': ['Vestiaires & douches', 'Parking gratuit', 'Bar & buvette', 'Éclairage LED'],
        },
        {
            'nom': 'Fitfive Forest',
            'commune': 'Forest',
            'adresse': 'Forest, 1190 Bruxelles',
            'emoji': '⚽',
            'couleur': '#0D2E1A',
            'horaires': 'Lun–Ven : 9h–23h · Sam–Dim : 8h–23h',
            'sports': ['Football en salle'],
            'equipements': ['Vestiaires & douches', 'Accès PMR', 'Cafétéria', 'Wi-Fi gratuit'],
        },
        {
            'nom': 'City Five',
            'commune': 'Molenbeek-Saint-Jean',
            'adresse': 'Molenbeek-Saint-Jean, 1080 Bruxelles',
            'emoji': '🎾',
            'couleur': '#7c3aed',
            'horaires': 'Lun–Ven : 10h–23h · Sam–Dim : 9h–22h',
            'sports': ['Football en salle', 'Padel'],
            'equipements': ['Vestiaires & douches', 'Location de matériel', 'Snack bar', 'Parking'],
        },
    ]
    terrains = Terrain.objects.filter(disponible=True).order_by('localisation', 'nom')
    terrains_par_commune = {}
    for t in terrains:
        terrains_par_commune.setdefault(t.localisation, []).append(t)
    for c in complexes_info:
        c['terrains'] = terrains_par_commune.get(c['commune'], [])
    return render(request, 'gestion/nos_complexes.html', {'complexes': complexes_info})


def contact(request):
    if request.method == 'POST':
        nom = request.POST.get('nom', '').strip()
        email_contact = request.POST.get('email', '').strip()
        sujet = request.POST.get('sujet', '').strip()
        message_body = request.POST.get('message', '').strip()
        if nom and email_contact and sujet and message_body:
            try:
                corps = f"Message reçu via le formulaire de contact Sportify.\n\nDe : {nom} <{email_contact}>\nSujet : {sujet}\n\n{message_body}"
                send_mail(
                    f'[Contact Sportify] {sujet}',
                    corps,
                    settings.DEFAULT_FROM_EMAIL,
                    [settings.EMAIL_HOST_USER],
                    reply_to=[email_contact],
                )
                messages.success(request, 'Votre message a bien été envoyé. Nous vous répondrons sous 48h.')
            except Exception:
                messages.error(request, 'Une erreur est survenue. Veuillez réessayer ou nous contacter directement par email.')
        else:
            messages.error(request, 'Veuillez remplir tous les champs.')
        return redirect('contact')
    return render(request, 'gestion/contact.html')


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
    from datetime import date as date_type, time as time_type
    from zoneinfo import ZoneInfo

    terrain_id = request.GET.get('terrain')
    date_str = request.GET.get('date')
    exclude_id = request.GET.get('exclude')
    only_available = request.GET.get('only') == '1'

    if not terrain_id or not date_str:
        return JsonResponse({'slots': []})

    terrain = get_object_or_404(Terrain, pk=terrain_id, disponible=True)
    try:
        d = date_type.fromisoformat(date_str)
    except (ValueError, TypeError):
        return JsonResponse({'slots': []})

    brussels = ZoneInfo('Europe/Brussels')
    now_brussels = timezone.now().astimezone(brussels)
    today_brussels = now_brussels.date()

    if d < today_brussels:
        return JsonResponse({'slots': []})

    slot_hours = [12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 0]
    qs = terrain.creneaux.filter(date=d)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    if only_available:
        qs = qs.filter(disponible=True)
    # Pour aujourd'hui, exclure les créneaux déjà passés
    if d == today_brussels:
        current_time = time_type(now_brussels.hour, now_brussels.minute)
        qs = qs.filter(heure_debut__gte=current_time)

    creneaux_map = {c.heure_debut.hour: c for c in qs}
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
        creneau__date=today, statut='confirmee', utilisateur__is_staff=False
    ).count()

    revenue_today = Reservation.objects.filter(
        creneau__date=today, statut='confirmee', utilisateur__is_staff=False
    ).aggregate(total=Sum('montant_total'))['total'] or 0

    revenue_month = Reservation.objects.filter(
        creneau__date__gte=month_start, statut='confirmee', utilisateur__is_staff=False
    ).aggregate(total=Sum('montant_total'))['total'] or 0

    total_users = Utilisateur.objects.filter(is_staff=False).count()

    total_slots = Creneau.objects.filter(date=today).count()
    reserved_slots = Creneau.objects.filter(date=today, disponible=False).count()
    taux_occupation = round(reserved_slots / total_slots * 100) if total_slots > 0 else 0

    reservations_du_mois = Reservation.objects.filter(
        creneau__date__gte=month_start, utilisateur__is_staff=False
    ).select_related('creneau__terrain', 'utilisateur').order_by('creneau__date', 'creneau__heure_debut')

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
            utilisateur__is_staff=False,
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
        statut='confirmee', utilisateur__is_staff=False, creneau__terrain__nom__icontains='Football'
    ).count()
    resa_padel = Reservation.objects.filter(
        statut='confirmee', utilisateur__is_staff=False, creneau__terrain__nom__icontains='Padel'
    ).count()
    total_sport = resa_football + resa_padel
    pct_football = round(resa_football / total_sport * 100) if total_sport > 0 else 50
    pct_padel = 100 - pct_football

    revenus_7j = []
    max_rev = 0
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        r = float(Reservation.objects.filter(
            creneau__date=d, statut='confirmee', utilisateur__is_staff=False
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
        'reservations_du_mois': reservations_du_mois,
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
    p.setFont('Helvetica', 10)
    p.setFillColor(colors.HexColor('#8ab89a'))
    p.drawString(50, h - 95, 'N° TVA : BE 0123.456.789')

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
    from datetime import timedelta, datetime as dt, time as time_type
    from zoneinfo import ZoneInfo

    brussels = ZoneInfo('Europe/Brussels')
    now_brussels = timezone.now().astimezone(brussels)
    today_brussels = now_brussels.date()

    reservation = get_object_or_404(Reservation, pk=reservation_id, utilisateur=request.user)

    if reservation.statut != 'confirmee':
        messages.error(request, 'Cette réservation ne peut pas être modifiée.')
        return redirect('dashboard')

    # Limite : modification impossible moins de 24h avant le créneau
    reservation_dt = dt.combine(
        reservation.creneau.date,
        reservation.creneau.heure_debut,
    ).replace(tzinfo=brussels)
    if (reservation_dt - now_brussels).total_seconds() < 86400:
        messages.error(request, 'La modification n\'est plus possible moins de 24h avant votre créneau.')
        return redirect('dashboard')

    terrain = reservation.creneau.terrain

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

    end_date = today_brussels + timedelta(days=30)
    current_time = time_type(now_brussels.hour, now_brussels.minute)

    from django.db.models import Q
    dispo_dates = list(
        Creneau.objects.filter(
            terrain=terrain, disponible=True,
        ).exclude(pk=reservation.creneau.pk).filter(
            Q(date__gt=today_brussels, date__lte=end_date) |
            Q(date=today_brussels, heure_debut__gte=current_time)
        ).values_list('date', flat=True).distinct()
    )
    dispo_json = json.dumps({str(terrain.id): [d.isoformat() for d in dispo_dates]})

    return render(request, 'gestion/reservation_modifier.html', {
        'reservation': reservation,
        'terrain': terrain,
        'dispo_json': dispo_json,
        'today': today_brussels.isoformat(),
        'exclude_id': reservation.creneau.pk,
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
                    from django.template.loader import render_to_string
                    complexes_map = {
                        'Anderlecht': 'Royal Foot Indoor',
                        'Forest': 'Fitfive Forest',
                        'Molenbeek-Saint-Jean': 'City Five',
                    }
                    corps_confirm = render_to_string('gestion/email_confirmation_reservation.txt', {
                        'prenom': request.user.get_full_name() or request.user.username,
                        'terrain_nom': creneau.terrain.nom,
                        'complexe': complexes_map.get(creneau.terrain.localisation, creneau.terrain.localisation),
                        'adresse': creneau.terrain.localisation + ', Bruxelles',
                        'date': creneau.date.strftime('%A %d %B %Y'),
                        'heure_debut': creneau.heure_debut.strftime('%H:%M'),
                        'heure_fin': creneau.heure_fin.strftime('%H:%M'),
                        'montant': creneau.terrain.prix_heure,
                        'reservation_id': reservation.id,
                    })
                    send_mail(
                        subject=f'✅ Confirmation de réservation — {creneau.terrain.nom}',
                        message=corps_confirm,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[request.user.email],
                        fail_silently=True,
                    )
                except Exception:
                    pass
        return render(request, 'gestion/paiement_succes.html', {'creneau': get_object_or_404(Creneau, pk=creneau_id)})

    return redirect('dashboard')
