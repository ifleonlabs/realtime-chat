"use strict";

const $ = (id) => document.getElementById(id);
const els = {
  join: $("join"),
  joinForm: $("join-form"),
  username: $("username"),
  room: $("room"),
  chat: $("chat"),
  roomName: $("room-name"),
  status: $("status"),
  leaveBtn: $("leave-btn"),
  messages: $("messages"),
  userList: $("user-list"),
  onlineCount: $("online-count"),
  messageForm: $("message-form"),
  messageInput: $("message-input"),
};

let socket = null;
let myName = "";

els.joinForm.addEventListener("submit", (e) => {
  e.preventDefault();
  myName = els.username.value.trim() || "anonymous";
  const room = (els.room.value.trim() || "general").toLowerCase();
  connect(room, myName);
});

els.leaveBtn.addEventListener("click", () => {
  if (socket) socket.close();
  els.chat.hidden = true;
  els.join.hidden = false;
  els.messages.innerHTML = "";
});

els.messageForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const content = els.messageInput.value.trim();
  if (!content || !socket || socket.readyState !== WebSocket.OPEN) return;
  socket.send(JSON.stringify({ content }));
  els.messageInput.value = "";
});

function connect(room, username) {
  els.join.hidden = true;
  els.chat.hidden = false;
  els.roomName.textContent = "#" + room;
  setStatus("connecting…", false);

  const proto = location.protocol === "https:" ? "wss" : "ws";
  const url = `${proto}://${location.host}/ws/${encodeURIComponent(room)}?username=${encodeURIComponent(username)}`;
  socket = new WebSocket(url);

  socket.onopen = () => {
    setStatus("live", true);
    els.messageInput.focus();
  };
  socket.onclose = () => setStatus("disconnected", false);
  socket.onerror = () => setStatus("error", false);
  socket.onmessage = (event) => handle(JSON.parse(event.data));
}

function setStatus(text, live) {
  els.status.textContent = text;
  els.status.classList.toggle("live", live);
}

function handle(frame) {
  switch (frame.type) {
    case "history":
      frame.messages.forEach(addMessage);
      break;
    case "message":
      addMessage(frame);
      break;
    case "system":
      addSystem(frame.content);
      break;
    case "presence":
      renderPresence(frame.users, frame.count);
      break;
  }
}

function addMessage(m) {
  const el = document.createElement("div");
  el.className = "msg" + (m.username === myName ? " me" : "");
  const time = new Date(m.created_at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  el.innerHTML = `<div class="who">${escapeHtml(m.username)}<span class="time">${time}</span></div>
                  <div class="text"></div>`;
  el.querySelector(".text").textContent = m.content;
  appendAndScroll(el);
}

function addSystem(text) {
  const el = document.createElement("div");
  el.className = "system";
  el.textContent = text;
  appendAndScroll(el);
}

function renderPresence(users, count) {
  els.onlineCount.textContent = count;
  els.userList.innerHTML = "";
  users.forEach((u) => {
    const li = document.createElement("li");
    li.textContent = u;
    els.userList.appendChild(li);
  });
}

function appendAndScroll(el) {
  const atBottom = els.messages.scrollHeight - els.messages.scrollTop - els.messages.clientHeight < 80;
  els.messages.appendChild(el);
  if (atBottom) els.messages.scrollTop = els.messages.scrollHeight;
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}
