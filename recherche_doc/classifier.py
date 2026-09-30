"""Classification des documents par catégorie avec CamemBERT (et repli lexical)."""

import os
import re
from typing import List, Optional, Tuple

from . import CATEGORIES, CATEGORY_SYNONYMS

_MODEL_NAME = os.environ.get("DOC_CLASSIFIER_MODEL", "camembert-base")
_MAX_TEXT = 4000


class DocumentClassifier:
    """Classifieur de catégorie basé sur CamemBERT.

    CamemBERT n'étant pas nativement un classifieur de catégories métier, la
    variante retenue est fine-tunable : on fournit `model_path` pointant vers
    un modèle fine-tuné (CamembertForSequenceClassification). En son absence,
    le texte est linéarisé via le pipeline et un repli lexical pondéré par les
    synonymes de catégories est utilisé (heuristique déterministe).
    """

    def __init__(self, model_path: Optional[str] = None, device: str = "cpu"):
        self.model_path = model_path
        self.device = device
        self._tokenizer = None
        self._model = None
        if model_path:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            self._tokenizer = AutoTokenizer.from_pretrained(model_path)
            self._model = AutoModelForSequenceClassification.from_pretrained(model_path)
            self._model.to(device)
            self._model.eval()
            self._labels = (
                list(self._model.config.id2label.values())
                if getattr(self._model.config, "id2label", None)
                else CATEGORIES
            )

    def classify(self, text: str) -> Tuple[str, float]:
        text = (text or "")[:_MAX_TEXT]
        if self._model is not None:
            return self._classify_model(text)
        return self._classify_lexical(text)

    def _classify_model(self, text: str) -> Tuple[str, float]:
        import torch

        inputs = self._tokenizer(
            text, return_tensors="pt", truncation=True, max_length=512
        ).to(self.device)
        with torch.no_grad():
            logits = self._model(**inputs).logits
        probs = torch.softmax(logits, dim=-1)[0]
        idx = int(probs.argmax())
        label = self._labels[idx]
        label = re.sub(r"^(LABEL_|_)[0-9_]+", "", label).strip() or "Autre"
        return label, float(probs[idx])

    def _classify_lexical(self, text: str) -> Tuple[str, float]:
        t = text.lower()
        scores = {c: 0.0 for c in CATEGORIES}
        for cat, words in CATEGORY_SYNONYMS.items():
            for w in words:
                n = len(re.findall(re.escape(w), t))
                if n:
                    scores[cat] += 1.0 + 0.1 * min(n, 10)
        best = max(scores, key=lambda c: scores[c])
        if scores[best] == 0.0:
            return "Autre", 0.5
        total = sum(scores.values())
        return best, round(scores[best] / total, 3)

    def classify_batch(self, texts: List[str]) -> List[Tuple[str, float]]:
        return [self.classify(t) for t in texts]
