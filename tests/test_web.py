"""Integration tests for the WebSocket endpoint and REST history."""

from __future__ import annotations


def test_index_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "realtime-chat" in res.text.lower()


def test_history_endpoint_empty_for_new_room(client):
    assert client.get("/api/rooms/brandnew/messages").json() == []


def test_single_client_join_and_echo(client):
    with client.websocket_connect("/ws/general?username=alice") as ws:
        # On join: history, then "joined" system frame, then presence.
        history = ws.receive_json()
        assert history["type"] == "history" and history["messages"] == []
        joined = ws.receive_json()
        assert joined["type"] == "system" and "alice joined" in joined["content"]
        presence = ws.receive_json()
        assert presence["type"] == "presence" and presence["users"] == ["alice"]

        # Sending a message echoes back as a message frame.
        ws.send_json({"content": "hello world"})
        msg = ws.receive_json()
        assert msg["type"] == "message"
        assert msg["username"] == "alice" and msg["content"] == "hello world"


def test_empty_messages_are_ignored(client):
    with client.websocket_connect("/ws/general?username=alice") as ws:
        for _ in range(3):  # drain join frames
            ws.receive_json()
        ws.send_json({"content": "   "})   # whitespace only -> ignored
        ws.send_json({"content": "real"})
        msg = ws.receive_json()
        assert msg["content"] == "real"


def test_broadcast_between_two_clients(client):
    with client.websocket_connect("/ws/room1?username=alice") as a:
        for _ in range(3):  # drain alice's own join frames
            a.receive_json()

        with client.websocket_connect("/ws/room1?username=bob") as b:
            assert b.receive_json()["type"] == "history"

            # Alice is told bob joined, with updated presence.
            a_sys = a.receive_json()
            assert a_sys["type"] == "system" and "bob joined" in a_sys["content"]
            a_pres = a.receive_json()
            assert a_pres["type"] == "presence" and set(a_pres["users"]) == {"alice", "bob"}

            # Drain bob's own join frames (system + presence).
            b.receive_json()
            b.receive_json()

            # A message from bob reaches alice.
            b.send_json({"content": "hi alice"})
            received = a.receive_json()
            assert received["type"] == "message"
            assert received["username"] == "bob" and received["content"] == "hi alice"


def test_history_persists_across_connections(client):
    with client.websocket_connect("/ws/persist?username=alice") as a:
        for _ in range(3):
            a.receive_json()
        a.send_json({"content": "remember me"})
        assert a.receive_json()["content"] == "remember me"

    # A later client gets the message in its history frame.
    with client.websocket_connect("/ws/persist?username=bob") as b:
        history = b.receive_json()
        assert history["type"] == "history"
        assert any(m["content"] == "remember me" for m in history["messages"])

    # And the REST endpoint sees it too.
    res = client.get("/api/rooms/persist/messages")
    assert any(m["content"] == "remember me" for m in res.json())
