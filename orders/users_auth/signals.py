from django.dispatch import Signal, receiver
from django_rest_passwordreset.signals import reset_password_token_created
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from .models import ConfirmEmailToken, User


user_is_registered = Signal()
order_is_created = Signal()


@receiver(user_is_registered)
def user_is_registered_signal(user_id, **kwargs):
    token, _ = ConfirmEmailToken.objects.get_or_create(user_id=user_id)
    msg = EmailMultiAlternatives(
        f"Токен для сброса пароля {token.user.email}",
        token.key,
        settings.EMAIL_HOST_USER,
        [token.user.email]
    )
    msg.send()


@receiver(reset_password_token_created)
def reset_token_created(sender, instance, reset_password_token, **kwargs):
    msg = EmailMultiAlternatives(
        f"Токен для сброса пароля для {reset_password_token.user}",
        reset_password_token.key,
        settings.EMAIL_HOST_USER,
        [reset_password_token.user.email]
    )
    msg.send()