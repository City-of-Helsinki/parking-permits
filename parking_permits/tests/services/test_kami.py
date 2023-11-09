import pytest

from parking_permits.services.kami import parse_street_data


class TestKamiService:
    @pytest.mark.parametrize(
        "street_address, street_name, street_number, apartment",
        [
            ("", "", "", ""),
            ("Mannerheimintie", "Mannerheimintie", "", ""),
            ("Mannerheimintie 2", "Mannerheimintie", "2", ""),
            ("Mannerheimintie 2 A 7", "Mannerheimintie", "2", "A 7"),
            ("Mannerheimintie 4-5", "Mannerheimintie", "4-5", ""),
            ("Mannerheimintie 2 as. 3", "Mannerheimintie", "2", "as. 3"),
            ("Mannerheimintie 5-7 A 3", "Mannerheimintie", "5-7", "A 3"),
            ("Mannerheimintie 6a B 10", "Mannerheimintie", "6a", "B 10"),
            ("Mannerheimintie 5-7b A 10", "Mannerheimintie", "5-7b", "A 10"),
            ("Mannerheimintie 20/4", "Mannerheimintie", "20/4", ""),
            ("Mannerheimintie 2 B 15a", "Mannerheimintie", "2", "B 15a"),
            ("Itäinen puistotie 3", "Itäinen puistotie", "3", ""),
            ("Itäinen puistotie 5a B 14c", "Itäinen puistotie", "5a", "B 14c"),
            ("Elisabeth Kochin tie 1", "Elisabeth Kochin tie", "1", ""),
            ("Elisabeth Kochin tie 1b D 10c", "Elisabeth Kochin tie", "1b", "D 10c"),
        ],
    )
    def test_parse_street_data_returns_correct_result(
        self, street_address, street_name, street_number, apartment
    ):
        assert (street_name, street_number, apartment) == parse_street_data(
            street_address
        )
