"""
URL configuration for sportify project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include('gestion.api_urls')),
    path('i18n/', include('django.conf.urls.i18n')),
    path('mot-de-passe-oublie/', auth_views.PasswordResetView.as_view(
        template_name='gestion/password_reset.html',
        email_template_name='gestion/password_reset_email.txt',
        success_url='/mot-de-passe-oublie/envoye/',
    ), name='password_reset'),
    path('mot-de-passe-oublie/envoye/', auth_views.PasswordResetDoneView.as_view(
        template_name='gestion/password_reset_done.html',
    ), name='password_reset_done'),
    path('reinitialiser/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='gestion/password_reset_confirm.html',
        success_url='/reinitialiser/termine/',
    ), name='password_reset_confirm'),
    path('reinitialiser/termine/', auth_views.PasswordResetCompleteView.as_view(
        template_name='gestion/password_reset_complete.html',
    ), name='password_reset_complete'),
    path('', include('gestion.urls')),
]
