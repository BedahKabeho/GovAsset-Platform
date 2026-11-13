from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def login_required_custom(view_func):
    """
    Blocks unauthenticated users from accessing any view.
    Redirects them to the login page.
    
    Usage: put @login_required_custom above any view function.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(request, "Please log in to access this page.")
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return wrapper


def role_required(*allowed_roles):
    """
    Blocks users whose role is not in the allowed list.
    
    Usage:
        @role_required('SUPER_ADMIN', 'MINISTRY_ADMIN')
        def my_view(request): ...
    
    This means only SUPER_ADMIN and MINISTRY_ADMIN can access that view.
    Everyone else gets redirected to dashboard with an error message.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            if request.user.role not in allowed_roles:
                messages.error(
                    request,
                    f"Access denied. This page requires one of: "
                    f"{', '.join(allowed_roles)}. Your role is: {request.user.role}"
                )
                return redirect('dashboard')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def ministry_isolation_check(view_func):
    """
    Extra security layer: confirms the user has a ministry_schema set
    before allowing access to any ministry-level view.
    
    Super Admin bypasses this check because they operate at platform level.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        # Super Admin is allowed — they have no ministry_schema and that is correct
        if request.user.role == 'SUPER_ADMIN':
            return view_func(request, *args, **kwargs)
        # Everyone else must have a ministry_schema
        if not request.user.ministry_schema:
            messages.error(
                request,
                "Your account is not assigned to any ministry. "
                "Contact your administrator."
            )
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return wrapper