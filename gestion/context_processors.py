from .models import Avis, Utilisateur


def admin_alertes(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return {}
    avis_count = Avis.objects.filter(statut='en_attente').count()
    comptes_count = Utilisateur.objects.filter(is_active=False, date_suppression_demandee__isnull=False).count()
    total = avis_count + comptes_count
    return {
        'alerte_avis': avis_count,
        'alerte_comptes': comptes_count,
        'alerte_total': total,
    }
