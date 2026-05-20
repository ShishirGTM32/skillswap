from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import Q


User = get_user_model()


def _name_match_q(field_prefix: str, names: list[str]) -> Q:
    clause = Q()
    for name in names:
        clause |= Q(**{f"{field_prefix}__name__iexact": name.strip()})
    return clause


def eligible_swap_users():
    return User.objects.filter(
        is_active=True,
        email_verified=True,
        deactivated_by_admin=False,
    )


def get_mutual_swap_matches(user):
    desired_names = list(user.desired_skills.values_list("name", flat=True))
    skill_names = list(user.skills.values_list("name", flat=True))

    if not desired_names or not skill_names:
        return User.objects.none()

    teaches_me = _name_match_q("skills", desired_names)
    wants_from_me = _name_match_q("desired_skills", skill_names)

    return (
        eligible_swap_users()
        .exclude(pk=user.pk)
        .filter(teaches_me)
        .filter(wants_from_me)
        .distinct()
        .prefetch_related("skills", "desired_skills")
    )


def matching_skills_for_user(
    owner,
    *,
    skill_names: set[str],
    desired_names: set[str],
) -> dict:
    skill_names_lower = {n.lower() for n in skill_names}
    desired_names_lower = {n.lower() for n in desired_names}

    they_offer = [
        {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "proficiency_percent": s.proficiency_percent,
        }
        for s in owner.skills.all()
        if s.name.lower() in desired_names_lower
    ]
    they_want = [
        {
            "id": d.id,
            "name": d.name,
            "description": d.description,
            "order": d.order,
        }
        for d in owner.desired_skills.all()
        if d.name.lower() in skill_names_lower
    ]
    return {"they_offer": they_offer, "they_want": they_want}


def build_match_payload(match_user, viewer, request=None) -> dict:
    viewer_skill_names = set(viewer.skills.values_list("name", flat=True))
    viewer_desired_names = set(viewer.desired_skills.values_list("name", flat=True))

    overlap = matching_skills_for_user(
        match_user,
        skill_names=viewer_desired_names,
        desired_names=viewer_skill_names,
    )
    you_offer = [
        {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "proficiency_percent": s.proficiency_percent,
        }
        for s in viewer.skills.all()
        if s.name.lower() in {d["name"].lower() for d in overlap["they_want"]}
    ]
    you_want = [
        {
            "id": d.id,
            "name": d.name,
            "description": d.description,
            "order": d.order,
        }
        for d in viewer.desired_skills.all()
        if d.name.lower() in {s["name"].lower() for s in overlap["they_offer"]}
    ]

    avatar = None
    if match_user.avatar and request:
        avatar = request.build_absolute_uri(match_user.avatar.url)

    return {
        "user": {
            "id": match_user.id,
            "username": match_user.username,
            "first_name": match_user.first_name,
            "last_name": match_user.last_name,
            "avatar": avatar,
            "bio": match_user.bio,
        },
        "they_offer": overlap["they_offer"],
        "they_want": overlap["they_want"],
        "you_offer": you_offer,
        "you_want": you_want,
    }


