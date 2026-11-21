import pytest
from pydantic import ValidationError

from app.models import StaffProfile, StudentProfile, TeacherProfile, UserType, parse_profile

BASE = {"firstName": "Ada", "lastName": "Lovelace", "email": "ada@example.com"}


@pytest.mark.parametrize(
    ("user_type", "field", "value", "model"),
    [
        ("student", "major", "Computer Science", StudentProfile),
        ("staff", "adminRole", "Registrar", StaffProfile),
        ("teacher", "speciality", "Distributed Systems", TeacherProfile),
    ],
)
def test_valid_profile_per_type(user_type, field, value, model):
    profile = parse_profile({**BASE, "userType": user_type, field: value})
    assert isinstance(profile, model)
    assert profile.user_type == UserType(user_type)
    dumped = profile.model_dump(by_alias=True)
    assert dumped[field] == value
    assert dumped["userType"] == user_type


@pytest.mark.parametrize(
    ("user_type", "missing"),
    [("student", "major"), ("staff", "adminRole"), ("teacher", "speciality")],
)
def test_type_specific_field_is_required(user_type, missing):
    with pytest.raises(ValidationError) as exc:
        parse_profile({**BASE, "userType": user_type})
    assert missing in str(exc.value)


@pytest.mark.parametrize(
    ("user_type", "own", "foreign"),
    [
        ("student", {"major": "CS"}, {"adminRole": "Registrar"}),
        ("student", {"major": "CS"}, {"speciality": "Math"}),
        ("staff", {"adminRole": "Registrar"}, {"major": "CS"}),
        ("staff", {"adminRole": "Registrar"}, {"speciality": "Math"}),
        ("teacher", {"speciality": "Math"}, {"major": "CS"}),
        ("teacher", {"speciality": "Math"}, {"adminRole": "Registrar"}),
    ],
)
def test_fields_of_other_types_are_rejected(user_type, own, foreign):
    with pytest.raises(ValidationError):
        parse_profile({**BASE, "userType": user_type, **own, **foreign})


@pytest.mark.parametrize("value", ["", "   "])
def test_type_specific_field_cannot_be_blank(value):
    with pytest.raises(ValidationError):
        parse_profile({**BASE, "userType": "student", "major": value})


def test_unknown_user_type_rejected():
    with pytest.raises(ValidationError):
        parse_profile({**BASE, "userType": "admin", "major": "CS"})


def test_missing_user_type_rejected():
    with pytest.raises(ValidationError):
        parse_profile({**BASE, "major": "CS"})


def test_invalid_email_rejected():
    with pytest.raises(ValidationError):
        parse_profile({**BASE, "email": "not-an-email", "userType": "student", "major": "CS"})


def test_whitespace_is_stripped_and_snake_case_accepted():
    profile = parse_profile(
        {
            "first_name": "  Ada ",
            "last_name": "Lovelace",
            "email": "ada@example.com",
            "user_type": "staff",
            "admin_role": "  Registrar  ",
        }
    )
    assert profile.first_name == "Ada"
    assert profile.admin_role == "Registrar"
