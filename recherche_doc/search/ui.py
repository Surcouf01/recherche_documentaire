r"""Interface de recherche (plugin de l'explorateur Windows) :

- `SearchUI` : interface Tkinter fonctionnant à la fois en application
  autonome et en fenêtre compagnon déclenchée à l'ouverture du drive.
- `ExplorerSearchPane` : squelette du namespace COM (shell) à enregistrer
  comme plugin de l'explorateur Windows (interface IExplorerPane /
 à associer au CLSID du drive).
"""

import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional

from .engine import SearchEngine


class SearchUI:
    def __init__(self, engine: SearchEngine, on_select: Optional[Callable[[str], None]] = None):
        self.engine = engine
        self.on_select = on_select
        self.root = None
        self.visited_dir = None

    def set_visited_dir(self, path: str):
        """Dossier visité dans l'explorateur (argument %V) : pré-remplit les
        filtres à partir du répertoire (catégorie/tag si l'arborescence
        Categories/ est détectée)."""
        self.visited_dir = path

    def launch(self):
        self.root = tk.Tk()
        self.root.title("Recherche Documentaire")
        self.root.geometry("880x520")
        self._build(self.root)
        self.root.mainloop()

    def _build(self, parent):
        if self.visited_dir:
            self._prefill_from_visited()
        top = ttk.Frame(parent, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="Catégorie:").pack(side="left")
        self.cat_var = tk.StringVar()
        self.cat_combo = ttk.Combobox(top, textvariable=self.cat_var, width=16)
        self.cat_combo["values"] = [""] + self.engine.list_categories()
        self.cat_combo.pack(side="left", padx=4)

        ttk.Label(top, text="Tags (ex: personne, émetteur):").pack(side="left", padx=(12, 2))
        self.tags_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.tags_var, width=24).pack(side="left", padx=4)

        ttk.Label(top, text="Date (YYYYMM):").pack(side="left", padx=(12, 2))
        self.date_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.date_var, width=10).pack(side="left", padx=4)

        self.go_btn = ttk.Button(top, text="Rechercher", command=self._do_search)
        self.go_btn.pack(side="left", padx=8)

        self.keyword_var = tk.StringVar()
        kw = ttk.Frame(parent, padding=(8, 0, 8, 4))
        kw.pack(fill="x")
        ttk.Label(kw, text="Mot-clé:").pack(side="left")
        ttk.Entry(kw, textvariable=self.keyword_var, width=60).pack(side="left", padx=4)
        ttk.Button(kw, text="Recherche plein texte", command=self._do_fts).pack(side="left", padx=4)

        cols = ("fichier", "catégorie", "tags", "date")
        self.tree = ttk.Treeview(parent, columns=cols, show="headings", height=18)
        for c, w in zip(cols, (240, 120, 280, 80)):
            self.tree.heading(c, text=c.title())
            self.tree.column(c, width=w)
        self.tree.pack(fill="both", expand=True, padx=8, pady=8)
        self.tree.bind("<Double-1>", self._on_double)

        self.status = ttk.Label(parent, text="", anchor="w")
        self.status.pack(fill="x", padx=8, pady=(0, 8))

        pending_cat = getattr(self, "_pending_category", None)
        pending_tag = getattr(self, "_pending_tag", None)
        if pending_cat and pending_cat in self.cat_combo["values"]:
            self.cat_var.set(pending_cat)
        if pending_tag:
            self.tags_var.set(pending_tag)
        if pending_cat or pending_tag:
            self.root.after(50, self._do_search)

    def _prefill_from_visited(self):
        """Si %V pointe sous Categories/<Cat>/<Tag>/, pré-sélectionne."""
        from pathlib import Path
        try:
            p = Path(self.visited_dir)
            parts = p.parts
            if "Categories" in parts:
                i = parts.index("Categories")
                if len(parts) > i + 1:
                    self._pending_category = parts[i + 1]
                if len(parts) > i + 2:
                    self._pending_tag = parts[i + 2]
        except Exception:
            pass

    def _do_search(self):
        tags = [t.strip() for t in self.tags_var.get().split(",") if t.strip()]
        rows = self.engine.search(
            category=self.cat_var.get() or None,
            tags=tags or None,
            date=self.date_var.get() or None,
        )
        self._show(rows)

    def _do_fts(self):
        q = self.keyword_var.get().strip()
        if not q:
            self.status.config(text="Entrez un mot-clé.")
            return
        self._show(self.engine.search_fulltext(q))

    def _show(self, rows: List[dict]):
        self.tree.delete(*self.tree.get_children())
        for r in rows:
            self.tree.insert("", "end", values=(
                r["filename"], r["category"], ", ".join(r["tags"]), r["main_date"] or ""
            ))
        self.status.config(text=f"{len(rows)} résultat(s).")

    def _on_double(self, _event):
        sel = self.tree.selection()
        if sel and self.on_select:
            filename = self.tree.item(sel[0], "values")[0]
            self.on_select(filename)


class ExplorerSearchPane:
    r"""Squelette d'intégration en plugin de l'explorateur Windows.

    Enregistre une command shell (« Recherche Documentaire ») visible dans
    l'explorateur lorsque le drive sync root est visité. Voir registre :
    HKCU\\Software\\Classes\\Drive\\shell\\RechercheDocumentaire
    """

    CLSID = "{7F3A4B2C-1D5E-4F6A-8B9C-0A1B2C3D4E5F}"

    def __init__(self, engine: SearchEngine):
        self.engine = engine

    def register(self):
        import winreg
        key = winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            r"Software\Classes\Drive\shell\RechercheDocumentaire",
            0,
            winreg.KEY_SET_VALUE,
        )
        winreg.SetValueEx(key, None, 0, winreg.REG_SZ, "Recherche Documentaire...")
        cmd = winreg.CreateKeyEx(key, "command", 0, winreg.KEY_SET_VALUE)
        import sys
        winreg.SetValueEx(cmd, None, 0, winreg.REG_SZ,
                          f'"{sys.executable}" -m recherche_doc.search.explorer_hook')
        return True
