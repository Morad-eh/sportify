from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta, time
from gestion.models import Terrain, Creneau

SLOTS = [
    (12, 13), (13, 14), (14, 15), (15, 16), (16, 17), (17, 18),
    (18, 19), (19, 20), (20, 21), (21, 22), (22, 23), (23, 0), (0, 1),
]


class Command(BaseCommand):
    help = 'Génère les créneaux 12h-01h pour tous les terrains (30 jours par défaut)'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=30)

    def handle(self, *args, **options):
        days = options['days']
        today = timezone.now().date()
        terrains = Terrain.objects.filter(disponible=True)
        created = 0

        for offset in range(days):
            date = today + timedelta(days=offset)
            for terrain in terrains:
                for debut_h, fin_h in SLOTS:
                    _, was_created = Creneau.objects.get_or_create(
                        terrain=terrain,
                        date=date,
                        heure_debut=time(debut_h, 0),
                        defaults={'heure_fin': time(fin_h, 0), 'disponible': True},
                    )
                    if was_created:
                        created += 1

        self.stdout.write(self.style.SUCCESS(
            f'{created} créneaux créés pour {terrains.count()} terrains sur {days} jours.'
        ))
