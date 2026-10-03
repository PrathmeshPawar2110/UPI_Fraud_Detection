import { useEffect, useRef, useState } from "react";

const MAX_BYTES = 10 * 1024 * 1024;
const MAX_SIDE = 1600;

async function decode(source, width, height) {
  const { default: jsQR } = await import("jsqr");
  const scale = Math.min(1, MAX_SIDE / Math.max(width, height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(width * scale);
  canvas.height = Math.round(height * scale);
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(source, 0, 0, canvas.width, canvas.height);
  const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
  return jsQR(img.data, img.width, img.height, { inversionAttempts: "attemptBoth" })?.data || null;
}

/** Decodes a QR in the browser (image upload or camera). Only the decoded text leaves the device. */
export default function QrScanner({ onDecoded }) {
  const [message, setMessage] = useState("");
  const [camera, setCamera] = useState(false);
  const videoRef = useRef(null);
  const streamRef = useRef(null);

  useEffect(() => () => stopCamera(), []);

  async function fromFile(file) {
    if (!file) return;
    if (!/^image\/(png|jpe?g|webp|gif|bmp)$/.test(file.type)) return setMessage("Please choose a PNG, JPG or WebP image.");
    if (file.size > MAX_BYTES) return setMessage("That image is too large (max 10 MB).");
    setMessage("Reading QR…");
    const url = URL.createObjectURL(file);
    try {
      const img = new Image();
      img.src = url;
      await img.decode();
      const text = await decode(img, img.naturalWidth, img.naturalHeight);
      if (text) { setMessage(""); onDecoded(text); }
      else setMessage("No QR code found. Try a sharper, closer image.");
    } catch {
      setMessage("Couldn't read this image.");
    } finally {
      URL.revokeObjectURL(url);
    }
  }

  async function startCamera() {
    if (!navigator.mediaDevices?.getUserMedia) return setMessage("Camera scanning isn't available in this browser. Upload a photo instead.");
    if (!window.isSecureContext) return setMessage("Camera scanning needs HTTPS. Upload a photo instead.");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
      streamRef.current = stream;
      setCamera(true);
      setMessage("Point the camera at the QR code.");
      requestAnimationFrame(() => {
        const v = videoRef.current;
        if (!v) return;
        v.srcObject = stream;
        v.play();
        tick();
      });
    } catch {
      setMessage("Camera permission was denied. Upload a photo instead.");
    }
  }

  async function tick() {
    const v = videoRef.current;
    if (!streamRef.current || !v) return;
    if (v.readyState >= 2 && v.videoWidth) {
      const text = await decode(v, v.videoWidth, v.videoHeight).catch(() => null);
      if (text) {
        stopCamera();
        setMessage("");
        onDecoded(text);
        return;
      }
    }
    setTimeout(() => requestAnimationFrame(tick), 250);
  }

  function stopCamera() {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setCamera(false);
  }

  return (
    <div className="qr-scanner">
      <div className="drop small-drop">
        <input type="file" accept="image/png,image/jpeg,image/webp" aria-label="Choose a QR image"
               onChange={(e) => fromFile(e.target.files[0])} />
        <strong>Upload a photo or screenshot of the QR</strong>
        <small>PNG, JPG or WebP · decoded on your device</small>
      </div>
      <div className="row-actions">
        {camera ? <button type="button" className="ghost" onClick={stopCamera}>Stop camera</button>
          : <button type="button" className="ghost" onClick={startCamera}>Scan with camera</button>}
      </div>
      {camera && <video ref={videoRef} className="qr-video" muted playsInline aria-label="Camera preview" />}
      {message && <p className="note" role="status">{message}</p>}
    </div>
  );
}
