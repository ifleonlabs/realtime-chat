"""HTTP API tests: auth and room management."""

from __future__ import annotations


def test_register_returns_token_and_user(client):
    res = client.post("/api/auth/register", json={"username": "alice", "password": "password123"})
    assert res.status_code == 201
    body = res.json()
    assert body["access_token"]
    assert body["user"]["username"] == "alice"


def test_register_validates_username(client):
    assert client.post("/api/auth/register", json={"username": "a b", "password": "password123"}).status_code == 422
    assert client.post("/api/auth/register", json={"username": "ok", "password": "123"}).status_code == 422


def test_login_and_me(client, auth):
    headers = auth("alice")
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200 and me.json()["username"] == "alice"

    login = client.post("/api/auth/login", data={"username": "alice", "password": "password123"})
    assert login.status_code == 200 and login.json()["user"]["username"] == "alice"


def test_login_wrong_password(client, auth):
    auth("alice")
    assert client.post("/api/auth/login", data={"username": "alice", "password": "nope"}).status_code == 401


def test_me_requires_auth(client):
    assert client.get("/api/auth/me").status_code == 401


def test_create_and_list_public_room(client, auth):
    headers = auth("alice")
    res = client.post("/api/rooms", json={"name": "General", "is_private": False}, headers=headers)
    assert res.status_code == 201
    room = res.json()
    assert room["is_owner"] and room["is_member"] and room["member_count"] == 1
    assert room["join_code"] is None  # public rooms have no code

    listed = client.get("/api/rooms", headers=headers).json()
    assert any(r["slug"] == room["slug"] for r in listed)


def test_private_room_owner_sees_code_others_dont(client, auth):
    owner = auth("alice")
    other = auth("bob")
    slug = client.post("/api/rooms", json={"name": "Secret", "is_private": True}, headers=owner).json()["slug"]

    # Private rooms aren't in the public list.
    assert all(r["slug"] != slug for r in client.get("/api/rooms", headers=other).json())
    # And a non-member can't view them.
    assert client.get(f"/api/rooms/{slug}", headers=other).status_code == 404


def test_join_private_requires_code(client, auth):
    owner = auth("alice")
    other = auth("bob")
    created = client.post("/api/rooms", json={"name": "Secret", "is_private": True}, headers=owner).json()
    slug, code = created["slug"], created["join_code"]

    assert client.post(f"/api/rooms/{slug}/join", json={"code": "wrong"}, headers=other).status_code == 403
    ok = client.post(f"/api/rooms/{slug}/join", json={"code": code}, headers=other)
    assert ok.status_code == 200 and ok.json()["is_member"]


def test_join_public_no_code(client, auth):
    owner = auth("alice")
    other = auth("bob")
    slug = client.post("/api/rooms", json={"name": "Open"}, headers=owner).json()["slug"]
    res = client.post(f"/api/rooms/{slug}/join", json={}, headers=other)
    assert res.status_code == 200 and res.json()["member_count"] == 2


def test_only_owner_can_delete(client, auth):
    owner = auth("alice")
    other = auth("bob")
    slug = client.post("/api/rooms", json={"name": "Open"}, headers=owner).json()["slug"]
    client.post(f"/api/rooms/{slug}/join", json={}, headers=other)

    assert client.delete(f"/api/rooms/{slug}", headers=other).status_code == 403
    assert client.delete(f"/api/rooms/{slug}", headers=owner).status_code == 204
    assert client.get(f"/api/rooms/{slug}", headers=owner).status_code == 404


def test_history_requires_membership(client, auth):
    owner = auth("alice")
    other = auth("bob")
    slug = client.post("/api/rooms", json={"name": "Open"}, headers=owner).json()["slug"]
    # Owner is a member; bob is not yet.
    assert client.get(f"/api/rooms/{slug}/messages", headers=owner).status_code == 200
    assert client.get(f"/api/rooms/{slug}/messages", headers=other).status_code == 403
