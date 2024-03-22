import collections
import json
import logging
from datetime import datetime
from typing import Dict, List

import requests
from django.conf import settings

from parking_permits.exceptions import ParkkihubiPermitError
from parking_permits.utils import get_end_time, pairwise

logger = logging.getLogger("db")


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

    def __repr__(self):
        return f"<{self}>"

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

    @property
    def start_time_formatted(self) -> str:
        return self.start_time.isoformat()

    @property
    def end_time_formatted(self) -> str:
        return self.end_time.isoformat()

    def to_json(self) -> Dict[str, str]:
        return {
            "start_time": self.start_time_formatted,
            "end_time": self.end_time_formatted,
            "registration_number": self.registration_number,
        }


class Parkkihubi:
    """Service class for making Parkkihubi requests."""

    def __init__(self, permit):
        self.permit = permit

    @classmethod
    def create(cls, permit) -> None:
        """Create a new instance on Parkkihubi for this permit."""
        cls(permit).create_permit()

    @classmethod
    def update(cls, permit) -> None:
        """Update existing Parkkihubi instance."""
        cls(permit).update_permit()

    @classmethod
    def update_or_create(cls, permit) -> None:
        """Update or instance on Parkkihubi for this permit."""
        try:
            cls(permit).update_permit()
        except ParkkihubiPermitError:
            cls(permit).create_permit()

    def create_permit(self):
        if settings.DEBUG_SKIP_PARKKIHUBI_SYNC:  # pragma: no cover
            logger.debug("Skipped Parkkihubi sync in permit creation.")
            return

        payload = json.dumps(self.get_payload(), default=str)

        response = requests.post(
            settings.PARKKIHUBI_OPERATOR_ENDPOINT,
            data=payload,
            headers=self.get_headers(),
        )

        logger.info(f"Create parkkihubi permit, request payload: {payload}")

        self.permit.synced_with_parkkihubi = response.status_code == 201
        self.permit.save()

        if response.status_code == 201:
            logger.info("Parkkihubi permit created")
        else:
            logger.error(
                "Failed to create permit to Parkkihubi."
                f"Error: {response.status_code} {response.reason}. "
                f"Detail: {response.text}"
            )
            raise ParkkihubiPermitError(
                "Cannot create permit to Parkkihubi."
                f"Error: {response.status_code} {response.reason}."
            )

    def update_permit(self) -> None:
        if settings.DEBUG_SKIP_PARKKIHUBI_SYNC:  # pragma: no cover
            logger.debug("Skipped Parkkihubi sync in permit update.")
            return

        payload = json.dumps(self.get_payload(), default=str)

        response = requests.patch(
            f"{settings.PARKKIHUBI_OPERATOR_ENDPOINT}{str(self.permit.pk)}/",
            data=payload,
            headers=self.get_headers(),
        )

        self.permit.synced_with_parkkihubi = response.status_code == 200
        self.permit.save()

        logger.info(f"Update parkkihubi permit, request payload: {payload}")

        if response.status_code == 200:
            logger.info("Parkkihubi update permit successful")
        else:
            logger.error(
                "Failed to update permit to Parkkihubi."
                f"Error: {response.status_code} {response.reason}. "
                f"Detail: {response.text}"
            )
            raise ParkkihubiPermitError(
                "Cannot update permit to Parkkihubi."
                f"Error: {response.status_code} {response.reason}."
            )

    def get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"ApiKey {settings.PARKKIHUBI_TOKEN}",
            "Content-Type": "application/json",
        }

    def get_payload(self) -> Dict:
        # Create list of subjects:
        # Each subject should consist of start+end time and registration numbers
        # Once we have list of subjects, ensure that there are no overlapping subjects.

        subjects = self.get_subjects()

        return {
            "series": settings.PARKKIHUBI_PERMIT_SERIES,
            "domain": settings.PARKKIHUBI_DOMAIN,
            "external_id": str(self.permit.pk),
            "properties": {"permit_type": str(self.permit.type)},
            "subjects": [subject.to_json() for subject in subjects],
            "areas": [
                {
                    "start_time": subjects[0].start_time_formatted,
                    "end_time": subjects[-1].end_time_formatted,
                    "area": self.permit.parking_zone.name,
                }
            ],
        }

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
        # = 3 subjects: default permit 1st-15th;  temp vehicle 15th-20th; default 20th > 31st.

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

        # add another subject for default permit if the end time of the last subject is less
        # than end of this permit
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
