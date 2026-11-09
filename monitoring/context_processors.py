from .models import CompanyProfile
from .decorators import get_user_allowed_pages
from django.core.cache import cache


def company_profile(request):
    # Cache company profile selama 5 menit — data ini jarang berubah
    profile = cache.get('company_profile_singleton')
    if profile is None:
        profile = CompanyProfile.objects.first()
        cache.set('company_profile_singleton', profile, timeout=300)  # 5 menit
    return {
        "company_profile": profile
    }


def user_permissions(request):
    """
    Context processor to inject user's allowed pages into all templates.
    This allows templates to show/hide menu items based on permissions.
    """
    if request.user.is_authenticated:
        cache_key = f'user_allowed_pages_{request.user.pk}'
        allowed_pages = cache.get(cache_key)
        if allowed_pages is None:
            allowed_pages = get_user_allowed_pages(request.user)
            cache.set(cache_key, allowed_pages, timeout=120)  # 2 menit
        return {
            'user_allowed_pages': allowed_pages
        }
    return {
        'user_allowed_pages': []
    }