from django.core import mail
from django.template.loader import render_to_string
from django.utils import translation
from django.utils.html import strip_tags
from django.utils.translation import gettext_lazy as _


class PermitEmailType:
    CREATED = "created"
    UPDATED = "updated"
    ENDED = "ended"
    TEMP_VEHICLE_ACTIVATED = "temp_vehicle_activated"
    TEMP_VEHICLE_DEACTIVATED = "temp_vehicle_deactivated"
    EXPIRATION_REMIND = "expiration_remind"


SUBJECT_PREFIX = _("Parking permits")

permit_email_subjects = {
    PermitEmailType.CREATED: "%s: %s"
    % (SUBJECT_PREFIX, _("New parking permit has been created for you")),
    PermitEmailType.UPDATED: "%s: %s"
    % (SUBJECT_PREFIX, _("Your parking permit information has been updated")),
    PermitEmailType.ENDED: "%s: %s" % (SUBJECT_PREFIX, _("Your order has ended")),
    PermitEmailType.TEMP_VEHICLE_ACTIVATED: "%s: %s"
    % (SUBJECT_PREFIX, _("Temporary vehicle attached to your permit")),
    PermitEmailType.TEMP_VEHICLE_DEACTIVATED: "%s: %s"
    % (SUBJECT_PREFIX, _("Your parking permit information has been updated")),
    PermitEmailType.EXPIRATION_REMIND: "%s: %s"
    % (SUBJECT_PREFIX, _("Your parking permit will expire soon")),
}

permit_email_templates = {
    PermitEmailType.CREATED: "emails/permit_created.html",
    PermitEmailType.UPDATED: "emails/permit_updated.html",
    PermitEmailType.ENDED: "emails/permit_ended.html",
    PermitEmailType.TEMP_VEHICLE_ACTIVATED: "emails/temporary_vehicle_activated.html",
    PermitEmailType.TEMP_VEHICLE_DEACTIVATED: "emails/temporary_vehicle_deactivated.html",
    PermitEmailType.EXPIRATION_REMIND: "emails/expiration_remind.html",
}


def send_permit_email(action, permit):
    with translation.override(permit.customer.language):
        subject = permit_email_subjects[action]
        template = permit_email_templates[action]
        html_message = render_to_string(template, context={"permit": permit})
        plain_message = strip_tags(html_message)
        recipient_list = [permit.customer.email]
        mail.send_mail(
            subject,
            plain_message,
            None,
            recipient_list,
            html_message=html_message,
        )


class RefundEmailType:
    CREATED = "created"
    ACCEPTED = "accepted"


refund_email_subjects = {
    RefundEmailType.CREATED: "%s: %s"
    % (SUBJECT_PREFIX, _("Your refund has been registered")),
    RefundEmailType.ACCEPTED: "%s: %s"
    % (SUBJECT_PREFIX, _("Your refund has been accepted")),
}


refund_email_templates = {
    RefundEmailType.CREATED: "emails/refund_created.html",
    RefundEmailType.ACCEPTED: "emails/refund_accepted.html",
}


def send_refund_email(action, customer, refund):
    with translation.override(customer.language):
        subject = refund_email_subjects[action]
        template = refund_email_templates[action]
        html_message = render_to_string(template, context={"refund": refund})
        plain_message = strip_tags(html_message)
        recipient_list = [customer.email]
        mail.send_mail(
            subject,
            plain_message,
            None,
            recipient_list,
            html_message=html_message,
        )
