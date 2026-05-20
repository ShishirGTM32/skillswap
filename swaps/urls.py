from django.urls import path

from .views import SwapMatchListView, SwapRequestDetailView, SwapRequestListCreateView

urlpatterns = [
    path("matches/", SwapMatchListView.as_view(), name="swap-matches"),
    path("requests/", SwapRequestListCreateView.as_view(), name="swap-requests"),
    path("requests/<int:pk>/", SwapRequestDetailView.as_view(), name="swap-request-detail"),
]
