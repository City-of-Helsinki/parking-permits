from django.test import TestCase

from parking_permits.forms import DataExportForm, PdfExportForm


class DataExportFormTestCase(TestCase):
    def test_form_is_valid_when_valid_data_provided(self):
        data = {
            "data_type": "orders",
            "order_by": '{"order_fields": ["id"], "order_direction": "DESC"}',
            "search_items": '[{"matchType": "exact", "fields": ["id"], "value": 1}]',
        }
        form = DataExportForm(data)
        self.assertTrue(form.is_valid())

    def test_form_not_valid_when_fail_to_decode_error(self):
        data = {"data_type": "orders", "order_by": ";{}"}
        form = DataExportForm(data)
        self.assertFalse(form.is_valid())
        self.assertTrue(form.has_error("order_by", code="decode_error"))

    def test_form_not_valid_when_invalid_order_by_provided(self):
        data = {"data_type": "orders", "order_by": '{"key": "value"}'}
        form = DataExportForm(data)
        self.assertFalse(form.is_valid())
        self.assertTrue(form.has_error("order_by", code="invalid_data"))

    def test_form_not_valid_when_fail_to_decode_search_items(self):
        data = {"data_type": "orders", "search_items": "[,]"}
        form = DataExportForm(data)
        self.assertFalse(form.is_valid())
        self.assertTrue(form.has_error("search_items", code="decode_error"))

    def test_form_not_valid_when_invalid_search_items_provided(self):
        data = {"data_type": "orders", "search_items": '[{"matchType": "exact"}]'}
        form = DataExportForm(data)
        self.assertFalse(form.is_valid())
        self.assertTrue(form.has_error("search_items", code="invalid_data"))


class PdfExportFormTestCase(TestCase):
    def test_form_is_valid_when_valid_data_provided(self):
        data = {
            "data_type": "permit",
            "object_id": 1,
        }
        form = PdfExportForm(data)
        self.assertTrue(form.is_valid())

    def test_form_not_valid_when_data_type_not_provided(self):
        data = {
            "object_id": 1,
        }
        form = PdfExportForm(data)
        self.assertFalse(form.is_valid())

    def test_form_not_valid_when_object_id_not_provided(self):
        data = {
            "data_type": "permit",
        }
        form = PdfExportForm(data)
        self.assertFalse(form.is_valid())
