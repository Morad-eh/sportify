from django.core.management.base import BaseCommand
from django.utils import timezone
from gestion.models import Utilisateur, Terrain, Creneau, Reservation, Paiement, Notification
import datetime
import decimal


NOMS = ['Benali', 'Dupont', 'Martin', 'Bernard', 'Petit', 'Durand', 'Leroy', 'Moreau',
        'Simon', 'Laurent', 'Michel', 'Garcia', 'David', 'Bertrand', 'Roux', 'Vincent',
        'Fournier', 'Morel', 'Girard', 'Andre']

PRENOMS = ['Amine', 'Sofia', 'Yassine', 'Lea', 'Adam', 'Nina', 'Lucas', 'Sarah',
           'Rayan', 'Emma', 'Noah', 'Jade', 'Ines', 'Louis', 'Mila', 'Yanis',
           'Manon', 'Mehdi', 'Eva', 'Nathan']

TERRAINS_DATA = [
    ('Terrain Football 1', 'football', '12 Rue du Stade, Bruxelles', decimal.Decimal('35.00')),
    ('Terrain Football 2', 'football', '25 Avenue des Sports, Liège', decimal.Decimal('38.00')),
    ('Terrain Padel 1',    'padel',    '8 Rue Centrale, Namur',       decimal.Decimal('28.00')),
    ('Terrain Padel 2',    'padel',    '44 Boulevard du Jeu, Charleroi', decimal.Decimal('30.00')),
    ('Terrain Tennis 1',   'tennis',   '19 Rue Verte, Mons',          decimal.Decimal('24.00')),
    ('Terrain Tennis 2',   'tennis',   '3 Place du Parc, Louvain',    decimal.Decimal('26.00')),
    ('Terrain Basket 1',   'basket',   '77 Rue du Collège, Anvers',   decimal.Decimal('22.00')),
    ('Terrain Basket 2',   'basket',   '61 Quai Sportif, Gand',       decimal.Decimal('23.00')),
    ('Terrain Futsal 1',   'futsal',   '14 Rue de la Gare, Tournai',  decimal.Decimal('32.00')),
    ('Terrain Futsal 2',   'futsal',   '90 Chaussée Royale, Waterloo', decimal.Decimal('34.00')),
]

TYPES_NOTIF = ['reservation', 'paiement', 'rappel', 'systeme']
MODES_PAIEMENT = ['carte', 'especes', 'paypal', 'virement']
STATUTS_PAIEMENT = ['paye', 'en_attente', 'echoue', 'rembourse']
STATUTS_RESERVATION = ['confirmee', 'en_attente', 'annulee', 'terminee']


class Command(BaseCommand):
    help = 'Génère les données de démonstration Sportify'

    def handle(self, *args, **options):
        self.stdout.write('Nettoyage des données existantes...')
        Notification.objects.all().delete()
        Paiement.objects.all().delete()
        Reservation.objects.all().delete()
        Creneau.objects.all().delete()
        Terrain.objects.all().delete()
        Utilisateur.objects.filter(is_superuser=False).exclude(username='admin').delete()

        # --- Comptes de test ---
        self.stdout.write('Création des comptes de test...')
        if not Utilisateur.objects.filter(username='admin').exists():
            Utilisateur.objects.create_superuser(
                username='admin',
                email='admin@sportify.be',
                password='Sportify2026!',
                first_name='Admin',
                last_name='Sportify',
                role='admin',
            )

        membre_test = Utilisateur.objects.create_user(
            username='membre_test',
            email='membre@sportify.be',
            password='Sportify2026',
            first_name='Test',
            last_name='Membre',
            telephone='0471000001',
            role='membre',
        )

        # --- 100 utilisateurs (membres + proprios) ---
        self.stdout.write('Création des 100 utilisateurs...')
        users = [membre_test]
        idx = 1
        for i in range(1, 101):
            nom = NOMS[(i - 1) % len(NOMS)]
            prenom = PRENOMS[(i - 1) % len(PRENOMS)]
            role = 'proprio' if 91 <= i <= 98 else 'membre'
            username = f"{prenom.lower()}.{nom.lower()}{i}"
            email = f"{prenom.lower()}.{nom.lower()}{i}@sportify.test"
            tel = f"047{(i % 10)}{str(i).zfill(6)}"
            u = Utilisateur.objects.create_user(
                username=username,
                email=email,
                password='TestPass2026!',
                first_name=prenom,
                last_name=nom,
                telephone=tel,
                role=role,
            )
            users.append(u)
            idx += 1

        # --- 10 terrains ---
        self.stdout.write('Création des 10 terrains...')
        terrains = []
        for nom, type_t, loc, prix in TERRAINS_DATA:
            desc = f"Terrain de {type_t} indoor de qualité, gazon synthétique dernière génération, éclairage LED, vestiaires et douches."
            t = Terrain.objects.create(
                nom=nom,
                description=desc,
                localisation=loc,
                prix_heure=prix,
                disponible=True,
            )
            terrains.append(t)

        # --- 100 créneaux (dates futures : juin–octobre 2026) ---
        self.stdout.write('Création des 100 créneaux...')
        creneaux = []
        horaires = [
            (datetime.time(8, 0),  datetime.time(9, 0)),
            (datetime.time(9, 0),  datetime.time(10, 0)),
            (datetime.time(10, 0), datetime.time(11, 0)),
            (datetime.time(11, 0), datetime.time(12, 0)),
            (datetime.time(14, 0), datetime.time(15, 0)),
            (datetime.time(15, 0), datetime.time(16, 0)),
            (datetime.time(16, 0), datetime.time(17, 0)),
            (datetime.time(17, 0), datetime.time(18, 0)),
            (datetime.time(18, 0), datetime.time(19, 0)),
            (datetime.time(19, 0), datetime.time(20, 0)),
        ]
        start_date = datetime.date(2026, 6, 1)
        for i in range(100):
            terrain = terrains[i % len(terrains)]
            jour = start_date + datetime.timedelta(days=i // len(terrains))
            h_debut, h_fin = horaires[i % len(horaires)]
            c = Creneau.objects.create(
                terrain=terrain,
                date=jour,
                heure_debut=h_debut,
                heure_fin=h_fin,
                disponible=True,
            )
            creneaux.append(c)

        # --- 100 réservations ---
        self.stdout.write('Création des 100 réservations...')
        reservations = []
        statuts_res = STATUTS_RESERVATION
        base_dt = timezone.now() - datetime.timedelta(days=30)
        for i in range(100):
            user = users[(i * 3) % len(users)]
            creneau = creneaux[i]
            statut = statuts_res[i % len(statuts_res)]
            dt = base_dt + datetime.timedelta(hours=i)
            r = Reservation(
                utilisateur=user,
                creneau=creneau,
                statut=statut,
                montant_total=creneau.terrain.prix_heure,
            )
            r.save()
            r.date_reservation = dt
            Reservation.objects.filter(pk=r.pk).update(date_reservation=dt)
            reservations.append(r)

        # --- 100 paiements ---
        self.stdout.write('Création des 100 paiements...')
        modes = MODES_PAIEMENT
        statuts_p = STATUTS_PAIEMENT
        for i, res in enumerate(reservations):
            mode = modes[i % len(modes)]
            statut = statuts_p[i % len(statuts_p)]
            ref = f"PAY-2026-{str(i + 1).zfill(4)}"
            Paiement.objects.create(
                reservation=res,
                montant=res.montant_total,
                mode_paiement=mode,
                statut=statut,
                stripe_payment_id=ref,
            )

        # --- 100 notifications ---
        self.stdout.write('Création des 100 notifications...')
        types_n = TYPES_NOTIF
        for i in range(100):
            user = users[i % len(users)]
            type_n = types_n[i % len(types_n)]
            num = i + 1
            Notification.objects.create(
                utilisateur=user,
                titre=f'Notification {num}',
                message=f'Bonjour, ceci est la notification de test numéro {num} concernant {type_n}.',
                type_notification=type_n,
                lu=(i % 3 == 0),
            )

        self.stdout.write(self.style.SUCCESS(
            f'\nDonnees generees avec succes :'
            f'\n  - {Utilisateur.objects.count()} utilisateurs'
            f'\n  - {Terrain.objects.count()} terrains'
            f'\n  - {Creneau.objects.count()} creneaux'
            f'\n  - {Reservation.objects.count()} reservations'
            f'\n  - {Paiement.objects.count()} paiements'
            f'\n  - {Notification.objects.count()} notifications'
            f'\n\nComptes de test :'
            f'\n  Admin  -> username: admin       | mdp: Sportify2026!'
            f'\n  Membre -> username: membre_test | mdp: Sportify2026'
        ))
