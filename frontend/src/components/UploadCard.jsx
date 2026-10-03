import { useCallback, useEffect, useState } from "react";
import { parseUpiText } from "../lib/ocrParse.js";

// OCR runs in the browser with Tesseract.js, so the image never leaves the device.
export default function UploadCard({ onParsed }) {
  const [preview, setPreview] = useState(null);
  const [message, setMessage] = useState("");
  const [progress, setProgress] = useState(0);
  const [chips, setChips] = useState({ found: [], missing: [] });
  const [drag, setDrag] = useState(false);

  useEffect(() => () => preview && URL.revokeObjectURL(preview), [preview]);

  const handleImage = useCallback(async (file) => {
    setPreview(URL.createObjectURL(file));
    setChips({ found: [], missing: [] });
    setProgress(0);
    setMessage("Reading screenshot…");
    try {
      const { default: Tesseract } = await import("tesseract.js");
      const { data } = await Tesseract.recognize(file, "eng", {
        logger: (m) => m.status === "recognizing text" && setProgress(Math.round(m.progress * 100)),
      });
      setProgress(100);
      const result = onParsed(parseUpiText(data.text));
      setChips(result);
      setMessage(result.found.length
        ? "Done. Please check the highlighted fields and add your balance."
        : "Couldn't find payment details in this image. Please enter them by hand.");
    } catch (err) {
      console.error(err);
      setMessage("Could not read this image (the text reader needs internet). Please enter the details by hand.");
    }
  }, [onParsed]);

  useEffect(() => {
    const onPaste = (e) => {
      const item = [...(e.clipboardData?.items || [])].find((i) => i.type.startsWith("image/"));
      if (item) handleImage(item.getAsFile());
    };
    document.addEventListener("paste", onPaste);
    return () => document.removeEventListener("paste", onPaste);
  }, [handleImage]);

  const onDrop = (e) => {
    e.preventDefault();
    setDrag(false);
    const f = e.dataTransfer.files[0];
    if (f && f.type.startsWith("image/")) handleImage(f);
  };
  const onDragOver = (e) => {
    e.preventDefault();
    setDrag(true);
  };

  return (
    <section className="card">
      <h2>
        <span className="step">1</span> Upload a payment screenshot{" "}
        <span className="hint" style={{ fontWeight: 400, color: "var(--muted)", fontSize: 13 }}>(optional)</span>
      </h2>
      <p className="sub">
        From Google Pay, PhonePe, Paytm, BHIM or your bank app. We read the amount, time, transaction ID and payee. The
        image is read on your device and never uploaded.
      </p>
      <div className={"drop" + (drag ? " drag" : "")} onDragEnter={onDragOver} onDragOver={onDragOver}
           onDragLeave={() => setDrag(false)} onDrop={onDrop}>
        <input type="file" accept="image/*" onChange={(e) => e.target.files[0] && handleImage(e.target.files[0])} />
        <strong>Drop a screenshot here, click to choose, or paste (Ctrl+V)</strong>
        <small>PNG or JPG</small>
      </div>
      {preview && (
        <div className="preview show">
          <img src={preview} alt="Screenshot preview" />
          <div className="ocr-status">
            <div>{message}</div>
            <div className="progress"><div style={{ width: progress + "%" }} /></div>
            <div className="chips">
              {chips.found.map((f) => <span key={f} className="chip">✓ {f}</span>)}
              {chips.missing.map((f) => <span key={f} className="chip miss">Add: {f}</span>)}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
