from distutils.util import strtobool
import ujson
from django.db.models import Q, F, Sum
from django.db import IntegrityError
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiExample
from ordering_goods.models import Shop
from ordering_goods.serializers import ShopSerializer
from .models import *
from .signals import *
from .serializers import *


@extend_schema(tags=['Пользователи'])
@extend_schema_view(
    create=extend_schema(summary='Добавление контактов пользователя',
                         request=ContactSerializer,
                         examples=[OpenApiExample("Пример добавления контактов пользователя",
                                                  value=
                                                    {
                                                        'city': 'Ногинск',
                                                        'street': '3 Интернационала',
                                                        'house': '185',
                                                        'building': '2',
                                                        'apartment': '45',
                                                        'phone': '+7 977 800 70 52'
                                                    }, status_codes=[str(status.HTTP_201_CREATED)])]),
    partial_update=extend_schema(summary='Частичное изменение контактов',
                         examples=[OpenApiExample("На примере изменения номера телефона",
                         value=
                        {
                            'phone': '+7 999 999 99 99'
                        }, status_codes=[str(status.HTTP_201_CREATED)])]),
    list=extend_schema(summary='Получение списка контактов'),
    retrieve=extend_schema(summary='Получение контактных данных пользователя по id'),
    destroy=extend_schema(summary='Удаление контактных данных пользователя по id'))
class ContactViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Contact.objects.all()
    serializer_class = ContactSerializer
    http_method_names = ['get', 'post', 'patch', 'delete', ]

    def create(self, request, *args, **kwargs):
        request.data.update({'user': request.user.id})
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            return Response({'status': True}, status=201)

    def retrieve(self, request, pk=None):
        cont = Contact.objects.filter(user_id=pk).first()
        serializer = self.serializer_class(cont)
        return Response(serializer.data)

    def partial_update(self, request, pk=None, *args, **kwargs):
        cont = Contact.objects.filter(user_id=pk).first()
        serializer = self.serializer_class(cont, data=request.data, partial=True)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            return Response({'status': True}, status=200)

    def destroy(self, request, pk=None, *args, **kwargs):
        cont = Contact.objects.filter(user_id=pk)
        self.perform_destroy(cont)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=['Заказы'])
class BasketView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        basket = Order.objects.filter(
            user_id=request.user.id, state='basket').prefetch_related(
            'ordered_items__product_info__product__category',
            'ordered_items__product_info__product_parameters__parameter').annotate(
            total_sum=Sum(F('ordered_items__quantity') * F('ordered_items__product_info__price'))).distinct()
        serializer = OrderSerializer(basket, many=True)
        return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        items_sting = request.data.get('items')
        if items_sting:
            try:
                items_dict = ujson.loads(items_sting)
            except ValueError:
                return Response({'Status': False, 'Errors': 'Неверный формат запроса'})
            else:
                basket, _ = Order.objects.get_or_create(user_id=request.user.id, state='basket')
                objects_created = 0
                for order_item in items_dict:
                    order_item.update({'order': basket.id})
                    serializer = OrderItemSerializer(data=order_item)
                    if serializer.is_valid():
                        try:
                            serializer.save()
                        except IntegrityError as error:
                            return Response({'Status': False, 'Errors': str(error)})
                        else:
                            objects_created += 1
                    else:
                        return Response({'Status': False, 'Errors': serializer.errors})
                return Response({'Status': True, 'Создано объектов': objects_created}, status=status.HTTP_201_CREATED)
        return Response({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})

    def put(self, request, *args, **kwargs):
        items_string = request.data.get('items')
        if items_string:
            try:
                items_dict = ujson.loads(items_string)
            except ValueError:
                return Response({'status': False, 'Error': 'Не верный формат запроса'})
            else:
                basket, _ = Order.objects.get_or_create(user_id=request.user.id, state='basket')
                objects_update = 0
                for order_item in items_dict:
                    if type(order_item['id']) == int and type(order_item['quantity']) == int:
                        objects_update += OrderItem.objects.filter(order_id=basket.id, id=order_item['id']).update(
                            quantity=order_item['quantity'])
                return Response({'status': True, 'Обновлено позиций': objects_update})
        return Response({'status': False, 'Error': 'Не указаны все необходимые параметры'})

    def delete(self, request, *args, **kwargs):
        items_string = request.data.get('items')
        if items_string:
            list_items = items_string.split(',')
            basket, _ = Order.objects.get_or_create(user_id=request.user.id, state='basket')
            query = Q()
            deleted_positions = False
            for item_id in list_items:
                if item_id.isdigit():
                    query = query | Q(order_id=basket.id, id=item_id)
                    deleted_positions = True
            if deleted_positions:
                deleted_positions_count = OrderItem.objects.filter(query).delete()[0]
                left_position_count = OrderItem.objects.filter(order_id=basket.id).count()
                if left_position_count == 0:
                    Order.objects.filter(state='basket', user_id=request.user.id).delete()
                    return Response({'status': True, 'Удалено объектов': f'{deleted_positions_count}. '
                                                                         'В вашей корзине пусто!'},
                                    status=status.HTTP_204_NO_CONTENT)
                return Response({'status': True, 'Удалено объектов': deleted_positions_count},
                                status=status.HTTP_204_NO_CONTENT)
        return Response({'status': False, 'Error': 'Не указаны все необходимые параметры'})


@extend_schema(tags=['Заказы'])
class OrderView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        if {'order_id', 'contact'}.issubset(request.data):
            try:
                updated = Order.objects.filter(user_id=request.user.id, id=request.data['order_id']).update(
                    contact_id=request.data['contact'], state='new')
            except IntegrityError as error:
                return Response({'status': False, 'Error': 'Не верно указаны аругменты'})
            else:
                if updated:
                    order_is_created.send(sender=self.__class__, user_id=request.user.id,
                                          order_id=request.data['order_id'])
                    return Response({'status': True})
        return Response({'status': False, 'Error': 'Не указаны все необходимые параметры'})

    def get(self, request, *args, **kwargs):
        order = Order.objects.filter(user_id=request.user.id).exclude(state='basket').prefetch_related(
            'ordered_items__product_info__product__category',
            'ordered_items__product_info__product_parameters__parameter').select_related('contact').annotate(
            total_sum=Sum(F('ordered_items__quantity') * F('ordered_items__product_info__price'))).distinct()
        serializer = OrderSerializer(order, many=True)
        return Response(serializer.data)


@extend_schema(tags=['Заказы'])
class PartnerOrders(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        if request.user.type != 'shop':
            return Response({'Status': False, 'Error': 'Только для магазинов'})
        order = Order.objects.filter(
            ordered_items__product_info__shop__user_id=request.user.id).exclude(state='basket').prefetch_related(
            'ordered_items__product_info__product__category',
            'ordered_items__product_info__product_parameters__parameter').select_related('contact').annotate(
            total_sum=Sum(F('ordered_items__quantity') * F('ordered_items__product_info__price'))).distinct()
        serializer = OrderSerializer(order, many=True)
        return Response(serializer.data)


@extend_schema(tags=['Поставщики'])
@extend_schema_view(
    retrieve=extend_schema(
        summary='Получение статуса поставщика по id'),
    list=extend_schema(summary='Получение всех активных поставщиков'),
    create=extend_schema(summary='Смена статуса поставщика',
                         examples=[OpenApiExample('Пример смены статуса поставщика',
                                                  value={'state': 'on'})]))
class PartnerStateSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Shop.objects.all()
    serializer_class = ShopSerializer
    http_method_names = ['post', 'get']

    def list(self, request, *args, **kwargs):
        queryset = Shop.objects.filter(state=True)
        serializer = self.serializer_class(queryset, many=True)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        if self.request.user.type != 'shop':
            return Response({'Status': False, 'Error': 'Только для магазинов'})
        state = request.data.get('state')
        if state:
            try:
                Shop.objects.filter(user_id=request.user.id).update(state=strtobool(state))
                return Response({'State changed to': state})
            except ValueError as error:
                return Response({'Status': False, 'Errors': str(error)})
        return Response({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})