"""User profile model.

Every profile shares a common base; each user type carries exactly one
type-specific field:

- student -> ``major``
- staff   -> ``adminRole``
- teacher -> ``speciality``

``userType`` is the discriminator: a payload is validated against the model
for its type, the type-specific field is required, and fields belonging to
other types are rejected (``extra="forbid"``).
"""

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, TypeAdapter
from pydantic.alias_generators import to_camel


class UserType(StrEnum):
    STUDENT = "student"
    STAFF = "staff"
    TEACHER = "teacher"


NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class ProfileBase(BaseModel):
    """Fields shared by all user types. Serialized with camelCase aliases."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    first_name: NonEmptyStr
    last_name: NonEmptyStr
    email: EmailStr
    bio: Annotated[str, StringConstraints(max_length=500)] | None = None
    avatar_url: Annotated[str, StringConstraints(max_length=2048)] | None = None


class StudentProfile(ProfileBase):
    user_type: Literal[UserType.STUDENT]
    major: NonEmptyStr


class StaffProfile(ProfileBase):
    user_type: Literal[UserType.STAFF]
    admin_role: NonEmptyStr


class TeacherProfile(ProfileBase):
    user_type: Literal[UserType.TEACHER]
    speciality: NonEmptyStr


Profile = Annotated[
    StudentProfile | StaffProfile | TeacherProfile,
    Field(discriminator="user_type"),
]

_profile_adapter: TypeAdapter[Profile] = TypeAdapter(Profile)


def parse_profile(data: Any) -> StudentProfile | StaffProfile | TeacherProfile:
    """Validate a raw payload (camelCase or snake_case keys) into the right profile type."""
    return _profile_adapter.validate_python(data)
