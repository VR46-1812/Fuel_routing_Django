from django.urls import path
from .views import OptimizeRouteView

app_name = 'fuel'

urlpatterns = [
    path('optimize-route/', OptimizeRouteView.as_view(), name='optimize-route'),
]
