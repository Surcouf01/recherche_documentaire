"""Outil de référencement documentaire « Recherche Documentaire »."""

__version__ = "0.1.0"

CATEGORIES = [
    "Facture",
    "Philosophie",
    "Religion",
    "Photo",
    "Video",
    "Ordonnance",
    "Resultat",
    "Autre",
]

CATEGORY_SYNONYMS = {
    "Facture": ["facture", "invoice", "paiement", "montant total", "tva", "ht", "réglée", "reglee"],
    "Philosophie": ["philosophie", "philosophique", "kant", "platon", "descartes", "nietzsche", "métaphysique"],
    "Religion": ["religion", "liturgie", "église", "eglise", "prière", "priere", "homélie", "homelie", "catéchisme", "catechisme"],
    "Photo": ["photo", "photographie", "image", "jpeg", "jpg", "png", "appareil"],
    "Video": ["vidéo", "video", "film", "mp4", "mov", "montage"],
    "Ordonnance": ["ordonnance", "prescription", "médecin", "medecin", "docteur", "posologie", "mg", "comprimés"],
    "Resultat": ["résultat", "resultat", "laboratoire", "concours", "analyse", "taux", "g/l", "ui/l"],
}

TAG_RULES = {
    "recipient": [r"\b(?:destinataire|pour|adress[ée]e? à|madame|monsieur|mme|m\.)\s+([A-ZÉÈÀÂ][\wéèàâêîôûç-]+)",],
    "emetteur": [r"\b(?:de|par|émetteur|docteur|dr)\.?\s+([A-ZÉÈÀÂ][\wéèàâêîôûç-]+)",],
}
