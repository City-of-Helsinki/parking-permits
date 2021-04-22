def test_database_connection_works_in_tests(django_user_model):
    django_user_model.objects.create_user(username="banana")
    assert django_user_model.objects.get(username="banana")
