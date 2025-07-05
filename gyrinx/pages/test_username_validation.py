"""Test username validation to prevent email addresses."""

from django.test import TestCase
from gyrinx.pages.forms import JoinWaitingListForm
from gyrinx.core.forms import SignupForm


class TestUsernameValidation(TestCase):
    """Test that usernames cannot be email addresses."""

    def test_waiting_list_form_rejects_email_as_username(self):
        """Test that the waiting list form rejects email addresses as usernames."""
        form_data = {
            "email": "test@example.com",
            "desired_username": "user@example.com",  # This should be rejected
            "captcha": "dummy",  # ReCaptcha would be mocked in real tests
        }
        form = JoinWaitingListForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("desired_username", form.errors)
        # Check that the error message mentions email/@ symbol
        error_messages = form.errors["desired_username"]
        self.assertTrue(
            any("@" in msg or "email" in msg.lower() for msg in error_messages)
        )

    def test_waiting_list_form_accepts_valid_username(self):
        """Test that the waiting list form accepts valid usernames."""
        form_data = {
            "email": "test@example.com",
            "desired_username": "valid_username123",
            "captcha": "dummy",
        }
        form = JoinWaitingListForm(data=form_data)
        # Note: form might still be invalid due to captcha, but username should be valid
        if not form.is_valid() and "desired_username" in form.errors:
            self.fail(f"Valid username rejected: {form.errors['desired_username']}")

    def test_signup_form_rejects_email_as_username(self):
        """Test that the signup form rejects email addresses as usernames."""
        form_data = {
            "username": "user@example.com",  # This should be rejected
            "email": "test@example.com",
            "password1": "ComplexPassword123!",
            "password2": "ComplexPassword123!",
            "captcha": "dummy",
        }
        form = SignupForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("username", form.errors)
        # Check that the error message mentions email/@ symbol
        error_messages = form.errors["username"]
        self.assertTrue(
            any("@" in msg or "email" in msg.lower() for msg in error_messages)
        )

    def test_signup_form_accepts_valid_username(self):
        """Test that the signup form accepts valid usernames."""
        form_data = {
            "username": "valid_username123",
            "email": "test@example.com",
            "password1": "ComplexPassword123!",
            "password2": "ComplexPassword123!",
            "captcha": "dummy",
        }
        form = SignupForm(data=form_data)
        # Note: form might still be invalid due to captcha, but username should be valid
        if not form.is_valid() and "username" in form.errors:
            self.fail(f"Valid username rejected: {form.errors['username']}")

    def test_username_help_text_mentions_no_email(self):
        """Test that help text mentions not using email address."""
        form = SignupForm()
        if "username" in form.fields:
            help_text = form.fields["username"].help_text
            self.assertIn("email", help_text.lower())
            self.assertIn("username", help_text.lower())
