"""Source page rendering for the review screen.

The left half of the review screen is the extracted table; the right half is the source page
with the cited region highlighted. That pairing is what makes a quantity checkable, so this
module is the practical expression of guardrail 2 -- every value reproducible from its cited
page region.

A ``bbox`` is stored in rendered-page coordinates (``words_from_pdf`` applies page rotation),
so a highlight drawn from it lands where the engineer is looking.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEFAULT_DPI = 110
HIGHLIGHT_PAD = 6.0


class RenderError(Exception):
    """Raised when a source region cannot be rendered."""


@dataclass(frozen=True, slots=True)
class RenderedRegion:
    """A rasterised source page plus where the highlight landed on it."""

    png: bytes
    page_width: float
    page_height: float
    scale: float
    highlight: tuple[float, float, float, float] | None

    @property
    def highlight_css(self) -> dict[str, float] | None:
        """Highlight box in rendered-image pixels, for absolute positioning in HTML."""
        if self.highlight is None:
            return None
        x0, y0, x1, y1 = self.highlight
        return {
            "left": x0 * self.scale,
            "top": y0 * self.scale,
            "width": max(x1 - x0, 1.0) * self.scale,
            "height": max(y1 - y0, 1.0) * self.scale,
        }


def render_source(
    source,
    *,
    search_dirs: list[Path] | None = None,
    dpi: int = DEFAULT_DPI,
    draw_box: bool = True,
) -> RenderedRegion:
    """Render the page a :class:`~boq.normalize.items.Source` cites, highlighting its bbox.

    ``search_dirs`` is where the original drawing files live. They are deliberately not kept
    in the repository, so the caller supplies the location.
    """
    if source.file_type not in (None, "pdf"):
        raise RenderError(
            f"{source.file} is a {source.file_type} source; only PDF pages can be rendered"
        )
    if source.page is None:
        raise RenderError(f"{source.file} has no page number to render")

    path = _resolve(source.file, search_dirs or [])
    if path is None:
        raise RenderError(
            f"{source.file} was not found. Drawing files are not kept in the repository; "
            f"point the review server at the project folder that holds them."
        )

    import pymupdf

    with pymupdf.open(path) as doc:
        index = source.page - 1
        if not 0 <= index < len(doc):
            raise RenderError(
                f"{source.file} has {len(doc)} pages; page {source.page} does not exist"
            )
        page = doc[index]
        scale = dpi / 72.0

        box = None
        if source.bbox:
            x0, y0, x1, y1 = source.bbox
            box = (
                max(x0 - HIGHLIGHT_PAD, 0.0),
                max(y0 - HIGHLIGHT_PAD, 0.0),
                min(x1 + HIGHLIGHT_PAD, page.rect.width),
                min(y1 + HIGHLIGHT_PAD, page.rect.height),
            )
            if draw_box:
                # Annotations are placed in *unrotated* page coordinates, while a stored
                # bbox is in rendered (rotated) space. Without derotating, the highlight is
                # drawn off-page on any /Rotate sheet -- silently, since nothing errors.
                rect = pymupdf.Rect(*box) * page.derotation_matrix
                annot = page.add_rect_annot(rect)
                annot.set_colors(stroke=(0.85, 0.15, 0.15))
                annot.set_border(width=2.0)
                annot.update(opacity=0.9)

        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale))
        return RenderedRegion(
            png=pixmap.tobytes("png"),
            page_width=page.rect.width,
            page_height=page.rect.height,
            scale=scale,
            highlight=box,
        )


def _resolve(filename: str, search_dirs: list[Path]) -> Path | None:
    """Find a drawing file by name in the configured directories."""
    name = Path(filename).name
    for directory in search_dirs:
        candidate = Path(directory) / name
        if candidate.is_file():
            return candidate
        matches = sorted(Path(directory).glob(f"**/{name}"))
        if matches:
            return matches[0]
    return None


def can_render(source, search_dirs: list[Path] | None = None) -> bool:
    """Whether a source could be shown, without actually rendering it."""
    if source.file_type not in (None, "pdf") or source.page is None:
        return False
    return _resolve(source.file, search_dirs or []) is not None
