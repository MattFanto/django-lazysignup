import re
import uuid

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.utils.timezone import now
from django.apps import apps as django_apps
import six

from lazysignup.constants import USER_AGENT_BLACKLIST
from lazysignup.exceptions import NotLazyError
from lazysignup.utils import is_lazy_user
from lazysignup.signals import converted
from lazysignup import constants
from django.contrib.auth import get_user_model
DEFAULT_BLACKLIST = (
    'slurp',
    'googlebot',
    'yandex',
    'msnbot',
    'baiduspider',
)

for user_agent in getattr(settings, 'LAZYSIGNUP_USER_AGENT_BLACKLIST', DEFAULT_BLACKLIST):
    USER_AGENT_BLACKLIST.append(re.compile(user_agent, re.I))


def get_lazy_user_model():
    """
    Return the User model that is active in this project.
    """
    lazy_user_model_class = getattr(settings, 'LAZYSIGNUP_LAZY_USER_MODEL', 'lazysignup.LazyUser')
    try:
        return django_apps.get_model(lazy_user_model_class, require_ready=False)
    except ValueError:
        raise ImproperlyConfigured("LAZYSIGNUP_LAZY_USER_MODEL must be of the form 'app_label.model_name'")
    except LookupError:
        raise ImproperlyConfigured(
            "LAZYSIGNUP_LAZY_USER_MODEL refers to model '%s' that has not been installed" % lazy_user_model_class
        )


class AbstractLazyUserManager(models.Manager):

    def __hash__(self):
        """
        Implemented so signal can be sent in .convert() for Django 1.8
        """
        return hash(str(self))

    username_field = get_user_model().USERNAME_FIELD

    def create_lazy_user(self):
        """ Create a lazy user. Returns a 2-tuple of the underlying User
        object (which may be of a custom class), and the username.
        """
        raise NotImplemented('LazyUserManager must implement create_lazy_user method')

    def convert(self, form):
        """ Convert a lazy user to a non-lazy one. The form passed
        in is expected to be a ModelForm instance, bound to the user
        to be converted.

        The converted ``User`` object is returned.

        Raises a TypeError if the user is not lazy.
        """
        raise NotImplemented('LazyUserManager must implement convert method')


class LazyUserManager(AbstractLazyUserManager):

    def create_lazy_user(self):
        """ Create a lazy user. Returns a 2-tuple of the underlying User
        object (which may be of a custom class), and the username.
        """
        user_class = self.model.get_user_class()
        username = self.generate_username(user_class)
        user = user_class.objects.create_user(username, '')
        self.create(user=user)
        return user, username

    def convert(self, form):
        """ Convert a lazy user to a non-lazy one. The form passed
        in is expected to be a ModelForm instance, bound to the user
        to be converted.

        The converted ``User`` object is returned.

        Raises a TypeError if the user is not lazy.
        """
        if not is_lazy_user(form.instance):
            raise NotLazyError('You cannot convert a non-lazy user')

        user = form.save()

        # We need to remove the LazyUser instance assocated with the
        # newly-converted user
        self.filter(user=user).delete()
        converted.send(self, user=user)
        return user

    def generate_username(self, user_class):
        """ Generate a new username for a user
        """
        m = getattr(user_class, 'generate_username', None)
        if m:
            return m()
        else:
            max_length = user_class._meta.get_field(
                self.username_field).max_length
            return uuid.uuid4().hex[:max_length]


@six.python_2_unicode_compatible
class AbstractLazyUser(models.Model):
    user = models.OneToOneField(constants.LAZYSIGNUP_USER_MODEL, on_delete=models.CASCADE)
    objects = AbstractLazyUserManager()

    @classmethod
    def get_user_class(cls):
        related_user_field = cls._meta.get_field('user')
        # Django < 1.9 has rel.to
        if hasattr(related_user_field, 'rel'):
            rel_to = related_user_field.rel.to if related_user_field.rel else None
        elif hasattr(related_user_field, 'remote_field'):
            rel_to = related_user_field.remote_field.model if related_user_field.remote_field else None
        return rel_to

    class Meta:
        abstract = True


@six.python_2_unicode_compatible
class LazyUser(AbstractLazyUser):
    created = models.DateTimeField(default=now, db_index=True)
    objects = LazyUserManager()

    def __str__(self):
        return '{0}:{1}'.format(self.user, self.created)


