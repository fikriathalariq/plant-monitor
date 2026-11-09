from ninja import Router, Schema
from django.contrib.auth import authenticate, login, logout
from pydantic import BaseModel
from django.http import JsonResponse

auth_router = Router(tags=["Auth"])

class LoginSchema(Schema):
    username: str
    password: str

class ErrorSchema(Schema):
    message: str

from django.views.decorators.csrf import csrf_exempt

@auth_router.post("/login")
@csrf_exempt
def login_api(request, payload: LoginSchema):
    user = authenticate(request, username=payload.username, password=payload.password)
    if user is not None:
        login(request, user)
        return {"success": True, "message": "Login berhasil", "username": user.username}
    else:
        return JsonResponse({"success": False, "message": "Username atau password salah"}, status=401)

@auth_router.post("/logout")
def logout_api(request):
    logout(request)
    return {"success": True, "message": "Berhasil logout"}

@auth_router.get("/me")
def check_session(request):
    if request.user.is_authenticated:
        from monitoring.decorators import get_user_allowed_pages
        role = "Operator"
        if request.user.is_superuser:
            role = "Superuser"
        elif request.user.is_staff:
            role = "Staff"
        else:
            try:
                if hasattr(request.user, 'operatorprofile') and request.user.operatorprofile.position:
                    role = request.user.operatorprofile.position.name
            except Exception:
                pass

        return {
            "authenticated": True,
            "username": request.user.username,
            "is_staff": request.user.is_staff or request.user.is_superuser,
            "allowed_pages": get_user_allowed_pages(request.user),
            "role": role,
        }
    return {"authenticated": False}
