from functools import wraps
from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from monitoring.models import OperatorProfile


def position_required(page_code):
    """
    Decorator untuk membatasi akses halaman berdasarkan posisi user.
    
    Args:
        page_code: Kode halaman yang harus ada di allowed_pages posisi user
    
    Usage:
        @login_required
        @position_required('dashboard')
        def dashboard(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            # Superuser dan staff dapat akses semua halaman
            if request.user.is_superuser or request.user.is_staff:
                return view_func(request, *args, **kwargs)
            
            # Check apakah user punya operator profile
            try:
                operator_profile = request.user.operatorprofile
            except OperatorProfile.DoesNotExist:
                # User tidak punya operator profile, redirect ke access denied
                return render(request, 'access_denied.html', {
                    'page_code': page_code,
                    'reason': 'no_profile'
                }, status=403)
            
            # Check apakah user punya position
            if not operator_profile or not operator_profile.position:
                return render(request, 'access_denied.html', {
                    'page_code': page_code,
                    'reason': 'no_position'
                }, status=403)
            
            # Check apakah position punya akses ke halaman ini
            allowed_page_codes = operator_profile.position.allowed_pages.filter(
                code=page_code,
                is_active=True
            ).values_list('code', flat=True)
            
            if page_code not in allowed_page_codes:
                return render(request, 'access_denied.html', {
                    'page_code': page_code,
                    'page_name': page_code.replace('_', ' ').title(),
                    'reason': 'permission_denied'
                }, status=403)
            
            # User memiliki akses, lanjutkan ke view
            return view_func(request, *args, **kwargs)
        
        return wrapped_view
    return decorator


def user_can_access_page(user, page_code):
    """
    Versi non-decorator dari position_required, dipakai di endpoint Django-Ninja
    (yang tidak selalu cocok dengan pola decorator berbasis Django view).
    """
    if user.is_superuser or user.is_staff:
        return True
    try:
        operator_profile = user.operatorprofile
    except OperatorProfile.DoesNotExist:
        return False
    if not operator_profile or not operator_profile.position:
        return False
    return operator_profile.position.allowed_pages.filter(
        code=page_code, is_active=True
    ).exists()


def get_user_allowed_pages(user):
    """
    Helper function untuk mendapatkan list kode halaman yang bisa diakses user.
    Digunakan untuk hide/show menu items di template.
    
    Returns:
        list: List of page codes yang bisa diakses user
    """
    # Superuser dan staff dapat akses semua halaman
    if user.is_superuser or user.is_staff:
        from monitoring.models import PagePermission
        return list(PagePermission.objects.filter(is_active=True).values_list('code', flat=True))
    
    # Check operator profile
    try:
        operator_profile = user.operatorprofile
        if operator_profile.position:
            return list(
                operator_profile.position.allowed_pages.filter(
                    is_active=True
                ).values_list('code', flat=True)
            )
    except OperatorProfile.DoesNotExist:
        pass
    
    return []
