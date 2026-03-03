import factory
from django.conf import settings
from django.contrib.gis.geos import MultiPolygon, Point, Polygon

from parking_permits.models import ParkingZone

from .faker import fake


def generate_point():
    return Point(
        24.915 + fake.random.uniform(0, 0.040),
        60.154 + fake.random.uniform(0, 0.022),
        srid=settings.SRID,
    )


def generate_polygon():
    center = generate_point()
    points = [
        Point(
            center.x + fake.random.uniform(-0.001, 0.001),
            center.y + fake.random.uniform(-0.001, 0.001),
            srid=settings.SRID,
        )
        for _ in range(3)
    ]
    points.append(points[0])
    return Polygon(points)


def generate_multi_polygon():
    return MultiPolygon(generate_polygon())


def generate_sequential_point(n):
    # NOTE: random fluctuations should be kept low enough to ensure
    # that the respective polygons created around consecutive
    # points do not overlap.
    return Point(
        24.915 + 0.05 * n + fake.random.uniform(0, 0.040),
        60.154 + 0.05 * n + fake.random.uniform(0, 0.022),
        srid=settings.SRID,
    )


def generate_sequential_polygon(n):
    center = generate_sequential_point(n)
    points = [
        Point(
            center.x + fake.random.uniform(-0.001, 0.001),
            center.y + fake.random.uniform(-0.001, 0.001),
            srid=settings.SRID,
        )
        for _ in range(3)
    ]
    points.append(points[0])
    return Polygon(points)


def generate_sequential_multi_polygon(n):
    return MultiPolygon(generate_sequential_polygon(n))


class ParkingZoneFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ParkingZone

    location = factory.Sequence(lambda n: generate_sequential_multi_polygon(n))
    name = factory.Sequence(lambda n: f"zone_{n + 1:d}")
