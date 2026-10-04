import { useCallback, useEffect, useState } from "react";
import { createOcr, IMAGE_TYPES, MAX_BATCH_IMAGES, MAX_IMAGE_BYTES } from "../lib/ocr.js";
import BatchScan from "./BatchScan.jsx";

// OCR runs in the browser with Tesseract.js, so the image never leaves the device.
// One screenshot fills the form directly; several are read as a batch (BatchScan).
export default function UploadCard({ onParsed }) {
  const [preview, setPreview] = useState(null);
  const [message, setMessage] = useState("");
  const [progress, setProgress] = useState(0);
  const [chips, setChips] = useState({ found: [], missing: [] });
  const [drag, setDrag] = useState(false);
  const [batch, setBatch] = useState(null);   // File[] when several screenshots were chosen
  const [notice, setNotice] = useState("");

  useEffect(() => () => preview && URL.revokeObjectURL(preview), [preview]);

  const handleImage = useCallback(async (file) => {
    setBatch(null);
    setPreview(URL.createObjectURL(file));
    setChips({ found: [], missing: [] });
    setProgress(0);
    setMessage("Reading screenshot…");
    try {
      const ocr = await createOcr(setProgress);
      const parsed = await ocr.read(file);
      ocr.close();
      setProgress(100);
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

  // One file -> the usual single flow; several -> batch. Non-images and oversized files are skipped.
  const handleFiles = useCallback((list) => {
    const all = [...(list || [])];
    const ok = all.filter((f) => IMAGE_TYPES.test(f.type) && f.size <= MAX_IMAGE_BYTES).slice(0, MAX_BATCH_IMAGES);
    const dropped = all.length - ok.length;
    setNotice(dropped > 0
      ? `Skipped ${dropped} file${dropped > 1 ? "s" : ""}: only PNG, JPG or WebP images up to 10 MB, at most ${MAX_BATCH_IMAGES} at a time.`
      : "");
    if (ok.length === 1) handleImage(ok[0]);
    else if (ok.length > 1) {
      setPreview(null);
      setBatch(ok);
    }
  }, [handleImage]);

  useEffect(() => {
    const onPaste = (e) => {
      const files = [...(e.clipboardData?.items || [])].filter((i) => i.type.startsWith("image/")).map((i) => i.getAsFile());
      if (files.length) handleFiles(files);
    };
    document.addEventListener("paste", onPaste);
    return () => document.removeEventListener("paste", onPaste);
  }, [handleFiles]);

  const onDrop = (e) => {
    e.preventDefault();
    setDrag(false);
    handleFiles(e.dataTransfer.files);
  };
  const onDragOver = (e) => {
    e.preventDefault();
    setDrag(true);
  };

  // "Use in form" from a batch item: same as a single scan, then bring the form into view.
  const useOne = (parsed) => {
    onParsed(parsed);
    document.getElementById("amount")?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  return (
    <section className="sec">
      <div className="sec-head">
        <span className="sec-no">01</span>
        <h2>Payment screenshots</h2>
        <span className="label">Optional</span>
      </div>
      <p className="sub">
        Sent or received, one or several at once. We read the amount, time, transaction ID and the other person's
        name. Images are read on your device and never uploaded.
      </p>
      <div className={"drop" + (drag ? " drag" : "")} onDragEnter={onDragOver} onDragOver={onDragOver}
           onDragLeave={() => setDrag(false)} onDrop={onDrop}>
        <input type="file" accept="image/png,image/jpeg,image/webp" multiple aria-label="Choose payment screenshots"
               onChange={(e) => { handleFiles(e.target.files); e.target.value = ""; }} />
        <svg width="26" height="38" viewBox="0 0 26 38" fill="none" stroke="currentColor" strokeWidth="1.3" aria-hidden="true">
          <rect x="1" y="1" width="24" height="36" rx="3" />
          <path d="M6 9h14M6 14h9M6 22h14M6 26h14M6 30h8" />
        </svg>
        <div>
          <strong>Drop screenshots, click to choose, or paste with Ctrl+V</strong>
          <small>One or up to {MAX_BATCH_IMAGES} at once · GPay · PhonePe · Paytm · BHIM · bank apps — PNG, JPG or WebP</small>
        </div>
      </div>
      {notice && <p className="warn-note" role="status">{notice}</p>}
      {batch && <BatchScan key={batch.map((f) => f.name + f.size).join("|")} files={batch} onUse={useOne} onClose={() => setBatch(null)} />}
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
