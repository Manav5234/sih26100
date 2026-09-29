"""Page OCR — PaddleOCR when its runtime is available, else PP-OCR via ONNX.

Both engines read the same PP-OCR models; only the runtime differs. Which one
actually ran is returned as `engine` and recorded on the document so the demo
never claims an engine it did not use.
"""
from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)

_ocr = None
_engine_name: str | None = None


def _load():
    """Load an OCR engine once, lazily. Paddle first, ONNX fallback."""
    global _ocr, _engine_name
    if _ocr is not None:
        return _ocr, _engine_name

    try:
        from paddleocr import PaddleOCR  # type: ignore

        _ocr = _PaddleWrapper(PaddleOCR())
        _engine_name = "paddleocr"
    except Exception as exc:  # paddlepaddle has no wheel on this Python — fall back
        logger.info("paddleocr_unavailable: %s", exc)
        try:
            from rapidocr_onnxruntime import RapidOCR

            _ocr = RapidOCR()
            _engine_name = "rapidocr_ppocr"
        except Exception as exc2:
            logger.info("rapidocr_unavailable: %s", exc2)
            _ocr = None
            _engine_name = "ocr_disabled"
    return _ocr, _engine_name


class _PaddleWrapper:
    """Normalises PaddleOCR 2.x/3.x result shapes into (text, confidence) pairs."""

    def __init__(self, ocr) -> None:
        self._ocr = ocr

    def __call__(self, img: np.ndarray):
        try:
            result = self._ocr.predict(input=img)
            if result:
                r = result[0]
                texts = r.get("rec_texts", [])
                scores = r.get("rec_scores", [])
                return list(zip(texts, scores))
        except Exception:
            pass
        # PaddleOCR 2.x shape: [[ [box, (text, conf)], ... ]]
        raw = self._ocr.ocr(img, cls=True)
        out = []
        for line in raw or []:
            for item in line or []:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    box, (text, conf) = item
                    out.append((text, conf))
        return out


def ocr_image(img: np.ndarray) -> tuple[str, float, str]:
    """OCR a colour image (RGB). Returns (text, mean_confidence, engine_name)."""
    engine, engine_name = _load()
    if engine is None:
        return "", 0.0, engine_name or "ocr_disabled"
    pairs: list[tuple[str, float]] = []

    if engine_name == "rapidocr_ppocr":
        # RapidOCR expects BGR, OpenCV convention.
        result, _ = engine(np.ascontiguousarray(img[:, :, ::-1]))
        for entry in result or []:
            if isinstance(entry, (list, tuple)) and len(entry) == 3:
                _box, text, conf = entry
                pairs.append((text, float(conf)))
    else:
        pairs = list(engine(img))

    text = "\n".join(t for t, _c in pairs) if pairs else ""
    conf = float(np.mean([c for _t, c in pairs])) if pairs else 0.0
    return text, conf, engine_name or "unknown"
