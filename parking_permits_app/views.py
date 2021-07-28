from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from .models import Customer, Product, Vehicle
from .permissions import ReadOnly
from .pricing.engine import calculate_cart_item_total_price
from .serializers import ProductSerializer
from .services import talpa


class TalpaResolveAvailability(APIView):
    def get(self, request, product_id, format=None):
        response = talpa.resolve_availability_response(
            product_id=product_id, availability=True
        )

        return Response(response)


class TalpaResolvePrice(APIView):
    def get(self, request, product_id, format=None):
        item_quantity = int(request.query_params.get("quantity", 0))
        vehicle_id = request.query_params.get("vehicleId", None)

        try:
            vehicle = Vehicle.objects.get(pk=vehicle_id)
        except Exception as e:
            return Response(
                {"message": f"{vehicle_id} vehicleId: {str(e)}"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not talpa.is_valid_uuid(product_id):
            return Response(
                {"message": "Invalid request"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            product = Product.objects.get(shared_product_id=product_id)
        except Exception:
            return Response(
                {"message": f"Price data for product {product_id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        total_price = calculate_cart_item_total_price(
            item_price=product.get_current_price(),
            item_quantity=item_quantity,
            vehicle_is_secondary=vehicle.primary_vehicle is False,
            vehicle_is_low_emission=vehicle.is_low_emission(),
        )

        response = talpa.resolve_price_response(
            product_id=product_id, total_price=total_price
        )

        return Response(response)


class TalpaResolveRightOfPurchase(APIView):
    def get(self, request, product_id, format=None):
        profile_id = request.query_params.get("profileId", None)
        vehicle_id = request.query_params.get("vehicleId", None)

        try:
            customer = Customer.objects.get(pk=profile_id)
            vehicle = Vehicle.objects.get(pk=vehicle_id)
        except Exception as e:
            return Response({"message": str(e)}, status=status.HTTP_404_NOT_FOUND)

        right_of_purchase = (
            customer.has_valid_address_within_zone()
            and customer.is_owner_or_holder_of_vehicle(vehicle)
            and customer.driving_licence.is_valid_for_vehicle(vehicle)
            and not vehicle.is_due_for_inspection()
        )

        response = talpa.resolve_right_of_purchase_response(
            product_id=product_id,
            right_of_purchase=right_of_purchase,
        )

        return Response(response)


class ProductViewSet(ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [ReadOnly]
