// Browser-side OCR (Tesseract.js). Images never leave the device; only the parsed fields are used.
import { parseUpiText } from "./ocrParse.js";

/**
 * One OCR engine, reusable for several images (loading it is the slow part).
 * `onProgress(0..100)` reports recognition progress of the image currently being read.
 */
export async function createOcr(onProgress) {
  const { default: Tesseract } = await import("tesseract.js");
  let report = onProgress;
  const worker = await Tesseract.createWorker("eng", 1, {
    logger: (m) => m.status === "recognizing text" && report?.(Math.round(m.progress * 100)),
  });
  // Sparse-text mode finds the big headline amount, which the default page layout often drops.
  await worker.setParameters({ tessedit_pageseg_mode: Tesseract.PSM.SPARSE_TEXT });
  return {
    async read(file, progress) {
      if (progress) report = progress;
      const { data } = await worker.recognize(file);
      const words = (data.words || []).map((w) => ({ text: w.text, h: w.bbox.y1 - w.bbox.y0 }));
      return parseUpiText(data.text, words);
    },
    close: () => worker.terminate(),
  };
}

export const IMAGE_TYPES = /^image\/(png|jpe?g|webp|gif|bmp)$/;
export const MAX_IMAGE_BYTES = 10 * 1024 * 1024;
export const MAX_BATCH_IMAGES = 20;
