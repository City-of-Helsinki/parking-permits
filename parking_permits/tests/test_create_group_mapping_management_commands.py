import pytest
from django.contrib.auth.models import Group
from django.core.management import call_command
from helusers.models import ADGroup, ADGroupMapping

from ..management.commands import create_group_mapping


@pytest.mark.django_db
def test_create_group_mapping():
    call_command(create_group_mapping.Command())

    assert ADGroup.objects.count() == 6
    assert ADGroupMapping.objects.count() == 6
    assert Group.objects.count() == 6
