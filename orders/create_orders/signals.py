from django.dispatch import Signal, receiver
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from users_auth.models import User


order_is_created = Signal()


@receiver(order_is_created)
def new_order(user_id, order_id, **kwargs):
    user = User.objects.get(id=user_id)
    msg = EmailMultiAlternatives(
        # заголовок письма:
        f'Статус заказа id{order_id} обновлен',
        # сообщение получателю:
        f'Заказ id{order_id} сформирован',
        # адрес отправителя:
        settings.EMAIL_HOST_USER,
        # адрес получателя:
        [user.email]
    )
    msg.send()