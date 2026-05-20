# Move profile columns onto User; Skill.user replaces Skill.profile.
# Idempotent DB steps: missing profile_id, profile table already dropped, Postgres + SQLite.

import django.db.models.deletion
import django.utils.timezone
import users.models
from django.conf import settings
from django.db import migrations, models


def _quote(schema_editor, name: str) -> str:
    return schema_editor.quote_name(name)


def _table_columns(cursor, connection, table: str) -> set[str]:
    if connection.vendor == "postgresql":
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = %s
            """,
            [table],
        )
        return {row[0] for row in cursor.fetchall()}
    if connection.vendor == "sqlite":
        cursor.execute("PRAGMA table_info(%s)" % _quote_raw_sqlite_table(table))
        return {row[1] for row in cursor.fetchall()}
    raise NotImplementedError(f"Unsupported database vendor: {connection.vendor!r}")


def _quote_raw_sqlite_table(table: str) -> str:
    if not table.replace("_", "").isalnum():
        raise ValueError("Unexpected table name for SQLite pragma")
    return '"%s"' % table.replace('"', '""')


def _table_exists(cursor, connection, table: str) -> bool:
    if connection.vendor == "postgresql":
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = current_schema() AND table_name = %s
            )
            """,
            [table],
        )
        return bool(cursor.fetchone()[0])
    if connection.vendor == "sqlite":
        cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = %s LIMIT 1",
            [table],
        )
        return cursor.fetchone() is not None
    raise NotImplementedError(f"Unsupported database vendor: {connection.vendor!r}")


def _drop_skill_profile_fk_postgres(cursor, schema_editor, skill_table: str):
    qt = schema_editor.quote_name(skill_table)
    cursor.execute(
        """
        SELECT tc.constraint_name
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        WHERE tc.table_schema = current_schema()
          AND tc.table_name = %s
          AND tc.constraint_type = 'FOREIGN KEY'
          AND kcu.column_name = 'profile_id'
        """,
        [skill_table],
    )
    for (constraint_name,) in cursor.fetchall():
        qc = schema_editor.quote_name(constraint_name)
        cursor.execute(f"ALTER TABLE {qt} DROP CONSTRAINT {qc}")


def _copy_profile_rows_to_user(apps, schema_editor):
    """ORM copy so FileField paths and all backends stay consistent."""
    connection = schema_editor.connection
    Profile = apps.get_model("users", "Profile")
    User = apps.get_model("users", "User")
    profile_table = Profile._meta.db_table
    with connection.cursor() as cursor:
        if not _table_exists(cursor, connection, profile_table):
            return
    for p in Profile.objects.select_related("user").iterator():
        u = User.objects.get(pk=p.user_id)
        u.avatar = p.avatar
        u.bio = p.bio or ""
        u.profile_updated_at = p.updated_at
        u.save(update_fields=["avatar", "bio", "profile_updated_at"])


def forwards_schema_and_data(apps, schema_editor):
    connection = schema_editor.connection
    User = apps.get_model("users", "User")
    Skill = apps.get_model("users", "Skill")
    Profile = apps.get_model("users", "Profile")

    user_table = User._meta.db_table
    skill_table = Skill._meta.db_table
    profile_table = Profile._meta.db_table

    qu = _quote(schema_editor, user_table)
    qs = _quote(schema_editor, skill_table)

    with connection.cursor() as cursor:
        user_cols = _table_columns(cursor, connection, user_table)
        skill_cols = _table_columns(cursor, connection, skill_table)

        if "avatar" not in user_cols:
            cursor.execute(f"ALTER TABLE {qu} ADD COLUMN avatar varchar(100) NULL")

        if "bio" not in user_cols:
            if connection.vendor == "postgresql":
                cursor.execute(f"ALTER TABLE {qu} ADD COLUMN bio text NOT NULL DEFAULT ''")
                cursor.execute(f"ALTER TABLE {qu} ALTER COLUMN bio DROP DEFAULT")
            else:
                cursor.execute(f"ALTER TABLE {qu} ADD COLUMN bio text NOT NULL DEFAULT ''")

        if "profile_updated_at" not in user_cols:
            if connection.vendor == "postgresql":
                cursor.execute(
                    f"ALTER TABLE {qu} ADD COLUMN profile_updated_at timestamp with time zone "
                    f"NOT NULL DEFAULT CURRENT_TIMESTAMP"
                )
                cursor.execute(f"ALTER TABLE {qu} ALTER COLUMN profile_updated_at DROP DEFAULT")
            else:
                cursor.execute(
                    f"ALTER TABLE {qu} ADD COLUMN profile_updated_at datetime NOT NULL "
                    f"DEFAULT CURRENT_TIMESTAMP"
                )

    _copy_profile_rows_to_user(apps, schema_editor)

    with connection.cursor() as cursor:
        skill_cols = _table_columns(cursor, connection, skill_table)
        profile_exists = _table_exists(cursor, connection, profile_table)

        if "user_id" not in skill_cols:
            if connection.vendor == "postgresql":
                cursor.execute(
                    f"ALTER TABLE {qs} ADD COLUMN user_id bigint NULL "
                    f"REFERENCES {qu}(id) DEFERRABLE INITIALLY DEFERRED"
                )
            else:
                cursor.execute(f"ALTER TABLE {qs} ADD COLUMN user_id bigint NULL REFERENCES {qu}(id)")

        skill_cols = _table_columns(cursor, connection, skill_table)

        if "profile_id" in skill_cols and profile_exists:
            qp = _quote(schema_editor, profile_table)
            if connection.vendor == "postgresql":
                cursor.execute(
                    f"""
                    UPDATE {qs} AS s
                    SET user_id = p.user_id
                    FROM {qp} AS p
                    WHERE s.profile_id = p.id AND s.user_id IS NULL
                    """
                )
            else:
                cursor.execute(
                    f"""
                    UPDATE {qs}
                    SET user_id = (
                        SELECT p.user_id FROM {qp} AS p
                        WHERE p.id = {qs}.profile_id
                    )
                    WHERE profile_id IS NOT NULL AND user_id IS NULL
                    """
                )

        cursor.execute(f"SELECT id FROM {qu} ORDER BY id ASC LIMIT 1")
        row = cursor.fetchone()
        first_user_id = row[0] if row else None
        if first_user_id is not None:
            cursor.execute(
                f"UPDATE {qs} SET user_id = %s WHERE user_id IS NULL",
                [first_user_id],
            )
        else:
            cursor.execute(f"DELETE FROM {qs} WHERE user_id IS NULL")

        skill_cols = _table_columns(cursor, connection, skill_table)
        if "profile_id" in skill_cols:
            if connection.vendor == "postgresql":
                _drop_skill_profile_fk_postgres(cursor, schema_editor, skill_table)
                cursor.execute(f"ALTER TABLE {qs} DROP COLUMN IF EXISTS profile_id")
            else:
                try:
                    cursor.execute(f"ALTER TABLE {qs} DROP COLUMN profile_id")
                except Exception:
                    pass

        skill_cols = _table_columns(cursor, connection, skill_table)
        if "user_id" in skill_cols:
            cursor.execute(f"SELECT COUNT(*) FROM {qs} WHERE user_id IS NULL")
            null_count = cursor.fetchone()[0]
            if null_count == 0 and connection.vendor == "postgresql":
                cursor.execute(f"ALTER TABLE {qs} ALTER COLUMN user_id SET NOT NULL")

        if _table_exists(cursor, connection, profile_table):
            if connection.vendor == "postgresql":
                cursor.execute(f"DROP TABLE IF EXISTS {_quote(schema_editor, profile_table)} CASCADE")
            else:
                cursor.execute(f"DROP TABLE IF EXISTS {_quote(schema_editor, profile_table)}")


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0002_remove_user_full_name"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(
                    model_name="skill",
                    name="profile",
                ),
                migrations.AddField(
                    model_name="skill",
                    name="user",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="skills",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                migrations.AddField(
                    model_name="user",
                    name="avatar",
                    field=models.ImageField(
                        blank=True,
                        null=True,
                        upload_to=users.models.user_avatar_upload_to,
                    ),
                ),
                migrations.AddField(
                    model_name="user",
                    name="bio",
                    field=models.TextField(blank=True),
                ),
                migrations.AddField(
                    model_name="user",
                    name="profile_updated_at",
                    field=models.DateTimeField(
                        auto_now=True,
                        default=django.utils.timezone.now,
                    ),
                    preserve_default=False,
                ),
                migrations.DeleteModel(
                    name="Profile",
                ),
            ],
            database_operations=[
                migrations.RunPython(forwards_schema_and_data, migrations.RunPython.noop),
            ],
        ),
    ]
