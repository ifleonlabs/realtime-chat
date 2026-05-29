// Peer-to-peer mesh over WebRTC data channels.
//
// File bytes travel directly between browsers — never through the server. The
// server's only role is relaying the tiny signaling handshake (offers/answers/
// ICE), which the caller wires up via `sendSignal`. Each peer also caches the
// blobs it has so it can re-serve them to anyone who asks (mini-torrent style).

export interface MediaMeta {
  id: string;
  name: string;
  mime: string;
  size: number;
}

type SendSignal = (target: string, signal: unknown) => void;
type OnBlob = (id: string, blob: Blob, meta: MediaMeta) => void;

const ICE_CONFIG: RTCConfiguration = {
  iceServers: [{ urls: "stun:stun.l.google.com:19302" }],
};
const CHUNK = 16 * 1024; // 16 KB chunks
const BUFFER_LIMIT = 256 * 1024; // backpressure threshold

interface Incoming {
  meta: MediaMeta;
  chunks: ArrayBuffer[];
}

export class PeerMesh {
  private peers = new Map<string, RTCPeerConnection>();
  private channels = new Map<string, RTCDataChannel>();
  private pendingIce = new Map<string, RTCIceCandidateInit[]>();
  private incoming = new Map<string, Incoming>(); // keyed by peer username
  private store = new Map<string, { blob: Blob; meta: MediaMeta }>(); // blobs we can serve

  constructor(
    private readonly self: string,
    private readonly sendSignal: SendSignal,
    private readonly onBlob: OnBlob,
  ) {}

  // --- public API --------------------------------------------------------
  /** Reconcile connections against the current room member list (presence). */
  setPeers(users: string[]): void {
    const others = new Set(users.filter((u) => u !== this.self));
    // Open connections to new peers (deterministic initiator avoids glare).
    for (const other of others) {
      if (!this.peers.has(other) && this.self < other) {
        this.connect(other, true);
      }
    }
    // Tear down peers who left.
    for (const other of [...this.peers.keys()]) {
      if (!others.has(other)) this.teardown(other);
    }
  }

  /** Handle a signaling message relayed from another peer. */
  async handleSignal(from: string, signal: any): Promise<void> {
    let pc = this.peers.get(from);
    if (!pc) pc = this.connect(from, false);

    if (signal.desc) {
      await pc.setRemoteDescription(signal.desc);
      // Drain any ICE that arrived before the remote description was set.
      const queued = this.pendingIce.get(from) || [];
      for (const c of queued) await pc.addIceCandidate(c).catch(() => {});
      this.pendingIce.delete(from);

      if (signal.desc.type === "offer") {
        const answer = await pc.createAnswer();
        await pc.setLocalDescription(answer);
        this.sendSignal(from, { desc: pc.localDescription });
      }
    } else if (signal.cand) {
      if (pc.remoteDescription) await pc.addIceCandidate(signal.cand).catch(() => {});
      else (this.pendingIce.get(from) || this.pendingIce.set(from, []).get(from)!).push(signal.cand);
    }
  }

  /** Cache a blob we own so peers can pull it from us. */
  put(id: string, blob: Blob, meta: MediaMeta): void {
    this.store.set(id, { blob, meta });
  }

  has(id: string): boolean {
    return this.store.has(id);
  }

  /** Ask every connected peer for a blob by id. */
  request(id: string): void {
    const msg = JSON.stringify({ t: "want", id });
    for (const ch of this.channels.values()) {
      if (ch.readyState === "open") ch.send(msg);
    }
  }

  /** Forget a blob (e.g. when its message expires). */
  drop(id: string): void {
    this.store.delete(id);
  }

  close(): void {
    for (const other of [...this.peers.keys()]) this.teardown(other);
  }

  // --- internals ---------------------------------------------------------
  private connect(other: string, initiator: boolean): RTCPeerConnection {
    const pc = new RTCPeerConnection(ICE_CONFIG);
    this.peers.set(other, pc);

    pc.onicecandidate = (e) => {
      if (e.candidate) this.sendSignal(other, { cand: e.candidate.toJSON() });
    };
    pc.onconnectionstatechange = () => {
      if (["failed", "closed", "disconnected"].includes(pc.connectionState)) this.teardown(other);
    };

    if (initiator) {
      const ch = pc.createDataChannel("data");
      this.setupChannel(other, ch);
      // Create and send the offer.
      pc.createOffer()
        .then((offer) => pc.setLocalDescription(offer))
        .then(() => this.sendSignal(other, { desc: pc.localDescription }))
        .catch(() => {});
    } else {
      pc.ondatachannel = (e) => this.setupChannel(other, e.channel);
    }
    return pc;
  }

  private setupChannel(other: string, ch: RTCDataChannel): void {
    ch.binaryType = "arraybuffer";
    ch.bufferedAmountLowThreshold = BUFFER_LIMIT;
    this.channels.set(other, ch);
    ch.onmessage = (e) => this.onChannelMessage(other, ch, e.data);
    ch.onclose = () => { if (this.channels.get(other) === ch) this.channels.delete(other); };
  }

  private onChannelMessage(other: string, ch: RTCDataChannel, data: unknown): void {
    if (typeof data === "string") {
      const msg = JSON.parse(data);
      if (msg.t === "want") {
        void this.serve(ch, msg.id);
      } else if (msg.t === "head") {
        this.incoming.set(other, { meta: msg.meta, chunks: [] });
      } else if (msg.t === "end") {
        const inc = this.incoming.get(other);
        this.incoming.delete(other);
        if (inc) {
          const blob = new Blob(inc.chunks, { type: inc.meta.mime });
          this.store.set(inc.meta.id, { blob, meta: inc.meta }); // re-seed
          this.onBlob(inc.meta.id, blob, inc.meta);
        }
      }
    } else if (data instanceof ArrayBuffer) {
      const inc = this.incoming.get(other);
      if (inc) inc.chunks.push(data);
    }
  }

  private async serve(ch: RTCDataChannel, id: string): Promise<void> {
    const rec = this.store.get(id);
    if (!rec || ch.readyState !== "open") return;
    ch.send(JSON.stringify({ t: "head", meta: rec.meta }));
    const buf = await rec.blob.arrayBuffer();
    for (let o = 0; o < buf.byteLength; o += CHUNK) {
      if (ch.bufferedAmount > BUFFER_LIMIT) await this.drain(ch);
      if (ch.readyState !== "open") return;
      ch.send(buf.slice(o, o + CHUNK));
    }
    ch.send(JSON.stringify({ t: "end", id }));
  }

  private drain(ch: RTCDataChannel): Promise<void> {
    return new Promise((resolve) => {
      const handler = () => { ch.removeEventListener("bufferedamountlow", handler); resolve(); };
      ch.addEventListener("bufferedamountlow", handler);
    });
  }

  private teardown(other: string): void {
    this.channels.get(other)?.close();
    this.peers.get(other)?.close();
    this.channels.delete(other);
    this.peers.delete(other);
    this.pendingIce.delete(other);
    this.incoming.delete(other);
  }
}
