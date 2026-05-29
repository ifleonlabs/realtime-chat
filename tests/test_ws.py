"""WebSocket tests: authentication, authorization, broadcast, and history."""

from __future__ import annotations

import pytest
from fastapi import WebSocketDisconnect


def _token(headers: dict) -> str:
    return headers["Authorization"].split(" ", 1)[1]


def _make_room(client, headers, **kw) -> str:
    payload = {"name": "Room"}
    payload.update(kw)
    return client.post("/api/rooms", json=payload, headers=headers).json()["slug"]


def test_ws_rejects_without_token(client, auth):
    headers = auth("alice")
    slug = _make_room(client, headers)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/{slug}") as ws:
            ws.receive_json()


def test_ws_rejects_unknown_room(client, auth):
    headers = auth("alice")
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/nope-xyz?token={_token(headers)}") as ws:
            ws.receive_json()


def test_ws_rejects_non_member_of_private_room(client, auth):
    owner = auth("alice")
    other = auth("bob")
    slug = _make_room(client, owner, name="Secret", is_private=True)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/{slug}?token={_token(other)}") as ws:
            ws.receive_json()


def test_ws_authorized_flow_and_echo(client, auth):
    headers = auth("alice")
    slug = _make_room(client, headers, name="General")
    with client.websocket_connect(f"/ws/{slug}?token={_token(headers)}") as ws:
        history = ws.receive_json()
        assert history["type"] == "history" and history["messages"] == []
        assert ws.receive_json()["type"] == "system"        # alice joined
        presence = ws.receive_json()
        assert presence["type"] == "presence" and presence["users"] == ["alice"]

        ws.send_json({"content": "hello"})
        msg = ws.receive_json()
        assert msg["type"] == "message" and msg["username"] == "alice" and msg["content"] == "hello"


def test_ws_broadcast_between_members(client, auth):
    owner = auth("alice")
    other = auth("bob")
    slug = _make_room(client, owner, name="Open")
    client.post(f"/api/rooms/{slug}/join", json={}, headers=other)  # bob joins

    with client.websocket_connect(f"/ws/{slug}?token={_token(owner)}") as a:
        for _ in range(3):  # drain alice's join frames
            a.receive_json()
        with client.websocket_connect(f"/ws/{slug}?token={_token(other)}") as b:
            assert b.receive_json()["type"] == "history"
            sys_frame = a.receive_json()
            assert sys_frame["type"] == "system" and "bob joined" in sys_frame["content"]
            a.receive_json()           # presence update for alice
            b.receive_json()           # bob's own system frame
            b.receive_json()           # bob's own presence frame

            b.send_json({"content": "hi alice"})
            received = a.receive_json()
            assert received["type"] == "message"
            assert received["username"] == "bob" and received["content"] == "hi alice"


def test_ws_typing_relayed_to_others_not_sender(client, auth):
    owner = auth("alice")
    other = auth("bob")
    slug = _make_room(client, owner, name="Open")
    client.post(f"/api/rooms/{slug}/join", json={}, headers=other)

    with client.websocket_connect(f"/ws/{slug}?token={_token(owner)}") as a:
        for _ in range(3):
            a.receive_json()
        with client.websocket_connect(f"/ws/{slug}?token={_token(other)}") as b:
            b.receive_json()      # history
            a.receive_json()      # system: bob joined
            a.receive_json()      # presence
            b.receive_json()      # bob's own system
            b.receive_json()      # bob's own presence

            # Bob types -> Alice sees a typing frame for bob; Bob does not.
            b.send_json({"type": "typing"})
            frame = a.receive_json()
            assert frame == {"type": "typing", "username": "bob"}

            # Confirm it isn't echoed to the sender: bob's next frame is a real
            # message (typing was not delivered back to bob).
            b.send_json({"type": "message", "content": "done typing"})
            assert b.receive_json()["content"] == "done typing"


def test_ws_rtc_signaling_relayed_to_target_only(client, auth):
    owner = auth("alice")
    other = auth("bob")
    slug = _make_room(client, owner, name="Open")
    client.post(f"/api/rooms/{slug}/join", json={}, headers=other)

    with client.websocket_connect(f"/ws/{slug}?token={_token(owner)}") as a:
        for _ in range(3):
            a.receive_json()
        with client.websocket_connect(f"/ws/{slug}?token={_token(other)}") as b:
            b.receive_json()      # history
            a.receive_json()      # bob joined
            a.receive_json()      # presence
            b.receive_json()      # bob's own system
            b.receive_json()      # bob's own presence

            a.send_json({"type": "rtc", "target": "bob", "signal": {"sdp": "offer-xyz"}})
            frame = b.receive_json()
            assert frame == {"type": "rtc", "from": "alice", "signal": {"sdp": "offer-xyz"}}

            b.send_json({"type": "rtc", "target": "alice", "signal": {"sdp": "answer-xyz"}})
            reply = a.receive_json()
            assert reply["type"] == "rtc" and reply["from"] == "bob"


def test_ws_history_persists(client, auth):
    headers = auth("alice")
    slug = _make_room(client, headers, name="Persist")
    with client.websocket_connect(f"/ws/{slug}?token={_token(headers)}") as ws:
        for _ in range(3):
            ws.receive_json()
        ws.send_json({"content": "remember me"})
        assert ws.receive_json()["content"] == "remember me"

    with client.websocket_connect(f"/ws/{slug}?token={_token(headers)}") as ws:
        history = ws.receive_json()
        assert history["type"] == "history"
        assert any(m["content"] == "remember me" for m in history["messages"])
