from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from gestion.models import Utilisateur


class Command(BaseCommand):
    help = 'Supprime définitivement les comptes désactivés depuis plus de 12 mois.'

    def handle(self, *args, **options):
        limite = timezone.now() - timedelta(days=365)
        comptes = Utilisateur.objects.filter(
            is_active=False,
            date_suppression_demandee__isnull=False,
            date_suppression_demandee__lte=limite,
        )
        total = comptes.count()
        comptes.delete()
        self.stdout.write(self.style.SUCCESS(f'{total} compte(s) purgé(s) définitivement.'))
