from django.db.models.signals import post_save, post_delete
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.contrib.contenttypes.models import ContentType
from django.dispatch import receiver
from monitoring.models import UserActivityLog
from django.contrib.auth.models import User
import logging

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """Helper untuk mendapatkan IP address client"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    """Log ketika user login"""
    UserActivityLog.objects.create(
        user=user,
        username=user.username,
        action='LOGIN',
        description=f"User {user.username} logged in",
        ip_address=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:255]
    )


@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    """Log ketika user logout"""
    if user:
        UserActivityLog.objects.create(
            user=user,
            username=user.username,
            action='LOGOUT',
            description=f"User {user.username} logged out",
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:255]
        )


# Auto-log untuk model-model penting
LOGGED_MODELS = [
    'Machine', 'MachineGroup', 'DyeingProcess', 
    'OperatorProfile', 'Position', 'Shift'
]


@receiver(post_save)
def log_model_save(sender, instance, created, **kwargs):
    """Log ketika model di-create atau update"""
    if sender.__name__ not in LOGGED_MODELS:
        return
    
    # Dapatkan request dari middleware
    request = getattr(UserActivityLog, '_current_request', None)
    if not request or not hasattr(request, 'user') or not request.user.is_authenticated:
        return
    
    action = 'CREATE' if created else 'UPDATE'
    UserActivityLog.objects.create(
        user=request.user,
        username=request.user.username,
        action=action,
        content_type=ContentType.objects.get_for_model(instance),
        object_id=instance.pk,
        object_repr=str(instance),
        description=f"{action.title()} {sender.__name__}: {instance}",
        ip_address=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:255]
    )


@receiver(post_delete)
def log_model_delete(sender, instance, **kwargs):
    """Log ketika model di-delete"""
    if sender.__name__ not in LOGGED_MODELS:
        return
    
    request = getattr(UserActivityLog, '_current_request', None)
    if not request or not hasattr(request, 'user') or not request.user.is_authenticated:
        return
    
    UserActivityLog.objects.create(
        user=request.user,
        username=request.user.username,
        action='DELETE',
        content_type=ContentType.objects.get_for_model(instance),
        object_repr=str(instance),
        description=f"Delete {sender.__name__}: {instance}",
        ip_address=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:255]
    )

# ── TRIGGER AUTO PREDICT PINN SAAT PROSES SELESAI ──
from monitoring.models import DyeingProcess


@receiver(post_save, sender=DyeingProcess)
def auto_predict_steam_pinn(sender, instance, created, **kwargs):
    """
    Jika proses baru saja komplit dan PINN uap belum dihitung,
    jalankan prediksi otomatis.
    """
    if getattr(instance, 'is_complete', False) and getattr(instance, 'predicted_steam_kg', None) is None:
        from monitoring.models import MachinePhysicsProfile
        from monitoring.services.steam_calibration_runner import SteamCalibrationRunner
        
        own_profile = MachinePhysicsProfile.objects.filter(
            machine=instance.machine, is_active=True).first()
        
        runner = SteamCalibrationRunner()
        
        if own_profile:
            best_profile = MachinePhysicsProfile.get_best_for_group(own_profile.machine_group)
            runner.predict_single_batch(instance, own_profile, best_profile)
        else:
            fallback = MachinePhysicsProfile.get_best_for_machine(instance.machine)
            if fallback:
                runner.predict_single_batch_fallback(instance, fallback)

    # Ketika DyeingProcess selesai, evaluasi anomali secara otomatis jika sudah ada identitas & program
    if getattr(instance, 'is_complete', False):
        try:
            ident = getattr(instance, 'identity', None)
            if ident and ident.program_id:
                from monitoring.management.commands.detect_anomalies import evaluate_identity_anomaly
                evaluate_identity_anomaly(ident)
        except Exception as e:
            logger.error(f"Gagal evaluasi anomali batch selesai {instance.id}: {e}", exc_info=True)


from monitoring.models import DyeingIdentity
@receiver(post_save, sender=DyeingIdentity)
def freeze_ideal_electricity(sender, instance, created, **kwargs):
    process = getattr(instance, 'dyeing_process', None)
    program = instance.program
    
    if not (process and program and program.durasi_ideal and process.machine_nominal_power):
        return
        
    from monitoring.models import DyeingProcess, GlobalSettings
    
    late_stop_mins = 0.0
    if process.reached_70c_time and process.end_time and process.end_time > process.reached_70c_time:
        late_stop_mins = max(0.0, (process.end_time - process.reached_70c_time).total_seconds() / 60.0)
    fabric_allowance_mins = min(late_stop_mins, 45.0)
    elec_ideal_mins = program.durasi_ideal + fabric_allowance_mins
    
    ideal_kwh = (elec_ideal_mins / 60.0) * process.machine_nominal_power
    settings = GlobalSettings.objects.first()
    
    update_data = {
        'program_ideal_duration_mins': program.durasi_ideal,
        'ideal_power_consumption_kwh': round(ideal_kwh, 2)
    }
    
    if settings and process.power_cost_total is not None:
        ideal_cost = ideal_kwh * settings.electricity_base_rate
        loss_cost = max(0.0, process.power_cost_total - ideal_cost)
        update_data['power_cost_ideal'] = round(ideal_cost, 2)
        update_data['power_cost_loss'] = round(loss_cost, 2)
        
    DyeingProcess.objects.filter(pk=process.pk).update(**update_data)

    # Evaluasi anomali secara otomatis saat DyeingIdentity disimpan & terhubung ke DyeingProcess
    try:
        from monitoring.management.commands.detect_anomalies import evaluate_identity_anomaly
        evaluate_identity_anomaly(instance)
    except Exception as e:
        logger.error(f"Gagal evaluasi anomali identity {instance.id}: {e}", exc_info=True)
