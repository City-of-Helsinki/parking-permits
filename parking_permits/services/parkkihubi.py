import collections
import json
import logging
from datetime import datetime
from typing import Dict, List, Literal

import requests
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder

from parking_permits.exceptions import ParkkihubiPermitError
from parking_permits.models.parking_permit import ParkingPermit
from parking_permits.utils import get_end_time, pairwise

logger = logging.getLogger("db")


def sync_with_parkkihubi(permit: ParkingPermit) -> None:
    """Update or instance on Parkkihubi for this permit.

    If DEBUG_SKIP_PARKKIHUBI_SYNC is True, will skip API call entirely.
    """

    if settings.DEBUG_SKIP_PARKKIHUBI_SYNC:
        logger.debug("Skipped Parkkihubi sync for permit.")
        return

    service = Parkkihubi(permit)

    try:
        service.update()
    except ParkkihubiPermitError:
        service.create()


class Subject:
    """Parkkihubi subject line."""

    def __init__(
        self,
        *,
        start_time: datetime,
        end_time: datetime,
        registration_number: str,
    ):
        self.start_time = start_time
        self.end_time = end_time
        self.registration_number = registration_number

    def __str__(self):
        return f"{self.start_time}-{self.end_time}: {self.registration_number}"

    def __hash__(self):
        return hash(str(self))

    def __eq__(self, other) -> bool:
        return (
            other.start_time == self.start_time
            and other.end_time == self.end_time
            and other.registration_number == self.registration_number
        )

    def __gt__(self, other) -> bool:
        return self.start_time > other.start_time

    def __lt__(self, other) -> bool:
        return self.start_time < other.start_time

    def to_json(self) -> Dict:
        return {
            "start_time": self.start_time,
            "end_time": self.end_time,
            "registration_number": self.registration_number,
        }


class Parkkihubi:
    """Service class for making Parkkihubi requests."""

    def __init__(self, permit):
        self.permit = permit

    def create(self):
        payload = self.get_payload_data()

        response = requests.post(
            settings.PARKKIHUBI_OPERATOR_ENDPOINT,
            data=payload,
            headers=self.get_headers(),
        )

        logger.info(f"Create parkkihubi permit, request payload: {payload}")

        self.handle_response(response, 201, "create")

    def update(self) -> None:
        payload = self.get_payload_data()

        response = requests.patch(
            f"{settings.PARKKIHUBI_OPERATOR_ENDPOINT}{str(self.permit.pk)}/",
            data=payload,
            headers=self.get_headers(),
        )

        logger.info(f"Update parkkihubi permit, request payload: {payload}")

        self.handle_response(response, 200, "update")

    def get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"ApiKey {settings.PARKKIHUBI_TOKEN}",
            "Content-Type": "application/json",
        }

    def get_payload(self) -> Dict:
        subjects = self.get_subjects()

        return {
            "series": settings.PARKKIHUBI_PERMIT_SERIES,
            "domain": settings.PARKKIHUBI_DOMAIN,
            "external_id": str(self.permit.pk),
            "properties": {"permit_type": str(self.permit.type)},
            "subjects": [subject.to_json() for subject in subjects],
            "areas": [
                {
                    "start_time": subjects[0].start_time,
                    "end_time": subjects[-1].end_time,
                    "area": self.permit.parking_zone.name,
                }
            ],
        }

    def get_payload_data(self) -> str:
        return json.dumps(self.get_payload(), cls=DjangoJSONEncoder)

    def get_subjects(self) -> List[Subject]:
        start_time = self.permit.start_time
        end_time = self.permit.end_time or get_end_time(self.permit.start_time, 1)
        registration_number = self.permit.vehicle.registration_number

        subjects = [
            Subject(
                start_time=start_time,
                end_time=end_time,
                registration_number=registration_number,
            )
        ]

        temp_vehicles = (
            self.permit.temp_vehicles.filter(
                is_active=True,
                start_time__lte=end_time,
            )
            .order_by("start_time")
            .select_related("vehicle")
        )

        subjects += [
            Subject(
                start_time=max(start_time, temp_vehicle.start_time),
                end_time=min(temp_vehicle.end_time, end_time),
                registration_number=temp_vehicle.vehicle.registration_number,
            )
            for temp_vehicle in temp_vehicles
        ]

        # adjust subjects to ensure none overlapping
        # example: permit starts 1st March and ends 31st March.
        # temp vehicle starts 15th March and ends 20th March.
        # = 3 subjects: default permit 1st-15th;
        # temp vehicle 15th-20th; default 20th > 31st.

        extra_subjects = []

        for subject_a, subject_b in pairwise(subjects):
            # ensure we don't have overlapping times

            if subject_a.end_time > subject_b.start_time:
                subject_a.end_time = subject_b.start_time

            # if gap between subjects, insert default permit vehicle between them
            if subject_b.start_time > subject_a.end_time:
                extra_subjects.append(
                    Subject(
                        start_time=subject_a.end_time,
                        end_time=subject_b.start_time,
                        registration_number=registration_number,
                    )
                )

        # add another subject for default permit if the end time
        # of the last subject is less than end of this permit
        last_end_time = max([subject.end_time for subject in subjects])

        if end_time > last_end_time:
            extra_subjects.append(
                Subject(
                    start_time=last_end_time,
                    end_time=end_time,
                    registration_number=registration_number,
                )
            )

        # dedupe and sort
        return sorted([*collections.Counter(subjects + extra_subjects)])

    def handle_response(
        self,
        response: requests.Response,
        target_status_code: int,
        action: Literal["create", "update"],
    ) -> None:
        if response.status_code == target_status_code:
            self.permit.synced_with_parkkihubi = True
            self.permit.save()
            logger.info(f"Parkkihubi sync permit successful: {self.permit.pk}")
            return

        error_description = (
            "Failed to sync permit with Parkkihubi."
            f"Action: {action}"
            f"Permit: {self.permit.pk}\n"
            f"Status: {response.status_code} {response.reason}.\n"
            f"Detail: {response.text}\n"
        )

        raise ParkkihubiPermitError(error_description)
