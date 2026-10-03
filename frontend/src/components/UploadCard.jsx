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
      const worker = await Tesseract.createWorker("eng", 1, {
        logger: (m) => m.status === "recognizing text" && setProgress(Math.round(m.progress * 100)),
      });
      // Sparse-text mode finds the big headline amount, which the default page layout often drops.
      await worker.setParameters({ tessedit_pageseg_mode: Tesseract.PSM.SPARSE_TEXT });
      const { data } = await worker.recognize(file);
      await worker.terminate();
      setProgress(100);
      const words = (data.words || []).map((w) => ({ text: w.text, h: w.bbox.y1 - w.bbox.y0 }));
      const parsed = parseUpiText(data.text, words);
      const result = onParsed(parsed);
      setChips(result);
      const what = [parsed.app && `${parsed.app} receipt`, parsed.direction && `money ${parsed.direction}`]
        .filter(Boolean).join(", ");
      setMessage(result.found.length
        ? `Read ${what || "the screenshot"}. Check the outlined fields and fill in the rest.`
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
    <section className="sec">
      <div className="sec-head">
        <span className="sec-no">01</span>
        <h2>Payment screenshot</h2>
        <span className="label">Optional</span>
      </div>
      <p className="sub">
        Sent or received. We read the amount, time, transaction ID and the other person's name. The image is read on
        your device and never uploaded.
      </p>
      <div className={"drop" + (drag ? " drag" : "")} onDragEnter={onDragOver} onDragOver={onDragOver}
           onDragLeave={() => setDrag(false)} onDrop={onDrop}>
        <input type="file" accept="image/*" aria-label="Choose a payment screenshot"
               onChange={(e) => e.target.files[0] && handleImage(e.target.files[0])} />
        <svg width="26" height="38" viewBox="0 0 26 38" fill="none" stroke="currentColor" strokeWidth="1.3" aria-hidden="true">
          <rect x="1" y="1" width="24" height="36" rx="3" />
          <path d="M6 9h14M6 14h9M6 22h14M6 26h14M6 30h8" />
        </svg>
        <div>
          <strong>Drop a screenshot, click to choose, or paste with Ctrl+V</strong>
          <small>GPay · PhonePe · Paytm · BHIM · bank apps — PNG or JPG</small>
        </div>
      </div>
      {preview && (
        <div className="preview" aria-live="polite">
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
