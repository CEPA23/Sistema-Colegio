from django.urls import path
from . import views

urlpatterns = [
    path('', views.inventory_list, name='inventory_list'),
    path('producto/nuevo/', views.product_create, name='product_create'),
    path('producto/<int:pk>/editar/', views.product_edit, name='product_edit'),
    path('producto/<int:pk>/eliminar/', views.product_delete, name='product_delete'),
    path('producto/<int:pk>/ajustar/', views.stock_adjust, name='stock_adjust'),
    path('venta/', views.inventory_sale, name='inventory_sale'),
    path('movimientos/', views.movement_history, name='movement_history'),
    path('movimientos/<int:pk>/', views.movement_history, name='movement_history_product'),
    path('api/alertas/', views.low_stock_alert_api, name='low_stock_alert_api'),
]
