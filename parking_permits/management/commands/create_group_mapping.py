from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction
from helusers.models import ADGroup, ADGroupMapping

from users.models import ParkingPermitGroups

CONTENT_TYPE = "parking_permits"
GROUPS = [
    {
        "name": ParkingPermitGroups.SUPER_ADMIN,
        "ad_group": "sg_kymp_pyva_asukpt_yllapito",
        "permissions": [
            "add_product",
            "change_product",
            "delete_product",
            "view_product",
            "add_lowemissioncriteria",
            "change_lowemissioncriteria",
            "delete_lowemissioncriteria",
            "view_lowemissioncriteria",
            "add_address",
            "change_address",
            "delete_address",
            "view_address",
            "add_parkingpermit",
            "change_parkingpermit",
            "delete_parkingpermit",
            "view_parkingpermit",
            "change_refund",
            "delete_refund",
            "view_refund",
            "view_order",
        ],
    },
    {
        "name": ParkingPermitGroups.SANCTIONS_AND_REFUNDS,
        "ad_group": "sg_kymp_pyva_asukpt_maksuseuraamukset_palautukset",
        "permissions": [
            "add_parkingpermit",
            "change_parkingpermit",
            "delete_parkingpermit",
            "view_parkingpermit",
            "change_refund",
            "delete_refund",
            "view_refund",
            "view_order",
        ],
    },
    {
        "name": ParkingPermitGroups.SANCTIONS,
        "ad_group": "sg_kymp_pyva_asukpt_maksuseuraamukset",
        "permissions": [
            "add_parkingpermit",
            "change_parkingpermit",
            "delete_parkingpermit",
            "view_parkingpermit",
            "change_refund",
            "delete_refund",
            "view_refund",
            "view_order",
        ],
    },
    {
        "name": ParkingPermitGroups.CUSTOMER_SERVICE,
        "ad_group": "sg_kymp_pyva_asukpt_asiakaspalvelu",
        "permissions": [
            "add_parkingpermit",
            "change_parkingpermit",
            "delete_parkingpermit",
            "view_parkingpermit",
            "change_refund",
            "delete_refund",
            "view_refund",
            "view_order",
        ],
    },
    {
        "name": ParkingPermitGroups.PREPARATORS,
        "ad_group": "sg_kymp_pyva_asukpt_valmistelijat",
        "permissions": [
            "view_parkingpermit",
            "view_order",
            "view_refund",
        ],
    },
    {
        "name": ParkingPermitGroups.INSPECTORS,
        "ad_group": "sg_kymp_pyva_asukpt_tarkastajat",
        "permissions": [
            "view_parkingpermit",
        ],
    },
]


class Command(BaseCommand):
    help = "Create parking permit group and ad group mapping"

    @transaction.atomic
    def handle(self, *args, **options):
        for group in GROUPS:
            ad_group = ADGroup.objects.get_or_create(
                name=group["ad_group"],
                display_name=group["ad_group"],
            )
            parking_permit_group = Group.objects.get_or_create(
                name=group["name"],
            )
            parking_permit_group[0].permissions.add(
                *Permission.objects.filter(
                    codename__in=group["permissions"],
                    content_type__app_label=CONTENT_TYPE,
                )
            )

            ADGroupMapping.objects.get_or_create(
                group=parking_permit_group[0],
                ad_group=ad_group[0],
            )
        self.stdout.write("Test Group and GroupMapping created")
