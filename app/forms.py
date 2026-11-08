from flask_wtf import FlaskForm
from sqlalchemy import func
from wtforms import (
    HiddenField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
    BooleanField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    Optional,
    Regexp,
    ValidationError,
)

from .models import STATUS_LABELS, Category, User
from .utils import normalize_name

try:  # WTForms >= 3.3
    from wtforms.fields import SelectChoice as _SelectChoice
except ImportError:  # pragma: no cover
    _SelectChoice = None


def make_choices(pairs):
    """Build SelectField choices without triggering the tuple deprecation warning."""
    pairs = list(pairs)
    return [_SelectChoice(v, l) for v, l in pairs] if _SelectChoice else pairs


PASSWORD_RULE = Length(min=8, max=128, message="Password must be 8–128 characters long.")


def _password_strength(form, field):
    pw = field.data or ""
    if not (any(c.isalpha() for c in pw) and any(c.isdigit() for c in pw)):
        raise ValidationError("Password must contain at least one letter and one digit.")


class RegisterForm(FlaskForm):
    username = StringField(
        "Username",
        validators=[
            DataRequired(),
            Length(min=3, max=32),
            Regexp(r"^[A-Za-z0-9_.-]+$", message="Use letters, digits, '_', '.' or '-' only."),
        ],
    )
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField("Password", validators=[DataRequired(), PASSWORD_RULE, _password_strength])
    confirm = PasswordField(
        "Confirm password", validators=[DataRequired(), EqualTo("password", message="Passwords do not match.")]
    )
    submit = SubmitField("Create account")

    def validate_username(self, field):
        if User.query.filter(func.lower(User.username) == field.data.strip().lower()).first():
            raise ValidationError("This username is already taken.")

    def validate_email(self, field):
        if User.query.filter(func.lower(User.email) == field.data.strip().lower()).first():
            raise ValidationError("An account with this email already exists.")


class LoginForm(FlaskForm):
    identifier = StringField("Username or email", validators=[DataRequired(), Length(max=120)])
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField("Remember me")
    submit = SubmitField("Sign in")


class ProfileForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=120)])
    submit = SubmitField("Save changes")

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._user = user

    def validate_email(self, field):
        other = User.query.filter(func.lower(User.email) == field.data.strip().lower()).first()
        if other and other.id != self._user.id:
            raise ValidationError("This email is used by another account.")


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Current password", validators=[DataRequired()])
    new_password = PasswordField("New password", validators=[DataRequired(), PASSWORD_RULE, _password_strength])
    confirm = PasswordField(
        "Confirm new password", validators=[DataRequired(), EqualTo("new_password", message="Passwords do not match.")]
    )
    submit = SubmitField("Change password")


class IdeaForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(min=5, max=140)])
    description = TextAreaField("Description", validators=[DataRequired(), Length(min=20, max=5000)])
    category = SelectField("Category", coerce=int, validators=[Optional()])
    new_category = StringField(
        "…or create a new category", validators=[Optional(), Length(min=2, max=50)]
    )
    submit = SubmitField("Submit idea")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [(c.id, c.name) for c in Category.query.order_by(Category.name).all()]
        self.category.choices = make_choices([(0, "— choose a category —")] + choices)

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators):
            return False
        has_new = bool(normalize_name(self.new_category.data))
        has_existing = bool(self.category.data)
        if not has_new and not has_existing:
            self.category.errors.append("Choose a category or create a new one.")
            return False
        return True


class CommentForm(FlaskForm):
    content = TextAreaField("Your comment", validators=[DataRequired(), Length(min=1, max=2000)])
    parent_id = HiddenField()
    submit = SubmitField("Post comment")


class ReviewForm(FlaskForm):
    status = SelectField("Status", choices=make_choices(STATUS_LABELS.items()), validators=[DataRequired()])
    review_note = TextAreaField("Reviewer note (visible to everyone)", validators=[Optional(), Length(max=2000)])
    submit = SubmitField("Save evaluation")


class CategoryForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(min=2, max=50)])
    description = StringField("Description", validators=[Optional(), Length(max=200)])
    submit = SubmitField("Save category")


class FeedbackForm(FlaskForm):
    kind = SelectField(
        "Type",
        choices=make_choices(
            [("bug", "Report a problem"), ("suggestion", "Suggest an improvement"), ("other", "Other")]
        ),
    )
    message = TextAreaField("Message", validators=[DataRequired(), Length(min=10, max=3000)])
    submit = SubmitField("Send feedback")
