from django.test import TestCase

from lazysignup.models import get_lazy_user_model


class LazyUserModelTests(TestCase):
    """
    Tests for LazyUser Model
    """
    def setUp(self):
        super(LazyUserModelTests, self).setUp()

    def test_str(self):
        """
        Tests str method on LazyUser
        """
        user, username = get_lazy_user_model().objects.create_lazy_user()
        lazyuser = user.lazyuser

        self.assertEqual(
            str(username) + ':' + str(lazyuser.created),
            str(user.lazyuser)
        )
