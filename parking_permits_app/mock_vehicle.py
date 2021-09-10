import random
from datetime import datetime, timedelta

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q

from parking_permits_app import constants
from parking_permits_app.constants import EmissionType, VehicleCategory
from parking_permits_app.models import Vehicle, VehicleType

CARS = [
    {"manufacturer": "Toyota", "model": "CH-R"},
    {"manufacturer": "Toyota", "model": "Corolla"},
    {"manufacturer": "Toyota", "model": "Yaris"},
    {"manufacturer": "Toyota", "model": "Avensis"},
    {"manufacturer": "Toyota", "model": "Aygo"},
    {"manufacturer": "Nissan", "model": "Micra"},
    {"manufacturer": "BMW", "model": "X1"},
    {"manufacturer": "Audi", "model": "A6"},
    {"manufacturer": "VW", "model": "Golf"},
]


def get_mock_vehicle(customer, registration):
    car = random.choice(CARS)
    vehicle_type = VehicleType.objects.get(type=constants.VehicleType.BENSIN.value)
    try:
        vehicle = Vehicle.objects.get(
            Q(registration_number__iexact=registration),
            Q(owner=customer) | Q(holder=customer),
        )
    except ObjectDoesNotExist:
        vehicle = Vehicle.objects.create(
            owner=customer,
            holder=customer,
            last_inspection_date=datetime.now() + timedelta(days=365),
            emission_type=EmissionType.EURO.value,
            emission=random.randint(50, 150),
            registration_number=registration,
            production_year=random.randint(2010, 2021),
            manufacturer=car.get("manufacturer"),
            model=car.get("model"),
            category=VehicleCategory.M1.value,
            type=vehicle_type,
        )
    return vehicle
