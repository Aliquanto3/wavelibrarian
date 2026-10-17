"""Génère les PDF du Mini-corpus à partir de leurs sources texte (fpdf2).

Usage : `uv run python scripts/make_minicorpus_pdfs.py`

Sources : `corpora/minicorpus/pdf-src/<nom>.txt` ; sortie : `corpora/minicorpus/docs/<nom>.pdf`.
Format d'une source : `# titre`, `## sous-titre`, paragraphes séparés par une ligne vide, une ligne
`<<page>>` force un saut de page. Une source sans `#` donne un PDF sans titre.

La police DejaVu Sans (licence libre, voir `scripts/fonts/DejaVu-LICENSE.txt`) est commitée, car les
polices intégrées de fpdf2 se limitent au latin-1 : « œ », « » et les tirets typographiques y
manqueraient. La date de création est fixée pour que la sortie soit reproductible.
"""

from datetime import UTC, datetime
from pathlib import Path

from fpdf import FPDF

RACINE = Path(__file__).resolve().parent.parent
SOURCES = RACINE / "corpora" / "minicorpus" / "pdf-src"
SORTIE = RACINE / "corpora" / "minicorpus" / "docs"
POLICES = Path(__file__).resolve().parent / "fonts"
SAUT_DE_PAGE = "<<page>>"
DATE_FIXE = datetime(2026, 10, 18, tzinfo=UTC)


def rendre(source: str) -> bytes:
    """PDF (octets) d'un texte source."""
    pdf = FPDF(format="A4")
    pdf.set_creation_date(DATE_FIXE)
    pdf.set_title("")
    pdf.add_font("DejaVu", "", str(POLICES / "DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", str(POLICES / "DejaVuSans-Bold.ttf"))
    pdf.set_margins(20, 20, 20)
    pdf.set_auto_page_break(True, margin=20)
    pdf.add_page()
    for bloc in source.strip().split("\n\n"):
        bloc = bloc.strip()
        if bloc == SAUT_DE_PAGE:
            pdf.add_page()
        elif bloc.startswith("## "):
            pdf.set_font("DejaVu", "B", 12)
            pdf.multi_cell(0, 7, bloc[3:], new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)
        elif bloc.startswith("# "):
            pdf.set_font("DejaVu", "B", 17)
            pdf.multi_cell(0, 9, bloc[2:], new_x="LMARGIN", new_y="NEXT")
            pdf.ln(3)
        else:
            pdf.set_font("DejaVu", "", 11)
            pdf.multi_cell(0, 6, bloc, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(3)
    return bytes(pdf.output())


def texte_attendu(source: str) -> str:
    """Texte que `pdf_text` doit retrouver : la source sans marqueurs, sans espaces."""
    lignes = [
        ligne.removeprefix("## ").removeprefix("# ")
        for ligne in source.splitlines()
        if ligne.strip() != SAUT_DE_PAGE
    ]
    return "".join("".join(lignes).split())


def main() -> None:
    SORTIE.mkdir(parents=True, exist_ok=True)
    for src in sorted(SOURCES.glob("*.txt")):
        cible = SORTIE / f"{src.stem}.pdf"
        cible.write_bytes(rendre(src.read_text(encoding="utf-8")))
        print(f"{src.name} -> {cible.name}")


if __name__ == "__main__":
    main()
