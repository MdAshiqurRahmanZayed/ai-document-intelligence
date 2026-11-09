import uuid

from tests.helpers import Api

URL = "/api/v1/chat/sessions"


async def make(api: Api, title: str | None = None) -> dict:  # type: ignore[type-arg]
    response = await api.client.post(URL, json={"title": title} if title else {})
    assert response.status_code == 201
    return response.json()  # type: ignore[no-any-return]


async def test_create_and_list_newest_first(api: Api) -> None:
    first = await make(api, "first")
    second = await make(api)

    body = (await api.client.get(URL)).json()

    assert second["title"] == "New chat" and second["message_count"] == 0
    assert body["total"] == 2
    # Created later, so listed first.
    assert [i["id"] for i in body["items"]] == [second["id"], first["id"]]


async def test_create_without_a_body(api: Api) -> None:
    assert (await api.client.post(URL)).status_code == 201


async def test_read_returns_the_session_with_no_messages_yet(api: Api) -> None:
    created = await make(api)
    body = (await api.client.get(f"{URL}/{created['id']}")).json()
    assert body["messages"] == [] and body["title"] == "New chat"


async def test_rename_and_order_unchanged(api: Api) -> None:
    older = await make(api)
    await make(api)

    response = await api.client.patch(f"{URL}/{older['id']}", json={"title": "  Hosting  "})

    assert response.status_code == 200 and response.json()["title"] == "Hosting"
    ids = [i["id"] for i in (await api.client.get(URL)).json()["items"]]
    assert ids[-1] == older["id"]


async def test_blank_or_long_title_is_rejected_and_nothing_changes(api: Api) -> None:
    created = await make(api, "keep")
    for title in ["   ", "x" * 101]:
        response = await api.client.patch(f"{URL}/{created['id']}", json={"title": title})
        assert response.status_code == 422
    assert (await api.client.get(f"{URL}/{created['id']}")).json()["title"] == "keep"


async def test_delete_then_not_found(api: Api) -> None:
    created = await make(api)

    assert (await api.client.delete(f"{URL}/{created['id']}")).status_code == 204

    for response in [
        await api.client.get(f"{URL}/{created['id']}"),
        await api.client.delete(f"{URL}/{created['id']}"),
        await api.client.patch(f"{URL}/{created['id']}", json={"title": "x"}),
    ]:
        assert response.status_code == 404
        assert response.json()["detail"] == {"reason": "session_not_found"}


async def test_unknown_id_is_404_and_bad_id_is_422(api: Api) -> None:
    assert (await api.client.get(f"{URL}/{uuid.uuid4()}")).status_code == 404
    assert (await api.client.get(f"{URL}/not-a-uuid")).status_code == 422


async def test_limit_is_checked_and_paging_works(api: Api) -> None:
    for _ in range(3):
        await make(api)
    assert (await api.client.get(URL, params={"limit": 0})).status_code == 422
    assert (await api.client.get(URL, params={"limit": 101})).status_code == 422
    page = (await api.client.get(URL, params={"limit": 2, "offset": 2})).json()
    assert len(page["items"]) == 1 and page["total"] == 3
