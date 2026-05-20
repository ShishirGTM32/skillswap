from django.urls import path

from .views import (
    DesiredSkillListView,
    SkillListView, ProfileDetailView, ResetPasswordView,
    ForgotPasswordView, VerifyOtpView, ResendOtpView,
    TokenRefreshView, UserLoginView, RegisterView
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("login/", UserLoginView.as_view(), name="auth-login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="auth-token-refresh"),
    path("resend-otp/", ResendOtpView.as_view(), name="auth-resend-otp"),
    path("verify-otp/", VerifyOtpView.as_view(), name="auth-verify-otp"),
    path("forgot-password/", ForgotPasswordView.as_view(), name="auth-forgot-password"),
    path("reset-password/", ResetPasswordView.as_view(), name="auth-reset-password"),
    path("self/profile/", ProfileDetailView.as_view(), name="me-profile"),
    path("self/skills/", SkillListView.as_view(), name="me-skills"),
    path("self/desired-skills/", DesiredSkillListView.as_view(), name="me-desired-skills"),
]
