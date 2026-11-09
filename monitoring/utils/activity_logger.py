from monitoring.models import UserActivityLog


def get_client_ip(request):
    """Helper untuk mendapatkan IP address client"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def log_activity(request, action, description, additional_data=None, content_type=None, object_id=None, object_repr=None):
    """
    Helper function untuk log aktivitas dari views.
    
    Args:
        request: Django request object
        action: Action type (VIEW, SEARCH, FILTER, EXPORT, etc)
        description: Human-readable description
        additional_data: Dict dengan data tambahan (optional)
        content_type: ContentType untuk model changes (optional)
        object_id: ID object yang diubah (optional)
        object_repr: String representasi object (optional)
    """
    if not request.user.is_authenticated:
        return
    
    try:
        UserActivityLog.objects.create(
            user=request.user,
            username=request.user.username,
            action=action,
            content_type=content_type,
            object_id=object_id,
            object_repr=object_repr,
            request_path=request.path,
            request_method=request.method,
            query_params=dict(request.GET) if request.GET else None,
            description=description,
            additional_data=additional_data,
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:255]
        )
    except Exception:
        # Silent fail
        pass
