from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView, Response
from rest_framework_simplejwt.serializers import TokenRefreshSerializer

from .email_service import send_otp_email
from .models import DesiredSkill, Skill
from .redis_otp import (
    OtpPurpose,
    consume_password_reset_session,
    create_password_reset_session,
    generate_numeric_otp,
    store_otp,
    verify_otp,
)
from .serializers import (
    ForgotPasswordSerializer,
    ProfileSerializer,
    RegisterSerializer,
    ResendOtpSerializer,
    ResetPasswordSerializer,
    DesiredSkillListPatchSerializer,
    DesiredSkillListSerializer,
    DesiredSkillSerializer,
    SkillListPatchSerializer,
    SkillListSerializer,
    SkillSerializer,
    UserLoginSerializer,
    VerifyOtpSerializer,
)
from .api_views import HandledAPIView
from .utils import get_error_message, get_tokens_for_user

User = get_user_model()
logger = logging.getLogger(__name__)


def _issue_activation_otp(user: User) -> None:
    otp = generate_numeric_otp()
    store_otp(OtpPurpose.ACTIVATE, user.email, otp)
    send_otp_email(
        to_email=user.email,
        otp=otp,
        subject="Verify your SkillSwap account",
        intro="Welcome! Use this code to activate your account.",
        recipient_name=f"{user.first_name} {user.last_name}",
        heading="Email Verification",
        instruction="Please use the OTP below to verify your email address:",
    )


class RegisterView(APIView):
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        print(request.data)
        try:
            ser = RegisterSerializer(data=request.data)
            ser.is_valid(raise_exception=True)
            user = ser.save()
            _issue_activation_otp(user)
            return Response(
                {
                    "success": True,
                    "message": "Registration successful. Check your email for the activation code.",
                    "data": {"email": user.email, "purpose": "activate"},
                },
                status=status.HTTP_201_CREATED,
            )
        except (DRFValidationError, DjangoValidationError) as exc:
            return Response(
                {
                    "success": False,
                    "error": get_error_message(exc),
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            return Response(
                {
                    "success": False,
                    "error": get_error_message(exc),
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ResendOtpView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            ser = ResendOtpSerializer(data=request.data)
            ser.is_valid(raise_exception=True)
            email = ser.validated_data["email"].strip().lower()
            purpose = OtpPurpose(ser.validated_data["purpose"])
            purpose_str = ser.validated_data["purpose"]
            user = User.objects.filter(email__iexact=email).first()
            resend_data = {"email": email, "purpose": purpose_str}

            if purpose == OtpPurpose.ACTIVATE:
                if not user:
                    return Response(
                        {
                            "success": True,
                            "message": "If an account exists, a code was sent.",
                            "data": resend_data,
                        },
                        status=status.HTTP_200_OK,
                    )
                if user.email_verified:
                    return Response(
                        {
                            "success": False,
                            "error": "Account is already verified."
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                _issue_activation_otp(user)
            else:
                if not user or not user.email_verified:
                    return Response(
                        {
                            "success": True,
                            "message": "If an account exists, a code was sent.",
                            "data": resend_data,
                        },
                        status=status.HTTP_200_OK,
                    )
                otp = generate_numeric_otp()
                store_otp(OtpPurpose.PASSWORD_RESET, user.email, otp)
                send_otp_email(
                    to_email=user.email,
                    otp=otp,
                    subject="Reset your SkillSwap password",
                    intro="You requested a password reset. Use this code to continue.",
                    recipient_name=f"{user.first_name} {user.last_name}",
                    heading="Password reset",
                    instruction="Please use the OTP below to continue resetting your password:",
                )

            return Response(
                {
                    "success": True,
                    "message": "OTP sent to email for verification.",
                    "data": resend_data,
                },
                status=status.HTTP_200_OK,
            )
        except (DRFValidationError, DjangoValidationError) as exc:
            return Response(
                {
                    "success": False,
                    "error": get_error_message(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            return Response(
                {
                    "success": False,
                    "error": get_error_message(exc)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class VerifyOtpView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        print(request.data)
        try:
            ser = VerifyOtpSerializer(data=request.data)
            ser.is_valid(raise_exception=True)
            email = ser.validated_data["email"].strip().lower()
            otp = ser.validated_data["otp"].strip()
            purpose = OtpPurpose(ser.validated_data["purpose"])

            if not verify_otp(purpose, email, otp):
                return Response(
                    {
                        "success": False,
                        "error": "Invalid or session expired."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user = User.objects.filter(email__iexact=email).first()

            if purpose == OtpPurpose.ACTIVATE:
                if not user:
                    return Response(
                        {
                            "success": False,
                            "error": "Invalid or session expired."
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if user.email_verified:
                    return Response(
                        {
                            "success": True,
                            "message": "Account already verified.",
                            "data": {"email_verified": True},
                        },
                        status=status.HTTP_200_OK,
                    )
                user.is_active = True
                user.email_verified = True
                user.save(update_fields=["is_active", "email_verified"])
                return Response(
                    {
                        "success": True,
                        "message": "Account verified. You can log in.",
                        "data": {"email_verified": True, "is_active": True},
                    },
                    status=status.HTTP_200_OK,
                )

            if not user or not user.email_verified or user.deactivated_by_admin or not user.is_active:
                return Response(
                    {
                        "success": False,
                        "error": "Invalid or session expired."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            reset_token = create_password_reset_session(user.email)
            return Response(
                {
                    "success": True,
                    "message": "OTP verified. Submit your new password to reset-password.",
                    "data": {"reset_token": reset_token},
                },
                status=status.HTTP_200_OK,
            )
        except (DRFValidationError, DjangoValidationError) as exc:
            print(exc)
            return Response(
                {
                    "success": False,
                    "error": get_error_message(exc)
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            print(exc)
            return Response(
                {
                    "success": False,
                    "error": get_error_message(exc)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            ser = ForgotPasswordSerializer(data=request.data)
            ser.is_valid(raise_exception=True)
            email = ser.validated_data["email"].strip().lower()
            user = User.objects.filter(email__iexact=email).first()
            if user and user.email_verified and user.is_active and not user.deactivated_by_admin:
                otp = generate_numeric_otp()
                store_otp(OtpPurpose.PASSWORD_RESET, user.email, otp)
                send_otp_email(
                    to_email=user.email,
                    otp=otp,
                    subject="Reset your SkillSwap password",
                    intro="You requested a password reset. Use this code to continue.",
                    recipient_name=f"{user.first_name} {user.last_name}",
                    heading="Password reset",
                    instruction="Please use the OTP below to continue resetting your password:",
                )
            return Response(
                {
                    "success": True,
                    "message": "OTP sent to your email.",
                    "data": {"email": email, "purpose": "password_reset"},
                },
                status=status.HTTP_200_OK,
            )
        except (DRFValidationError, DjangoValidationError) as exc:
            return Response(
                {
                    "success": False,
                    "message": "",
                    "error": get_error_message(exc),
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            return Response(
                {
                    "success": False,
                    "message": "",
                    "error": get_error_message(exc),
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            ser = ResetPasswordSerializer(data=request.data)
            ser.is_valid(raise_exception=True)
            token = ser.validated_data["reset_token"]
            new_password = ser.validated_data["new_password"]
            email = consume_password_reset_session(token)
            if not email:
                return Response(
                    {
                        "success": False,
                        "error": "Invalid or expired reset session.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user = User.objects.filter(email__iexact=email).first()
            if not user:
                return Response(
                    {
                        "success": False,
                        "error": "User not found."
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            user.set_password(new_password)
            user.save(update_fields=["password"])
            return Response(
                {
                    "success": True,
                    "message": "Password has been reset.",
                    "data": {"confirm_password_match": True},
                },
                status=status.HTTP_200_OK,
            )
        except (DRFValidationError, DjangoValidationError) as exc:
            return Response(
                {
                    "success": False,
                    "message": "",
                    "error": get_error_message(exc),
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            return Response(
                {
                    "success": False,
                    "message": "",
                    "error": get_error_message(exc),
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class UserLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = UserLoginSerializer(
            data=request.data, context={"request": request}
        )
        try:
            serializer.is_valid(raise_exception=True)
        except DRFValidationError as e:
            return Response(
                {"error": get_error_message(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user_data = serializer.validated_data

        if isinstance(user_data, dict) and user_data.get("needs_activation"):
            return Response(
                {
                    "success":False,
                    "error": "Account not activated. OTP sent.",
                    "needs_activation": True,
                    "data": {
                        "email": user_data["email"],
                        "purpose": "activate"
                    }
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        user = user_data
        tokens = get_tokens_for_user(user)
        logger.info("[USER LOGIN] User authenticated successfully.")
        return Response(
            {
                "success": True,
                "user": {
                    "profile_complete": user.is_profile_complete,
                    "role": "admin" if user.is_superuser else "user",
                },
                "tokens": tokens,
                "is_admin": user.is_superuser,
                "message": "Login successful",
            },
            status=status.HTTP_200_OK,
        )


class TokenRefreshView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            ser = TokenRefreshSerializer(data=request.data)
            ser.is_valid(raise_exception=True)
            out = {"access": ser.validated_data["access"]}
            if "refresh" in ser.validated_data:
                out["refresh"] = ser.validated_data["refresh"]
            return Response(
                {"success": True, "message": "", "data": out},
                status=status.HTTP_200_OK,
            )
        except (DRFValidationError, DjangoValidationError) as exc:
            return Response(
                {
                    "success": False,
                    "message": "",
                    "error": get_error_message(exc),
                    "data": None,
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except Exception as exc:
            return Response(
                {
                    "success": False,
                    "message": "",
                    "error": get_error_message(exc),
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ProfileDetailView(APIView):
    permission_classes = [IsAuthenticated]
        

    def get(self, request):
        try:
            ser = ProfileSerializer(request.user, context={"request":request})
            return Response(
                {"success": True, "data": ser.data},
                status=status.HTTP_200_OK,
            )
        except (DRFValidationError, DjangoValidationError) as exc:
            return Response(
                {
                    "success": False,
                    "error": get_error_message(exc)
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            return Response(
                {
                    "success": False,
                    "error": get_error_message(exc)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def patch(self, request):
        try:
            ser = ProfileSerializer(request.user, data=request.data, partial=True)
            ser.is_valid(raise_exception=True)
            ser.save()
            return Response(
                {
                    "success": True,
                    "message": "Profile updated.",
                    "data": ser.data,
                },
                status=status.HTTP_200_OK,
            )
        except (DRFValidationError, DjangoValidationError) as exc:
            return Response(
                {
                    "success": False,
                    "error": get_error_message(exc)
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            return Response(
                {
                    "success": False,
                    "error": get_error_message(exc)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class SkillListView(HandledAPIView):
    def get(self, request):
        return self.run_action(
            lambda: SkillSerializer(
                Skill.objects.filter(user=request.user),
                many=True,
            ).data,
            message="Skill Fetched successfully",
            with_data=True,
        )

    @transaction.atomic
    def post(self, request):
        def action():
            ser = SkillListSerializer(
                data=request.data.copy(),
                context={"request": request},
            )
            ser.is_valid(raise_exception=True)
            ser.save(user=request.user)

        return self.run_action(
            action,
            message="Skills set successfully.",
            status_code=status.HTTP_201_CREATED,
        )

    def patch(self, request):
        def action():
            serializer = SkillListPatchSerializer(
                data=request.data,
                context={"request": request},
            )
            serializer.is_valid(raise_exception=True)
            serializer.sync(request.user)

        return self.run_action(action, message="Skills updated successfully.")


class DesiredSkillListView(HandledAPIView):
    def get(self, request):
        return self.run_action(
            lambda: DesiredSkillSerializer(
                DesiredSkill.objects.filter(user=request.user),
                many=True,
            ).data,
            message="Desired skills fetched successfully.",
            with_data=True,
        )

    @transaction.atomic
    def post(self, request):
        def action():
            ser = DesiredSkillListSerializer(
                data=request.data,
                context={"request": request},
            )
            ser.is_valid(raise_exception=True)
            ser.save(user=request.user)

        return self.run_action(
            action,
            message="Desired skills set successfully.",
            status_code=status.HTTP_201_CREATED,
        )

    def patch(self, request):
        def action():
            serializer = DesiredSkillListPatchSerializer(
                data=request.data,
                context={"request": request},
            )
            serializer.is_valid(raise_exception=True)
            serializer.sync(request.user)

        return self.run_action(action, message="Desired skills updated successfully.")
