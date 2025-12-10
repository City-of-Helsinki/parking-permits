import json

ALL_METHODS = ("get", "post", "put", "patch", "delete")


def get(api_client, url, status_code=200):
    response = api_client.get(url)
    assert response.status_code == status_code, (
        f"{response.status_code} {response.data}"
    )
    return json.loads(response.content.decode("utf-8"))


def post(api_client, url, data=None, status_code=201):
    response = api_client.post(url, data)
    assert response.status_code == status_code, (
        f"{response.status_code} {response.data}"
    )
    return json.loads(response.content.decode("utf-8"))


def put(api_client, url, data=None, status_code=200):
    response = api_client.put(url, data)
    assert response.status_code == status_code, (
        f"{response.status_code} {response.data}"
    )
    return json.loads(response.content.decode("utf-8"))


def patch(api_client, url, data=None, status_code=200):
    response = api_client.patch(url, data)
    assert response.status_code == status_code, (
        f"{response.status_code} {response.data}"
    )
    return json.loads(response.content.decode("utf-8"))


def delete(api_client, url, status_code=204):
    response = api_client.delete(url)
    assert response.status_code == status_code, (
        f"{response.status_code} {response.data}"
    )
