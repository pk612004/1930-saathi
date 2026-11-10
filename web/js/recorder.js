// Push-to-talk WAV recorder. Prisma's REST API accepts WAV (not WebM), 8-44.1 kHz,
// so we capture raw PCM and encode 16-bit mono WAV in the browser.
// "Phone line" mode downsamples to 8 kHz to match real telephone audio.
class WavRecorder {
  constructor() { this.ctx = null; this.stream = null; this.node = null; this.chunks = []; this.recording = false; }

  async start() {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: false, autoGainControl: true }
    });
    this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    const src = this.ctx.createMediaStreamSource(this.stream);
    this.node = this.ctx.createScriptProcessor(4096, 1, 1);
    this.chunks = [];
    this.node.onaudioprocess = e => { if (this.recording) this.chunks.push(new Float32Array(e.inputBuffer.getChannelData(0))); };
    src.connect(this.node); this.node.connect(this.ctx.destination);
    this.recording = true;
  }

  async stop(targetRate = 16000) {
    this.recording = false;
    const inRate = this.ctx ? this.ctx.sampleRate : 48000;
    if (this.node) this.node.disconnect();
    if (this.stream) this.stream.getTracks().forEach(t => t.stop());
    if (this.ctx) await this.ctx.close();
    let len = this.chunks.reduce((n, c) => n + c.length, 0);
    const all = new Float32Array(len); let o = 0;
    for (const c of this.chunks) { all.set(c, o); o += c.length; }
    const pcm = WavRecorder.downsample(all, inRate, targetRate);
    return { b64: WavRecorder.toBase64(WavRecorder.encodeWav(pcm, targetRate)), seconds: pcm.length / targetRate };
  }

  static downsample(buf, inRate, outRate) {
    if (outRate >= inRate) return buf;
    const ratio = inRate / outRate, out = new Float32Array(Math.floor(buf.length / ratio));
    for (let i = 0; i < out.length; i++) {           // box-filter average = cheap anti-aliasing
      const s = Math.floor(i * ratio), e = Math.min(buf.length, Math.floor((i + 1) * ratio));
      let sum = 0; for (let j = s; j < e; j++) sum += buf[j];
      out[i] = sum / Math.max(1, e - s);
    }
    return out;
  }

  static encodeWav(samples, rate) {
    const buf = new ArrayBuffer(44 + samples.length * 2), v = new DataView(buf);
    const w = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
    w(0, 'RIFF'); v.setUint32(4, 36 + samples.length * 2, true); w(8, 'WAVE'); w(12, 'fmt ');
    v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
    v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
    w(36, 'data'); v.setUint32(40, samples.length * 2, true);
    for (let i = 0; i < samples.length; i++) {
      const s = Math.max(-1, Math.min(1, samples[i]));
      v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }
    return buf;
  }

  static toBase64(buf) {
    const bytes = new Uint8Array(buf); let bin = '';
    for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    return btoa(bin);
  }
}
