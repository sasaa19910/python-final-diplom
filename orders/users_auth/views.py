from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from rest_framework.generics import CreateAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet
from rest_framework import viewsets, status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiExample
from django_rest_passwordreset.views import ResetPasswordConfirm, ResetPasswordRequestToken
from .serializers import *
from .models import *
from .signals import user_is_registered


@extend_schema(tags=['Пользователи'])
@extend_schema_view(
    create=extend_schema(summary='Регистрация пользователя',
                         request=UserSerializer,
                         examples=[OpenApiExample("Пример регистрации пользователя с необязательным параметром"
                                                  " shop - регистрация от имени поставщика",
                                                  description="Ответ в электронной почте должен содержать токен"
                                                              " для последующего подтверждения этой самой почты",
                                                  value=
                                                   {
                                                     'first_name': 'Вася',
                                                     'last_name': 'Васечкин',
                                                     'email': 'ваш_адрес_эл_почты',
                                                     'password': '15wvfus89',
                                                     'company': 'Вкусно и точка',
                                                     'position': 'Директор',
                                                     'type': 'shop'
                                                   }, status_codes=[str(status.HTTP_201_CREATED)])]))
class UserRegister(ModelViewSet):
    authentication_classes=()
    serializer_class = UserSerializer
    http_method_names = ['post', ]

    def create(self, request, *args, **kwargs):
        password = self.request.data.get('password', None)
        if not password:
            return Response({'error': 'Не указан пароль пользователя'}, status=400)
        try:
            validate_password(password)
        except Exception as password_error:
            errors_array = []
            for item in password_error:
                errors_array.append(item)
            return Response({'status': False, 'errors': {'password': errors_array}})
        else:
            self.request.data["password"] = make_password(password)
            serializer = self.serializer_class(data=self.request.data)
            serializer.is_valid(raise_exception=True)
            user = serializer.save()
            user_is_registered.send(sender=self.__class__, user_id=user.pk)
            return Response({'status': 'Создан новый пользователь'}, status=201)


@extend_schema(tags=['Пользователи'])
@extend_schema_view(
    post=extend_schema(summary='Подтверждение адреса электронной почты',
                       examples=[OpenApiExample("Пример запроса",
                                                description="Для тестирования модифицировать пример " 
                                                            "запроса вставив токен полученный из почты",
                                                value={'email': 'gosh20goga@mail.ru', 'token': 'токен_из_почты'},
                                                status_codes=[str(status.HTTP_201_CREATED)])]))
class EmailConfirmation(CreateAPIView):
    authentication_classes=()
    serializer_class = UserSerializer
    queryset = User.objects.all()

    def post(self, request, *args, **kwargs):
        if {'email', 'token'}.issubset(request.data):
            token = ConfirmEmailToken.objects.filter(user__email=request.data['email'],
                                                    key=request.data['token']).first()
            if token:
                token.user.is_active = True
                token.user.save()
                token.delete()
                return Response({'status': True})
            else:
                return Response({'status': False, 'Errors': 'Не верно указан токен и(или) email'})
        return Response({'status': False, 'Errors': 'Не все обязательные параметры указаны'})


@extend_schema(tags=['Пользователи'])
@extend_schema_view(
    post=extend_schema(summary='Вход на сайт с помощью email и password',
                       examples=[OpenApiExample("Пример запроса",
                                                description='ответ должен содержать токен авторизации',
                                                value={'email': 'gosh20goga@mail.ru', 'password': '15wvfus89'},
                                                status_codes=[str(status.HTTP_201_CREATED)])]))
class UserLogin(CreateAPIView):
    authentication_classes=()
    serializer_class = UserSerializer
    queryset = User.objects.all()

    def post(self, request, *args, **kwargs):
        if {'email', 'password'}.issubset(request.data):
            user = authenticate(request, username=request.data['email'], password=request.data['password'])
            if user is not None:
                if user.is_active:
                    token, _ = Token.objects.get_or_create(user=user)
                    return Response({'status': True, 'Token': token.key})
            return Response({'status': False, 'Errors': 'Нe удалось авторизовать пользователя'}, status=400)
        return Response({'status': False, 'Errors': 'Не указаны все необходимые аргументы'})


@extend_schema(tags=['Пользователи'])
@extend_schema_view(
    list=extend_schema(summary='Получение списка пользователeй с детальной информацией'),
    retrieve=extend_schema(summary='Получение детальной информации о пользователе по id'),
)
class UserDetailsSet(viewsets.ReadOnlyModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='Частичное изменение параметров пользователя',
                   description='Указать id пользователя и значение изменяемого параметра',
                   examples=[
                       OpenApiExample(
                           'Пример изменения пароля пользователя',
                           description='Пример нового пароля',
                           value={'password': '12wvfus89'},
                           status_codes=[status.HTTP_200_OK])])
    @action(detail=True, methods=['POST'])
    def change(self, request, pk=None):
        if 'password' in self.request.data:
            try:
                validate_password(self.request.data['password'])
            except Exception as password_error:
                errors_array = []
                for item in password_error:
                    errors_array.append(item)
                    return Response({'status': False, 'errors': {'password': errors_array}})
            else:
                self.request.data["password"] = make_password(self.request.data["password"])
        details = self.get_object()
        serializer = UserSerializer(details, data=self.request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({'status': True})
        else:
            return Response({'status': False, 'Errors': serializer.errors})


@extend_schema(tags=['Пользователи'])
@extend_schema_view(
    post=extend_schema(
        summary='Получение токена для сброса пароля',
        examples=[OpenApiExample("Пример сброса текущего пароля",
                                 description="Ответ в электронной почте должен содержать токен",
                                                value=
                                                {
                                                    'email': 'gosh20goga@mail.ru',

                                                }, status_codes=[str(status.HTTP_201_CREATED)])]
    )
)
class MyResetPasswordRequestToken(ResetPasswordRequestToken):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'reset_password'


@extend_schema(tags=['Пользователи'])
@extend_schema_view(
    post=extend_schema(
        summary='Замена текущего пароля',
        examples=[OpenApiExample("Пример нового пароля",
                                 description="Для тестирования модифицировать пример " 
                                             "запроса вставив токен полученный из почты "
                                             "После данной процедуры необходимо заново авторизоваться",
                                 value={'password': '12wbfus89', 'token': 'токен_из_почты'},
                                 status_codes=[str(status.HTTP_201_CREATED)])]
    )
)
class MyResetPasswordConfirm(ResetPasswordConfirm):
    pass

