# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.6.2] - 2025-03-06

### Fixed

- Fix permit getting wrong price ([859dd36](https://github.com/City-of-Helsinki/parking-permits/commit/859dd36b171d41eca38cc46d091f283a46ae2551))
- Add hard limit for amount of returted products ([518cf4d](https://github.com/City-of-Helsinki/parking-permits/commit/518cf4db675329f9b148c79bef0c0e56bc134f5f))

## [1.6.1] - 2024-12-20

### Fixed

- Enhance open-ended permit end time calculation ([75f7006](https://github.com/City-of-Helsinki/parking-permits/commit/75f7006073a3bbe0b052743b9b7ab8441ccdcfc2))

## [1.6.0] - 2024-12-19

### Added

- Add emails_handled-flag to AnnouncementAdmin ([39e0b0c](https://github.com/City-of-Helsinki/parking-permits/commit/39e0b0cdfe55fae55ec2aef7707ba01ad0f3bf83))
- Add more logging to Talpa PaymentView ([7e7b612](https://github.com/City-of-Helsinki/parking-permits/commit/7e7b6123cc7ff4d149b5c03bf55c8ad57fd218b0))
- Improve permit automatic expiration tests ([e4f3334](https://github.com/City-of-Helsinki/parking-permits/commit/e4f3334e43a93b349ef0429ab50e25f5864da886))

### Changed

- Handle announcement emails from management command ([337b3a4](https://github.com/City-of-Helsinki/parking-permits/commit/337b3a4ddc15516c751dd72a512f70322d73d6ab))

### Fixed

- Fix issue with low emission consent command ([6a1e816](https://github.com/City-of-Helsinki/parking-permits/commit/6a1e81645c83d62c1786e1c8da000e3b786b17bf))
- Mark open-ended order items as refunded first time ([97e17bb](https://github.com/City-of-Helsinki/parking-permits/commit/97e17bbeaab16cf200d385f3e3f4a3160486a63c))
- Update to use next vehicle in new order ([b3ed47a](https://github.com/City-of-Helsinki/parking-permits/commit/b3ed47ae6526c2004acf175c42d1dd88c6c792fb))

## [1.5.0] - 2024-12-09

### Added

- Add support for webshop permit preliminary status ([d8b3846](https://github.com/City-of-Helsinki/parking-permits/commit/d8b38460c1ef77d83cd05117308f1ed5ff1d4dc2))
- Enable login for both Tunnistamo and KeyCloak ([3365134](https://github.com/City-of-Helsinki/parking-permits/commit/3365134237d0c4672a1b147d353a7bc4b00876db))
- Add management command to change consent_low_emission_accepted to False ([03e440e](https://github.com/City-of-Helsinki/parking-permits/commit/03e440e703d422d53bae973d99b27f3fd0b5a1b5))
- Allow StatusLog searches ([a7d35c2](https://github.com/City-of-Helsinki/parking-permits/commit/a7d35c2e9022c8abf6ac8cf66af35519dad0116c))
- Add id to OrderItemAdmin list display ([021c8da](https://github.com/City-of-Helsinki/parking-permits/commit/021c8da55acad6c4256c7090d3e07d0d1934db6e))

### Changed

- Update OIDC auth accepted audience format to list ([3b81294](https://github.com/City-of-Helsinki/parking-permits/commit/3b81294ef2750a84e66b210be3972c04c4bc9807))
- Update customer permit tests ([31128aa](https://github.com/City-of-Helsinki/parking-permits/commit/31128aa0ad39c4bd2752793f682bdf5c5591590d))
- Update Django Admin search fields ([37bd5d9](https://github.com/City-of-Helsinki/parking-permits/commit/37bd5d960acae3b5331f61fc327f76294e8791b2))
- Update existing draft permit if it exists ([c0ca12a](https://github.com/City-of-Helsinki/parking-permits/commit/c0ca12acfd6c56f1255754d61054099e6649b3b1))
- Update permit renewal end time calculation ([a0d4528](https://github.com/City-of-Helsinki/parking-permits/commit/a0d4528da7a815e5350f3d08d2357508345c18a8))
- Update Django Admin fields and ordering ([40257ca](https://github.com/City-of-Helsinki/parking-permits/commit/40257ca87dee3cbb243788829f3d31acbf5aa662))

### Fixed

- Fix a date bug where there might be gaps in days sent to Talpa ([3d1122c](https://github.com/City-of-Helsinki/parking-permits/commit/3d1122c42fcc3bbe9a6f7ef9c1069670dbc94e34))
- Increase Gunicorn header size limit ([e2d9803](https://github.com/City-of-Helsinki/parking-permits/commit/e2d98030108d8d410dcd8ce9a4523ba319623a37))
- Limit order items refunding to one time only ([81e4368](https://github.com/City-of-Helsinki/parking-permits/commit/81e43688f54274828d02d8e6ad5bc85036999e83))
- Update open-ended permit months left calculation ([24a8e9e](https://github.com/City-of-Helsinki/parking-permits/commit/24a8e9ed6f7911a7faa439064cb7d82e838b1ffb))

## [1.4.0] - 2024-11-25

### Added

- Allow draft permit creation in admin resolvers ([be80a24](https://github.com/City-of-Helsinki/parking-permits/commit/be80a2403783b471658240323aa15756f75f758f))

### Changed

- Keycloak backend integration ([d8ed26d](https://github.com/City-of-Helsinki/parking-permits/commit/d8ed26d01e5fe0d403270226e87be59d96e2b60b))
- Enable helusers migration ([8e3bc92](https://github.com/City-of-Helsinki/parking-permits/commit/8e3bc92cf2089f0c5b0fcf8f1fff6f2db38abb70))

### Fixed

- Update helsinki profile to use POST requests ([0b10293](https://github.com/City-of-Helsinki/parking-permits/commit/0b10293f3239f255f2beaa256eeab950f0801dac))
- Send email to customer when extension is created ([24b6adf](https://github.com/City-of-Helsinki/parking-permits/commit/24b6adfe03a9e4f7518f9f3e5ed4b1b013c6b098))

## [1.3.0] - 2024-11-14

### Added

- Accounting support for products ([7801d6d](https://github.com/City-of-Helsinki/parking-permits/commit/7801d6dad2a539b766b98b4e18855137308eb3b8))
- Update OrderAdmin to display all distinct VATs ([eafcc58](https://github.com/City-of-Helsinki/parking-permits/commit/eafcc588f764ef4356accb9d4a56a17792e6cdd6))
- Add DVV-checks for Talpa rights of purchase (disabled for now) ([11a1f74](https://github.com/City-of-Helsinki/parking-permits/commit/11a1f74c49dd09907f68e72a3d8600a25ed4ec2a))

### Changed

- Refactor Refund creation to own utility ([0c2d613](https://github.com/City-of-Helsinki/parking-permits/commit/0c2d61311f307ccce34eab8138a375c2dc9b8fe1))
- Calculate vehicle change refunds as VAT-based ([4c221c7](https://github.com/City-of-Helsinki/parking-permits/commit/4c221c77e42239b128325c00732f4a5064f801c9))
- Update refund order linking and vats ([8d0275f](https://github.com/City-of-Helsinki/parking-permits/commit/8d0275fb3ef1fdd62ecb7d4686d3e24b6653ee9e))
- Update address change functionality ([776f0cc](https://github.com/City-of-Helsinki/parking-permits/commit/776f0ccfe5242e31557cc108d4ec71f13c41de07))
- Update VAT-based refund calculation ([2c90a05](https://github.com/City-of-Helsinki/parking-permits/commit/2c90a05d4127f25354c14e63c211861cc21422d6))
- Update refund to support multiple orders ([d33af03](https://github.com/City-of-Helsinki/parking-permits/commit/d33af03538d1cd78a070e8d987e1e0ea3482f26f))
- Update unused items calculation ([be7e7c2](https://github.com/City-of-Helsinki/parking-permits/commit/be7e7c2582ea3708e47a788b0e69c80e4e700c63))

### Fixed

- Fix end times for open ended permits ([5dc3423](https://github.com/City-of-Helsinki/parking-permits/commit/5dc34237dd6fe228598ae0d11345d7170878d2d6))
- Fix Talpa order renewal vat format ([947b243](https://github.com/City-of-Helsinki/parking-permits/commit/947b2434885d7dc74c7276efa0c18718100f65c6))


## [1.2.4] - 2024-11-04

### Added

- Add apt-get update to CI workflow ([5be5e73](https://github.com/City-of-Helsinki/parking-permits/commit/5be5e73c1caa1d92273006098d01009ab240935b))

### Changed

- Revert "Fix open ended permit end time calculation" ([56b293f](https://github.com/City-of-Helsinki/parking-permits/commit/56b293ffc931b04054c1635a895249529e2eedc8))
- Use raw id fields in OrderItemAdmin ([5581984](https://github.com/City-of-Helsinki/parking-permits/commit/5581984b22cf5984d55479978e6fe7b7556e924d))

## [1.2.3] - 2024-10-29

### Added

- Add email max batch and throttle setup ([33ee6f3](https://github.com/City-of-Helsinki/parking-permits/commit/33ee6f365ad116a44fe560285f848538c54a1939))

## [1.2.2] - 2024-10-02

### Changed

- Increase customer name fields max length ([f00d4a1](https://github.com/City-of-Helsinki/parking-permits/pull/544/commits/f00d4a1c301fe1bfe349a172ede3d7f0af36a1df))
- Switch email backend to django-mailer ([b6d916d](https://github.com/City-of-Helsinki/parking-permits/pull/544/commits/b6d916d1392ca01fe2bbe3bb34cbd9090744d4c4))
- Add missing django-mailer settings ([e1c0bb4](https://github.com/City-of-Helsinki/parking-permits/pull/544/commits/e1c0bb44e5214e100dc66b03c5a662882483c69f))
- Add command for sending mail ([9affed7](https://github.com/City-of-Helsinki/parking-permits/pull/544/commits/9affed75aa19733882d5a2bd82cf91b32d5b9d86))

### Fixed

- Use period start and end times in renewal orders ([88a271f](https://github.com/City-of-Helsinki/parking-permits/pull/544/commits/88a271fa4fb5713fa3b4e4793a316db751a83bbe))
- Fix open ended permit end time calculation ([5dbd481](https://github.com/City-of-Helsinki/parking-permits/pull/544/commits/5dbd481f1509d69ee34c5e98d36ac3da2e3ff2c0))

## [1.2.1] - 2024-09-03

### Added

- Add VAT-percents to Django Admin ([305c396](https://github.com/City-of-Helsinki/parking-permits/commit/305c396091d68e49657f1299210e233678edf96b))
- Add vat and vat_percent properties to Order ([0e6612d](https://github.com/City-of-Helsinki/parking-permits/commit/0e6612d6031d9d7ade6a7422b1e6b3ecd2a9a513))

### Fixed

- Wrap accepted refund to list in email sending ([eeebdbc](https://github.com/City-of-Helsinki/parking-permits/commit/eeebdbc4355066ca15eaaaf591861eba1e2f1c02))

## [1.2.0] - 2024-08-30

### Added

- Add VAT and VAT-amount to Refund-model ([d4e72f8](https://github.com/City-of-Helsinki/parking-permits/commit/d4e72f80d6ac20fc85b69c47e843d55f8bbbb31b))
- Add VAT to Refund in Django Admin ([273018b](https://github.com/City-of-Helsinki/parking-permits/commit/273018bd9c34c5456b1d52c0fd83ce91e9fbd1ed))

### Changed

- Update low-emission criteria evaluation rules ([08aeef5](https://github.com/City-of-Helsinki/parking-permits/commit/08aeef571eab6228830ced83c9c4d2028023b5d9))
- Explicitly use Ubuntu 20.04 base image with GitHub Actions ([8c29d7a](https://github.com/City-of-Helsinki/parking-permits/commit/8c29d7a3aa4038350bec140d4f6baa83d9f506e3))
- Update VAT-percentages from Talpa-endpoints ([f79f9dd](https://github.com/City-of-Helsinki/parking-permits/commit/f79f9dda6b258823ec689da2ac8a48b533a87766))
- Update VAT-percentages for Refund ([4afdb80](https://github.com/City-of-Helsinki/parking-permits/commit/4afdb80edf6f1f1fc339a24fa39f43c3fc43a4c2))
- Use AWS ECR Docker image repository ([c7ef79d](https://github.com/City-of-Helsinki/parking-permits/commit/c7ef79d7dd9ca830297a7fd0da2ff301b576db79))
- Change Refund VAT to be dynamic ([8e7ca2f](https://github.com/City-of-Helsinki/parking-permits/commit/8e7ca2fa716569815813bcb31b5e951aa1672f48))
- Change Refund creation to be VAT-based ([1ce4469](https://github.com/City-of-Helsinki/parking-permits/commit/1ce44694eff95ff4a42c3d8012d1242da30c067c))

### Fixed

- Fix price calculation for first days of the month ([f96ebd6](https://github.com/City-of-Helsinki/parking-permits/commit/f96ebd69a737acad40e52df9332d4c257b38f2b0))
- Fix find_next_date-utility function ([326da62](https://github.com/City-of-Helsinki/parking-permits/commit/326da625d2fb8d46ebb1cc918854b35af24d890e))

## [1.1.0] - 2024-06-19

### Added

- Add changelog to project ([2d4300a](https://github.com/City-of-Helsinki/parking-permits/commit/2d4300a6bc329533474e33b861d2e73cc887460c))

### Changed

- Update Python version to 3.11 from CI ([dd07848](https://github.com/City-of-Helsinki/parking-permits/commit/dd0784825344cdf09081b6a7dad937241e1c65d5))
- Update application packages ([f0e2e5c](https://github.com/City-of-Helsinki/parking-permits/commit/f0e2e5c3dd72cfc8102d2e888651b5e60b3d6019))
- Update fi/sv/en translations ([f60e86d](https://github.com/City-of-Helsinki/parking-permits/commit/f60e86d659daf8bf342e294c6c53ddd41becfee5))
- Update Azure CI-settings ([456ddf4](https://github.com/City-of-Helsinki/parking-permits/commit/456ddf40b77952101877d9b7375c596fae4c447d))

### Removed

- Remove obsolete Docker Compose version ([8e3b8ab](https://github.com/City-of-Helsinki/parking-permits/commit/8e3b8ab3d8173b575dc8d55313469b438238cbb0))

## [1.0.0] - 2024-06-12

* PV-76 Initializing a barebone django project by @sam-hosseini in https://github.com/City-of-Helsinki/parking-permits/pull/1
* PV-39 Dockerization by @sam-hosseini in https://github.com/City-of-Helsinki/parking-permits/pull/2
* PV-81 Production foundation by @sam-hosseini in https://github.com/City-of-Helsinki/parking-permits/pull/4
* PV-80 Db dockerization by @sam-hosseini in https://github.com/City-of-Helsinki/parking-permits/pull/5
* PV-82 Testing foundation by @sam-hosseini in https://github.com/City-of-Helsinki/parking-permits/pull/6
* PV-85 pre-commit by @sam-hosseini in https://github.com/City-of-Helsinki/parking-permits/pull/9
* PV-86 Documentation and leftover fixes by @sam-hosseini in https://github.com/City-of-Helsinki/parking-permits/pull/10
* New pysakoinnin-verkkokauppa project pipeline yamls. by @AnttiKoistinen431a in https://github.com/City-of-Helsinki/parking-permits/pull/11
* PV-88 Feature/ariadne integration by @sam-hosseini in https://github.com/City-of-Helsinki/parking-permits/pull/12
* PV-106 Foundation/graphql federation by @sam-hosseini in https://github.com/City-of-Helsinki/parking-permits/pull/13
* Add Python VirtualEnv support by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/14
* PV-108 non-root-user in Docker by @sam-hosseini in https://github.com/City-of-Helsinki/parking-permits/pull/15
* Adapt project to use RedHat base image with GDAL 3 by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/16
* Parking Permits Datamodel by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/17
* PV-133 PV-131 PV-161 Feature/add DRF by @sam-hosseini in https://github.com/City-of-Helsinki/parking-permits/pull/18
* Update main by @sam-hosseini in https://github.com/City-of-Helsinki/parking-permits/pull/19
* Merge pull request #19 from City-of-Helsinki/develop by @sam-hosseini in https://github.com/City-of-Helsinki/parking-permits/pull/20
* PV-168 Use container_name in compose file by @sam-hosseini in https://github.com/City-of-Helsinki/parking-permits/pull/21
* Read .env file content to settings on local development by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/23
* Feature/product mapping by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/24
* Product and Price model with GET product endpoint by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/25
* PV-132 Feature/pricing engine low emission by @sam-hosseini in https://github.com/City-of-Helsinki/parking-permits/pull/26
* PV-172 Feature/pricing engine secondary vehicle by @sam-hosseini in https://github.com/City-of-Helsinki/parking-permits/pull/27
* Product mapping by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/28
* Product REST API for retrieving products (GET-endpoint) by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/29
* PV-170 Part 1 by @sam-hosseini in https://github.com/City-of-Helsinki/parking-permits/pull/22
* Add missing module requests to requirements by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/31
* PV-170 Part 2 by @sam-hosseini in https://github.com/City-of-Helsinki/parking-permits/pull/30
* PV-170 Part 3 by @sam-hosseini in https://github.com/City-of-Helsinki/parking-permits/pull/32
* PV-132 PR-1 by @sam-hosseini in https://github.com/City-of-Helsinki/parking-permits/pull/33
* PV-132 PR-2 by @sam-hosseini in https://github.com/City-of-Helsinki/parking-permits/pull/34
* PV-130 PR-1 by @sam-hosseini in https://github.com/City-of-Helsinki/parking-permits/pull/35
* PV-130 PR-1 by @sam-hosseini in https://github.com/City-of-Helsinki/parking-permits/pull/36
* PV-130 PR-2 by @sam-hosseini in https://github.com/City-of-Helsinki/parking-permits/pull/37
* PV-130 PR-3 by @sam-hosseini in https://github.com/City-of-Helsinki/parking-permits/pull/38
* PV-177 PR-1 by @sam-hosseini in https://github.com/City-of-Helsinki/parking-permits/pull/40
* Model update by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/41
* Remove product model by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/42
* Parking zone importer by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/44
* Update views for talpa endpoints by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/45
* Model updates by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/46
* Order/Payment notify rest end point by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/47
* PV-177 extending AddressNode with KMO info by @sam-hosseini in https://github.com/City-of-Helsinki/parking-permits/pull/43
* PV-203 PV-204 graphql mutation foundation by @sam-hosseini in https://github.com/City-of-Helsinki/parking-permits/pull/48
* Feature/frontend helsinki kmo integration by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/50
* Feature/Address to have city also in swedish by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/51
* Replace all print with logger by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/52
* Get shared product id through graphql by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/53
* Feature/Graphql permits by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/54
* Include Swedish descriptions for parking zones by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/55
* Part 1: Mutations by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/56
* Part 2: Mutations bug fixes by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/58
* Include isLowEmission field in Vehicle node by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/57
* Refactoring and resolving talpa prices by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/59
* Add authentication for endpoints also clean the dead codes by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/60
* Apply schema case fallback resolver by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/61
* Minor bug fixes by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/62
* Creating parking permits by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/63
* Add admin graphql endpoint for parking permits by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/64
* Protect admin graphql with jwt token verifications by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/65
* Update graphql permits query to include more infromation by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/67
* Add missing fields to the priceNode and add endpoint to update registration number by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/66
* Apply ordering to permits query results by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/68
* Add Admin UI env variables to env.example by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/69
* Refactor parking_permits_app admin by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/72
* Add GHA-configuration for running tests by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/70
* Fix the resident ui app graphql endpoint API token verfication by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/71
* Remove pyjwt and JWT_SECRET settings by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/73
* Integrate with SonarCloud by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/74
* Implement permit query filtering for permits query resolver  by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/75
* Add Talpa orderId and subscriptionId to permit by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/76
* Fix minor bug with status value by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/77
* Refactor zone price, improve error handling and add some tests by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/78
* Add graphql resolver for permit detail by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/79
* Track change history for parking permits by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/80
* Editing parking permit by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/82
* Migration for processing status and using timezone as default date time by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/83
* Feature/test delete permit by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/84
* Test case for updating parking permit by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/85
* Add reversion for permits by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/86
* Add admin ui resolver for creating resident permit by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/87
* Use date format only if date exist by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/88
* Improve changelog messages by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/89
* Refund model by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/90
* Update parking permit status and fix saving resident permit by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/91
* Add more fields to vehicle for create resident permit resolver by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/92
* Talpa api-key authorization by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/94
* Talpa status change through notification endpoint on the backend by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/95
* Implemented end permit by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/93
* Disable beta subscription manager by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/96
* Created a common base exception class for all parking permits exceptions by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/97
* Fix management command for creating parking zone by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/98
* Refactor models to accommodate new requirements by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/99
* Mutation for ending valid parking permits by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/100
* Update end time calculation by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/102
* Prevent saving names and address information is security ban is checked by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/101
* Increase refund price for secondary vehicle by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/103
* Subscription id can be null by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/104
* Fix minor graphql schema error by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/105
* Convert string datetime value to datetime object when updating permit by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/106
* Move talpa order to backend by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/108
* Create order and product related models by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/107
* Ending of valid permit should delete all draft permit by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/109
* Add backend resolvers for update (edit) resident permit by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/110
* Refactor management commands and make parking zone name unique by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/111
* Update Dockerfile by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/112
* Update Dockerfile by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/113
* Remove id field from ZoneNode by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/114
* Create orders for customer by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/115
* Add properties to get products from zone instances by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/116
* Multiple price support by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/117
* Update graphql schema for products by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/118
* Rhel beta images doesn't exist so disabling it by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/119
* Store talpa checkout url and receipt url to order instances by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/120
* Feature/django db logger by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/121
* Products resolver by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/122
* Fix tests in test_customer_permit by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/123
* Add graphql resolvers for products queries and mutations by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/124
* Allow setting product vat as percentage value by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/125
* Add create product resolver by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/126
* Skip changelogs for draft permits by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/127
* Fix products date range query by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/128
* Feature/age calculation by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/129
* Fix subscription issue as it can be null by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/130
* Feature/Api docs by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/131
* Update graphql schema and resolvers for saving addresses by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/132
* Add zoneByLocation graphql query by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/133
* Feature/Talpa checkout multiple price by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/134
* Refactor the refund calculate and order renewal for varying product prices by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/135
* Automatic expiration of parking permit by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/136
* Implement GDPR API by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/137
* Add a cron job script that automatically remove obsolte customer data by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/139
* Feature/parkkihubi integration by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/138
* Feature/parkkihubi integration by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/140
* Add refund detail resolver by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/141
* Fix talpa price calculations by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/142
* Fix resident UI end time calculation by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/143
* Return created permit info for createResidentPermit mutation by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/144
* Include page range and count in page info by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/145
* Talpa open ended subscription by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/147
* Add a GraphQL query to get price changes for permit changes by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/146
* Calculate price for talpa and resolve right of purchase by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/148
* Update main branch from develop by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/149
* Fix the refund calculation logic when updating permit by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/150
* Update api docs by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/151
* Using entitlement keys instead of personal Red Hat subscriptions by @SuviVappula in https://github.com/City-of-Helsinki/parking-permits/pull/153
* Get meta from orderItem by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/152
* Send startdate as UTC format to talpa by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/154
* Fix field name for checkout visibility by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/155
* Add description field to ParkingPermit model by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/156
* Prevent saving address if non-disclosure is checked by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/157
* Merge develop to main by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/158
* Move saving profile address into its own function by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/159
* Add resolvers for changing address and related price changes  by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/161
* Merge develop to main by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/162
* Fix open ended price change info format by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/163
* Add missing end_date for open ended price change info by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/164
* Change address extra payment case by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/165
* Traficom integration by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/160
* Fix management command for bootstraping parking permit by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/166
* Add more logging for temporary debug purposes by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/168
* Bump django from 3.2 to 3.2.12 by @dependabot in https://github.com/City-of-Helsinki/parking-permits/pull/167
* Merge develop to main by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/169
* Remove owner/holder filter for admin vehicle resolver by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/170
* Remove non-exist fields when saving vehicles by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/171
* Add DVV integration by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/172
* Include otherAddress in GraphQL CustomerNode and CustomerInput by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/174
* Merge develop to main by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/173
* Add logging for talpa payload and responses by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/175
* Refactor address model by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/176
* Upgrade pip-tools to 6.5.1 and resolve incompatible requirements by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/177
* Upgrade black to 22.3.0 by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/178
* Include additional fields in dvv customer and address data  by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/179
* Add DVV integration environment variables to .env.example file by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/180
* Traficom integration by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/181
* Remove hard coded ssn from resolver by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/182
* Minor refactoring on creating renewal order by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/183
* Make parking permit manager utility methods available for both manager and  queryset by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/185
* Feat/traficom check by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/184
* Query Traficom vehicle details for admin ui vehicle resolver by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/186
* Admin UI Orders list view by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/187
* Update graphql vehicle interface to use low emission fields by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/188
* Merge develop to main by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/189
* Use order item dates for Talpa product description by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/191
* Prevent creating more than 2 permits for the same customer by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/190
* Add LocaleMiddleware and LOCALE_PATHS settings by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/192
* Bump django from 3.2.12 to 3.2.13 by @dependabot in https://github.com/City-of-Helsinki/parking-permits/pull/193
* Update azure-pipelines-develop.yml by @lorand-ibm in https://github.com/City-of-Helsinki/parking-permits/pull/194
* Add batch trigger to azure-pipelines-release.yml by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/197
* Implement csv exporter by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/196
* Vehicle change by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/198
* Add an addresses resolver by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/200
* Vehicle change with refund and talpa order by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/202
* Add address maintenance resolvers by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/201
* Refactor subscription and order models by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/199
* Fix order id changes by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/203
* Fix refund graphql node by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/204
* Restart the parking permit id sequence by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/205
* Add graphql resolvers for low emission criteria CRUD operations by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/206
* Fix vehicle change price changes by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/207
* Refactor permit price calculation for Admin UI by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/208
* Add a total refund amount property by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/210
* Refactor the search filters by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/209
* Add email configurations by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/211
* Send parking permit type to parkkihubi by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/213
* Add language field to customer model and a graphql resolve to save customer language by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/212
* Send emails when parking permit is created/updated/ended by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/214
* Low emission fields fix and get updated permits before sending email by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/216
* PDF-report creation by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/215
* End parking permit by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/217
* Add zone changed property to Permit model by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/218
* Email templates styling fixes by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/219
* Various email templates fixes by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/220
* Validate secondary permit validity period by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/221
* Fix low emissin calculation when emission is 0 by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/222
* Fix parking permit not being able to send email by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/223
* Activate customer language when rendering email message by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/224
* Adjust Permit PDF according to latest layout by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/225
* Fix static files to work with collectstatic by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/226
* Update webshop permit create/update resolvers by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/227
* Allow searching refunds with different search criteria by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/229
* Update requirements-test.txt by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/228
* Update requirements by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/230
* Refund PDF-report by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/231
* Add None-check for paid time by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/232
* Add admin resolvers for accepting refunds and requesting for approval by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/233
* Add refund accepted_at and accepted_by by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/234
* Cron to sync permit with parkkihubi every 30 min by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/235
* Fix conflicted migrations by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/236
* Send emails to customers when refund is created or accepted by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/237
* Fix parkkihubi error while updating response from talpa by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/238
* Refactor object list search, filter and order through object specific forms by @mingfeng in https://github.com/City-of-Helsinki/parking-permits/pull/239
* Encrypted fields for sensitive data by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/240
* Update primary/secondary permit fi-translations by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/241
* Add receipt URL to the response by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/242
* Feat/pv 420 address maintenance by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/244
* Temporary vehicle support by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/245
* Email templating for temporary vehicles by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/246
* Add management commands for the cron jobs by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/248
* Feat/use traficom check variable to validate owners by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/249
* Add pull request template by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/250
* Force Subscription registering process by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/251
* Test for dockerfile without redhat image by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/252
* Add missing .gitconfig-file by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/253
* Remove unneeded .gitconfig-declarations by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/254
* Update SECRET_KEY to be DJANGO_SECRET_KEY by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/255
* Fix dockerfile by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/256
* Fix/talpa endpoints by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/257
* Add Sentry-integration by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/258
* Update address extractor and exclude saving it to database if not in Helsinki by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/259
* Fix bugs related to address after testing sessions by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/261
* Use env template for environment variables by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/262
* Bump django from 3.2.13 to 3.2.15 by @dependabot in https://github.com/City-of-Helsinki/parking-permits/pull/247
* Fix KMO parse_street_name_and_number by @danipran in https://github.com/City-of-Helsinki/parking-permits/pull/263
* PV-402: Add support for searching orders by @danipran in https://github.com/City-of-Helsinki/parking-permits/pull/260
* Update finnish translations by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/264
* Add price and vat information to the refund template by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/265
* PV-402: Return only distinct orders by @danipran in https://github.com/City-of-Helsinki/parking-permits/pull/266
* Retrieve both user addresses from DVV by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/267
* [Snyk] Security upgrade django from 3.2.15 to 3.2.16 by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/269
* Add test address for user Hessu Hesalainen by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/270
* Add is is_order_confirmed calculated property to parking permit by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/271
* Refactor User address handling by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/272
* Translate email-templates by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/273
* Add management command for creating group mapping by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/274
* Parking permit expiration remind email by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/275
* [Snyk] Security upgrade django from 3.2.15 to 3.2.16 by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/268
* Send permit end email on automatic permit ending by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/276
* Feat/PV-280 Role based access control decorators for users by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/277
* Vehicle low emission discount for 3rd party parking providers by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/278
* PV-346: Add database model & endpoints for announcements by @danipran in https://github.com/City-of-Helsinki/parking-permits/pull/279
* PV-368: Send announcement emails by @danipran in https://github.com/City-of-Helsinki/parking-permits/pull/280
* PV-421/PV-444: Add customer list, retrieve customer by ID, retrieve more customer data, fix GDPR API view by @danipran in https://github.com/City-of-Helsinki/parking-permits/pull/281
* Show only vehicle registration number third party emails by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/282
* PV-458: Return empty queryset by default in customer/refund/permit/order forms by @danipran in https://github.com/City-of-Helsinki/parking-permits/pull/283
* Allow Traficom check overriding through settings by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/285
* Role base access control by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/284
* PV-459: Add address search parameters by @danipran in https://github.com/City-of-Helsinki/parking-permits/pull/286
* Use original permit start time for validity start by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/288
* PV-463: Fix CSV export parameters by @danipran in https://github.com/City-of-Helsinki/parking-permits/pull/287
* Fix GDPR permission issue for super admin by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/290
* Fix traficom error for not parsing ssn by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/289
* Add low emission consent to a vehcile change by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/291
* Update Talpa-checkout layout by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/293
* Fix second vehicle adding by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/294
* PV-449: Create audit logger app for structured logging by @danipran in https://github.com/City-of-Helsinki/parking-permits/pull/295
* Fix: Add audit_logger to .dockerignore by @danipran in https://github.com/City-of-Helsinki/parking-permits/pull/297
* Feat/vehicle power type by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/296
* Add missing vehicle power type from vehicle node by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/298
* Update 2022 low-emission criteria default values by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/299
* Fix: Change VehiclePowerTypeNode's identifier type to String! by @danipran in https://github.com/City-of-Helsinki/parking-permits/pull/300
* Reset the month count for permits if primary vehicle is changed by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/301
* Minimum role to create a permit is customer service by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/303
* Fix ending of permit by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/304
* Update project translations by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/305
* Create a refund only if there is a valid refund amount by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/306
* Fix: Fix vehicle power type in vehicle update/create by @danipran in https://github.com/City-of-Helsinki/parking-permits/pull/307
* Update JSON serialization to work with proxies by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/308
* Explicitly update also permit address by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/309
* Adjust CSV- and PDF-export lowest role to be preparator by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/313
* PV-449: Add audit logging in resolvers by @danipran in https://github.com/City-of-Helsinki/parking-permits/pull/310
* Refund should be created for an open ended permit if not started by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/314
* Fix Admin UI create permit issues by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/315
* End time can not be less than start time by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/316
* Send permit email if payment is done in case order is created by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/317
* Use current timestamp in low-emission discount emails by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/318
* Fix address change refund by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/319
* Validate temporary vehicle start time by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/320
* Fix webshop permit vehicle- and address-change processes by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/321
* Calculate permit total price change with month count by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/322
* Fix permit creation issues by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/323
* Admin UI: Validate permit creation main cases by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/324
* Add temporary vehicle support for admin view by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/325
* PV-350: Add parking permit events by @danipran in https://github.com/City-of-Helsinki/parking-permits/pull/327
* Admin UI update permit with change vehicle and change address features by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/326
* Use Python v.3.9 in Dockerfile by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/328
* PV-350: Remove django-reversion by @danipran in https://github.com/City-of-Helsinki/parking-permits/pull/329
* Update Admin UI searches and PDF-export by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/331
* PV-350: Add temporary vehicle events (add, remove), add missing change address event by @danipran in https://github.com/City-of-Helsinki/parking-permits/pull/332
* Fix Admin UI permit ending and exporters by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/333
* Admin UI: Prevent secondary permit end date to exceed first active permit by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/335
* Update Talpa checkout orders to have two decimals by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/336
* Permit emails: Use permit end time only with fixed-period permit by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/334
* Order partial refunds support by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/337
* Fix: Permit editing admin by @amanpdyadav in https://github.com/City-of-Helsinki/parking-permits/pull/338
* Update GitHub CI Python and PostGIS versions by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/341
* PV-363: Add PASI CSV import command by @danipran in https://github.com/City-of-Helsinki/parking-permits/pull/340
* PV-519: Add end time for open-ended permits' order items, show current period end time for open-ended permit exports/emails. by @danipran in https://github.com/City-of-Helsinki/parking-permits/pull/345
* [Snyk] Security upgrade setuptools from 39.0.1 to 65.5.1 by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/311
* [Snyk] Security upgrade setuptools from 39.0.1 to 65.5.1 by @snyk-bot in https://github.com/City-of-Helsinki/parking-permits/pull/312
* [Snyk] Security upgrade wheel from 0.37.1 to 0.38.0 by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/292
* [Snyk] Security upgrade setuptools from 39.0.1 to 65.5.1 by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/342
* [Snyk] Fix for 2 vulnerabilities by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/343
* Fix: Round VAT percentage to an integer in Talpa integration by @danipran in https://github.com/City-of-Helsinki/parking-permits/pull/346
* PV-519: Fix typo in permit info email template by @danipran in https://github.com/City-of-Helsinki/parking-permits/pull/350
* Add support for Talpa Subscription events by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/358
* Subscription renewals by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/364
* Cancel linked Talpa order and subscription by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/365
* Add apartment support for addresses by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/366
* Make update_or_create_address null-safe by @danipran in https://github.com/City-of-Helsinki/parking-permits/pull/368
* Feature/pv 614 prevent duplicate address creation by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/372
* Fix open-ended permit deletion to work with latest Talpa-integration requests by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/373
* Permit-form DVV customer search should also take address apartments into account by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/374
* Use customer full name in customer notification emails by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/375
* Enhance Talpa subscription validation by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/376
* Fix subscription data format by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/377
* Add checkout_url to GraphQL schema by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/378
* Always check subscription existence by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/379
* Improve "right of purchase" Talpa webhook handling by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/380
* Use vehicle decommissioned status directly by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/381
* Adapt to changed Talpa resolve price schema by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/382
* Update Subscription renewal process to match latest Talpa-specifications by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/383
* Use only valid permits in order renewal phase by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/385
* Round refund prices to two-decimal precision without localization by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/386
* Improve temporary vehicle email templates by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/387
* Improve Talpa-views error handling by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/388
* Update customer info retrieval by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/392
* Always use permit start- and end-times in permit emails by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/393
* Use Base64-encoded PNG-image as Helsinki logo in emails by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/394
* Set emission to zero if None by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/395
* Handle multiple values and previous vehicles in order search by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/396
* Pv 624 order search fixes by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/399
* Pv 655 change address bugfix by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/400
* Set end_time when start_time is set by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/401
* Fix datetime-format to use milliseconds by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/402
* Set Helsinki time zone when creating Talpa order by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/403
* Update talpa checkout data labels by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/404
* Start time should always be parsed before end time calculation by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/405
* Ensure start_time is normalized to local timezone before doing by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/406
* Improve permit text search by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/408
* Fix open-ended permit order item dates by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/409
* Remove Traficom checks from PASI CSV-import by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/410
* Multiple refunds per order by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/411
* Add Talpa resolve product endpoint with tests by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/413
* Localize Talpa checkout data by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/412
* Talpa Order renewal fixes by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/414
* Always bypass Talpa order cancel event handling by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/415
* Call Talpa cancels as final step in permit ending by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/416
* Allow open-ended permit renewal for address and vehicle changes by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/418
* Automatic permit expiration cronjob updates by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/420
* Set default emission value from Traficom to 0 if none found. by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/421
* When checking if vehicle is low-emission, check 0 as well as None by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/424
* Do not create an order if the pricing is equal when updating permit by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/425
* Handle open ended permit price change month count by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/426
* Add base_price and discount_price to Product in GetPermits resolver by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/427
* Skip Refund creation when ending open-ended permit by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/428
* Show traficom restrictions by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/430
* Apply 2nd vehicle premium to unit price after setting from discount by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/431
* Add canBeRefunded to webshop GraphQL schema by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/432
* When fetching customer info from DVV, look up active permits from database by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/433
* Add totalRefundAmount to webshop permit GraphQL by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/434
* When calculating product prices, apply 2nd vehicle premium to base_price by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/435
* Update Helsinki profile GDPR implementation by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/436
* Add extra check if permit is refundable: if open ended and end time > 1 by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/437
* Traficom error message fixes by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/438
* Make Helsinki address checks optional by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/439
* Check if Swedish address is not null before parsing by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/440
* Open-ended permit refund amount should depend on total refund amount by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/441
* Remove Traficom attributions from PDF and CSV files. by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/443
* Secure cookie/session changes  by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/444
* Pv 758 vat calculation fixes by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/445
* Update VAT and net price calculations for individual orders. by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/447
* Pass iban to Subscription.cancel() by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/448
* Use calc_vat_price() for permit price list change by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/450
* When TRAFICOM_MOCK environment variable is set, fetches Traficom details from local db by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/451
* Use correct VAT amounts in refund emails by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/452
* Add message change to include data restrictions check. by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/454
* Add Traficom service unit tests by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/455
* Ensure that the permit prices resolver sets correct timezone for start by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/456
* Add the start time to customer active permits in admin GraphQL. by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/457
* Use localtime explicitly when checking permit statuses by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/458
* Ensure any single quotes in the address passed to WSF are escaped by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/459
* Traficom carbon fixes by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/460
* Ensure we compare the street name correctly when extracting geometric by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/461
* Fix talpa rounding error by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/462
* Update resolve-product endpoint to always send also modified order item metadata by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/464
* Update Vehicle classes and driving class mappings by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/466
* Log closed permit id on expiration of permits by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/469
* Bypass traficom setting by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/465
* Use only vehicle own weight as weight limit by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/470
* Mark permit as cancelled after 15 minutes of order creation by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/472
* Permit can be ended if current period end time same day or less than by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/473
* Improve mail error handling by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/474
* Add one month using localtime by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/475
* Cancel order and it's permits in ORDER_CANCELLED-event by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/476
* Update low emission discount email contents by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/477
* Send announcements only to valid permits by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/478
* Update Talpa order cancellation conditions by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/479
* Temporarily disable vehicle user check by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/480
* Add ParkingPermitExtensionRequest model and workflows by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/471
* Add PERMIT_EXTENSIONS_ENABLED flag to allow extending permits by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/481
* Update vehicle fetch logic by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/482
* Use more explicit JSON key-formats by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/484
* Second permit extension month limit by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/483
* Call Parkkihubi in ParkingPermit.extend_permit() method by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/485
* Validate order only when orderId and userId exists by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/486
* Cancel order and it's permits only when the permit was marked to be ended immediately  by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/487
* Added admin resolver for creating a permit extension. by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/488
* Add Parking permit event types for customer and admin extension by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/489
* Regard vehicle without emissions as normal vehicle by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/490
* Enforce upper case for all manually entered national ID numbers. by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/491
* Permit active temporary vehicle should be None if current time outside by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/492
* Update vehicle with the exact registration number returned from Traficom by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/493
* Set validity period of add/remove temp vehicle permits to the temp by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/494
* Normalize address fields returned from DVV by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/495
* Calculate Talpa pricing by subtracting VAT from gross to give net. by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/497
* Ensure that the end time accounts for DST by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/496
* Send permit expiration email only for fixed-period permits by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/498
* Allow start and end times for temp vehicles before current time.  by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/499
* Add command to find and adjust open ended permits with local time 0:59 by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/500
* Add modifications to Vehicle Admin: restrictions and users can be empty by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/501
* Add direct support for L3e-class vehicles by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/502
* Set end time of temp vehicle to permit end time if the latter is before by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/503
* Admin UI search fixes by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/504
* Cron to delete permits extensions by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/505
* Add talpa_update_card_url to Order model. by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/506
* Parkkihubi changes by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/507
* Set status_changed_at for extension requests in management command. by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/508
* Add resolver_utils module for common functionality between resolver and admin resolver by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/509
* Avoid re-fetching vehicle after initial lookup by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/510
* Update card link by @danjacob-anders in https://github.com/City-of-Helsinki/parking-permits/pull/511
* Add vehicle and permit for order in extended permit by @tonipel in https://github.com/City-of-Helsinki/parking-permits/pull/512
* Add support for more detailed L3-vehicle classes by @mhieta in https://github.com/City-of-Helsinki/parking-permits/pull/513
* Add talpa order id to api by @tonipel in https://github.com/City-of-Helsinki/parking-permits/pull/514
* Add new driving licences and classes by @tonipel in https://github.com/City-of-Helsinki/parking-permits/pull/515
* Fix bug in traficom vehicle api by @tonipel in https://github.com/City-of-Helsinki/parking-permits/pull/516
* Add fallback to L3eA1 for motorcycles in case traficom doesn't return power or vehicle sub class by @tonipel in https://github.com/City-of-Helsinki/parking-permits/pull/517
* Cleanup and refactor L3 -classification in traficom api by @tonipel in https://github.com/City-of-Helsinki/parking-permits/pull/518
* Change admin ui order date search to search orders by @tonipel in https://github.com/City-of-Helsinki/parking-permits/pull/519
* Fix date search by @tonipel in https://github.com/City-of-Helsinki/parking-permits/pull/520
* Add logging to payment view by @tonipel in https://github.com/City-of-Helsinki/parking-permits/pull/521
* Update packages by @tonipel in https://github.com/City-of-Helsinki/parking-permits/pull/522
* Update python and django versions by @tonipel in https://github.com/City-of-Helsinki/parking-permits/pull/523
* Add missing package by @tonipel in https://github.com/City-of-Helsinki/parking-permits/pull/525
* Add new test cases. Handle special chars and if no ssn is received. by @tonipel in https://github.com/City-of-Helsinki/parking-permits/pull/524

## New Contributors
* @sam-hosseini made their first contribution in https://github.com/City-of-Helsinki/parking-permits/pull/1
* @AnttiKoistinen431a made their first contribution in https://github.com/City-of-Helsinki/parking-permits/pull/11
* @mhieta made their first contribution in https://github.com/City-of-Helsinki/parking-permits/pull/14
* @amanpdyadav made their first contribution in https://github.com/City-of-Helsinki/parking-permits/pull/23
* @mingfeng made their first contribution in https://github.com/City-of-Helsinki/parking-permits/pull/55
* @SuviVappula made their first contribution in https://github.com/City-of-Helsinki/parking-permits/pull/153
* @dependabot made their first contribution in https://github.com/City-of-Helsinki/parking-permits/pull/167
* @danipran made their first contribution in https://github.com/City-of-Helsinki/parking-permits/pull/263
* @snyk-bot made their first contribution in https://github.com/City-of-Helsinki/parking-permits/pull/312
* @danjacob-anders made their first contribution in https://github.com/City-of-Helsinki/parking-permits/pull/372
* @tonipel made their first contribution in https://github.com/City-of-Helsinki/parking-permits/pull/512

**Full Changelog**: https://github.com/City-of-Helsinki/parking-permits/commits/release-1.0.0
