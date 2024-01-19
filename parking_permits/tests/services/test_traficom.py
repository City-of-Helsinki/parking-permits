import datetime
from unittest import mock

from django.test import TestCase, override_settings

from parking_permits.exceptions import TraficomFetchVehicleError
from parking_permits.models import DrivingClass, DrivingLicence
from parking_permits.services.traficom import Traficom
from parking_permits.tests.factories.customer import CustomerFactory
from parking_permits.tests.factories.vehicle import VehicleFactory


class MockResponse:
    def __init__(self, text="", status_code=200):
        self.text = text
        self.status_code = status_code


class TestTraficom(TestCase):
    registration_number = "BCI-707"
    hetu = "290200A905H"

    @classmethod
    def setUpTestData(cls):
        cls.traficom = Traficom()

    def test_fetch_vehicle(self):
        with mock.patch("requests.post", return_value=MockResponse(PAYLOAD_VEHICLE_OK)):
            vehicle = self.traficom.fetch_vehicle_details(self.registration_number)
            self.assertEqual(vehicle.registration_number, self.registration_number)

    def test_fetch_vehicle_already_exists(self):
        vehicle = VehicleFactory(registration_number=self.registration_number)

        with mock.patch("requests.post", return_value=MockResponse(PAYLOAD_VEHICLE_OK)):
            fetched_vehicle = self.traficom.fetch_vehicle_details(
                self.registration_number
            )
            self.assertEqual(fetched_vehicle, vehicle)

    def test_traficom_api_error(self):
        with mock.patch("requests.post", return_value=MockResponse(status_code=500)):
            self.assertRaises(
                TraficomFetchVehicleError,
                self.traficom.fetch_vehicle_details,
                self.registration_number,
            )

    def test_vehicle_not_found(self):
        with mock.patch(
            "requests.post", return_value=MockResponse(PAYLOAD_VEHICLE_NOT_FOUND)
        ):
            self.assertRaises(
                TraficomFetchVehicleError,
                self.traficom.fetch_vehicle_details,
                self.registration_number,
            )

    def test_unsupported_vehicle_class(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(PAYLOAD_UNSUPPORTED_VEHICLE_CLASS),
        ):
            self.assertRaises(
                TraficomFetchVehicleError,
                self.traficom.fetch_vehicle_details,
                self.registration_number,
            )

    def test_vehicle_decommissioned(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(PAYLOAD_DECOMISSIONED),
        ):
            self.assertRaises(
                TraficomFetchVehicleError,
                self.traficom.fetch_vehicle_details,
                self.registration_number,
            )

    def test_fetch_vehicle_from_db(self):
        VehicleFactory(registration_number=self.registration_number)
        with override_settings(TRAFICOM_MOCK=True):
            with mock.patch("requests.post") as mock_traficom:
                vehicle = self.traficom.fetch_vehicle_details(self.registration_number)
                self.assertEqual(vehicle.registration_number, self.registration_number)
                mock_traficom.assert_not_called()

    def test_fetch_vehicle_from_db_not_found(self):
        with override_settings(TRAFICOM_MOCK=True):
            with mock.patch("requests.post") as mock_traficom:
                self.assertRaises(
                    TraficomFetchVehicleError,
                    self.traficom.fetch_vehicle_details,
                    self.registration_number,
                )

                mock_traficom.assert_not_called()

    def test_fetch_valid_licence(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(PAYLOAD_LICENCE_OK),
        ):
            result = self.traficom.fetch_driving_licence_details(self.hetu)
            self.assertEqual(len(result["driving_classes"]), 7)
            self.assertEqual(result["issue_date"], "2023-09-01")

    def test_fetch_invalid_licence(self):
        with mock.patch(
            "requests.post",
            return_value=MockResponse(PAYLOAD_INVALID_LICENCE),
        ):
            self.assertRaises(
                TraficomFetchVehicleError,
                self.traficom.fetch_driving_licence_details,
                self.hetu,
            )

    def test_fetch_licence_from_db(self):
        customer = CustomerFactory(national_id_number=self.hetu)
        licence = DrivingLicence.objects.create(
            customer=customer,
            start_date=datetime.date(2023, 6, 3),
        )
        assert licence.start_date == datetime.date(2023, 6, 3)
        driving_class = DrivingClass.objects.create(identifier="A")
        licence.driving_classes.add(driving_class)

        with override_settings(TRAFICOM_MOCK=True):
            with mock.patch("requests.post") as mock_traficom:
                result = self.traficom.fetch_driving_licence_details(self.hetu)
                self.assertEqual(result["issue_date"], licence.start_date)
                self.assertEqual(result["driving_classes"].count(), 1)
                mock_traficom.assert_not_called()

    def test_fetch_licence_from_db_not_found(self):
        with override_settings(TRAFICOM_MOCK=True):
            with mock.patch("requests.post") as mock_traficom:
                self.assertRaises(
                    TraficomFetchVehicleError,
                    self.traficom.fetch_driving_licence_details,
                    self.hetu,
                )

                mock_traficom.assert_not_called()


PAYLOAD_INVALID_LICENCE = """
<kehys><yleinen><sanomatyyppi>TPSUOTIEDOTKORTTIHAKUOUT</sanomatyyppi><erakoodi /><sekvenssinumero /><sovellus>TPSUO</sovellus><ymparisto>LONTOO,LONTOO</ymparisto><virhe><virheluokka>info</virheluokka><virhekoodi>578</virhekoodi><virheselite>Henkilölle ei löydy ajokorttia</virheselite></virhe></yleinen><sanoma><ktp>
    <ajokorttiluokanTiedot>
        <ajokorttiluokkatieto>
            <hetu>290200A905H</hetu>
        </ajokorttiluokkatieto>
    </ajokorttiluokanTiedot>
</ktp></sanoma></kehys>
"""  # noqa: E501

PAYLOAD_VEHICLE_NOT_FOUND = """
<kehys><yleinen><sanomatyyppi>TPSUOTIEDOTLAAJAHAKUOUT</sanomatyyppi><erakoodi /><sekvenssinumero /><sovellus>TPSUO</sovellus><ymparisto>LONTOO,LONTOO</ymparisto><virhe><virheluokka>info</virheluokka><virhekoodi>550</virhekoodi><virheselite>Ajoneuvoa ei löydy rekisteristä, tarkista rekisteritunnus.</virheselite></virhe></yleinen><sanoma><ajoneuvontiedot>
    <laaja hetu="true">
        <tunnus laji="1">
            <rekisteritunnus>BCI-707</rekisteritunnus>
        </tunnus>
    </laaja>
</ajoneuvontiedot></sanoma></kehys>
"""  # noqa: E501

PAYLOAD_LICENCE_OK = """
<kehys><yleinen><sanomatyyppi>TPSUOTIEDOTKORTTIHAKUOUT</sanomatyyppi><erakoodi/><sekvenssinumero/><sovellus>TPSUO</sovellus><ymparisto>LONTOO,LONTOO</ymparisto></yleinen><sanoma><ktp>
    <ajokorttiluokanTiedot>
        <ajokorttiluokkatieto>
            <hetu>290200A905H</hetu>
            <sukunimi>Kiviniemi</sukunimi>
            <etunimet>Helge Abel</etunimet>
            <ajokorttiluokka>A B</ajokorttiluokka>
            <ajokortinMyontamisPvm>2023-09-01</ajokortinMyontamisPvm>
            <ajooikeusluokat>
                <ajooikeusluokka>
                    <ajooikeusluokka>A1</ajooikeusluokka>
                    <alkamispvm>2023-09-01</alkamispvm>
                </ajooikeusluokka>
                <ajooikeusluokka>
                    <ajooikeusluokka>B</ajooikeusluokka>
                    <alkamispvm>2023-09-01</alkamispvm>
                </ajooikeusluokka>
                <ajooikeusluokka>
                    <ajooikeusluokka>M</ajooikeusluokka>
                    <alkamispvm>2023-09-01</alkamispvm>
                </ajooikeusluokka>
            </ajooikeusluokat>
            <viimeisinajooikeus>
                <ajooikeusluokka>
                    <ajooikeusluokka>A</ajooikeusluokka>
                    <alkamispvm>2023-09-01</alkamispvm>
                </ajooikeusluokka>
                <ajooikeusluokka>
                    <ajooikeusluokka>A1</ajooikeusluokka>
                    <alkamispvm>2023-09-01</alkamispvm>
                </ajooikeusluokka>
                <ajooikeusluokka>
                    <ajooikeusluokka>A2</ajooikeusluokka>
                    <alkamispvm>2023-09-01</alkamispvm>
                </ajooikeusluokka>
                <ajooikeusluokka>
                    <ajooikeusluokka>AM/120</ajooikeusluokka>
                    <alkamispvm>2023-09-01</alkamispvm>
                </ajooikeusluokka>
                <ajooikeusluokka>
                    <ajooikeusluokka>AM/121</ajooikeusluokka>
                    <alkamispvm>2023-09-01</alkamispvm>
                </ajooikeusluokka>
                <ajooikeusluokka>
                    <ajooikeusluokka>B</ajooikeusluokka>
                    <alkamispvm>2023-09-01</alkamispvm>
                </ajooikeusluokka>
                <ajooikeusluokka>
                    <ajooikeusluokka>T</ajooikeusluokka>
                    <alkamispvm>2023-09-01</alkamispvm>
                </ajooikeusluokka>
            </viimeisinajooikeus>
        </ajokorttiluokkatieto>
    </ajokorttiluokanTiedot>
</ktp></sanoma></kehys>"""  # noqa: E501

PAYLOAD_VEHICLE_OK = """
<kehys><yleinen><sanomatyyppi>TPSUOTIEDOTLAAJAHAKUOUT</sanomatyyppi><erakoodi/><sekvenssinumero/><sovellus>TPSUO</sovellus><ymparisto>LONTOO,LONTOO</ymparisto></yleinen><sanoma><ajoneuvontiedot>
    <laaja hetu="true">
        <tunnus laji="1">
            <rekisteritunnus>BCI-707</rekisteritunnus>
            <valmistenumero>WF0WXXGCDW5D05303</valmistenumero>
            <jarjestelmatunnus>0041237599</jarjestelmatunnus>
        </tunnus>
        <ajoneuvonTiedot>
            <ajoneuvoluokka>M1</ajoneuvoluokka>
            <merkki>135</merkki>
            <merkkiSelvakielinen>Ford</merkkiSelvakielinen>
            <mallimerkinta>4D FOCUS STW 1.6VCT-DA3/264</mallimerkinta>
            <tila>3</tila>
            <ajoneuvonKaytto>01</ajoneuvonKaytto>
            <rekisterointitod1Osa>
                <jarjestysnumero>28</jarjestysnumero>
                <tulostuspaiva>2023-06-13</tulostuspaiva>
            </rekisterointitod1Osa>
            <rekisterointitod2Osa>
                <jarjestysnumero>14</jarjestysnumero>
                <tulostuspaiva>2018-06-18</tulostuspaiva>
            </rekisterointitod2Osa>
        </ajoneuvonTiedot>
        <ajoneuvonPerustiedot>
            <tyyppihyvaksyntanro>e13*2001/116*0144*06</tyyppihyvaksyntanro>
            <variantti>HXDA1W</variantti>
            <versio>5ABAL6</versio>
            <kaupallinenNimi>FOCUS</kaupallinenNimi>
            <tyyppikoodi>5135572533</tyyppikoodi>
            <kayttoonottopvm>20051205</kayttoonottopvm>
            <mkAjanAlkupvm>2023-06-13</mkAjanAlkupvm>
            <mkAjanLoppupvm>2024-06-18</mkAjanLoppupvm>
            <katsastusajankohta>2023-06-13</katsastusajankohta>
            <katsastuspaatos>2</katsastuspaatos>
            <katsastuspaikka>Porvoon Autokatsastus</katsastuspaikka>
            <ajovakaudenHallinta>false</ajovakaudenHallinta>
            <valmistenumeronSijainti>Z</valmistenumeronSijainti>
            <rakennettuAjoneuvo>false</rakennettuAjoneuvo>
            <valmistenumeronSijaintiMuu>VALMISTEKILPI: B-PILARISSA. PAINETTU.</valmistenumeronSijaintiMuu>
            <ovienSijainti>01</ovienSijainti>
            <tekninen-tieto>
                <vari>6</vari>
                <lisavari>b</lisavari>
                <ovienLukumaara>4</ovienLukumaara>
            </tekninen-tieto>
            <tyyppinimi>DA3</tyyppinimi>
            <ensirekisterointipvm>2005-12-05</ensirekisterointipvm>
            <viimeisinkilometrilukema>
                <kilometrilukema>
                    <matkamittarilukema>187508</matkamittarilukema>
                    <ajankohta>2023-06-13</ajankohta>
                </kilometrilukema>
            </viimeisinkilometrilukema>
        </ajoneuvonPerustiedot>
        <erikoisehdot>
            <erikoisehto>
                <erikoisehdOsaalue>1007</erikoisehdOsaalue>
                <kooditettuHuomautus>0003/1007</kooditettuHuomautus>
                <teksti>MOOTTORINTUNNISTE HXDA, 5-V. KÄSIVALINTAINEN VAIHTEISTO.</teksti>
                <tulostettava>true</tulostettava>
            </erikoisehto>
            <erikoisehto>
                <erikoisehdOsaalue>1007</erikoisehdOsaalue>
                <teksti>VETOJÄRJESTELMÄ: 4X2</teksti>
                <tulostettava>true</tulostettava>
            </erikoisehto>
            <erikoisehto>
                <erikoisehdOsaalue>1007</erikoisehdOsaalue>
                <teksti>VALMISTUSMAA: DE</teksti>
                <tulostettava>true</tulostettava>
            </erikoisehto>
            <erikoisehto>
                <erikoisehdOsaalue>1007</erikoisehdOsaalue>
                <teksti>VOIMASSA VALMISTENUMEROSTA/AJANKOHDASTA: E13*01/116*0144*06</teksti>
                <tulostettava>true</tulostettava>
            </erikoisehto>
            <erikoisehto>
                <erikoisehdOsaalue>2003</erikoisehdOsaalue>
                <kooditettuHuomautus>0005/2003</kooditettuHuomautus>
                <teksti>5135572533</teksti>
                <tulostettava>true</tulostettava>
            </erikoisehto>
            <erikoisehto>
                <erikoisehdOsaalue>2003</erikoisehdOsaalue>
                <kooditettuHuomautus>0006/2003</kooditettuHuomautus>
                <teksti>4D FOCUS STW 1.6VCT-DA3/264</teksti>
                <tulostettava>true</tulostettava>
            </erikoisehto>
        </erikoisehdot>
        <omistajatHaltijat>
            <omistajaHaltija luovutusrajoitus="1">
                <asiakaslaji>0</asiakaslaji>
                <omistajuustyyppi>01</omistajuustyyppi>
                <suhteenAlkupvm>2018-05-09</suhteenAlkupvm>
            </omistajaHaltija>
        </omistajatHaltijat>
        <vakuutustiedot luovutusrajoitus="1">
            <vakuutusyhtiokoodi>44</vakuutusyhtiokoodi>
            <vakuutustyyppi>01</vakuutustyyppi>
            <vakuutusyhtionNimi>LähiTapiola</vakuutusyhtionNimi>
            <vakuutuksenAlkupvm>2018-06-18</vakuutuksenAlkupvm>
        </vakuutustiedot>
        <rakenne>
            <kilvenMalli>01</kilvenMalli>
            <akselienLkm>2</akselienLkm>
            <meistoksenVarmennus>false</meistoksenVarmennus>
            <vaihteisto>1</vaihteisto>
            <vaihteidenLkm>5</vaihteidenLkm>
            <valmistajanKilvenSijainti>b-pilari, oikea</valmistajanKilvenSijainti>
            <tehostettuOhjaus>true</tehostettuOhjaus>
            <akselitiedot>
                <akseli>
                    <sijainti>1</sijainti>
                    <ohjaava>true</ohjaava>
                    <kevennettava>false</kevennettava>
                    <paripyorillaVarustettu>false</paripyorillaVarustettu>
                    <nostettava>false</nostettava>
                    <vetava>true</vetava>
                    <pyorajarrunTyyppi>1</pyorajarrunTyyppi>
                    <seisontajarru>false</seisontajarru>
                    <tieliikSuurSallMassa>895</tieliikSuurSallMassa>
                    <teknSuurSallMassa>895</teknSuurSallMassa>
                    <jarruttava>true</jarruttava>
                    <ohjautuva>false</ohjautuva>
                    <rengas>
                        <sijainti>1</sijainti>
                        <rengaslaji>1</rengaslaji>
                        <rengaskoko>195/65R15</rengaskoko>
                        <vannekoko>6JX15 H2</vannekoko>
                        <offset>52.5</offset>
                        <kuormitusJaNopeusluokka>87U</kuormitusJaNopeusluokka>
                    </rengas>
                    <rengas>
                        <sijainti>1</sijainti>
                        <rengaslaji>1</rengaslaji>
                        <rengaskoko>205/50R17</rengaskoko>
                        <vannekoko>6,5JX17 H2</vannekoko>
                        <offset>52.5</offset>
                        <kuormitusJaNopeusluokka>87U</kuormitusJaNopeusluokka>
                    </rengas>
                    <rengas>
                        <sijainti>1</sijainti>
                        <rengaslaji>1</rengaslaji>
                        <rengaskoko>205/55R16</rengaskoko>
                        <vannekoko>6,5JX16 H2</vannekoko>
                        <offset>52.5</offset>
                        <kuormitusJaNopeusluokka>87U</kuormitusJaNopeusluokka>
                    </rengas>
                    <rengas>
                        <sijainti>1</sijainti>
                        <rengaslaji>1</rengaslaji>
                        <rengaskoko>225/40R18</rengaskoko>
                        <vannekoko>7,5JX18 H2</vannekoko>
                        <offset>52.5</offset>
                        <kuormitusJaNopeusluokka>87U</kuormitusJaNopeusluokka>
                    </rengas>
                </akseli>
                <akseli>
                    <sijainti>2</sijainti>
                    <ohjaava>false</ohjaava>
                    <kevennettava>false</kevennettava>
                    <paripyorillaVarustettu>false</paripyorillaVarustettu>
                    <nostettava>false</nostettava>
                    <vetava>false</vetava>
                    <pyorajarrunTyyppi>1</pyorajarrunTyyppi>
                    <seisontajarru>true</seisontajarru>
                    <tieliikSuurSallMassa>1090</tieliikSuurSallMassa>
                    <teknSuurSallMassa>1090</teknSuurSallMassa>
                    <jarruttava>true</jarruttava>
                    <ohjautuva>false</ohjautuva>
                    <rengas>
                        <sijainti>2</sijainti>
                        <rengaslaji>1</rengaslaji>
                        <rengaskoko>195/65R15</rengaskoko>
                        <vannekoko>6JX15 H2</vannekoko>
                        <offset>52.5</offset>
                        <kuormitusJaNopeusluokka>87U</kuormitusJaNopeusluokka>
                    </rengas>
                    <rengas>
                        <sijainti>2</sijainti>
                        <rengaslaji>1</rengaslaji>
                        <rengaskoko>205/50R17</rengaskoko>
                        <vannekoko>6,5JX17 H2</vannekoko>
                        <offset>52.5</offset>
                        <kuormitusJaNopeusluokka>87U</kuormitusJaNopeusluokka>
                    </rengas>
                    <rengas>
                        <sijainti>2</sijainti>
                        <rengaslaji>1</rengaslaji>
                        <rengaskoko>205/55R16</rengaskoko>
                        <vannekoko>6,5JX16 H2</vannekoko>
                        <offset>52.5</offset>
                        <kuormitusJaNopeusluokka>87U</kuormitusJaNopeusluokka>
                    </rengas>
                    <rengas>
                        <sijainti>2</sijainti>
                        <rengaslaji>1</rengaslaji>
                        <rengaskoko>225/40R18</rengaskoko>
                        <vannekoko>7,5JX18 H2</vannekoko>
                        <offset>52.5</offset>
                        <kuormitusJaNopeusluokka>87U</kuormitusJaNopeusluokka>
                    </rengas>
                </akseli>
            </akselitiedot>
        </rakenne>
        <moottori>
            <kayttovoima>01</kayttovoima>
            <iskutilavuus>1590</iskutilavuus>
            <suurinNettoteho>85.0</suurinNettoteho>
            <sylintereidenLkm>4</sylintereidenLkm>
            <ahdin>false</ahdin>
            <valijaahdytin>false</valijaahdytin>
            <paastotaso>23</paastotaso>
            <pakokaasunPuhdistus>
                <laite>03</laite>
            </pakokaasunPuhdistus>
            <kayttovoimat>
                <kayttovoima>
                    <yksittaisKayttovoima>01</yksittaisKayttovoima>
                    <voimakkuusMeluPaikallaan>81.0</voimakkuusMeluPaikallaan>
                    <voimakkuusMeluOhiajossa>70.0</voimakkuusMeluOhiajossa>
                    <kierroksillaMeluPaikallaan>4500</kierroksillaMeluPaikallaan>
                    <paastot>
                        <paasto>
                            <tyyppi>03</tyyppi>
                            <paastolaji>01</paastolaji>
                            <maara>0.31400</maara>
                        </paasto>
                        <paasto>
                            <tyyppi>03</tyyppi>
                            <paastolaji>03</paastolaji>
                            <maara>0.03600</maara>
                        </paasto>
                        <paasto>
                            <tyyppi>03</tyyppi>
                            <paastolaji>06</paastolaji>
                            <maara>0.08500</maara>
                        </paasto>
                    </paastot>
                    <kulutukset>
                        <kulutus>
                            <kulutuslaji>1</kulutuslaji>
                            <maara>5.1</maara>
                        </kulutus>
                        <kulutus>
                            <kulutuslaji>2</kulutuslaji>
                            <maara>8.7</maara>
                        </kulutus>
                        <kulutus>
                            <kulutuslaji>3</kulutuslaji>
                            <maara>6.4</maara>
                        </kulutus>
                        <kulutus>
                            <kulutuslaji>4</kulutuslaji>
                            <maara>155.0</maara>
                        </kulutus>
                    </kulutukset>
                </kayttovoima>
            </kayttovoimat>
            <sahkohybridi>false</sahkohybridi>
        </moottori>
        <massa>
            <kattokuorma>75</kattokuorma>
            <omamassa>1279</omamassa>
            <teknSuurSallKokmassa>1825</teknSuurSallKokmassa>
            <tieliikSuurSallKokmassa>1825</tieliikSuurSallKokmassa>
        </massa>
        <mitat>
            <ajonKokPituus>4470</ajonKokPituus>
            <ajonLeveys>1840</ajonLeveys>
            <ajonKorkeus>1460</ajonKorkeus>
            <akselivalit>
                <akselivali>
                    <sijainti>1</sijainti>
                    <pituus>2640</pituus>
                </akselivali>
            </akselivalit>
        </mitat>
        <kori>
            <korityyppi>AC</korityyppi>
            <ohjaamotyyppi>1</ohjaamotyyppi>
            <istuimetKuljVieressa>1</istuimetKuljVieressa>
            <istumapaikkojenLkm>5</istumapaikkojenLkm>
        </kori>
        <jarrut>
            <voimanvalJaTehostamistapa>05</voimanvalJaTehostamistapa>
            <voimanvalJaTehostamistapaLisatieto>
                <lisatieto>1</lisatieto>
            </voimanvalJaTehostamistapaLisatieto>
        </jarrut>
        <kevyenKytkenta>
            <autonKokmassaPVkaytossa>1900</autonKokmassaPVkaytossa>
            <yhdistelmanSuurSallMassa>3025</yhdistelmanSuurSallMassa>
            <massaJarruitta>635</massaJarruitta>
            <massaJarruin>1200</massaJarruin>
            <massaJarruittaValmSall>635</massaJarruittaValmSall>
            <massaJarruinValmSall>1200</massaJarruinValmSall>
        </kevyenKytkenta>
        <turvavarusteet>
            <turvavaruste>
                <laji>et</laji>
                <penkkirivi>1</penkkirivi>
                <sijainti>1</sijainti>
                <pakollisuus>1</pakollisuus>
            </turvavaruste>
            <turvavaruste>
                <laji>et</laji>
                <penkkirivi>1</penkkirivi>
                <sijainti>3</sijainti>
                <pakollisuus>1</pakollisuus>
            </turvavaruste>
            <turvavaruste>
                <laji>vk</laji>
                <penkkirivi>1</penkkirivi>
                <sijainti>1</sijainti>
                <pakollisuus>1</pakollisuus>
            </turvavaruste>
            <turvavaruste>
                <laji>vk</laji>
                <penkkirivi>1</penkkirivi>
                <sijainti>3</sijainti>
                <pakollisuus>1</pakollisuus>
            </turvavaruste>
        </turvavarusteet>
    </laaja>
</ajoneuvontiedot></sanoma></kehys>
"""  # noqa: E501

PAYLOAD_UNSUPPORTED_VEHICLE_CLASS = """
<kehys><yleinen><sanomatyyppi>TPSUOTIEDOTLAAJAHAKUOUT</sanomatyyppi><erakoodi /><sekvenssinumero /><sovellus>TPSUO</sovellus><ymparisto>LONTOO,LONTOO</ymparisto></yleinen><sanoma><ajoneuvontiedot>
    <laaja hetu="true">
        <tunnus laji="2">
            <rekisteritunnus>BCI-707</rekisteritunnus>
            <valmistenumero>LE500A-027778</valmistenumero>
            <jarjestelmatunnus>0024134114</jarjestelmatunnus>
        </tunnus>
        <ajoneuvonTiedot>
            <ajoneuvoluokka>L3</ajoneuvoluokka>
            <merkki>906</merkki>
            <merkkiSelvakielinen>Kawasaki</merkkiSelvakielinen>
            <mallimerkinta>KLE 500</mallimerkinta>
            <tila>3</tila>
            <ajoneuvoryhmat>
                <ajoneuvoryhma>109</ajoneuvoryhma>
            </ajoneuvoryhmat>
            <ajoneuvonKaytto>01</ajoneuvonKaytto>
            <rekisterointitod1Osa>
                <jarjestysnumero>9</jarjestysnumero>
                <tulostuspaiva>2024-01-16</tulostuspaiva>
            </rekisterointitod1Osa>
            <rekisterointitod2Osa>
                <jarjestysnumero>9</jarjestysnumero>
                <tulostuspaiva>2024-01-16</tulostuspaiva>
            </rekisterointitod2Osa>
        </ajoneuvonTiedot>
        <ajoneuvonPerustiedot>
            <tyyppikoodi>9906251</tyyppikoodi>
            <kayttoonottopvm>19930402</kayttoonottopvm>
            <yksittainMaahantuotu>1</yksittainMaahantuotu>
            <tuontimaa>276</tuontimaa>
            <ulkomainenRekisteritunnus>K-WQ1</ulkomainenRekisteritunnus>
            <rakennettuAjoneuvo>false</rakennettuAjoneuvo>
            <ensirekisterointipvm>2003-06-25</ensirekisterointipvm>
        </ajoneuvonPerustiedot>
        <erikoisehdot>
            <erikoisehto>
                <erikoisehdOsaalue>2003</erikoisehdOsaalue>
                <kooditettuHuomautus>0005/2003</kooditettuHuomautus>
                <teksti>9906251</teksti>
                <tulostettava>true</tulostettava>
            </erikoisehto>
            <erikoisehto>
                <erikoisehdOsaalue>2003</erikoisehdOsaalue>
                <kooditettuHuomautus>0006/2003</kooditettuHuomautus>
                <teksti>KLE 500</teksti>
                <tulostettava>true</tulostettava>
            </erikoisehto>
            <erikoisehto>
                <erikoisehdOsaalue>3002</erikoisehdOsaalue>
                <teksti>RENKAAT: 90/90-21, 130/80-17.</teksti>
                <tulostettava>true</tulostettava>
            </erikoisehto>
            <erikoisehto>
                <erikoisehdOsaalue>3002</erikoisehdOsaalue>
                <teksti>Vetojärjestelmä: 2X1</teksti>
                <tulostettava>true</tulostettava>
            </erikoisehto>
            <erikoisehto>
                <erikoisehdOsaalue>3006</erikoisehdOsaalue>
                <teksti>Kaasuttimen merkki/malli: KEIHIN CVK34</teksti>
                <tulostettava>true</tulostettava>
            </erikoisehto>
            <erikoisehto>
                <erikoisehdOsaalue>3009</erikoisehdOsaalue>
                <teksti>Valmistusmaa: JAPANI</teksti>
                <tulostettava>true</tulostettava>
            </erikoisehto>
        </erikoisehdot>
        <omistajatHaltijat>
            <omistajaHaltija luovutusrajoitus="0">
                <omistajanTunnus>290200A905H</omistajanTunnus>
                <sukunimiPaayksikko>Hesalainen</sukunimiPaayksikko>
                <etunimiAlayksikko>Hessu</etunimiAlayksikko>
                <asiakaslaji>0</asiakaslaji>
                <omistajuustyyppi>03</omistajuustyyppi>
                <suhteenAlkupvm>2024-01-16</suhteenAlkupvm>
                <hallintasuhde>02</hallintasuhde>
                <markkinointikielto>false</markkinointikielto>
                <lahiosoite>Tarkk'ampujankatu 80 A 3a</lahiosoite>
                <postinumero>00130</postinumero>
                <postitoimipaikka>HELSINKI</postitoimipaikka>
                <asiointikieli>fi</asiointikieli>
            </omistajaHaltija>
            <omistajaHaltija luovutusrajoitus="0">
                <omistajanTunnus>290574-329E</omistajanTunnus>
                <sukunimiPaayksikko>Sandvik</sukunimiPaayksikko>
                <etunimiAlayksikko>Kalervo Lauri</etunimiAlayksikko>
                <asiakaslaji>0</asiakaslaji>
                <omistajuustyyppi>01</omistajuustyyppi>
                <suhteenAlkupvm>2022-06-29</suhteenAlkupvm>
                <markkinointikielto>false</markkinointikielto>
                <lahiosoite>Välskärintie 9 as 9</lahiosoite>
                <postinumero>90630</postinumero>
                <postitoimipaikka>OULU</postitoimipaikka>
                <asiointikieli>fi</asiointikieli>
            </omistajaHaltija>
        </omistajatHaltijat>
        <vakuutustiedot luovutusrajoitus="0">
            <vakuutusyhtiokoodi>36</vakuutusyhtiokoodi>
            <vakuutustyyppi>01</vakuutustyyppi>
            <vakuutusyhtionNimi>Pohjola</vakuutusyhtionNimi>
            <vakuutuksenottajanTunnus>290574-329E</vakuutuksenottajanTunnus>
            <vakuutuksenottajanNimi>Sandvik, Kalervo Lauri</vakuutuksenottajanNimi>
            <vakuutuksenAlkupvm>2022-06-29</vakuutuksenAlkupvm>
        </vakuutustiedot>
        <rakenne>
            <kilvenMalli>01</kilvenMalli>
            <akselienLkm>2</akselienLkm>
            <akselitiedot>
                <akseli>
                    <sijainti>1</sijainti>
                    <ohjaava>true</ohjaava>
                    <vetava>false</vetava>
                    <omaMassaKevYlh>95</omaMassaKevYlh>
                    <tieliikSuurSallMassa>140</tieliikSuurSallMassa>
                    <teknSuurSallMassa>140</teknSuurSallMassa>
                </akseli>
                <akseli>
                    <sijainti>2</sijainti>
                    <ohjaava>false</ohjaava>
                    <vetava>true</vetava>
                    <omaMassaKevYlh>105</omaMassaKevYlh>
                    <tieliikSuurSallMassa>265</tieliikSuurSallMassa>
                    <teknSuurSallMassa>265</teknSuurSallMassa>
                </akseli>
            </akselitiedot>
        </rakenne>
        <moottori>
            <kayttovoima>01</kayttovoima>
            <iskutilavuus>499</iskutilavuus>
            <suurinNettoteho>37.0</suurinNettoteho>
            <kayttovoimat>
                <kayttovoima>
                    <yksittaisKayttovoima>01</yksittaisKayttovoima>
                </kayttovoima>
            </kayttovoimat>
        </moottori>
        <massa>
            <omamassa>200</omamassa>
            <teknSuurSallKokmassa>380</teknSuurSallKokmassa>
            <tieliikSuurSallKokmassa>380</tieliikSuurSallKokmassa>
        </massa>
        <mitat>
            <ajonLeveys>880</ajonLeveys>
            <akselivalit>
                <akselivali>
                    <sijainti>1</sijainti>
                    <pituus>1510</pituus>
                </akselivali>
            </akselivalit>
        </mitat>
        <kori>
            <istumapaikkojenLkm>1</istumapaikkojenLkm>
        </kori>
        <jarrut>
            <voimanvalJaTehostamistapa>02</voimanvalJaTehostamistapa>
        </jarrut>
    </laaja>
</ajoneuvontiedot></sanoma></kehys>
"""  # noqa: E501

PAYLOAD_DECOMISSIONED = """
<kehys><yleinen><sanomatyyppi>TPSUOTIEDOTLAAJAHAKUOUT</sanomatyyppi><erakoodi /><sekvenssinumero /><sovellus>TPSUO</sovellus><ymparisto>LONTOO,LONTOO</ymparisto></yleinen><sanoma><ajoneuvontiedot>
    <laaja hetu="true">
        <tunnus laji="1">
            <rekisteritunnus>BCI-707</rekisteritunnus>
            <valmistenumero>WVWZZZ3CZ6E116952</valmistenumero>
            <jarjestelmatunnus>0008606859</jarjestelmatunnus>
        </tunnus>
        <ajoneuvonTiedot>
            <ajoneuvoluokka>M1</ajoneuvoluokka>
            <merkki>267</merkki>
            <merkkiSelvakielinen>Volkswagen</merkkiSelvakielinen>
            <mallimerkinta>5D PASSAT VARIANT 1.9TDI-3C/271</mallimerkinta>
            <tila>4</tila>
            <ajoneuvonKaytto>01</ajoneuvonKaytto>
            <rekisterointitod1Osa>
                <jarjestysnumero>24</jarjestysnumero>
                <tulostuspaiva>2023-03-19</tulostuspaiva>
            </rekisterointitod1Osa>
            <rekisterointitod2Osa>
                <jarjestysnumero>10</jarjestysnumero>
                <tulostuspaiva>2023-03-19</tulostuspaiva>
            </rekisterointitod2Osa>
        </ajoneuvonTiedot>
        <ajoneuvonPerustiedot>
            <tyyppihyvaksyntanro>e1*2001/116*0307*05</tyyppihyvaksyntanro>
            <variantti>ACBKCX0</variantti>
            <versio>FM5FM5A4032STO0GG</versio>
            <kaupallinenNimi>PASSAT</kaupallinenNimi>
            <tyyppikoodi>5267077510</tyyppikoodi>
            <kayttoonottopvm>20051130</kayttoonottopvm>
            <mkAjanAlkupvm>2022-09-26</mkAjanAlkupvm>
            <mkAjanLoppupvm>2023-09-26</mkAjanLoppupvm>
            <katsastusajankohta>2022-09-26</katsastusajankohta>
            <katsastuspaatos>2</katsastuspaatos>
            <katsastuspaikka>Katsastus Team Oy Pohjois-Suomi/Pudasjärvi</katsastuspaikka>
            <valmistenumeronSijainti>Z</valmistenumeronSijainti>
            <rakennettuAjoneuvo>false</rakennettuAjoneuvo>
            <valmistenumeronSijaintiMuu>MEISTOS: MOOTTORITILASSA OIKEALLA VESIKAUKALOSSA.</valmistenumeronSijaintiMuu>
            <tekninen-tieto>
                <vari>1</vari>
                <lisavari>c</lisavari>
            </tekninen-tieto>
            <tyyppinimi>3C</tyyppinimi>
            <ensirekisterointipvm>2005-11-30</ensirekisterointipvm>
            <viimeisinkilometrilukema>
                <kilometrilukema>
                    <matkamittarilukema>594839</matkamittarilukema>
                    <ajankohta>2022-09-26</ajankohta>
                </kilometrilukema>
            </viimeisinkilometrilukema>
        </ajoneuvonPerustiedot>
        <erikoisehdot>
            <erikoisehto>
                <erikoisehdOsaalue>1007</erikoisehdOsaalue>
                <kooditettuHuomautus>0003/1007</kooditettuHuomautus>
                <teksti>MOOTTORINTUNNISTE BKC, 5-V. KÄSIVALINTAINEN VAIHTEISTO.</teksti>
            </erikoisehto>
            <erikoisehto>
                <erikoisehdOsaalue>1007</erikoisehdOsaalue>
                <kooditettuHuomautus>0007/1007</kooditettuHuomautus>
                <teksti>e1*01/116*0307*05 VARIANTTI: ACBKCX0 VERSIO: FM5FM5A4032STO0GG</teksti>
            </erikoisehto>
            <erikoisehto>
                <erikoisehdOsaalue>1007</erikoisehdOsaalue>
                <teksti>VETOJÄRJESTELMÄ: 4X2</teksti>
            </erikoisehto>
            <erikoisehto>
                <erikoisehdOsaalue>1007</erikoisehdOsaalue>
                <teksti>VOIMASSA VALMISTENUMEROSTA/AJANKOHDASTA: E1*01/116*0307*05</teksti>
            </erikoisehto>
            <erikoisehto>
                <erikoisehdOsaalue>1007</erikoisehdOsaalue>
                <teksti>VALMISTUSMAA: DE</teksti>
            </erikoisehto>
            <erikoisehto>
                <erikoisehdOsaalue>2003</erikoisehdOsaalue>
                <kooditettuHuomautus>0005/2003</kooditettuHuomautus>
                <teksti>5267077510</teksti>
            </erikoisehto>
            <erikoisehto>
                <erikoisehdOsaalue>2003</erikoisehdOsaalue>
                <kooditettuHuomautus>0006/2003</kooditettuHuomautus>
                <teksti>5D PASSAT VARIANT 1.9TDI-3C/271</teksti>
            </erikoisehto>
        </erikoisehdot>
        <rajoitustiedot>
            <rajoitustieto>
                <rajoitusLaji>10</rajoitusLaji>
                <vakavuus>1</vakavuus>
            </rajoitustieto>
            <rajoitustieto>
                <rajoitusLaji>18</rajoitusLaji>
                <rajoitusAlalaji>01</rajoitusAlalaji>
                <voimoloAlkuaika>2023-03-19</voimoloAlkuaika>
                <vakavuus>1</vakavuus>
                <kasittelija>JärjestelmätunnusOmaTrafi</kasittelija>
            </rajoitustieto>
        </rajoitustiedot>
        <omistajatHaltijat>
            <omistajaHaltija luovutusrajoitus="0">
                <omistajanTunnus>170267-309U</omistajanTunnus>
                <sukunimiPaayksikko>Julkunen</sukunimiPaayksikko>
                <etunimiAlayksikko>Eljas Nikolai</etunimiAlayksikko>
                <asiakaslaji>0</asiakaslaji>
                <omistajuustyyppi>01</omistajuustyyppi>
                <suhteenAlkupvm>2021-11-18</suhteenAlkupvm>
                <markkinointikielto>false</markkinointikielto>
                <lahiosoite>Luhtimäki 7 A 1</lahiosoite>
                <postinumero>01660</postinumero>
                <postitoimipaikka>VANTAA</postitoimipaikka>
                <asiointikieli>fi</asiointikieli>
            </omistajaHaltija>
        </omistajatHaltijat>
        <vakuutustiedot luovutusrajoitus="0">
            <vakuutusyhtiokoodi>44</vakuutusyhtiokoodi>
            <vakuutustyyppi>01</vakuutustyyppi>
            <vakuutusyhtionNimi>LähiTapiola</vakuutusyhtionNimi>
            <vakuutuksenottajanTunnus>170267-309U</vakuutuksenottajanTunnus>
            <vakuutuksenottajanNimi>Julkunen, Eljas Nikolai</vakuutuksenottajanNimi>
            <vakuutuksenAlkupvm>2021-11-20</vakuutuksenAlkupvm>
        </vakuutustiedot>
        <rakenne>
            <kilvenMalli>01</kilvenMalli>
            <akselienLkm>2</akselienLkm>
            <tehostettuOhjaus>false</tehostettuOhjaus>
            <akselitiedot>
                <akseli>
                    <sijainti>1</sijainti>
                    <ohjaava>true</ohjaava>
                    <paripyorillaVarustettu>false</paripyorillaVarustettu>
                    <vetava>true</vetava>
                    <tieliikSuurSallMassa>1070</tieliikSuurSallMassa>
                    <teknSuurSallMassa>1070</teknSuurSallMassa>
                    <rengas>
                        <sijainti>1</sijainti>
                        <rengaskoko>205/55R16</rengaskoko>
                        <vannekoko>6,5JX16</vannekoko>
                        <offset>42.0</offset>
                        <kuormitusJaNopeusluokka>91H</kuormitusJaNopeusluokka>
                    </rengas>
                    <rengas>
                        <sijainti>1</sijainti>
                        <rengaskoko>205/55R16</rengaskoko>
                        <vannekoko>7JX16</vannekoko>
                        <offset>45.0</offset>
                        <kuormitusJaNopeusluokka>91H</kuormitusJaNopeusluokka>
                    </rengas>
                    <rengas>
                        <sijainti>1</sijainti>
                        <rengaskoko>215/55R16</rengaskoko>
                        <vannekoko>6,5JX16</vannekoko>
                        <offset>42.0</offset>
                        <kuormitusJaNopeusluokka>93H</kuormitusJaNopeusluokka>
                    </rengas>
                    <rengas>
                        <sijainti>1</sijainti>
                        <rengaskoko>215/55R16</rengaskoko>
                        <vannekoko>7JX16</vannekoko>
                        <offset>45.0</offset>
                        <kuormitusJaNopeusluokka>93H</kuormitusJaNopeusluokka>
                    </rengas>
                    <rengas>
                        <sijainti>1</sijainti>
                        <rengaskoko>235/45R17</rengaskoko>
                        <vannekoko>7,5JX17</vannekoko>
                        <offset>47.0</offset>
                        <kuormitusJaNopeusluokka>94H</kuormitusJaNopeusluokka>
                    </rengas>
                    <rengas>
                        <sijainti>1</sijainti>
                        <rengaskoko>205/50R17 M+S</rengaskoko>
                        <vannekoko>6JX17</vannekoko>
                        <offset>45.0</offset>
                        <kuormitusJaNopeusluokka>93H</kuormitusJaNopeusluokka>
                    </rengas>
                </akseli>
                <akseli>
                    <sijainti>2</sijainti>
                    <ohjaava>false</ohjaava>
                    <paripyorillaVarustettu>false</paripyorillaVarustettu>
                    <vetava>false</vetava>
                    <tieliikSuurSallMassa>1080</tieliikSuurSallMassa>
                    <teknSuurSallMassa>1080</teknSuurSallMassa>
                    <rengas>
                        <sijainti>2</sijainti>
                        <rengaskoko>205/55R16</rengaskoko>
                        <vannekoko>6,5JX16</vannekoko>
                        <offset>42.0</offset>
                        <kuormitusJaNopeusluokka>91H</kuormitusJaNopeusluokka>
                    </rengas>
                    <rengas>
                        <sijainti>2</sijainti>
                        <rengaskoko>205/55R16</rengaskoko>
                        <vannekoko>7JX16</vannekoko>
                        <offset>45.0</offset>
                        <kuormitusJaNopeusluokka>91H</kuormitusJaNopeusluokka>
                    </rengas>
                    <rengas>
                        <sijainti>2</sijainti>
                        <rengaskoko>215/55R16</rengaskoko>
                        <vannekoko>6,5JX16</vannekoko>
                        <offset>42.0</offset>
                        <kuormitusJaNopeusluokka>93H</kuormitusJaNopeusluokka>
                    </rengas>
                    <rengas>
                        <sijainti>2</sijainti>
                        <rengaskoko>215/55R16</rengaskoko>
                        <vannekoko>7JX16</vannekoko>
                        <offset>45.0</offset>
                        <kuormitusJaNopeusluokka>93H</kuormitusJaNopeusluokka>
                    </rengas>
                    <rengas>
                        <sijainti>2</sijainti>
                        <rengaskoko>235/45R17</rengaskoko>
                        <vannekoko>7,5JX17</vannekoko>
                        <offset>47.0</offset>
                        <kuormitusJaNopeusluokka>94H</kuormitusJaNopeusluokka>
                    </rengas>
                    <rengas>
                        <sijainti>2</sijainti>
                        <rengaskoko>205/50R17 M+S</rengaskoko>
                        <vannekoko>6JX17</vannekoko>
                        <offset>45.0</offset>
                        <kuormitusJaNopeusluokka>93H</kuormitusJaNopeusluokka>
                    </rengas>
                </akseli>
            </akselitiedot>
        </rakenne>
        <moottori>
            <kayttovoima>02</kayttovoima>
            <iskutilavuus>1890</iskutilavuus>
            <suurinNettoteho>77.0</suurinNettoteho>
            <sylintereidenLkm>4</sylintereidenLkm>
            <ahdin>true</ahdin>
            <paastotaso>23</paastotaso>
            <kayttovoimat>
                <kayttovoima>
                    <yksittaisKayttovoima>02</yksittaisKayttovoima>
                    <voimakkuusMeluPaikallaan>80.0</voimakkuusMeluPaikallaan>
                    <voimakkuusMeluOhiajossa>72.0</voimakkuusMeluOhiajossa>
                    <kierroksillaMeluPaikallaan>3000</kierroksillaMeluPaikallaan>
                    <paastot>
                        <paasto>
                            <tyyppi>03</tyyppi>
                            <paastolaji>01</paastolaji>
                            <maara>0.19300</maara>
                        </paasto>
                        <paasto>
                            <tyyppi>03</tyyppi>
                            <paastolaji>03</paastolaji>
                            <maara>0.19400</maara>
                        </paasto>
                        <paasto>
                            <tyyppi>03</tyyppi>
                            <paastolaji>10</paastolaji>
                            <maara>0.01800</maara>
                        </paasto>
                        <paasto>
                            <tyyppi>03</tyyppi>
                            <paastolaji>11</paastolaji>
                            <maara>0.22900</maara>
                        </paasto>
                    </paastot>
                    <kulutukset>
                        <kulutus>
                            <kulutuslaji>1</kulutuslaji>
                            <maara>4.9</maara>
                        </kulutus>
                        <kulutus>
                            <kulutuslaji>2</kulutuslaji>
                            <maara>7.4</maara>
                        </kulutus>
                        <kulutus>
                            <kulutuslaji>3</kulutuslaji>
                            <maara>5.8</maara>
                        </kulutus>
                        <kulutus>
                            <kulutuslaji>4</kulutuslaji>
                            <maara>157.0</maara>
                        </kulutus>
                    </kulutukset>
                </kayttovoima>
            </kayttovoimat>
        </moottori>
        <massa>
            <kattokuorma>100</kattokuorma>
            <omamassa>1552</omamassa>
            <teknSuurSallKokmassa>2100</teknSuurSallKokmassa>
            <tieliikSuurSallKokmassa>2100</tieliikSuurSallKokmassa>
            <modulinKokonaismassa>3600</modulinKokonaismassa>
        </massa>
        <mitat>
            <ajonKokPituus>4770</ajonKokPituus>
            <ajonLeveys>1820</ajonLeveys>
            <ajonKorkeus>1470</ajonKorkeus>
            <akselivalit>
                <akselivali>
                    <sijainti>1</sijainti>
                    <pituus>2710</pituus>
                </akselivali>
            </akselivalit>
        </mitat>
        <kori>
            <korityyppi>AC</korityyppi>
            <istuimetKuljVieressa>1</istuimetKuljVieressa>
            <istumapaikkojenLkm>5</istumapaikkojenLkm>
        </kori>
        <jarrut>
            <voimanvalJaTehostamistapa>05</voimanvalJaTehostamistapa>
            <voimanvalJaTehostamistapaLisatieto>
                <lisatieto>1</lisatieto>
            </voimanvalJaTehostamistapaLisatieto>
        </jarrut>
        <kevyenKytkenta>
            <autonKokmassaPVkaytossa>2135</autonKokmassaPVkaytossa>
            <yhdistelmanSuurSallMassa>3600</yhdistelmanSuurSallMassa>
            <massaJarruitta>750</massaJarruitta>
            <massaJarruin>1500</massaJarruin>
            <massaJarruittaValmSall>750</massaJarruittaValmSall>
            <massaJarruinValmSall>1500</massaJarruinValmSall>
        </kevyenKytkenta>
        <turvavarusteet>
            <turvavaruste>
                <laji>et</laji>
                <penkkirivi>1</penkkirivi>
                <sijainti>1</sijainti>
                <pakollisuus>1</pakollisuus>
            </turvavaruste>
            <turvavaruste>
                <laji>et</laji>
                <penkkirivi>1</penkkirivi>
                <sijainti>3</sijainti>
                <pakollisuus>1</pakollisuus>
            </turvavaruste>
            <turvavaruste>
                <laji>vk</laji>
                <penkkirivi>1</penkkirivi>
                <sijainti>1</sijainti>
                <pakollisuus>1</pakollisuus>
            </turvavaruste>
            <turvavaruste>
                <laji>vk</laji>
                <penkkirivi>1</penkkirivi>
                <sijainti>3</sijainti>
                <pakollisuus>1</pakollisuus>
            </turvavaruste>
        </turvavarusteet>
    </laaja>
</ajoneuvontiedot></sanoma></kehys>
"""  # noqa: E501
