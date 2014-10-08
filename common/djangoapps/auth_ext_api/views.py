"""
Student Views
"""
import datetime
import logging
import re
import uuid
import time
from collections import defaultdict
from pytz import UTC

from django.conf import settings
from django.contrib.auth import logout, authenticate, login
from django.contrib.auth.models import User, AnonymousUser
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import password_reset_confirm
from django.contrib import messages
from django.core.context_processors import csrf
from django.core.mail import send_mail, BadHeaderError, EmailMultiAlternatives
from django.core.urlresolvers import reverse
from django.core.validators import validate_email, validate_slug, ValidationError
from django.db import IntegrityError, transaction
from django.http import (HttpResponse, HttpResponseBadRequest, HttpResponseForbidden,
                         Http404)
from django.shortcuts import redirect
from django.utils.translation import ungettext
from django_future.csrf import ensure_csrf_cookie
from django.utils.http import cookie_date, base36_to_int
from django.utils.translation import ugettext as _, get_language
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_GET
from django.utils.html import strip_tags

from django.db.models.signals import post_save
from django.dispatch import receiver

from django.template.response import TemplateResponse

from ratelimitbackend.exceptions import RateLimitException

from edxmako.shortcuts import render_to_response, render_to_string
from mako.exceptions import TopLevelLookupException

from course_modes.models import CourseMode
from student.models import (
    Registration, UserProfile, PendingNameChange,
    PendingEmailChange, CourseEnrollment, unique_id_for_user,
    CourseEnrollmentAllowed, UserStanding, LoginFailures,
    create_comments_service_user, PasswordHistory, UserSignupSource
)
from student.forms import PasswordResetFormNoActive

from verify_student.models import SoftwareSecurePhotoVerification, MidcourseReverificationWindow
from certificates.models import CertificateStatuses, certificate_status_for_student
from dark_lang.models import DarkLangConfig

from xmodule.modulestore.exceptions import ItemNotFoundError
from xmodule.modulestore.django import modulestore
from opaque_keys.edx.locations import SlashSeparatedCourseKey
from xmodule.modulestore import ModuleStoreEnum

from collections import namedtuple

from courseware.courses import get_courses, sort_by_announcement,get_course_about_section
from courseware.access import has_access

from django_comment_common.models import Role

from external_auth.models import ExternalAuthMap
import external_auth.views

from bulk_email.models import Optout, CourseAuthorization
import shoppingcart
from user_api.models import UserPreference
from lang_pref import LANGUAGE_KEY

import track.views

from dogapi import dog_stats_api

from util.json_request import JsonResponse
from util.bad_request_rate_limiter import BadRequestRateLimiter

from microsite_configuration import microsite

from util.password_policy_validators import (
    validate_password_length, validate_password_complexity,
    validate_password_dictionary
)

from third_party_auth import pipeline, provider
from xmodule.error_module import ErrorDescriptor

log = logging.getLogger("edx.student")
AUDIT_LOG = logging.getLogger("audit")


def login(request, extra_context=None):
    context = {
        'course_id': request.GET.get('course_id'),
        'email': '',
        'enrollment_action': request.GET.get('enrollment_action'),
        'name': '',
        'running_pipeline': None,
        'platform_name': microsite.get_value(
            'platform_name',
            settings.PLATFORM_NAME
        ),
        'selected_provider': '',
        'username': '',
    }
    
    return render_to_response('loginext.html', context)

@ensure_csrf_cookie
def post(request, error=""):  # pylint: disable-msg=too-many-statements,unused-argument
    """AJAX request to log in the user."""

    backend_name = None
    email = None
    password = None
    redirect_url = None
    response = None
    running_pipeline = None
    third_party_auth_requested = settings.FEATURES.get('ENABLE_THIRD_PARTY_AUTH') and pipeline.running(request)
    third_party_auth_successful = False
    trumped_by_first_party_auth = bool(request.POST.get('email')) or bool(request.POST.get('password'))
    user = None

    

    

    if 'email' not in request.POST or 'password' not in request.POST:
        return JsonResponse({
            "success": False,
            "value": _('There was an error receiving your login information. Please email us.'),  # TODO: User error message
        })  # TODO: this should be status code 400  # pylint: disable=fixme

    email = request.POST['email']
    password = request.POST['password']
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        if settings.FEATURES['SQUELCH_PII_IN_LOGS']:
            AUDIT_LOG.warning(u"Login failed - Unknown user email")
        else:
            AUDIT_LOG.warning(u"Login failed - Unknown user email: {0}".format(email))

    # see if account has been locked out due to excessive login failures
    user_found_by_email_lookup = user
    if user_found_by_email_lookup and LoginFailures.is_feature_enabled():
        if LoginFailures.is_user_locked_out(user_found_by_email_lookup):
            return JsonResponse({
                "success": False,
                "value": _('This account has been temporarily locked due to excessive login failures. Try again later.'),
            })  # TODO: this should be status code 429  # pylint: disable=fixme

    # see if the user must reset his/her password due to any policy settings
    if PasswordHistory.should_user_reset_password_now(user_found_by_email_lookup):
        return JsonResponse({
            "success": False,
            "value": _('Your password has expired due to password policy on this account. You must '
                       'reset your password before you can log in again. Please click the '
                       '"Forgot Password" link on this page to reset your password before logging in again.'),
        })  # TODO: this should be status code 403  # pylint: disable=fixme

    # if the user doesn't exist, we want to set the username to an invalid
    # username so that authentication is guaranteed to fail and we can take
    # advantage of the ratelimited backend
    username = user.username if user else ""

    if not third_party_auth_successful:
        try:
            user = authenticate(username=username, password=password, request=request)
        # this occurs when there are too many attempts from the same IP address
        except RateLimitException:
            return JsonResponse({
                "success": False,
                "value": _('Too many failed login attempts. Try again later.'),
            })  # TODO: this should be status code 429  # pylint: disable=fixme

    if user is None:
        # tick the failed login counters if the user exists in the database
        if user_found_by_email_lookup and LoginFailures.is_feature_enabled():
            LoginFailures.increment_lockout_counter(user_found_by_email_lookup)

        # if we didn't find this username earlier, the account for this email
        # doesn't exist, and doesn't have a corresponding password
        if username != "":
            if settings.FEATURES['SQUELCH_PII_IN_LOGS']:
                loggable_id = user_found_by_email_lookup.id if user_found_by_email_lookup else "<unknown>"
                AUDIT_LOG.warning(u"Login failed - password for user.id: {0} is invalid".format(loggable_id))
            else:
                AUDIT_LOG.warning(u"Login failed - password for {0} is invalid".format(email))
        return JsonResponse({
            "success": False,
            "value": _('Email or password is incorrect.'),
        })  # TODO: this should be status code 400  # pylint: disable=fixme

    # successful login, clear failed login attempts counters, if applicable
    if LoginFailures.is_feature_enabled():
        LoginFailures.clear_lockout_counter(user)

    if user is not None and user.is_active:
        try:
            # We do not log here, because we have a handler registered
            # to perform logging on successful logins.
            login(request, user)
            if request.POST.get('remember') == 'true':
                request.session.set_expiry(604800)
                log.debug("Setting user session to never expire")
            else:
                request.session.set_expiry(0)
        except Exception as e:
            AUDIT_LOG.critical("Login failed - Could not create session. Is memcached running?")
            log.critical("Login failed - Could not create session. Is memcached running?")
            log.exception(e)
            raise

        
        response = JsonResponse({
            "success": True,
            "username": user.username,
            "email": user.email
        })

        # set the login cookie for the edx marketing site 
        # we want this cookie to be accessed via javascript
        # so httponly is set to None

        if request.session.get_expire_at_browser_close():
            max_age = None
            expires = None
        else:
            max_age = request.session.get_expiry_age()
            expires_time = time.time() + max_age
            expires = cookie_date(expires_time)

        response.set_cookie(
            settings.EDXMKTG_COOKIE_NAME, 'true', max_age=max_age,
            expires=expires, domain=settings.SESSION_COOKIE_DOMAIN,
            path='/', secure=None, httponly=None,
        )

        return response

    if settings.FEATURES['SQUELCH_PII_IN_LOGS']:
        AUDIT_LOG.warning(u"Login failed - Account not active for user.id: {0}, resending activation".format(user.id))
    else:
        AUDIT_LOG.warning(u"Login failed - Account not active for user {0}, resending activation".format(username))

    reactivation_email_for_user(user)
    not_activated_msg = _("This account has not been activated. We have sent another activation message. Please check your e-mail for the activation instructions.")
    return JsonResponse({
        "success": False,
        "value": not_activated_msg,
    })  # TODO: this should be status code 400  # pylint: disable=fixme

