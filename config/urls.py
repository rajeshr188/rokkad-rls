"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
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
from django.urls import include, path

from billing.views import billing_webhook_api
from core.views import healthz, landing_page, pricing_page
from workspaces.views import workspace_create_page, workspace_home_page

urlpatterns = [
    path('healthz/', healthz, name='healthz'),
    path('', landing_page, name='landing-page'),
    path('pricing/', pricing_page, name='pricing-page'),
    path('billing/webhooks/<slug:provider>/', billing_webhook_api, name='billing-webhook-api'),
    path('app/', workspace_home_page, name='workspace-home'),
    path('workspaces/new/', workspace_create_page, name='workspace-create'),
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('accounts/', include('allauth.urls')),
    path('invitations/', include('workspace_invitations.urls')),
    path('w/<slug:workspace_slug>/', include('workspaces.urls')),
]
