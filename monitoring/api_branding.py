from ninja import Router
from monitoring.models import CompanyProfile

branding_router = Router()

@branding_router.get("/")
def get_branding(request):
    company = CompanyProfile.objects.first()
    if company and company.logo:
        # Mengembalikan url gambar statis dari tabel CompanyProfile
        return {"logo_url": company.logo.url, "name": company.name}
    return {"logo_url": None, "name": "Plant Monitor"}
