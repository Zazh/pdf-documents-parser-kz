from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('upload/', views.upload_document, name='upload_document'),
    path('documents/', views.document_list, name='document_list'),
    path('documents/<int:pk>/', views.document_detail, name='document_detail'),
    path('calibrate/', views.coordinate_calibration, name='coordinate_calibration'),
    path('api/save-coordinates/', views.save_coordinates, name='save_coordinates'),
    path('api/get-coordinates/', views.get_coordinates, name='get_coordinates'),
]