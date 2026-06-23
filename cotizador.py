import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.font import Font as _TkFont
import json
import os
import math
import xml.etree.ElementTree as ET
import threading

try:
    from svgpathtools import parse_path
    HAS_SVG = True
except ImportError:
    HAS_SVG = False

# ---------------------------------------------------------------------------
# Rounded-corner widget helpers
# ---------------------------------------------------------------------------
def _rr_pts(x1, y1, x2, y2, r):
    """Polygon points for a smooth rounded rectangle."""
    return [x1+r,y1, x2-r,y1, x2,y1, x2,y1+r,
            x2,y2-r, x2,y2, x2-r,y2, x1+r,y2,
            x1,y2, x1,y2-r, x1,y1+r, x1,y1]

def _hex_mix(color, amount=25):
    """Lighten a hex color by adding `amount` to each channel."""
    c = color.lstrip("#")
    r = min(255, int(c[0:2], 16) + amount)
    g = min(255, int(c[2:4], 16) + amount)
    b = min(255, int(c[4:6], 16) + amount)
    return f"#{r:02x}{g:02x}{b:02x}"


class RoundedButton(tk.Canvas):
    """A flat, rounded-corner button drawn on a Canvas."""
    RADIUS = 9

    def __init__(self, parent, text, bg, fg, command=None,
                 parent_bg=None, font=("Segoe UI", 9, "bold"),
                 padx=14, pady=6, cursor="hand2", **kw):
        self._bg  = bg
        self._fg  = fg
        self._cmd = command
        self._enabled = True

        fnt = _TkFont(family=font[0], size=font[1],
                      weight=font[2] if len(font) > 2 else "normal")
        cw = fnt.measure(text) + padx * 2
        ch = fnt.metrics("linespace") + pady * 2

        pbg = parent_bg or self._parent_bg(parent)
        super().__init__(parent, width=cw, height=ch,
                         bg=pbg, highlightthickness=0, bd=0, cursor=cursor, **kw)

        r = min(self.RADIUS, ch // 2)
        self._shape = self.create_polygon(
            _rr_pts(0, 0, cw, ch, r), smooth=True, fill=bg, outline="")
        self._tid = self.create_text(
            cw // 2, ch // 2, text=text, fill=fg, font=font, anchor="center")

        # Bind only on the canvas level to avoid double-firing through item propagation
        self.bind("<Button-1>",  self._click)
        self.bind("<Enter>",     self._enter)
        self.bind("<Leave>",     self._leave)
        self.bind("<Configure>", self._on_resize)
        self._ch = ch

    def _on_resize(self, e):
        cw, ch = e.width, self._ch
        r = min(self.RADIUS, ch // 2)
        self.coords(self._shape, _rr_pts(0, 0, cw, ch, r))
        self.coords(self._tid, cw // 2, ch // 2)

    @staticmethod
    def _parent_bg(w):
        try:
            return w.cget("bg")
        except Exception:
            return "#f5f5f5"

    def _click(self, _e=None):
        if self._enabled and self._cmd:
            self._cmd()

    def _enter(self, _e=None):
        if self._enabled:
            self.itemconfig(self._shape, fill=_hex_mix(self._bg, 20))

    def _leave(self, _e=None):
        self.itemconfig(self._shape,
                        fill="#aaaaaa" if not self._enabled else self._bg)

    def config(self, **kw):
        if "state" in kw:
            self._enabled = kw.pop("state") != "disabled"
            self.itemconfig(self._shape,
                            fill="#aaaaaa" if not self._enabled else self._bg)
        if "text" in kw:
            self.itemconfig(self._tid, text=kw.pop("text"))
        if kw:
            super().config(**kw)

    configure = config


class RoundedEntry(tk.Canvas):
    """An Entry field with a rounded-corner border."""
    RADIUS = 6

    def __init__(self, parent, textvariable=None, bg="#e8e8e8", fg="#1a1a1a",
                 parent_bg=None, font=("Segoe UI", 10), width=15,
                 insertbackground=None, state="normal", **kw):
        fnt = _TkFont(family=font[0], size=font[1])
        cw = fnt.measure("0") * width + 14
        ch = fnt.metrics("linespace") + 14

        pbg = parent_bg or self._parent_bg(parent)
        super().__init__(parent, width=cw, height=ch,
                         bg=pbg, highlightthickness=0, bd=0)

        r = min(self.RADIUS, ch // 2)
        self.create_polygon(_rr_pts(0, 0, cw, ch, r),
                            smooth=True, fill=bg, outline="")

        self._entry = tk.Entry(
            self, textvariable=textvariable, bg=bg, fg=fg,
            relief="flat", bd=0, font=font, width=width,
            insertbackground=insertbackground or fg,
            state=state, **kw)
        self.create_window(cw // 2, ch // 2, window=self._entry)

    @staticmethod
    def _parent_bg(w):
        try:
            return w.cget("bg")
        except Exception:
            return "#f5f5f5"

    # proxy common Entry methods
    def get(self):            return self._entry.get()
    def insert(self, *a):    self._entry.insert(*a)
    def delete(self, *a):    self._entry.delete(*a)
    def bind(self, *a, **k): return self._entry.bind(*a, **k)


class RoundedText(tk.Canvas):
    """A Text widget with a rounded-corner border."""
    RADIUS = 6

    def __init__(self, parent, bg="#e8e8e8", fg="#1a1a1a",
                 parent_bg=None, font=("Segoe UI", 9),
                 width=26, height=4, **kw):
        fnt = _TkFont(family=font[0], size=font[1])
        cw = fnt.measure("0") * width + 14
        lh = fnt.metrics("linespace")
        ch = lh * height + 14

        pbg = parent_bg or self._parent_bg(parent)
        super().__init__(parent, width=cw, height=ch,
                         bg=pbg, highlightthickness=0, bd=0)

        r = min(self.RADIUS, 14)
        self.create_polygon(_rr_pts(0, 0, cw, ch, r),
                            smooth=True, fill=bg, outline="")

        self._text = tk.Text(
            self, bg=bg, fg=fg, relief="flat", bd=0,
            font=font, width=width, height=height,
            insertbackground=fg, wrap="word",
            padx=6, pady=6, **kw)
        self.create_window(cw // 2, ch // 2, window=self._text)

    @staticmethod
    def _parent_bg(w):
        try:
            return w.cget("bg")
        except Exception:
            return "#f5f5f5"

    def get(self, *a):        return self._text.get(*a)
    def insert(self, *a):    self._text.insert(*a)
    def delete(self, *a):    self._text.delete(*a)
    def bind(self, *a, **k): return self._text.bind(*a, **k)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# When frozen by PyInstaller --onefile, sys.executable is the actual .exe path;
# __file__ would point to the temp extraction folder (_MEIPASS) which is deleted on exit.
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

DEFAULT_CONFIG = {
    "precios": {
        "acrilico_lamina":    1924,
        "aluminio_lamina":    2450,
        "mano_obra_letra":     700,
        "led_rollo":           362,
        "pvc6_lamina":           0,
        "pvc2_lamina":           0,
        "instalacion":           0,
        "fee_asociado":          0,
        "vinil_unit":          100,   # por unidad 120×60
        "vinil_transfer_extra":  60,  # extra si es con transfer
        "esparragos_unit":      3.66, # Espárrago (4 por letra)
        "snaps_unit":          10.00, # Snaps (4 por letra)
        "tubo_roscado_unit":   15.00, # Tubo roscado 10cm (4 por letra)
    },
    "papel_plantilla": {
        "ancho_cm": 120,
        "alto_cm":   60,
        "precio":    15,
    },
    "basicos": [],
    "folio":   6000,   # auto-increments with each PDF export
    "empresa": {
        "nombre":    "Anuncios Luminosos LB",
        "director":  "Ricardo Lobo Sáenz",
        "cargo":     "Director general",
        "tel":       "59906035",
        "email":     "rlobo2515@gmail.com",
        "domicilio": "Romulo O Farril 434 bodega 30, Colonia Olivar de Los Padres, 01780 México, CDMX",
        "logo":      "",   # ruta a imagen del logo (png/jpg)
        "vigencia_dias": 30,
        "iva_pct":   16.0,
        "isr_pct":    1.25,
    },
    "fuentes": [
        {"watts": 15,  "precio": 197},
        {"watts": 35,  "precio": 450},
        {"watts": 60,  "precio": 636},
        {"watts": 100, "precio": 711},
        {"watts": 150, "precio": 964},
    ],
}

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(json.dumps(DEFAULT_CONFIG))


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# SVG parser
# ---------------------------------------------------------------------------
def _strip_ns(tag):
    return tag.split("}")[-1] if "}" in tag else tag


def _iter_tag(elem, tag):
    for child in elem.iter():
        if _strip_ns(child.tag) == tag:
            yield child


def parse_svg(filepath):
    """
    Returns:
        svg_width_px  : float
        letters       : list of {"name", "perimeter_px", "bbox_px": (x,y,w,h)}
    """
    tree = ET.parse(filepath)
    root = tree.getroot()

    # SVG dimensions
    vb = root.get("viewBox", "")
    svg_w, svg_h = 0.0, 0.0
    if vb:
        parts = vb.split()
        svg_w, svg_h = float(parts[2]), float(parts[3])
    else:
        raw_w = root.get("width", "0").replace("px", "").replace("pt", "").strip()
        raw_h = root.get("height", "0").replace("px", "").replace("pt", "").strip()
        svg_w = float(raw_w) if raw_w else 0
        svg_h = float(raw_h) if raw_h else 0

    # Top-level <g> elements = Illustrator layers = letters
    letters = []
    top_groups = [c for c in root if _strip_ns(c.tag) == "g"]

    # Fallback: if SVG has no top-level <g> groups, treat root itself as one group
    if not top_groups:
        top_groups = [root]

    for group in top_groups:
        name = group.get("id", "?")
        # prefer <title> if present
        title_elem = next(_iter_tag(group, "title"), None)
        if title_elem is not None and title_elem.text:
            name = title_elem.text.strip()

        total_len = 0.0
        xs, ys = [], []
        shapes = []   # for rendering: {"type": "path"|"rect"|"poly", ...}

        # <path> elements
        for pe in _iter_tag(group, "path"):
            d = pe.get("d", "").strip()
            if not d:
                continue
            try:
                p = parse_path(d)
                total_len += p.length(error=1e-4)
                bb = p.bbox()
                xs += [bb[0], bb[1]]
                ys += [bb[2], bb[3]]
                shapes.append({"type": "path", "d": d})
            except Exception:
                pass

        # <rect> elements
        for re_ in _iter_tag(group, "rect"):
            try:
                rx = float(re_.get("x", 0))
                ry = float(re_.get("y", 0))
                rw = float(re_.get("width", 0))
                rh = float(re_.get("height", 0))
                if rw > 0 and rh > 0:
                    total_len += 2 * (rw + rh)
                    xs += [rx, rx + rw]
                    ys += [ry, ry + rh]
                    shapes.append({"type": "rect", "x": rx, "y": ry, "w": rw, "h": rh})
            except Exception:
                pass

        # <circle> elements
        for ce in _iter_tag(group, "circle"):
            try:
                cx = float(ce.get("cx", 0))
                cy = float(ce.get("cy", 0))
                cr = float(ce.get("r", 0))
                if cr > 0:
                    total_len += 2 * math.pi * cr
                    xs += [cx - cr, cx + cr]
                    ys += [cy - cr, cy + cr]
                    shapes.append({"type": "circle", "cx": cx, "cy": cy, "r": cr})
            except Exception:
                pass

        # <ellipse> elements
        for ee in _iter_tag(group, "ellipse"):
            try:
                cx = float(ee.get("cx", 0))
                cy = float(ee.get("cy", 0))
                a = float(ee.get("rx", 0))
                b = float(ee.get("ry", 0))
                if a > 0 and b > 0:
                    perim = math.pi * (3*(a+b) - math.sqrt((3*a+b)*(a+3*b)))
                    total_len += perim
                    xs += [cx - a, cx + a]
                    ys += [cy - b, cy + b]
                    shapes.append({"type": "ellipse", "cx": cx, "cy": cy, "rx": a, "ry": b})
            except Exception:
                pass

        # <polygon> / <polyline> elements
        for pe in list(_iter_tag(group, "polygon")) + list(_iter_tag(group, "polyline")):
            try:
                pts_str = pe.get("points", "").strip().split()
                pts = [float(v) for v in pts_str]
                coords = list(zip(pts[0::2], pts[1::2]))
                if len(coords) >= 2:
                    seg_len = 0.0
                    for i in range(len(coords) - 1):
                        dx = coords[i+1][0] - coords[i][0]
                        dy = coords[i+1][1] - coords[i][1]
                        seg_len += math.sqrt(dx*dx + dy*dy)
                    if _strip_ns(pe.tag) == "polygon":
                        dx = coords[0][0] - coords[-1][0]
                        dy = coords[0][1] - coords[-1][1]
                        seg_len += math.sqrt(dx*dx + dy*dy)
                    total_len += seg_len
                    xs += [c[0] for c in coords]
                    ys += [c[1] for c in coords]
                    shapes.append({"type": "poly", "coords": coords,
                                   "closed": _strip_ns(pe.tag) == "polygon"})
            except Exception:
                pass

        if total_len == 0 or not xs:
            continue

        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        letters.append(
            {
                "name": name,
                "perimeter_px": total_len,
                "bbox_px": (min_x, min_y, max_x - min_x, max_y - min_y),
                "shapes": shapes,
            }
        )

    svg_w_cm = svg_w / 72 * 2.54   # Illustrator viewBox units are pts (1pt = 1/72 in)
    return svg_w, letters, svg_w_cm


# ---------------------------------------------------------------------------
# Nesting — polygon nesting real con shapely
# ---------------------------------------------------------------------------
PIECE_W      = 120.0
PIECE_H      = 60.0
PIECE_MARGIN = 1.5    # cm margen en bordes
LETTER_GAP   = 0.8    # cm espacio entre letras
GRID_RES     = 2.0    # cm resolución del grid de búsqueda
ANGLES       = [0, 90, 180, 270]   # 4 orientaciones cardinales

# Tres tamaños de plantilla disponibles
PIECE_CONFIGS = {
    "xl":   (120.0, 240.0),   # lámina completa 240×120 (orientación vertical)
    "full": (120.0,  60.0),   # cuarto de lámina 120×60
    "tall": ( 60.0, 120.0),   # medio de lámina 60×120
    "half": ( 60.0,  60.0),   # octavo de lámina 60×60
}
# Equivalencia en unidades de 120×60 para cotización
PIECE_BILLING = {
    "xl":   4.0,
    "full": 1.0,
    "tall": 1.0,
    "half": 0.5,
}

# Vinil pricing per 120×60 equivalent unit
VINIL_PRECIO_UNIT      = 100   # pesos por unidad 120x60
VINIL_TRANSFER_EXTRA   =  60   # pesos extra si es "con transfer"


def build_letter_polygon(shapes):
    """Construye un polígono shapely real a partir de los shapes de una letra."""
    import re
    try:
        from shapely.geometry import Polygon, Point
        from shapely import affinity as sa

        polys = []
        for shape in shapes:
            if shape["type"] == "path":
                for sp_str in re.findall(r'[Mm][^Mm]+', shape["d"]):
                    try:
                        sp = parse_path(sp_str)
                        pts = []
                        for k in range(64):
                            c = sp.point(k / 64)
                            pts.append((c.real, c.imag))
                        p = Polygon(pts).buffer(0)
                        if p.is_valid and p.area > 1:
                            polys.append(p)
                    except Exception:
                        pass
            elif shape["type"] == "rect":
                x, y, w, h = shape["x"], shape["y"], shape["w"], shape["h"]
                polys.append(Polygon([(x,y),(x+w,y),(x+w,y+h),(x,y+h)]))
            elif shape["type"] == "circle":
                polys.append(Point(shape["cx"], shape["cy"]).buffer(shape["r"], resolution=16))
            elif shape["type"] == "ellipse":
                p = Point(shape["cx"], shape["cy"]).buffer(shape["rx"], resolution=16)
                polys.append(sa.scale(p, 1.0, shape["ry"] / max(shape["rx"], 0.001)))
            elif shape["type"] == "poly" and len(shape["coords"]) >= 3:
                polys.append(Polygon(shape["coords"]).buffer(0))

        if not polys:
            return None

        # Largest poly = outer; contained smaller polys = holes
        polys.sort(key=lambda p: p.area, reverse=True)
        result = polys[0]
        for poly in polys[1:]:
            if result.contains(poly.centroid):
                result = result.difference(poly)
            else:
                result = result.union(poly)
        return result.buffer(0)
    except Exception:
        return None


def polygon_nest(letter_data, scale, progress_cb=None):
    """
    letter_data : list of {name, poly_px, shapes, bbox_origin, bbox_size_px}
    scale       : SVG px → cm
    progress_cb : callable(fraction 0-1)
    Returns     : (n_pieces, placements, piece_sizes_dict)
      piece_sizes_dict : {pi: "full"|"xl"} — only non-"full" entries are stored
                         (caller treats missing key as "full")
    Letters larger than 120×60 are automatically placed on XL (120×240) pieces.
    """
    try:
        from shapely.geometry import box
        from shapely import affinity as sa
    except ImportError:
        n, pl = _nest_fallback_simple(letter_data, scale)
        return n, pl, {}

    GAP = LETTER_GAP / 2

    # Effective usable area per piece type
    FULL_EW = PIECE_CONFIGS["full"][0] - 2 * PIECE_MARGIN   # 117.0
    FULL_EH = PIECE_CONFIGS["full"][1] - 2 * PIECE_MARGIN   #  57.0
    XL_EW   = PIECE_CONFIGS["xl"][0]   - 2 * PIECE_MARGIN   # 117.0
    XL_EH   = PIECE_CONFIGS["xl"][1]   - 2 * PIECE_MARGIN   # 237.0

    full_box = box(0, 0, FULL_EW, FULL_EH)
    xl_box   = box(0, 0, XL_EW,   XL_EH)

    def make_candidate(poly_px, angle):
        """Rota, escala a cm, añade buffer, normaliza a origen (0,0)."""
        poly_cm  = sa.scale(poly_px, scale, scale, origin=(0, 0))
        rotated  = sa.rotate(poly_cm, angle)
        buffered = rotated.buffer(GAP, resolution=4)
        b = buffered.bounds
        return sa.translate(buffered, -b[0], -b[1])

    def _try_place(cb, bw, bh, info):
        """Bottom-left search in a piece described by info dict.
        Returns (gx, gy, placed_shape) or None."""
        ew, eh = info["ew"], info["eh"]
        pb  = info["pb"]
        occ = info["occ"]
        if bw > ew or bh > eh:
            return None
        xs = [i * GRID_RES for i in range(int((ew - bw) / GRID_RES) + 2)]
        ys = [i * GRID_RES for i in range(int((eh - bh) / GRID_RES) + 2)]
        for gx in xs:
            for gy in ys:
                cand = sa.translate(cb, gx, gy)
                if not pb.contains(cand):
                    break   # gy too large for this gx → next gx
                if occ is None or not occ.intersects(cand):
                    return gx, gy, cand
        return None

    # pieces_info: list of {type, ew, eh, pb, occ}
    pieces_info = []
    placements  = []

    # Ordenar por área descendente (letras grandes primero)
    items = sorted(letter_data, key=lambda l: l["poly_px"].area, reverse=True)
    n_total = len(items)

    for item_idx, letter in enumerate(items):
        if progress_cb:
            progress_cb(item_idx / n_total)

        # Pre-compute candidates for all angles and check which piece types fit
        angle_cands = {}
        fits_full = False
        fits_xl   = False
        for angle in ANGLES:
            cb = make_candidate(letter["poly_px"], angle)
            bw, bh = cb.bounds[2], cb.bounds[3]
            angle_cands[angle] = (cb, bw, bh)
            if bw <= FULL_EW and bh <= FULL_EH:
                fits_full = True
            if bw <= XL_EW and bh <= XL_EH:
                fits_xl = True

        placed = False

        # Try existing pieces (prefer full over xl for small letters)
        for pi, info in enumerate(pieces_info):
            ptype = info["type"]
            if ptype == "full" and not fits_full:
                continue
            if ptype == "xl" and not fits_xl:
                continue
            for angle in ANGLES:
                cb, bw, bh = angle_cands[angle]
                result = _try_place(cb, bw, bh, info)
                if result is not None:
                    gx, gy, cand = result
                    info["occ"] = cand if info["occ"] is None else info["occ"].union(cand)
                    b = cand.bounds
                    placements.append({
                        "piece":        pi,
                        "x":            PIECE_MARGIN + gx + GAP,
                        "y":            PIECE_MARGIN + gy + GAP,
                        "actual_w":     max(b[2]-b[0] - 2*GAP, 0.1),
                        "actual_h":     max(b[3]-b[1] - 2*GAP, 0.1),
                        "angle":        angle,
                        "name":         letter["name"],
                        "shapes":       letter["shapes"],
                        "bbox_origin":  letter["bbox_origin"],
                        "bbox_size_px": letter["bbox_size_px"],
                        "scale":        scale,
                    })
                    placed = True
                    break
            if placed:
                break

        if not placed:
            # Open a new piece — prefer full if letter fits, else use xl
            if fits_full:
                new_type = "full"
                ew, eh, pb = FULL_EW, FULL_EH, full_box
            elif fits_xl:
                new_type = "xl"
                ew, eh, pb = XL_EW, XL_EH, xl_box
            else:
                # Letter is too large even for XL; force onto an XL piece anyway
                new_type = "xl"
                ew, eh, pb = XL_EW, XL_EH, xl_box

            new_pi = len(pieces_info)
            pieces_info.append({"type": new_type, "ew": ew, "eh": eh,
                                 "pb": pb, "occ": None})

            for angle in ANGLES:
                cb, bw, bh = angle_cands[angle]
                if bw <= ew and bh <= eh:
                    pieces_info[new_pi]["occ"] = cb
                    b = cb.bounds
                    placements.append({
                        "piece":        new_pi,
                        "x":            PIECE_MARGIN + GAP,
                        "y":            PIECE_MARGIN + GAP,
                        "actual_w":     max(b[2]-b[0] - 2*GAP, 0.1),
                        "actual_h":     max(b[3]-b[1] - 2*GAP, 0.1),
                        "angle":        angle,
                        "name":         letter["name"],
                        "shapes":       letter["shapes"],
                        "bbox_origin":  letter["bbox_origin"],
                        "bbox_size_px": letter["bbox_size_px"],
                        "scale":        scale,
                    })
                    placed = True
                    break
            if not placed:
                # Last resort: force-place at origin with clipped size
                placements.append({
                    "piece":        new_pi,
                    "x":            PIECE_MARGIN,
                    "y":            PIECE_MARGIN,
                    "actual_w":     min(ew, 10),
                    "actual_h":     min(eh, 10),
                    "angle":        0,
                    "name":         letter["name"],
                    "shapes":       letter["shapes"],
                    "bbox_origin":  letter["bbox_origin"],
                    "bbox_size_px": letter["bbox_size_px"],
                    "scale":        scale,
                })

    if progress_cb:
        progress_cb(1.0)

    # Build piece_sizes dict (only store non-"full" types; "full" is the default)
    piece_sizes = {pi: info["type"]
                   for pi, info in enumerate(pieces_info)
                   if info["type"] != "full"}

    return len(pieces_info), placements, piece_sizes


def _nest_fallback_simple(letter_data, scale):
    """Shelf algorithm de emergencia si shapely no está disponible."""
    EFF_W = PIECE_W - 2 * PIECE_MARGIN
    EFF_H = PIECE_H - 2 * PIECE_MARGIN
    GAP   = LETTER_GAP
    pieces, shelves, placements = 1, [], []
    for letter in sorted(letter_data, key=lambda l: l["bbox_size_px"][1]*scale, reverse=True):
        w = letter["bbox_size_px"][0] * scale
        h = letter["bbox_size_px"][1] * scale
        placed = False
        used_h = sum(s["height"] for s in shelves)
        for shelf in shelves:
            if shelf["remaining_x"] >= w + GAP and shelf["height"] >= h + GAP:
                placements.append({"piece": pieces-1, "x": shelf["used_x"]+GAP/2,
                    "y": shelf["y"]+GAP/2, "actual_w": w, "actual_h": h,
                    "angle": 0, "name": letter["name"], "shapes": letter["shapes"],
                    "bbox_origin": letter["bbox_origin"], "bbox_size_px": letter["bbox_size_px"],
                    "scale": scale})
                shelf["used_x"] += w+GAP; shelf["remaining_x"] -= w+GAP
                placed = True; break
        if not placed and used_h + h + GAP <= EFF_H:
            shelves.append({"height": h+GAP, "remaining_x": EFF_W-w-GAP,
                "used_x": PIECE_MARGIN+w+GAP, "y": PIECE_MARGIN+used_h})
            placements.append({"piece": pieces-1, "x": PIECE_MARGIN+GAP/2,
                "y": PIECE_MARGIN+used_h+GAP/2, "actual_w": w, "actual_h": h,
                "angle": 0, "name": letter["name"], "shapes": letter["shapes"],
                "bbox_origin": letter["bbox_origin"], "bbox_size_px": letter["bbox_size_px"],
                "scale": scale})
            placed = True
        if not placed:
            pieces += 1; shelves = []
            shelves.append({"height": h+GAP, "remaining_x": EFF_W-w-GAP,
                "used_x": PIECE_MARGIN+w+GAP, "y": PIECE_MARGIN})
            placements.append({"piece": pieces-1, "x": PIECE_MARGIN+GAP/2,
                "y": PIECE_MARGIN+GAP/2, "actual_w": w, "actual_h": h,
                "angle": 0, "name": letter["name"], "shapes": letter["shapes"],
                "bbox_origin": letter["bbox_origin"], "bbox_size_px": letter["bbox_size_px"],
                "scale": scale})
    return pieces, placements, {}


def compute_letter_min_bbox(shapes):
    """
    Usa shapely para encontrar el rectángulo mínimo que envuelve la letra.
    Devuelve (w_px, h_px, angle_deg) o None si falla.
    El ángulo es el que HAY QUE APLICAR para que la letra quepa en w_px × h_px.
    """
    import re
    try:
        from shapely.geometry import MultiPoint
        pts = []
        for shape in shapes:
            if shape["type"] == "path":
                for sp_str in re.findall(r'[Mm][^Mm]+', shape["d"]):
                    try:
                        sp = parse_path(sp_str)
                        for k in range(48):
                            c = sp.point(k / 48)
                            pts.append((c.real, c.imag))
                    except Exception:
                        pass
            elif shape["type"] == "rect":
                x, y, w, h = shape["x"], shape["y"], shape["w"], shape["h"]
                pts += [(x, y), (x+w, y), (x+w, y+h), (x, y+h)]
            elif shape["type"] == "circle":
                cx, cy, r = shape["cx"], shape["cy"], shape["r"]
                for k in range(24):
                    a = 2*math.pi*k/24
                    pts.append((cx + r*math.cos(a), cy + r*math.sin(a)))
            elif shape["type"] == "ellipse":
                cx, cy = shape["cx"], shape["cy"]
                for k in range(24):
                    a = 2*math.pi*k/24
                    pts.append((cx + shape["rx"]*math.cos(a),
                                cy + shape["ry"]*math.sin(a)))
            elif shape["type"] == "poly":
                pts += shape["coords"]

        if len(pts) < 3:
            return None

        hull = MultiPoint(pts).convex_hull
        mrr  = hull.minimum_rotated_rectangle   # shapely ≥ 1.8
        coords = list(mrr.exterior.coords)

        e1 = (coords[1][0]-coords[0][0], coords[1][1]-coords[0][1])
        e2 = (coords[2][0]-coords[1][0], coords[2][1]-coords[1][1])
        len1 = math.hypot(*e1)
        len2 = math.hypot(*e2)

        # Align longer side as width
        if len1 >= len2:
            angle = math.degrees(math.atan2(e1[1], e1[0]))
            w, h = len1, len2
        else:
            angle = math.degrees(math.atan2(e2[1], e2[0]))
            w, h = len2, len1

        return w, h, -angle   # negate: SVG y-axis is inverted
    except Exception:
        return None


def nest_letters(items):
    """
    items : list of (min_w_cm, min_h_cm, base_angle_deg, name)
    Returns (n_pieces, placements)
    placement keys: piece, x, y, actual_w, actual_h, angle, name
      - actual_w/h: espacio que ocupa en la pieza (cm)
      - angle: rotación total aplicada a la letra (grados)
    """
    if not items:
        return 0, []

    try:
        from rectpack import newPacker, PackingMode, SORT_RATIO
    except ImportError:
        # Fallback básico sin rectpack
        return _nest_fallback(items)

    eff_w = PIECE_W - 2 * PIECE_MARGIN
    eff_h = PIECE_H - 2 * PIECE_MARGIN
    g = LETTER_GAP

    packer = newPacker(mode=PackingMode.Offline, sort_algo=SORT_RATIO, rotation=True)
    packer.add_bin(eff_w, eff_h, count=float("inf"))

    for i, (w, h, angle, name) in enumerate(items):
        packer.add_rect(w + g, h + g, rid=i)

    packer.pack()

    placements = []
    n_bins = 0
    for bin_idx, bin_obj in enumerate(packer):
        n_bins = bin_idx + 1
        for rect in bin_obj:
            w_orig, h_orig, base_angle, name = items[rect.rid]
            # rectpack swaps w/h when it rotates 90°
            rect_rotated = abs(rect.width - (h_orig + g)) < 0.5
            extra_angle  = 90 if rect_rotated else 0
            total_angle  = base_angle + extra_angle
            actual_w = rect.width  - g
            actual_h = rect.height - g
            placements.append({
                "piece":    bin_idx,
                "x":        PIECE_MARGIN + rect.x + g / 2,
                "y":        PIECE_MARGIN + rect.y + g / 2,
                "actual_w": actual_w,
                "actual_h": actual_h,
                "angle":    total_angle,
                "name":     name,
            })

    return n_bins, placements


def _nest_fallback(items):
    """Shelf algorithm sin rectpack (emergencia)."""
    eff_w = PIECE_W - 2 * PIECE_MARGIN
    eff_h = PIECE_H - 2 * PIECE_MARGIN
    g = LETTER_GAP
    pieces, shelves, placements = 1, [], []
    for w, h, angle, name in sorted(items, key=lambda t: t[1], reverse=True):
        used_h = sum(s["height"] for s in shelves)
        placed = False
        for shelf in shelves:
            if shelf["remaining_x"] >= w + g and shelf["height"] >= h + g:
                placements.append({"piece": pieces-1, "x": shelf["used_x"]+g/2,
                                   "y": shelf["y"]+g/2, "actual_w": w,
                                   "actual_h": h, "angle": angle, "name": name})
                shelf["used_x"] += w + g
                shelf["remaining_x"] -= w + g
                placed = True; break
        if not placed and used_h + h + g <= eff_h:
            shelves.append({"height": h+g, "remaining_x": eff_w-w-g,
                            "used_x": PIECE_MARGIN+w+g, "y": PIECE_MARGIN+used_h})
            placements.append({"piece": pieces-1, "x": PIECE_MARGIN+g/2,
                               "y": PIECE_MARGIN+used_h+g/2, "actual_w": w,
                               "actual_h": h, "angle": angle, "name": name})
            placed = True
        if not placed:
            pieces += 1; shelves = []
            shelves.append({"height": h+g, "remaining_x": eff_w-w-g,
                            "used_x": PIECE_MARGIN+w+g, "y": PIECE_MARGIN})
            placements.append({"piece": pieces-1, "x": PIECE_MARGIN+g/2,
                               "y": PIECE_MARGIN+g/2, "actual_w": w,
                               "actual_h": h, "angle": angle, "name": name})
    return pieces, placements


# ---------------------------------------------------------------------------
# Quote calculation
# ---------------------------------------------------------------------------
def calculate(svg_w_px, letters, real_width_cm, cfg):
    if real_width_cm <= 0 or not letters:
        return None

    # Use content bounding box width, not canvas width
    all_x2 = [l["bbox_px"][0] + l["bbox_px"][2] for l in letters]
    all_x1 = [l["bbox_px"][0] for l in letters]
    content_w_px = max(all_x2) - min(all_x1)
    if content_w_px == 0:
        return None

    scale = real_width_cm / content_w_px  # px → cm

    total_perim_cm = sum(l["perimeter_px"] * scale for l in letters)

    # Construir polígonos reales para polygon nesting
    letter_data = []
    for l in letters:
        poly_px = build_letter_polygon(l["shapes"])
        if poly_px is None or poly_px.is_empty:
            # Fallback: bounding box rectangle
            from shapely.geometry import box as shbox
            bx = l["bbox_px"]
            poly_px = shbox(bx[0], bx[1], bx[0]+bx[2], bx[1]+bx[3])
        letter_data.append({
            "name":         l["name"],
            "poly_px":      poly_px,
            "shapes":       l["shapes"],
            "bbox_origin":  (l["bbox_px"][0], l["bbox_px"][1]),
            "bbox_size_px": (l["bbox_px"][2], l["bbox_px"][3]),
        })

    n_letters = len(letters)

    # ── Group letters by layer suffix ──────────────────────────────────────
    def _letter_group(name):
        n = name.strip().lower()
        if n.endswith("_vt"):
            return "vt"
        elif n.endswith("_v"):
            return "v"
        return "normal"

    groups = {"normal": [], "v": [], "vt": []}
    for ld in letter_data:
        groups[_letter_group(ld["name"])].append(ld)

    # Nest each group independently so they never share pieces
    placements     = []
    auto_piece_sizes = {}
    piece_vinil    = {}   # pi → "vinil" | "transfer"
    total_pieces   = 0

    for group_key in ("normal", "v", "vt"):
        grp = groups[group_key]
        if not grp:
            continue
        n, pls, ps = polygon_nest(grp, scale)
        for pl in pls:
            pl["piece"] += total_pieces
        for pi, sz in ps.items():
            auto_piece_sizes[pi + total_pieces] = sz
        if group_key != "normal":
            vstate = "transfer" if group_key == "vt" else "vinil"
            for pi in range(n):
                piece_vinil[pi + total_pieces] = vstate
        total_pieces += n
        placements.extend(pls)

    n_pieces = total_pieces
    n_xl   = sum(1 for v in auto_piece_sizes.values() if v == "xl")
    n_full = n_pieces - n_xl   # piezas 120x60
    n_half = 0
    billing    = n_xl * PIECE_BILLING["xl"] + n_full * PIECE_BILLING["full"]
    n_acrilico = billing / 4

    area_al_cm2 = total_perim_cm * 5.0
    n_aluminio = (area_al_cm2 / (240 * 120)) * 1.40   # exacto + 40% merma

    perim_m = total_perim_cm / 100.0
    n_rollos = perim_m / 5.0
    watts_total = n_rollos * 40

    fuente = max(cfg["fuentes"], key=lambda f: -f["watts"] if f["watts"] >= watts_total else float("-inf"))
    # fallback: use largest if none fits
    if fuente["watts"] < watts_total:
        fuente = max(cfg["fuentes"], key=lambda f: f["watts"])

    p = cfg["precios"]
    c_acrilico = n_acrilico * p["acrilico_lamina"]
    c_aluminio = n_aluminio * p["aluminio_lamina"]

    # PVC 6mm — mismo nesting que acrílico
    n_pvc6 = n_acrilico
    c_pvc6 = n_pvc6 * p.get("pvc6_lamina", 0)

    # PVC 2mm — tiras de 2cm, igual que aluminio
    area_pvc2_cm2 = total_perim_cm * 2.0
    n_pvc2 = (area_pvc2_cm2 / (240 * 120)) * 1.40   # exacto + 40% merma
    c_pvc2 = n_pvc2 * p.get("pvc2_lamina", 0)

    c_mano_base   = n_letters * p["mano_obra_letra"]
    c_fee         = c_mano_base * 0.20
    c_mano        = c_mano_base + c_fee
    c_leds = n_rollos * p["led_rollo"]
    c_fuente      = fuente["precio"]
    c_instalacion = p.get("instalacion", 0)
    _tipo_fijacion  = cfg.get("tipo_fijacion", "Ninguno")
    _fij_precios    = {
        "Espárrago":       p.get("esparragos_unit",    3.66),
        "Snaps":           p.get("snaps_unit",         10.00),
        "Tubo roscado 10cm": p.get("tubo_roscado_unit", 15.00),
    }
    n_esparragos    = n_letters * 4
    c_esparragos    = n_esparragos * _fij_precios[_tipo_fijacion] if _tipo_fijacion != "Ninguno" else 0.0

    # Papel plantilla — cubre el área total del anuncio en posición final
    all_y1 = [l["bbox_px"][1] for l in letters]
    all_y2 = [l["bbox_px"][1] + l["bbox_px"][3] for l in letters]
    sign_h_cm  = (max(all_y2) - min(all_y1)) * scale
    sign_area_cm2 = real_width_cm * sign_h_cm
    papel_cfg = cfg.get("papel_plantilla", {"ancho_cm": 90, "alto_cm": 120, "precio": 15})
    # Contar pliegos por grilla física, no por área — el papel no se puede redistribuir
    n_papel = (math.ceil(real_width_cm / papel_cfg["ancho_cm"]) *
               math.ceil(sign_h_cm    / papel_cfg["alto_cm"]))
    c_papel = n_papel * papel_cfg["precio"]

    basicos = cfg.get("basicos", [])
    c_basicos_items = [(b["nombre"], b["precio"]) for b in basicos]
    c_basicos_total = sum(x[1] for x in c_basicos_items)

    # Vinil — calculado desde el inicio según sufijos _v / _vt de las capas
    vinil_unit   = p.get("vinil_unit",           VINIL_PRECIO_UNIT)
    vinil_xtra   = p.get("vinil_transfer_extra", VINIL_TRANSFER_EXTRA)
    c_vinil = 0.0
    for pi, vstate in piece_vinil.items():
        size  = auto_piece_sizes.get(pi, "full")
        units = PIECE_BILLING.get(size, 1.0)
        c_vinil += units * (vinil_unit + (vinil_xtra if vstate == "transfer" else 0))

    total = (c_acrilico + c_aluminio + c_pvc6 + c_pvc2 +
             c_mano + c_leds + c_fuente + c_instalacion +
             c_basicos_total + c_papel + c_vinil + c_esparragos)

    # Per-letter perimeters for aluminum visual
    letter_perims_cm = [l["perimeter_px"] * scale for l in letters]

    # Letter bboxes + shapes in sign space (cm), relative to sign top-left corner
    sign_x0_px = min(all_x1)
    sign_y0_px = min(all_y1)
    letter_bboxes_cm = []
    for l in letters:
        # Transform each shape from SVG px to sign-space cm
        shapes_cm = []
        for sh in l.get("shapes", []):
            t = sh["type"]
            if t == "path":
                shapes_cm.append({"type": "path", "d": sh["d"],
                                   "ox": sign_x0_px, "oy": sign_y0_px,
                                   "scale": scale})
            elif t == "rect":
                shapes_cm.append({"type": "rect",
                                   "x": (sh["x"] - sign_x0_px) * scale,
                                   "y": (sh["y"] - sign_y0_px) * scale,
                                   "w": sh["w"] * scale,
                                   "h": sh["h"] * scale})
            elif t == "circle":
                shapes_cm.append({"type": "circle",
                                   "cx": (sh["cx"] - sign_x0_px) * scale,
                                   "cy": (sh["cy"] - sign_y0_px) * scale,
                                   "r":  sh["r"] * scale})
            elif t == "ellipse":
                shapes_cm.append({"type": "ellipse",
                                   "cx": (sh["cx"] - sign_x0_px) * scale,
                                   "cy": (sh["cy"] - sign_y0_px) * scale,
                                   "rx": sh["rx"] * scale,
                                   "ry": sh["ry"] * scale})
            elif t == "poly":
                shapes_cm.append({"type": "poly",
                                   "coords": [((cx - sign_x0_px) * scale,
                                               (cy - sign_y0_px) * scale)
                                              for cx, cy in sh["coords"]],
                                   "closed": sh["closed"]})
        letter_bboxes_cm.append({
            "name": l["name"],
            "x": (l["bbox_px"][0] - sign_x0_px) * scale,
            "y": (l["bbox_px"][1] - sign_y0_px) * scale,
            "w": l["bbox_px"][2] * scale,
            "h": l["bbox_px"][3] * scale,
            "shapes": shapes_cm,
        })

    return {
        "n_letters": n_letters,
        "perim_cm": total_perim_cm,
        "perim_m": perim_m,
        "n_pieces": n_pieces,
        "n_xl":   n_xl,
        "n_full": n_full,
        "n_half": n_half,
        "piece_sizes": auto_piece_sizes,   # pre-populated from nesting; persists between NestingWindow opens
        "placements": placements,
        "n_acrilico": n_acrilico,
        "area_al_cm2": area_al_cm2,
        "n_aluminio": n_aluminio,
        "letter_perims_cm": letter_perims_cm,
        "letter_bboxes_cm": letter_bboxes_cm,
        "letter_names": [l["name"] for l in letters],
        "n_rollos": n_rollos,
        "watts": watts_total,
        "fuente": fuente,
        "n_pvc6": n_pvc6,
        "area_pvc2_cm2": area_pvc2_cm2,
        "n_pvc2": n_pvc2,
        "c_acrilico": c_acrilico,
        "c_aluminio": c_aluminio,
        "c_pvc6": c_pvc6,
        "c_pvc2": c_pvc2,
        "c_mano": c_mano,
        "c_leds": c_leds,
        "c_fuente": c_fuente,
        "c_instalacion": c_instalacion,
        "c_fee": c_fee,
        "basicos": c_basicos_items,
        "c_basicos_total": c_basicos_total,
        "c_vinil": c_vinil,
        "piece_vinil": piece_vinil,   # {pi: "vinil"|"transfer"} from layer suffixes
        "vinil_prices": {"unit": vinil_unit, "transfer_extra": vinil_xtra},
        "sign_w_cm": real_width_cm,
        "sign_h_cm": sign_h_cm,
        "sign_area_cm2": sign_area_cm2,
        "n_papel": n_papel,
        "c_papel": c_papel,
        "papel_cfg": papel_cfg,
        "n_esparragos":  n_esparragos,
        "c_esparragos":  c_esparragos,
        "tipo_fijacion": _tipo_fijacion,
        "total": total,
    }


def fmt(n):
    return f"${n:,.2f}"


def _draw_reg_marks_canvas(cv, ox, oy, pw, ph,
                           arm=24, gap=0, color="#ff6060"):
    """
    Draw registration/crop marks at the 4 corners of a piece on a tkinter Canvas.
    ox,oy = top-left of piece in canvas px.
    pw,ph = piece width/height in canvas px.
    arm   = length of each mark arm in canvas px.
    gap=0 → marks start exactly at the piece edge (matches SVG export).
    """
    corners = [
        (ox, oy,           +1, +1),   # top-left
        (ox + pw, oy,      -1, +1),   # top-right
        (ox, oy + ph,      +1, -1),   # bottom-left
        (ox + pw, oy + ph, -1, -1),   # bottom-right
    ]
    for (cx, cy, dx, dy) in corners:
        # horizontal arm — starts at edge
        x0 = cx + dx * gap
        x1 = cx + dx * (gap + arm)
        cv.create_line(x0, cy, x1, cy, fill=color, width=1)
        # vertical arm — starts at edge
        y0 = cy + dy * gap
        y1 = cy + dy * (gap + arm)
        cv.create_line(cx, y0, cx, y1, fill=color, width=1)


def _reg_marks_svg(pw_cm, ph_cm, arm_cm=1.5, gap_cm=0.0, y0=0.0):
    """
    Return SVG lines for registration/crop marks at the 4 corners.
    Coordinates in cm (piece space: 0,0 = top-left of section).
    gap_cm=0  → marks start exactly at the piece edge (cut line).
    arm_cm    → length of each mark arm extending outward.
    """
    lines = ['<g id="reg_marks" stroke="#ff0000" stroke-width="0.04"'
             ' fill="none" stroke-linecap="square">']
    corners = [
        (0,     y0,          +1, +1),
        (pw_cm, y0,          -1, +1),
        (0,     y0 + ph_cm,  +1, -1),
        (pw_cm, y0 + ph_cm,  -1, -1),
    ]
    for (cx, cy, dx, dy) in corners:
        # horizontal arm — starts at edge, extends outward
        hx0 = cx + dx * gap_cm
        hx1 = cx + dx * (gap_cm + arm_cm)
        lines.append(f'  <line x1="{hx0:.4f}" y1="{cy:.4f}"'
                     f' x2="{hx1:.4f}" y2="{cy:.4f}"/>')
        # vertical arm — starts at edge, extends outward
        vy0 = cy + dy * gap_cm
        vy1 = cy + dy * (gap_cm + arm_cm)
        lines.append(f'  <line x1="{cx:.4f}" y1="{vy0:.4f}"'
                     f' x2="{cx:.4f}" y2="{vy1:.4f}"/>')
        # small crosshair circle at the exact corner
        lines.append(f'  <circle cx="{cx:.4f}" cy="{cy:.4f}" r="0.15"'
                     f' stroke-width="0.04"/>')
    lines.append('</g>')
    return lines


def _draw_shapes_on_canvas(cv, shapes_cm, S, ox, oy, fill, outline, samples=60):
    """
    Draws letter shapes (in cm, sign-space) onto a tkinter Canvas.
    ox, oy: canvas pixel origin of sign top-left.
    S: px per cm scale.
    """
    for sh in shapes_cm:
        t = sh["type"]
        if t == "path" and HAS_SVG:
            try:
                from svgpathtools import parse_path as _pp
                path = _pp(sh["d"])
                pts = []
                total = path.length(error=1e-3)
                if total == 0:
                    continue
                n = max(samples, int(total / 4))
                for i in range(n + 1):
                    pt = path.point(i / n)
                    px = ox + (pt.real - sh["ox"]) * sh["scale"] * S
                    py = oy + (pt.imag - sh["oy"]) * sh["scale"] * S
                    pts.extend([px, py])
                if len(pts) >= 4:
                    cv.create_polygon(pts, fill=fill, outline=outline,
                                      width=1, smooth=True)
            except Exception:
                pass
        elif t == "rect":
            x1 = ox + sh["x"] * S;  y1 = oy + sh["y"] * S
            x2 = x1 + sh["w"] * S;  y2 = y1 + sh["h"] * S
            cv.create_rectangle(x1, y1, x2, y2, fill=fill, outline=outline, width=1)
        elif t == "circle":
            cx = ox + sh["cx"] * S;  cy = oy + sh["cy"] * S
            r  = sh["r"] * S
            cv.create_oval(cx-r, cy-r, cx+r, cy+r, fill=fill, outline=outline, width=1)
        elif t == "ellipse":
            cx = ox + sh["cx"] * S;  cy = oy + sh["cy"] * S
            rx = sh["rx"] * S;       ry = sh["ry"] * S
            cv.create_oval(cx-rx, cy-ry, cx+rx, cy+ry, fill=fill, outline=outline, width=1)
        elif t == "poly":
            pts = []
            for (cx, cy) in sh["coords"]:
                pts.extend([ox + cx * S, oy + cy * S])
            if len(pts) >= 4:
                if sh.get("closed"):
                    cv.create_polygon(pts, fill=fill, outline=outline, width=1)
                else:
                    cv.create_line(pts, fill=outline, width=1)


# ---------------------------------------------------------------------------
# PDF export
# ---------------------------------------------------------------------------
def _pil_nesting_image(placements, n_pieces, piece_sizes, scale=6):
    """Render nesting layout to a PIL Image with actual letter shapes."""
    from PIL import Image, ImageDraw
    COLS = 3
    GAP  = 12
    PW = int(PIECE_W * scale)
    PH = int(PIECE_H * scale)
    rows = math.ceil(n_pieces / COLS)
    W = COLS * (PW + GAP) + GAP
    H = rows * (PH + GAP) + GAP

    img  = Image.new("RGB", (W, H), "#f0f0f0")
    draw = ImageDraw.Draw(img)

    COLORS_PIL = ["#4f86c6","#e05c5c","#3aaa6a","#e07c3a","#8a5cd0",
                  "#c45c8a","#3aaab4","#d4a017","#5c8ae0","#7a7a7a"]

    # Draw piece backgrounds
    for pi in range(n_pieces):
        col, row = pi % COLS, pi // COLS
        psize = piece_sizes.get(pi, "full")
        is_half = psize == "half"
        is_tall = psize == "tall"
        is_xl   = psize == "xl"
        pcw, pch = PIECE_CONFIGS.get(psize, PIECE_CONFIGS["full"])
        pw = int(pcw * scale)
        ph = int(pch * scale)
        ox = GAP + col * (PW + GAP)
        oy = GAP + row * (PH + GAP)
        draw.rectangle([ox, oy, ox+pw, oy+ph], fill="#ffffff", outline="#cccccc", width=2)
        label = {"xl": "120x240", "full": "120x60", "tall": "60x120", "half": "60x60"}.get(psize, "120x60")
        draw.text((ox+4, oy+4), f"P{pi+1} ({label} cm)", fill="#aaaaaa")

    def _tc(px_, py_, cx_svg, cy_svg, sc, cos_a, sin_a, pcx, pcy):
        dx = (px_ - cx_svg) * sc
        dy = (py_ - cy_svg) * sc
        return (pcx + dx*cos_a - dy*sin_a,
                pcy + dx*sin_a + dy*cos_a)

    def _shape_polygons(p, ox, oy):
        """Returns list of pixel-coordinate polygon point lists for all shapes."""
        bx0, by0   = p.get("bbox_origin",  (0, 0))
        w_px, h_px = p.get("bbox_size_px", (1, 1))
        sc   = p.get("scale", 1.0)
        ang  = p.get("angle", 0.0)
        cos_a = math.cos(math.radians(ang))
        sin_a = math.sin(math.radians(ang))
        cx_svg = bx0 + w_px / 2
        cy_svg = by0 + h_px / 2
        pcx = p["x"] + p["actual_w"] / 2
        pcy = p["y"] + p["actual_h"] / 2

        def tc(px_, py_):
            x, y = _tc(px_, py_, cx_svg, cy_svg, sc, cos_a, sin_a, pcx, pcy)
            return (ox + x * scale, oy + y * scale)

        polys = []
        for shape in p.get("shapes", []):
            try:
                t = shape["type"]
                if t == "path":
                    for sp_str in __import__("re").findall(r'[Mm][^Mm]+', shape["d"]):
                        try:
                            sp = parse_path(sp_str)
                            pts = [tc(sp.point(k/80).real, sp.point(k/80).imag)
                                   for k in range(81)]
                            if len(pts) >= 3:
                                polys.append(pts)
                        except Exception:
                            pass
                elif t == "rect":
                    corners = [(shape["x"],              shape["y"]),
                               (shape["x"]+shape["w"],   shape["y"]),
                               (shape["x"]+shape["w"],   shape["y"]+shape["h"]),
                               (shape["x"],              shape["y"]+shape["h"])]
                    polys.append([tc(x, y) for x, y in corners])
                elif t in ("circle", "ellipse"):
                    r1 = shape.get("r", shape.get("rx", 1))
                    r2 = shape.get("r", shape.get("ry", 1))
                    cx2, cy2 = shape.get("cx", 0), shape.get("cy", 0)
                    pts = [tc(cx2 + r1*math.cos(2*math.pi*k/32),
                              cy2 + r2*math.sin(2*math.pi*k/32)) for k in range(32)]
                    polys.append(pts)
                elif t == "poly":
                    polys.append([tc(x, y) for x, y in shape["coords"]])
            except Exception:
                pass
        return polys

    # Draw letters
    for i, p in enumerate(placements):
        pi  = p["piece"]
        col = pi % COLS
        row = pi // COLS
        ox  = GAP + col * (PW + GAP)
        oy  = GAP + row * (PH + GAP)
        color = COLORS_PIL[i % len(COLORS_PIL)]

        polys = _shape_polygons(p, ox, oy)
        if polys:
            for pts in polys:
                flat = [c for pt in pts for c in pt]
                if len(flat) >= 6:
                    draw.polygon(flat, fill=color, outline="#ffffff")
        else:
            # fallback: bounding box
            lx = int(ox + p["x"] * scale)
            ly = int(oy + p["y"] * scale)
            lw = max(int(p["actual_w"] * scale), 4)
            lh = max(int(p["actual_h"] * scale), 4)
            draw.rectangle([lx, ly, lx+lw, ly+lh], fill=color, outline="#ffffff", width=1)

        # Label
        pcx = int(ox + (p["x"] + p["actual_w"]/2) * scale)
        pcy = int(oy + (p["y"] + p["actual_h"]/2) * scale)
        draw.text((pcx - len(p["name"])*3, pcy - 6), p["name"], fill="#ffffff")

    return img


def _pil_aluminum_image(letter_perims_cm, letter_names, strip_w, scale=3, merma=0.40):
    """Render aluminum/PVC-2mm strip layout to a PIL Image."""
    from PIL import Image, ImageDraw
    SHEET_W, SHEET_H = 240.0, 120.0
    COLS = 3
    GAP  = 12
    SW = int(SHEET_W * scale)
    SH = int(SHEET_H * scale)

    strips = sorted(zip(letter_perims_cm, letter_names), reverse=True)
    sheets, col_x, col_y = [[]], 0.0, 0.0
    letter_colors = {}
    color_idx = 0
    COLORS_PIL = ["#4f86c6","#e05c5c","#3aaa6a","#e07c3a","#8a5cd0",
                  "#c45c8a","#3aaab4","#d4a017","#5c8ae0","#7a7a7a"]

    for perim, name in strips:
        if name not in letter_colors:
            letter_colors[name] = COLORS_PIL[color_idx % len(COLORS_PIL)]
            color_idx += 1
        remaining = perim + perim * merma  # include merma
        while remaining > 0.01:
            if col_y >= SHEET_H - 0.1:
                col_x += strip_w; col_y = 0.0
            if col_x + strip_w > SHEET_W + 0.1:
                sheets.append([]); col_x = col_y = 0.0
            seg = min(remaining, SHEET_H - col_y)
            is_merma = perim > 0 and remaining <= perim * merma
            sheets[-1].append((col_x, col_y, strip_w, seg, name, is_merma))
            col_y += seg; remaining -= seg

    n = len(sheets)
    rows = math.ceil(n / COLS)
    W = COLS * (SW + GAP) + GAP
    H = rows * (SH + GAP) + GAP
    img  = Image.new("RGB", (W, H), "#f0f0f0")
    draw = ImageDraw.Draw(img)

    for si, sheet in enumerate(sheets):
        col, row = si % COLS, si // COLS
        ox = GAP + col * (SW + GAP)
        oy = GAP + row * (SH + GAP)
        draw.rectangle([ox, oy, ox+SW, oy+SH], fill="#ffffff", outline="#cccccc", width=2)
        draw.text((ox+4, oy+4), f"Hoja {si+1}", fill="#aaaaaa")
        for (sx, sy, sw, sh, name, is_merma) in sheet:
            color = "#dddddd" if is_merma else letter_colors.get(name, "#aaaaaa")
            x1, y1 = ox+int(sx*scale), oy+int(sy*scale)
            x2, y2 = x1+max(int(sw*scale)-1,2), y1+max(int(sh*scale)-1,2)
            draw.rectangle([x1, y1, x2, y2], fill=color, outline="#ffffff")
            if (y2-y1) > 12 and not is_merma:
                draw.text((x1+2, y1+2), name[:4], fill="#ffffff")
    return img


def export_pdf(r, placements, piece_sizes, n_pieces, output_path):
    import io, datetime
    from reportlab.lib.pagesizes import letter as RL_PAGE
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                    Table, TableStyle, HRFlowable, Image as RLImage,
                                    PageBreak)
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfgen import canvas as rl_canvas

    PAGE = RL_PAGE
    LM = RM = 2.0 * cm
    TM = 2.2 * cm
    BM = 1.8 * cm
    PW = PAGE[0] - LM - RM

    # ── Datos ─────────────────────────────────────────────────────────────
    empresa   = r.get("empresa", {})
    emp_nombre= empresa.get("nombre",   "Anuncios Luminosos LB")
    emp_dom   = empresa.get("domicilio","")
    emp_tel   = empresa.get("tel",      "")
    emp_email = empresa.get("email",    "")
    director  = empresa.get("director", "Ricardo Lobo Sáenz")
    cargo     = empresa.get("cargo",    "Director general")
    logo_path = empresa.get("logo", "")
    if logo_path and not os.path.isabs(logo_path):
        logo_path = os.path.join(BASE_DIR, logo_path)
    iva_pct   = empresa.get("iva_pct",  16.0)
    isr_pct   = empresa.get("isr_pct",  1.25)
    vigencia  = empresa.get("vigencia_dias", 30)
    folio     = r.get("folio", 0)

    cliente   = r.get("cliente",         "")
    emp_c     = r.get("empresa_cliente", "")
    direccion = r.get("direccion",       "")
    proyecto  = r.get("proyecto",        "")
    desc_txt  = r.get("descripcion",     "")

    today     = datetime.date.today()
    today_s   = today.strftime("%d/%m/%Y")
    _meses    = ["enero","febrero","marzo","abril","mayo","junio",
                 "julio","agosto","septiembre","octubre","noviembre","diciembre"]
    today_long = f"{today.day} de {_meses[today.month-1]} de {today.year}"
    vence = (today + datetime.timedelta(days=vigencia)).strftime("%d/%m/%Y")

    tipo_persona = r.get("tipo_persona", "Persona Física")
    aplica_isr   = tipo_persona == "Persona Moral"
    subtotal   = r.get("total", 0.0)
    iva        = subtotal * iva_pct / 100
    isr        = subtotal * isr_pct / 100 if aplica_isr else 0.0
    imp_neto   = iva - isr
    total_gral = subtotal + imp_neto

    def money(v): return f"${v:,.2f}"

    # ── Colors / styles ───────────────────────────────────────────────────
    BLACK = colors.black
    GRAY  = colors.HexColor("#595959")
    LGRAY = colors.HexColor("#cccccc")
    RED   = colors.HexColor("#cc0000")

    def _s(name, **kw):
        defaults = dict(fontName="Helvetica", fontSize=9, leading=13, textColor=BLACK)
        defaults.update(kw)
        return ParagraphStyle(name, **defaults)

    s_norm    = _s("n")
    s_small   = _s("sm",  fontSize=8,  leading=11, textColor=GRAY)
    s_bold9   = _s("b9",  fontName="Helvetica-Bold")
    s_bold10  = _s("b10", fontName="Helvetica-Bold", fontSize=10, leading=14)
    s_bold12  = _s("b12", fontName="Helvetica-Bold", fontSize=12, leading=16)
    s_bold14  = _s("b14", fontName="Helvetica-Bold", fontSize=14, leading=18)
    s_right   = _s("r",   alignment=2)
    s_right_b = _s("rb",  alignment=2, fontName="Helvetica-Bold", fontSize=10)
    s_red     = _s("red", fontSize=8,  textColor=RED)
    s_th      = _s("th",  fontName="Helvetica-Bold", fontSize=8,
                          textColor=colors.black)

    story = []
    SP  = lambda n=6:  story.append(Spacer(1, n))
    HR  = lambda c=LGRAY, t=0.5: story.append(HRFlowable(width="100%", color=c, thickness=t))

    # ── Footer callback ────────────────────────────────────────────────────
    footer_text = f"{emp_dom}     Página N° "

    def _draw_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GRAY)
        y = BM * 0.55
        canvas.drawString(LM, y, footer_text + str(doc.page))
        canvas.restoreState()

    # ── Header: logo + folio ──────────────────────────────────────────────
    def _logo_cell():
        if logo_path and os.path.isfile(logo_path):
            try:
                return RLImage(logo_path, width=3.5*cm, height=1.4*cm)
            except Exception:
                pass
        return Paragraph(f"<b>{emp_nombre}</b>",
                         _s("lg", fontName="Helvetica-Bold", fontSize=13))

    folio_cell = Table([
        [Paragraph(f"<b>Presupuesto N° {folio}</b>",
                   _s("fo", fontName="Helvetica-Bold", fontSize=14, alignment=2))],
        [Paragraph(today_long,  _s("fd", fontSize=8, textColor=GRAY, alignment=2))],
        [Paragraph("Página 1 de 1", _s("fp", fontSize=8, textColor=GRAY, alignment=2))],
    ], colWidths=[PW * 0.40])
    folio_cell.setStyle(TableStyle([
        ("ALIGN",  (0,0),(-1,-1), "RIGHT"),
        ("VALIGN", (0,0),(-1,-1), "TOP"),
        ("TOPPADDING",    (0,0),(-1,-1), 2),
        ("BOTTOMPADDING", (0,0),(-1,-1), 2),
    ]))

    header = Table([[_logo_cell(), Spacer(1,1), folio_cell]],
                   colWidths=[PW*0.38, PW*0.22, PW*0.40])
    header.setStyle(TableStyle([
        ("VALIGN", (0,0),(-1,-1), "TOP"),
        ("LEFTPADDING",  (0,0),(-1,-1), 0),
        ("RIGHTPADDING", (0,0),(-1,-1), 0),
    ]))
    story.append(header)
    SP(14)

    # ── Bloque cliente ────────────────────────────────────────────────────
    if cliente:
        story.append(Paragraph(cliente, s_bold12))
        SP(2)
    if emp_c:
        story.append(Paragraph(emp_c, s_bold10))
        SP(2)
    if direccion:
        for line in direccion.split(","):
            line = line.strip()
            if line:
                story.append(Paragraph(line, s_small))
    SP(8)

    if proyecto:
        story.append(Paragraph(f"<b>Proyecto:</b> {proyecto}", s_bold9))
    HR(BLACK, 0.8)
    SP(8)

    story.append(Paragraph(
        "Tenemos el gusto de dirigirnos a usted para poner a su disposición el siguiente presupuesto.",
        s_norm))
    SP(8)

    if desc_txt and desc_txt.strip():
        story.append(Paragraph(
            desc_txt.strip().replace("\n", "<br/>"),
            _s("desc_comp", fontSize=9, leading=13, textColor=colors.HexColor("#333333"))))
        SP(8)

    # ── Tabla de items ────────────────────────────────────────────────────
    th_style = _s("th2", fontName="Helvetica-Bold", fontSize=8, textColor=BLACK)
    hrow = [
        Paragraph("DESCRIPCIÓN", th_style),
        Paragraph("CANT.", _s("thc", fontName="Helvetica-Bold", fontSize=8, alignment=1)),
        Paragraph("UNITARIO", _s("thr", fontName="Helvetica-Bold", fontSize=8, alignment=2)),
        Paragraph("IMPORTE",  _s("thr2",fontName="Helvetica-Bold", fontSize=8, alignment=2)),
    ]
    items_rows = [hrow]

    # Desglose automático (siempre visible)
    if True:
        def _row(desc, cant, unit, imp):
            return [Paragraph(desc, s_norm),
                    Paragraph(str(cant), _s("c1", alignment=1)),
                    Paragraph(money(unit), s_right),
                    Paragraph(money(imp),  s_right)]

        def _unit(imp, qty):
            """Precio unitario = importe / cantidad, evitando división entre cero."""
            try:
                q = float(qty)
                return imp / q if q else imp
            except (TypeError, ValueError):
                return imp

        if r.get("c_acrilico", 0):
            items_rows.append(_row("Acrílico Z2 (lám. 240×120 cm)",
                f"{r['n_acrilico']:.3f}", _unit(r["c_acrilico"], r["n_acrilico"]), r["c_acrilico"]))
        if r.get("c_pvc6", 0):
            items_rows.append(_row("PVC 6mm (lám. 240×120 cm)",
                f"{r['n_pvc6']:.3f}", _unit(r["c_pvc6"], r["n_pvc6"]), r["c_pvc6"]))
        if r.get("c_aluminio", 0):
            items_rows.append(_row("Spec (+40% merma)",
                f"{r['n_aluminio']:.3f}", _unit(r["c_aluminio"], r["n_aluminio"]), r["c_aluminio"]))
        if r.get("c_pvc2", 0):
            items_rows.append(_row("PVC 2mm (+40% merma)",
                f"{r['n_pvc2']:.3f}", _unit(r["c_pvc2"], r["n_pvc2"]), r["c_pvc2"]))
        if r.get("c_leds", 0):
            items_rows.append(_row("Tira LED 5m (rollo)",
                f"{r.get('n_rollos',0):.3f}", _unit(r["c_leds"], r.get("n_rollos", 1)), r["c_leds"]))
        if r.get("c_fuente", 0):
            fu = r.get("fuente", {})
            items_rows.append(_row(f"Fuente de poder {fu.get('watts','')}W",
                1, r["c_fuente"], r["c_fuente"]))
        if r.get("c_mano", 0):
            items_rows.append(_row("Mano de obra (letras)",
                r.get("n_letters", 0), _unit(r["c_mano"], r.get("n_letters", 1)), r["c_mano"]))
        if r.get("c_instalacion", 0):
            items_rows.append(_row("Instalación", 1, r["c_instalacion"], r["c_instalacion"]))
        if r.get("c_vinil", 0):
            items_rows.append(_row("Vinil / transfer (plantillas)", 1, r["c_vinil"], r["c_vinil"]))
        if r.get("c_esparragos", 0):
            n_esp = r.get("n_esparragos", 0)
            u_esp = r["c_esparragos"] / n_esp if n_esp else 0
            items_rows.append(_row(r.get("tipo_fijacion", "Fijación"), n_esp, u_esp, r["c_esparragos"]))
        if r.get("c_papel", 0):
            pc2 = r.get("papel_cfg", {})
            items_rows.append(_row(
                f"Papel plantilla {pc2.get('ancho_cm',120)}×{pc2.get('alto_cm',60)} cm",
                r.get("n_papel",0), pc2.get("precio",0), r["c_papel"]))
        for bn, bv in r.get("basicos", []):
            items_rows.append(_row(bn, 1, bv, bv))


    cw = [PW*0.54, PW*0.09, PW*0.18, PW*0.19]
    items_tbl = Table(items_rows, colWidths=cw, repeatRows=1)
    n_rows = len(items_rows)
    items_tbl.setStyle(TableStyle([
        ("FONTNAME",      (0,0),(-1,-1), "Helvetica"),
        ("FONTSIZE",      (0,0),(-1,-1), 9),
        ("VALIGN",        (0,0),(-1,-1), "TOP"),
        ("ALIGN",         (1,0),(-1,-1), "RIGHT"),
        ("ALIGN",         (1,0),(1,-1),  "CENTER"),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("LEFTPADDING",   (0,0),(-1,-1), 4),
        ("RIGHTPADDING",  (0,0),(-1,-1), 4),
        ("LINEBELOW",     (0,0),(-1,0),  0.6, BLACK),   # bajo header
        ("LINEBELOW",     (0,n_rows-1),(-1,n_rows-1), 0.6, BLACK),  # bajo último
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [colors.white, colors.HexColor("#f8f8f8")]),
    ]))
    story.append(items_tbl)
    SP(6)

    # ── Totales ───────────────────────────────────────────────────────────
    tot_rows = [
        [Paragraph("Sub Total:",             s_norm),   Paragraph(money(subtotal),  s_right)],
        [Paragraph(f"IVA ({iva_pct:.0f}%):", s_norm),   Paragraph(money(iva),       s_right)],
    ]
    if aplica_isr:
        tot_rows.append([
            Paragraph(f"Retención ISR ({isr_pct:.2f}%):", s_norm),
            Paragraph(f"- {money(isr)}", s_right),
        ])
    tot_rows.append([
        Paragraph("Total General:", s_bold10),
        Paragraph(money(total_gral), s_right_b),
    ])
    tot_tbl = Table(tot_rows, colWidths=[PW*0.78, PW*0.22])
    tot_tbl.setStyle(TableStyle([
        ("ALIGN",         (1,0),(-1,-1), "RIGHT"),
        ("TOPPADDING",    (0,0),(-1,-1), 3),
        ("BOTTOMPADDING", (0,0),(-1,-1), 3),
        ("LINEABOVE",     (0,-1),(-1,-1), 0.6, BLACK),
    ]))
    story.append(tot_tbl)
    SP(16)

    # ── Condiciones ───────────────────────────────────────────────────────
    story.append(Paragraph(
        f"<b>Condiciones de pago:</b> 50% de anticipo y el resto a la entrega.", s_norm))
    SP(3)
    story.append(Paragraph(
        f"<b>Tiempo de Entrega:</b> 7 días después de recibido el anticipo", s_norm))
    SP(3)
    story.append(Paragraph(
        f"<b>Vigencia:</b> {vigencia} días. Vence el {vence}.", s_norm))
    SP(3)
    story.append(Paragraph("<b>Observaciones:</b>", s_norm))
    SP(3)
    story.append(Paragraph(
        f"Los impuestos están calculados con el {iva_pct:.0f}% de IVA "
        f"y un -{isr_pct:.2f}% de retención del ISR.", s_red))
    SP(24)

    # ── Firmas ────────────────────────────────────────────────────────────
    line = "___________________________________"
    sig = Table([
        [Paragraph("Atentamente:", s_norm), Paragraph("Acepto:", s_norm),
         Paragraph("Fecha:_____ / _____ / _____", s_norm)],
        [Spacer(1, 22), Spacer(1, 22), Spacer(1, 22)],
        [Paragraph(line, s_norm), Paragraph(line, s_norm), Paragraph("", s_norm)],
        [Paragraph(f"<b>{director}</b><br/>{cargo}<br/>Tel.: {emp_tel}<br/>Email: {emp_email}",
                   s_small),
         Paragraph(cliente or "Cliente", s_small),
         Paragraph("", s_norm)],
    ], colWidths=[PW*0.38, PW*0.38, PW*0.24])
    sig.setStyle(TableStyle([
        ("VALIGN",  (0,0),(-1,-1), "TOP"),
        ("TOPPADDING",    (0,0),(-1,-1), 3),
        ("BOTTOMPADDING", (0,0),(-1,-1), 3),
        ("LEFTPADDING",   (0,0),(-1,-1), 0),
        ("RIGHTPADDING",  (0,0),(-1,-1), 6),
    ]))
    story.append(sig)

    # ── Página 2: gráficos de nesting ─────────────────────────────────────
    def pil_to_rl(pil_img, max_w):
        buf = io.BytesIO()
        pil_img.save(buf, format="PNG")
        buf.seek(0)
        ratio = pil_img.height / pil_img.width
        w = min(max_w, pil_img.width * 0.75)
        return RLImage(buf, width=w, height=w*ratio)

    s_img = _s("img", fontName="Helvetica-Bold", fontSize=9, textColor=GRAY,
               spaceBefore=10, spaceAfter=4)

    story.append(PageBreak())
    story.append(Paragraph("Nesting — Acrílico Z2 / PVC 6mm", s_img))
    story.append(pil_to_rl(_pil_nesting_image(placements, n_pieces, piece_sizes, scale=5), PW))
    SP(14)
    story.append(Paragraph("Distribución — Aluminio (tiras 5 cm)", s_img))
    story.append(pil_to_rl(_pil_aluminum_image(
        r.get("letter_perims_cm",[]), r.get("letter_names",[]), strip_w=5.0, scale=2), PW))
    SP(14)
    story.append(Paragraph("Distribución — PVC 2mm (tiras 2 cm)", s_img))
    story.append(pil_to_rl(_pil_aluminum_image(
        r.get("letter_perims_cm",[]), r.get("letter_names",[]), strip_w=2.0, scale=2), PW))

    doc = SimpleDocTemplate(output_path, pagesize=PAGE,
                            leftMargin=LM, rightMargin=RM,
                            topMargin=TM, bottomMargin=BM)
    doc.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    return output_path


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------
def _placement_subpaths_cm(p, samples=80):
    """
    Returns list of [(x_cm, y_cm), ...] point lists for all subpaths of a
    placement, already transformed (rotated + positioned) in piece coordinates.
    """
    import re
    bx0, by0   = p["bbox_origin"]
    w_px, h_px = p["bbox_size_px"]
    sc  = p["scale"]
    ang = p["angle"]
    cos_a, sin_a = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    cx_svg, cy_svg = bx0 + w_px/2, by0 + h_px/2
    pcx = p["x"] + p["actual_w"] / 2
    pcy = p["y"] + p["actual_h"] / 2

    def tf(px_, py_):
        dx = (px_ - cx_svg) * sc
        dy = (py_ - cy_svg) * sc
        return pcx + dx*cos_a - dy*sin_a, pcy + dx*sin_a + dy*cos_a

    result = []
    for shape in p.get("shapes", []):
        try:
            t = shape["type"]
            if t == "path":
                for sp_str in re.findall(r'[Mm][^Mm]+', shape["d"]):
                    sp = parse_path(sp_str)
                    pts = [tf(sp.point(k/samples).real, sp.point(k/samples).imag)
                           for k in range(samples + 1)]
                    if len(pts) >= 3:
                        result.append(pts)
            elif t == "rect":
                corners = [(shape["x"],            shape["y"]),
                           (shape["x"]+shape["w"], shape["y"]),
                           (shape["x"]+shape["w"], shape["y"]+shape["h"]),
                           (shape["x"],            shape["y"]+shape["h"])]
                result.append([tf(x, y) for x, y in corners])
            elif t in ("circle", "ellipse"):
                r1 = shape.get("r", shape.get("rx", 1))
                r2 = shape.get("r", shape.get("ry", 1))
                cx2, cy2 = shape.get("cx", 0), shape.get("cy", 0)
                pts = [tf(cx2 + r1*math.cos(2*math.pi*k/48),
                          cy2 + r2*math.sin(2*math.pi*k/48))
                       for k in range(49)]
                result.append(pts)
            elif t == "poly" and shape["coords"]:
                result.append([tf(x, y) for x, y in shape["coords"]])
        except Exception:
            pass
    return result


def export_svg(placements, n_pieces, output_folder, piece_sizes=None):
    """
    Export each piece as SVG using the ORIGINAL path data from Illustrator.
    Letters that span multiple pieces are clipped to each piece they overlap,
    so a large letter crossing two pieces appears correctly in both SVGs.
    """
    if piece_sizes is None:
        piece_sizes = {}

    def _piece_size_cm(pi):
        size = piece_sizes.get(pi, "full")
        return PIECE_CONFIGS.get(size, (PIECE_W, PIECE_H))

    # Cache layout origins (mirrors NestingWindow._compute_layout)
    MAX_COL_H_CM = 240.0
    _origin_cache = {}

    def _build_origin_cache():
        if _origin_cache:
            return
        col_x       = 0.0
        col_h       = 0.0
        col_max_w   = 0.0
        for p in range(n_pieces):
            pw, ph = _piece_size_cm(p)
            if col_h > 0 and col_h + ph > MAX_COL_H_CM + 0.01:
                col_x     += col_max_w
                col_h      = 0.0
                col_max_w  = 0.0
            _origin_cache[p] = (col_x, col_h)
            col_h     += ph
            col_max_w  = max(col_max_w, pw)

    def _piece_origin_cm(pi):
        _build_origin_cache()
        return _origin_cache.get(pi, (0.0, 0.0))

    os.makedirs(output_folder, exist_ok=True)
    files = []
    stroke_w_px = 1
    # ── generate SVGs ───────────────────────────────────────────────────────
    XL_SECTION_H = 60.0
    _reg_bleed   = 0.6 + 0.1   # arm_cm + small margin so marks aren't clipped

    def _build_letter_lines(overlapping):
        """Return SVG lines for all letters (no clip — caller adds clip per section)."""
        llines = []
        for letter, dx, dy in overlapping:
            bx0, by0   = letter["bbox_origin"]
            w_px, h_px = letter["bbox_size_px"]
            sc = letter["scale"]; angle = letter["angle"]
            pcx = letter["x"] + letter["actual_w"]/2 + dx
            pcy = letter["y"] + letter["actual_h"]/2 + dy
            cx_svg = bx0 + w_px/2; cy_svg = by0 + h_px/2
            tf = (f"translate({pcx:.6f},{pcy:.6f})"
                  f" rotate({angle:.4f})"
                  f" scale({sc:.10f})"
                  f" translate({-cx_svg:.6f},{-cy_svg:.6f})")
            llines.append(f'<g clip-path="url(#sec)">')
            llines.append(f'  <g transform="{tf}" fill="none" stroke="#ff0000"'
                          f' stroke-width="{stroke_w_px}">')
            for shape in letter.get("shapes", []):
                t = shape["type"]
                if t == "path":
                    llines.append(f'    <path d="{shape["d"]}"/>')
                elif t == "rect":
                    llines.append(f'    <rect x="{shape["x"]}" y="{shape["y"]}"'
                                  f' width="{shape["w"]}" height="{shape["h"]}"/>')
                elif t == "circle":
                    llines.append(f'    <circle cx="{shape["cx"]}" cy="{shape["cy"]}"'
                                  f' r="{shape["r"]}"/>')
                elif t == "ellipse":
                    llines.append(f'    <ellipse cx="{shape["cx"]}" cy="{shape["cy"]}"'
                                  f' rx="{shape["rx"]}" ry="{shape["ry"]}"/>')
                elif t == "poly":
                    pts_str = " ".join(f"{x},{y}" for x,y in shape["coords"])
                    tag = "polygon" if shape.get("closed") else "polyline"
                    llines.append(f'    <{tag} points="{pts_str}"/>')
            llines.append('  </g>')
            llines.append('</g>')
        return llines

    def _write_section(fpath, title, pw, sec_y0, sec_h, letter_lines):
        """
        Write one SVG section file.
        Coordinates stay in PIECE-LOCAL space (0,0 = piece top-left).
        viewBox zooms into [0..pw] × [sec_y0..sec_y0+sec_h].
        The clipPath 'sec' clips letters to this section's rectangle.
        """
        _vx = -_reg_bleed
        _vy = sec_y0 - _reg_bleed
        _vw = pw + 2 * _reg_bleed
        _vh = sec_h + 2 * _reg_bleed
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" overflow="hidden"',
            f'  width="{_vw*10:.2f}mm" height="{_vh*10:.2f}mm"',
            f'  viewBox="{_vx:.4f} {_vy:.4f} {_vw:.4f} {_vh:.4f}">',
            f'<title>{title}</title>',
            f'<defs><clipPath id="sec">',
            f'  <rect x="0" y="{sec_y0:.4f}" width="{pw:.4f}" height="{sec_h:.4f}"/>',
            f'</clipPath></defs>',
        ]
        lines += letter_lines
        lines += _reg_marks_svg(pw, sec_h, y0=sec_y0)
        lines.append('</svg>')
        with open(fpath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return fpath

    for pi in range(n_pieces):
        pw, ph       = _piece_size_cm(pi)
        pi_ox, pi_oy = _piece_origin_cm(pi)
        size         = piece_sizes.get(pi, "full")

        # Collect letters overlapping the full piece (used for all sections)
        full_overlapping = []
        for letter in placements:
            pj = letter["piece"]
            pj_ox, pj_oy = _piece_origin_cm(pj)
            lx0 = pj_ox + letter["x"];  ly0 = pj_oy + letter["y"]
            lx1 = lx0 + letter["actual_w"]; ly1 = ly0 + letter["actual_h"]
            if lx1 > pi_ox and lx0 < pi_ox + pw and \
               ly1 > pi_oy and ly0 < pi_oy + ph:
                full_overlapping.append((letter,
                                         pj_ox - pi_ox,
                                         pj_oy - pi_oy))

        letter_lines = _build_letter_lines(full_overlapping)

        if size == "xl":
            # Generate one SVG per 60cm section — same letter content, different viewport
            n_sections = int(round(ph / XL_SECTION_H))
            labels = "abcdefghij"
            for si in range(n_sections):
                sec_y0 = si * XL_SECTION_H
                sec_h  = min(XL_SECTION_H, ph - sec_y0)
                fpath  = os.path.join(output_folder,
                                      f"pieza_{pi+1:02d}{labels[si]}.svg")
                title  = f"Pieza {pi+1}{labels[si].upper()} ({sec_y0:.0f}-{sec_y0+sec_h:.0f}cm)"
                files.append(_write_section(fpath, title, pw, sec_y0, sec_h, letter_lines))
        else:
            # Single section = the whole piece (sec_y0=0)
            fpath = os.path.join(output_folder, f"pieza_{pi+1:02d}.svg")
            files.append(_write_section(fpath, f"Pieza {pi+1}", pw, 0.0, ph, letter_lines))
        files.append(fpath)
    return files


def export_dxf(placements, n_pieces, output_folder):
    """
    Export each piece as DXF. Uses high-resolution LWPOLYLINE (300 pts/subpath).
    For perfect bezier curves open the SVG in Illustrator and export from there.
    """
    import ezdxf
    os.makedirs(output_folder, exist_ok=True)
    files = []
    MM = 10   # cm → mm
    SAMPLES = 300  # high resolution to minimize faceting

    for pi in range(n_pieces):
        doc = ezdxf.new("R2010")
        doc.units = 4  # mm
        msp = doc.modelspace()
        doc.layers.new("BORDE", dxfattribs={"color": 5})
        doc.layers.new("CORTE", dxfattribs={"color": 1})

        # Piece boundary
        msp.add_lwpolyline(
            [(0,0),(PIECE_W*MM,0),(PIECE_W*MM,PIECE_H*MM),(0,PIECE_H*MM)],
            close=True, dxfattribs={"layer": "BORDE"})

        for letter in [p for p in placements if p["piece"] == pi]:
            for pts in _placement_subpaths_cm(letter, samples=SAMPLES):
                if len(pts) < 2:
                    continue
                mm_pts = [(x*MM, (PIECE_H - y)*MM) for x, y in pts]
                msp.add_lwpolyline(mm_pts, close=True,
                                   dxfattribs={"layer": "CORTE"})

        fpath = os.path.join(output_folder, f"pieza_{pi+1:02d}.dxf")
        doc.saveas(fpath)
        files.append(fpath)
    return files


# ---------------------------------------------------------------------------
# Nesting visualization window
# ---------------------------------------------------------------------------
COLORS = ["#4f86c6","#e05c5c","#3aaa6a","#e07c3a","#8a5cd0",
          "#c45c8a","#3aaab4","#d4a017","#5c8ae0","#7a7a7a"]

class NestingWindow(tk.Toplevel):
    S         = 4.0    # canvas px per cm
    MAX_COL_H = 240.0  # cm máximo por columna (= 1 lámina 240×120)
    COL_GAP   = 130    # px separación entre columnas (room for Vinil checkboxes)
    PAD       = 8      # outer margin (px)

    def __init__(self, parent, n_pieces, placements, n_acrilico,
                 on_change=None, piece_sizes=None, piece_vinil=None,
                 vinil_prices=None):
        super().__init__(parent)
        self.title("Nesting de plantillas")
        self.configure(bg="#f5f5f5")
        self.resizable(True, True)

        self.n_pieces   = n_pieces
        self.placements = placements   # mutable list
        self.selected   = None
        self._drag_ref  = None
        self._drag_last = None
        self._on_change = on_change

        # Use external dict if provided so state persists across open/close
        self.piece_sizes   = piece_sizes if piece_sizes is not None else {}
        # piece_vinil: {pi: "vinil"|"transfer"} — auto-set from layer suffixes _v/_vt
        self.piece_vinil   = piece_vinil if piece_vinil is not None else {}
        _vp = vinil_prices or {}
        self._vinil_unit   = _vp.get("unit",           VINIL_PRECIO_UNIT)
        self._vinil_xtra   = _vp.get("transfer_extra", VINIL_TRANSFER_EXTRA)
        self._angle_var    = None
        self.piece_options = {}   # pi → {"vinil": BooleanVar, "transfer": BooleanVar}
        self._cb_wins      = []   # canvas window IDs for checkboxes

        self._build_ui()
        self._render()
        self.state("zoomed")   # open fullscreen on Windows
        # Fire once so vinil costs are reflected immediately on open
        self.after(50, self._notify)

    # ── UI skeleton ────────────────────────────────────────────────────────
    def _build_ui(self):
        NW_BG  = "#f5f5f5"
        NW_BG2 = "#e8e8e8"
        NW_FG  = "#1a1a1a"
        NW_FG2 = "#666666"
        NW_ACC = "#111111"

        top = tk.Frame(self, bg=NW_BG)
        top.pack(fill="x", padx=10, pady=(10, 0))

        self.hdr = tk.Label(top, text="", bg=NW_BG, fg=NW_ACC,
                             font=("Segoe UI", 11, "bold"))
        self.hdr.pack(side="left")

        # Rotation input (visible when letter selected)
        self._angle_var = tk.StringVar(value="0")
        rot_frame = tk.Frame(top, bg=NW_BG)
        rot_frame.pack(side="left", padx=16)
        tk.Label(rot_frame, text="Angulo:", bg=NW_BG, fg=NW_FG2,
                 font=("Segoe UI", 9)).pack(side="left")
        self._angle_entry = RoundedEntry(rot_frame, textvariable=self._angle_var,
                                         width=5, bg=NW_BG2, fg=NW_FG,
                                         parent_bg=NW_BG, font=("Segoe UI", 10))
        self._angle_entry.pack(side="left", padx=4)
        tk.Label(rot_frame, text="°", bg=NW_BG, fg=NW_FG2,
                 font=("Segoe UI", 9)).pack(side="left")
        RoundedButton(rot_frame, text="-15", bg=NW_BG2, fg=NW_FG,
                      parent_bg=NW_BG, font=("Segoe UI", 8),
                      command=lambda: self._rotate_by(-15), padx=8, pady=4
                      ).pack(side="left", padx=2)
        RoundedButton(rot_frame, text="+15", bg=NW_BG2, fg=NW_FG,
                      parent_bg=NW_BG, font=("Segoe UI", 8),
                      command=lambda: self._rotate_by(15), padx=8, pady=4
                      ).pack(side="left", padx=2)
        self._angle_entry.bind("<Return>", self._on_angle_enter)
        self._angle_entry.bind("<FocusOut>", self._on_angle_enter)

        tk.Label(top, bg=NW_BG, fg=NW_FG2, font=("Segoe UI", 9),
                 text="  Click: seleccionar  │  R: rotar  │  ←→: cambiar pieza  │  Arrastrar: mover"
                 ).pack(side="left")

        self.del_btn = RoundedButton(top, text="× Eliminar última pieza",
                                      bg=NW_BG2, fg="#c0392b", parent_bg=NW_BG,
                                      font=("Segoe UI", 9), padx=10, pady=5,
                                      command=self._del_last_piece)
        self.del_btn.pack(side="right", padx=(4, 0))
        RoundedButton(top, text="+ 240x120", bg=NW_BG2, fg="#27ae60",
                      parent_bg=NW_BG, font=("Segoe UI", 9), padx=8, pady=5,
                      command=lambda: self._add_piece("xl")).pack(side="right", padx=2)
        RoundedButton(top, text="+ 120x60", bg=NW_BG2, fg="#27ae60",
                      parent_bg=NW_BG, font=("Segoe UI", 9), padx=8, pady=5,
                      command=lambda: self._add_piece("full")).pack(side="right", padx=2)
        RoundedButton(top, text="+ 60x120", bg=NW_BG2, fg="#27ae60",
                      parent_bg=NW_BG, font=("Segoe UI", 9), padx=8, pady=5,
                      command=lambda: self._add_piece("tall")).pack(side="right", padx=2)
        RoundedButton(top, text="+ 60x60", bg=NW_BG2, fg="#27ae60",
                      parent_bg=NW_BG, font=("Segoe UI", 9), padx=8, pady=5,
                      command=lambda: self._add_piece("half")).pack(side="right", padx=2)
        RoundedButton(top, text="Exportar…", bg=NW_ACC, fg="#ffffff",
                      parent_bg=NW_BG, font=("Segoe UI", 9, "bold"), padx=12, pady=5,
                      command=self._export).pack(side="right", padx=8)

        cf = tk.Frame(self, bg=NW_BG)
        cf.pack(fill="both", expand=True, padx=10, pady=10)

        self.cv = tk.Canvas(cf, bg="#ffffff", width=1200, height=500)
        vsb = tk.Scrollbar(cf, orient="vertical",   command=self.cv.yview)
        hsb = tk.Scrollbar(cf, orient="horizontal", command=self.cv.xview)
        self.cv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right",  fill="y")
        hsb.pack(side="bottom", fill="x")
        self.cv.pack(side="left", fill="both", expand=True)

        self.cv.bind("<Button-1>",        self._on_click)
        self.cv.bind("<B1-Motion>",       self._on_drag)
        self.cv.bind("<ButtonRelease-1>", self._on_release)
        self.cv.bind("<MouseWheel>",
            lambda e: self.cv.yview_scroll(int(-1*(e.delta/120)), "units"))
        self.cv.bind("<Shift-MouseWheel>",
            lambda e: self.cv.xview_scroll(int(-1*(e.delta/120)), "units"))
        self.bind("<r>", lambda e: self._rotate_by(15))
        self.bind("<R>", lambda e: self._rotate_by(-15))
        self.bind("<Left>",  lambda e: self._shift_piece(-1))
        self.bind("<Right>", lambda e: self._shift_piece(+1))

    # ── geometry helpers ───────────────────────────────────────────────────
    def _piece_dims(self, pi):
        """Canvas (w_px, h_px) and real (w_cm, h_cm) for this piece."""
        S    = self.S
        size = self.piece_sizes.get(pi, "full")
        w_cm, h_cm = PIECE_CONFIGS.get(size, (PIECE_W, PIECE_H))
        return int(w_cm * S), int(h_cm * S), w_cm, h_cm

    def _compute_layout(self):
        """Return dict pi → (canvas_x, canvas_y).
        Columnas de hasta MAX_COL_H cm. Gap entre columnas, sin gap entre filas.
        """
        S, PAD = self.S, self.PAD
        layout      = {}
        col_x_px    = PAD
        col_h_cm    = 0.0
        col_max_w_px = 0

        for pi in range(self.n_pieces):
            pw_px, ph_px, pw_cm, ph_cm = self._piece_dims(pi)
            # Nueva columna si esta pieza no cabe en la altura máxima
            if col_h_cm > 0 and col_h_cm + ph_cm > self.MAX_COL_H + 0.01:
                col_x_px    += col_max_w_px + self.COL_GAP
                col_h_cm     = 0.0
                col_max_w_px = 0

            layout[pi]   = (col_x_px, 44 + PAD + int(col_h_cm * S))
            col_h_cm    += ph_cm
            col_max_w_px = max(col_max_w_px, pw_px)

        self._layout_cache = layout
        return layout

    def _piece_origin(self, pi):
        if not hasattr(self, "_layout_cache"):
            self._compute_layout()
        return self._layout_cache.get(pi, (self.PAD, 44 + self.PAD))

    def _update_scroll(self):
        layout = self._compute_layout()
        if not layout:
            self.cv.configure(scrollregion=(0, 0, 200, 200))
            return
        CB_EXTRA = 120  # px reserved for checkboxes to the right of each piece
        max_x = max(ox + self._piece_dims(pi)[0] + CB_EXTRA for pi, (ox, oy) in layout.items())
        max_y = max(oy + self._piece_dims(pi)[1] for pi, (ox, oy) in layout.items())
        self.cv.configure(scrollregion=(0, 0, max_x + self.PAD, max_y + self.PAD))

    # ── full render ────────────────────────────────────────────────────────
    def _render(self):
        # Remove old checkbox windows
        for wid in self._cb_wins:
            self.cv.delete(wid)
        self._cb_wins.clear()
        self.cv.delete("all")
        self._update_scroll()
        S = self.S

        # Header: count pieces and compute sheet cost
        counts = {"xl": 0, "full": 0, "tall": 0, "half": 0}
        for pi in range(self.n_pieces):
            counts[self.piece_sizes.get(pi, "full")] += 1
        billing = sum(counts[k] * PIECE_BILLING[k] for k in counts)
        n_lam   = billing / 4   # láminas 240x120
        parts   = []
        if counts["xl"]:   parts.append(f"{counts['xl']} × 240x120")
        if counts["full"]: parts.append(f"{counts['full']} × 120x60")
        if counts["tall"]: parts.append(f"{counts['tall']} × 60x120")
        if counts["half"]: parts.append(f"{counts['half']} × 60x60")
        self.hdr.config(text="  +  ".join(parts) + f"  =  {n_lam:.3f} lám. 240x120")

        # Update angle entry to show selected letter's angle
        if self.selected is not None and self.selected < len(self.placements):
            ang = self.placements[self.selected].get("angle", 0)
            self._angle_var.set(f"{ang:.1f}")

        # Piece backgrounds
        for pi in range(self.n_pieces):
            ox, oy = self._piece_origin(pi)
            pw, ph, _, _ = self._piece_dims(pi)
            size_lbl = {"xl": "240x120", "full": "120x60", "tall": "60x120", "half": "60x60"}.get(
                self.piece_sizes.get(pi, "full"), "120x60")
            empty = not any(p["piece"] == pi for p in self.placements)
            self.cv.create_rectangle(ox, oy, ox+pw, oy+ph,
                fill="#f8f8f8" if empty else "#ffffff",
                outline="#cccccc", width=2)
            self.cv.create_text(ox+6, oy+6, anchor="nw",
                text=f"P{pi+1} ({size_lbl})",
                fill="#aaaaaa", font=("Segoe UI", 8))
            m = PIECE_MARGIN * S
            self.cv.create_rectangle(ox+m, oy+m, ox+pw-m, oy+ph-m,
                outline="#dddddd", width=1, dash=(3,3))
            # Registration marks at the 4 corners
            _draw_reg_marks_canvas(self.cv, ox, oy, pw, ph)

            # Guías cada 60cm para piezas XL (120×240)
            if self.piece_sizes.get(pi, "full") == "xl":
                _, _, pw_cm, ph_cm = self._piece_dims(pi)
                g_step = 60.0
                g_y = g_step
                sec = 1
                while g_y < ph_cm - 0.1:
                    gy_px = oy + int(g_y * S)
                    self.cv.create_line(ox, gy_px, ox + pw, gy_px,
                                        fill="#4f86c6", width=1, dash=(6, 3))
                    self.cv.create_text(ox + pw - 4, gy_px - 5, anchor="e",
                                        text=f"— {g_y:.0f} cm —",
                                        fill="#4f86c6", font=("Segoe UI", 7))
                    sec += 1
                    g_y += g_step

            # Checkboxes a la derecha de cada pieza
            if pi not in self.piece_options:
                pv = self.piece_vinil.get(pi)   # "vinil", "transfer", or None
                self.piece_options[pi] = {
                    "vinil":    tk.BooleanVar(value=(pv == "vinil")),
                    "transfer": tk.BooleanVar(value=(pv == "transfer")),
                }
            opts = self.piece_options[pi]

            # Mutual exclusion + live cost update
            def _on_vinil(pi=pi):
                if self.piece_options[pi]["vinil"].get():
                    self.piece_options[pi]["transfer"].set(False)
                self._notify()

            def _on_transfer(pi=pi):
                if self.piece_options[pi]["transfer"].get():
                    self.piece_options[pi]["vinil"].set(False)
                self._notify()

            cb_frame = tk.Frame(self.cv, bg="#f5f5f5", bd=0)
            def _show_size_menu(event, p=pi, frm=cb_frame):
                menu = tk.Menu(frm, tearoff=0)
                labels = [("full","120×60"), ("xl","120×240"), ("tall","60×120"), ("half","60×60")]
                cur = self.piece_sizes.get(p, "full")
                for key, label in labels:
                    txt = f"✓  {label}" if key == cur else f"    {label}"
                    menu.add_command(label=txt, command=lambda k=key: self._set_piece_size(p, k))
                menu.tk_popup(event.x_root, event.y_root)
            size_btn = tk.Button(cb_frame, text="⇄ tamaño",
                      bg="#e8e8e8", fg="#555555", relief="flat", bd=1,
                      font=("Segoe UI", 8), cursor="hand2", pady=2)
            size_btn.bind("<Button-1>", _show_size_menu)
            size_btn.pack(fill="x", pady=(0, 6))
            tk.Checkbutton(cb_frame, text="Vinil",
                           variable=opts["vinil"],
                           command=_on_vinil,
                           bg="#f5f5f5", fg="#1a1a1a",
                           selectcolor="#e8e8e8", activebackground="#f5f5f5",
                           font=("Segoe UI", 8), cursor="hand2").pack(anchor="w")
            tk.Checkbutton(cb_frame, text="Vinil con transfer",
                           variable=opts["transfer"],
                           command=_on_transfer,
                           bg="#f5f5f5", fg="#1a1a1a",
                           selectcolor="#e8e8e8", activebackground="#f5f5f5",
                           font=("Segoe UI", 8), cursor="hand2").pack(anchor="w")
            wid = self.cv.create_window(ox + pw + 8, oy + 6,
                                         anchor="nw", window=cb_frame)
            self._cb_wins.append(wid)

        # Letters
        for i, p in enumerate(self.placements):
            self._render_letter(i, p, selected=(i == self.selected))

        # Delete-button state
        last = self.n_pieces - 1
        self.del_btn.config(state="normal" if self.n_pieces > 1 else "disabled")

    # ── render one letter ──────────────────────────────────────────────────
    def _render_letter(self, idx, p, selected=False):
        S   = self.S
        ox, oy = self._piece_origin(p["piece"])
        tag = f"pl_{idx}"
        color   = COLORS[idx % len(COLORS)]
        outline = "#111111" if selected else "#ffffff"
        width   = 2        if selected else 1

        bx0, by0   = p.get("bbox_origin",  (0, 0))
        w_px, h_px = p.get("bbox_size_px", (1, 1))
        sc  = p.get("scale", 1.0)
        ang = p.get("angle", 0.0)
        cos_a, sin_a = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        pcx = p["x"] + p["actual_w"] / 2
        pcy = p["y"] + p["actual_h"] / 2
        cx_svg, cy_svg = bx0 + w_px/2, by0 + h_px/2

        def tc(px_, py_,
               _cx=cx_svg, _cy=cy_svg, _sc=sc,
               _ca=cos_a, _sa=sin_a,
               _ox=ox, _oy=oy, _pcx=pcx, _pcy=pcy):
            dx = (px_-_cx)*_sc;  dy = (py_-_cy)*_sc
            return (_ox+(_pcx + dx*_ca - dy*_sa)*S,
                    _oy+(_pcy + dx*_sa + dy*_ca)*S)

        # Invisible hitbox for click detection
        lx = ox + p["x"]*S;  ly = oy + p["y"]*S
        self.cv.create_rectangle(lx, ly,
            lx + p["actual_w"]*S, ly + p["actual_h"]*S,
            fill="", outline="", tags=(tag, "hitbox"))

        for shape in p.get("shapes", []):
            try:
                t = shape["type"]
                if t == "path":
                    self._draw_path_shape(shape["d"], tc, color, tag, outline, width)
                elif t == "rect":
                    corners = [(shape["x"],           shape["y"]),
                               (shape["x"]+shape["w"],shape["y"]),
                               (shape["x"]+shape["w"],shape["y"]+shape["h"]),
                               (shape["x"],           shape["y"]+shape["h"])]
                    pts = [c for x2,y2 in corners for c in tc(x2,y2)]
                    self.cv.create_polygon(pts, fill=color,
                        outline=outline, width=width, tags=tag)
                elif t in ("circle", "ellipse"):
                    r1 = shape.get("r", shape.get("rx", 1))
                    r2 = shape.get("r", shape.get("ry", 1))
                    cx2, cy2 = shape.get("cx",0), shape.get("cy",0)
                    pts = []
                    for k in range(32):
                        a = 2*math.pi*k/32
                        pts += list(tc(cx2+r1*math.cos(a), cy2+r2*math.sin(a)))
                    self.cv.create_polygon(pts, fill=color,
                        outline=outline, width=width, tags=tag)
                elif t == "poly":
                    pts = [c for x2,y2 in shape["coords"] for c in tc(x2,y2)]
                    if len(pts)>=6:
                        self.cv.create_polygon(pts, fill=color,
                            outline=outline, width=width, tags=tag)
            except Exception:
                pass

        # Label
        fs = max(7, min(11, int(min(p["actual_w"], p["actual_h"])*S/4)))
        self.cv.create_text(ox+pcx*S, oy+pcy*S, text=p["name"],
            fill="#1e1e2e", font=("Segoe UI", fs, "bold"), tags=tag)

    def _draw_path_shape(self, d, tc, color, tag, outline, width, samples=80):
        import re
        for sp_str in re.findall(r'[Mm][^Mm]+', d):
            try:
                sp = parse_path(sp_str)
                pts = []
                for k in range(samples+1):
                    c = sp.point(k/samples)
                    pts += list(tc(c.real, c.imag))
                if len(pts) >= 6:
                    self.cv.create_polygon(pts, fill=color, outline=outline,
                        smooth=True, width=width, tags=tag)
            except Exception:
                pass

    # ── mouse events ───────────────────────────────────────────────────────
    def _on_click(self, event):
        x = self.cv.canvasx(event.x)
        y = self.cv.canvasy(event.y)

        found = None
        for item in reversed(self.cv.find_overlapping(x-6, y-6, x+6, y+6)):
            for tag in self.cv.gettags(item):
                if tag.startswith("pl_"):
                    found = int(tag[3:]); break
            if found is not None: break

        prev = self.selected
        self.selected = found
        if found is not None:
            pl = self.placements[found]
            ox, oy = self._piece_origin(pl["piece"])
            self._drag_ref  = {"sx": x, "sy": y,
                                "orig_x": pl["x"], "orig_y": pl["y"],
                                "orig_piece": pl["piece"],
                                "orig_ox": ox, "orig_oy": oy}
            self._drag_last = (x, y)
        else:
            self._drag_ref = self._drag_last = None

        if prev != found:
            self._render()

    def _on_drag(self, event):
        if self.selected is None or self._drag_last is None: return
        x = self.cv.canvasx(event.x)
        y = self.cv.canvasy(event.y)
        ddx, ddy = x-self._drag_last[0], y-self._drag_last[1]
        self._drag_last = (x, y)
        self.cv.move(f"pl_{self.selected}", ddx, ddy)

    def _on_release(self, event):
        if self.selected is None or self._drag_ref is None: return
        x = self.cv.canvasx(event.x)
        y = self.cv.canvasy(event.y)

        ref = self._drag_ref
        S   = self.S
        PW  = int(PIECE_W*S);  PH = int(PIECE_H*S)
        pl  = self.placements[self.selected]

        # Find which piece the cursor is over
        target = ref["orig_piece"]
        for pi in range(self.n_pieces):
            ox, oy = self._piece_origin(pi)
            if ox <= x <= ox+PW and oy <= y <= oy+PH:
                target = pi; break

        # Compute new letter position relative to target piece
        t_ox, t_oy = self._piece_origin(target)
        total_dx = x - ref["sx"]
        total_dy = y - ref["sy"]
        orig_canvas_x = ref["orig_ox"] + ref["orig_x"]*S
        orig_canvas_y = ref["orig_oy"] + ref["orig_y"]*S
        pl["x"] = (orig_canvas_x + total_dx - t_ox) / S
        pl["y"] = (orig_canvas_y + total_dy - t_oy) / S
        pl["piece"] = target

        # Clamp within piece margins (use piece-specific dimensions)
        _, _, pw_cm, ph_cm = self._piece_dims(target)
        pl["x"] = max(PIECE_MARGIN, min(pl["x"], pw_cm-PIECE_MARGIN-pl["actual_w"]))
        pl["y"] = max(PIECE_MARGIN, min(pl["y"], ph_cm-PIECE_MARGIN-pl["actual_h"]))

        self._drag_ref = self._drag_last = None
        self._render()

    # ── rotation ───────────────────────────────────────────────────────────
    def _rotate_by(self, delta_deg):
        if self.selected is None: return
        pl = self.placements[self.selected]
        new_angle = (pl["angle"] + delta_deg) % 360
        self._apply_angle(pl, new_angle)
        self._render()

    def _on_angle_enter(self, event=None):
        if self.selected is None: return
        try:
            new_angle = float(self._angle_var.get()) % 360
        except ValueError:
            return
        pl = self.placements[self.selected]
        self._apply_angle(pl, new_angle)
        self._render()

    @staticmethod
    def _apply_angle(pl, new_angle):
        """Apply rotation: swap actual_w/h only on 90° crossings."""
        old_q = int(pl["angle"] / 90) % 2
        new_q = int(new_angle  / 90) % 2
        if old_q != new_q:
            pl["actual_w"], pl["actual_h"] = pl["actual_h"], pl["actual_w"]
        pl["angle"] = new_angle

    def _shift_piece(self, delta):
        if self.selected is None: return
        pl = self.placements[self.selected]
        new_pi = pl["piece"] + delta
        if 0 <= new_pi < self.n_pieces:
            pl["piece"] = new_pi
            pl["x"] = PIECE_MARGIN + LETTER_GAP/2
            pl["y"] = PIECE_MARGIN + LETTER_GAP/2
            self._render()

    # ── piece management ───────────────────────────────────────────────────
    def _notify(self):
        if self._on_change:
            counts = {"xl": 0, "full": 0, "tall": 0, "half": 0}
            for pi in range(self.n_pieces):
                counts[self.piece_sizes.get(pi, "full")] += 1

            # Vinil cost: sum across pieces that have vinil or vinil+transfer checked
            c_vinil = 0.0
            for pi in range(self.n_pieces):
                opts = self.piece_options.get(pi)
                if opts is None:
                    continue
                units = PIECE_BILLING.get(self.piece_sizes.get(pi, "full"), 1.0)
                if opts["transfer"].get():
                    c_vinil += units * (self._vinil_unit + self._vinil_xtra)
                elif opts["vinil"].get():
                    c_vinil += units * self._vinil_unit

            self._on_change(counts["xl"], counts["full"] + counts["tall"], counts["half"],
                            c_vinil=c_vinil)

    # ── export ─────────────────────────────────────────────────────────────
    def _export(self):
        win = tk.Toplevel(self)
        win.title("Exportar para laser")
        win.configure(bg="#1e1e2e")
        win.resizable(False, False)
        win.grab_set()

        tk.Label(win, text="Formato de exportacion", bg="#1e1e2e", fg="#cba6f7",
                 font=("Segoe UI", 11, "bold")).pack(padx=24, pady=(18, 8))

        fmt_var = tk.StringVar(value="svg")
        for val, label in [("svg",  "SVG  (Illustrator, Inkscape, LightBurn)"),
                            ("dxf",  "DXF  (LightBurn, RDWorks, AutoCAD)"),
                            ("both", "SVG + DXF")]:
            tk.Radiobutton(win, text=label, variable=fmt_var, value=val,
                           bg="#1e1e2e", fg="#cdd6f4", selectcolor="#313244",
                           activebackground="#1e1e2e",
                           font=("Segoe UI", 10)).pack(anchor="w", padx=24)

        tk.Label(win,
                 text="SVG: curvas bezier exactas de Illustrator (recomendado)\n"
                      "DXF: polilineas de alta resolucion (para LightBurn/RDWorks)\n"
                      "Capa CORTE (rojo) = lineas de corte\n"
                      "Capa BORDE (azul) = borde 120x60 cm de referencia",
                 bg="#1e1e2e", fg="#6c7086",
                 font=("Segoe UI", 9), justify="left").pack(padx=24, pady=(10, 4))

        def do_export():
            folder = filedialog.askdirectory(title="Carpeta de destino")
            if not folder:
                return
            fmt = fmt_var.get()
            try:
                files = []
                if fmt in ("svg", "both"):
                    files += export_svg(self.placements, self.n_pieces, folder,
                                        piece_sizes=self.piece_sizes)
                if fmt in ("dxf", "both"):
                    files += export_dxf(self.placements, self.n_pieces, folder)
                win.destroy()
                messagebox.showinfo("Exportacion completa",
                                    f"Se exportaron {len(files)} archivos en:\n{folder}")
                os.startfile(folder)
            except Exception as e:
                messagebox.showerror("Error al exportar", str(e))

        RoundedButton(win, text="Elegir carpeta y exportar",
                      bg="#111111", fg="#ffffff", parent_bg=win.cget("bg"),
                      font=("Segoe UI", 10, "bold"), padx=16, pady=8,
                      command=do_export).pack(pady=(12, 18), padx=24)

    def _set_piece_size(self, pi, size):
        self.piece_sizes[pi] = size
        _, _, pw_cm, ph_cm = self._piece_dims(pi)
        for pl in self.placements:
            if pl["piece"] == pi:
                pl["x"] = max(PIECE_MARGIN, min(pl["x"], pw_cm - PIECE_MARGIN - pl["actual_w"]))
                pl["y"] = max(PIECE_MARGIN, min(pl["y"], ph_cm - PIECE_MARGIN - pl["actual_h"]))
        self._render()
        self._notify()

    def _cycle_piece(self, pi):
        cur = self.piece_sizes.get(pi, "full")
        nxt = {"full": "xl", "xl": "tall", "tall": "half", "half": "full"}.get(cur, "full")
        self._set_piece_size(pi, nxt)

    def _add_piece(self, size="full"):
        self.piece_sizes[self.n_pieces] = size
        self.n_pieces += 1
        self._render()
        self._notify()

    def _del_last_piece(self):
        last = self.n_pieces - 1
        if last < 1: return
        # Mover letras de la última pieza a la penúltima
        dest = last - 1
        _, _, pw_cm, ph_cm = self._piece_dims(dest)
        for pl in self.placements:
            if pl["piece"] == last:
                pl["piece"] = dest
                pl["x"] = max(PIECE_MARGIN, min(pl["x"], pw_cm - PIECE_MARGIN - pl["actual_w"]))
                pl["y"] = max(PIECE_MARGIN, min(pl["y"], ph_cm - PIECE_MARGIN - pl["actual_h"]))
        self.piece_sizes.pop(last, None)
        self.n_pieces -= 1
        self._render()
        self._notify()


# ---------------------------------------------------------------------------
# Settings window
# ---------------------------------------------------------------------------
class AluminumWindow(tk.Toplevel):
    """
    Visual layout of aluminum strips on 240x120 sheets.
    Strips are cut along the 120cm axis (guillotine limit).
    Each strip is STRIP_W cm wide × max 120cm long.
    Strips are stacked in columns along the 240cm axis.
    """
    SHEET_W = 240.0
    SHEET_H = 120.0
    S       = 3.5   # canvas px per cm
    COLS    = 3
    PAD     = 8     # outer margin (px)
    GAP     = 0     # gap between sheets (flush)

    def __init__(self, parent, letter_perims_cm, letter_names, n_sheets,
                 strip_w=5.0, title="Aluminio", merma=0.40):
        super().__init__(parent)
        self.title(f"Distribucion de {title}")
        self.configure(bg="#f5f5f5")
        self.resizable(True, True)
        self.STRIP_W = strip_w
        self.MERMA   = merma
        self._build(letter_perims_cm, letter_names, n_sheets)

    def _build(self, perims, names, n_sheets_calc):
        S, GAP, COLS = self.S, self.GAP, self.COLS
        SW = int(self.SHEET_W * S)
        SH = int(self.SHEET_H * S)

        # ── packing ───────────────────────────────────────────────────────
        # Each strip: STRIP_W wide × up to SHEET_H (120cm) long
        # Pack in columns: cur_col_x = position along 240cm axis
        #                  cur_y     = position within current column (120cm axis)
        strips = sorted(zip(perims, names), reverse=True)

        sheets   = [[]]   # list of [(x, y, w, h, name), ...]
        col_x    = 0.0    # current column left edge (along 240cm)
        col_y    = 0.0    # used height in current column (along 120cm)
        color_idx = 0

        letter_colors = {}  # name → color index (consistent across splits)

        def start_new_column():
            nonlocal col_x, col_y
            col_x += self.STRIP_W
            col_y  = 0.0

        def start_new_sheet():
            nonlocal col_x, col_y
            sheets.append([])
            col_x = 0.0
            col_y = 0.0

        for perim, name in strips:
            if name not in letter_colors:
                letter_colors[name] = color_idx
                color_idx += 1
            remaining = perim

            while remaining > 0.01:
                if col_y >= self.SHEET_H - 0.1:
                    start_new_column()
                if col_x + self.STRIP_W > self.SHEET_W + 0.1:
                    start_new_sheet()

                seg_len = min(remaining, self.SHEET_H - col_y)
                sheets[-1].append((col_x, col_y, self.STRIP_W, seg_len, name, False))
                col_y    += seg_len
                remaining -= seg_len

        # ── merma — tiras adicionales en gris ─────────────────────────────
        merma_pct = int(self.MERMA * 100)
        merma_remaining = sum(perims) * self.MERMA
        while merma_remaining > 0.01:
            if col_y >= self.SHEET_H - 0.1:
                start_new_column()
            if col_x + self.STRIP_W > self.SHEET_W + 0.1:
                start_new_sheet()
            seg_len = min(merma_remaining, self.SHEET_H - col_y)
            sheets[-1].append((col_x, col_y, self.STRIP_W, seg_len, f"Merma {merma_pct}%", True))
            col_y          += seg_len
            merma_remaining -= seg_len

        # ── canvas ────────────────────────────────────────────────────────
        PAD = self.PAD
        n = len(sheets)
        rows = math.ceil(n / COLS)
        cw = PAD + COLS * SW + PAD
        ch = 50 + PAD + rows * SH + PAD

        header = tk.Label(
            self, bg="#f5f5f5", fg="#1a1a1a", font=("Segoe UI", 11, "bold"),
            text=f"{n} hojas 240x120 cm  |  tiras {self.STRIP_W} cm x max 120 cm  "
                 f"|  gris = merma {merma_pct}%")
        header.pack(padx=10, pady=(10, 0), anchor="w")

        frame = tk.Frame(self, bg="#f5f5f5")
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        cv = tk.Canvas(frame, bg="#ffffff",
                       width=min(cw, 1200), height=min(ch, 700),
                       scrollregion=(0, 0, cw, ch))
        vsb = tk.Scrollbar(frame, orient="vertical",   command=cv.yview)
        hsb = tk.Scrollbar(frame, orient="horizontal", command=cv.xview)
        cv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        cv.pack(side="left", fill="both", expand=True)

        # Axis labels
        cv.create_text(PAD + SW//2, 14, text="← 240 cm →",
                       fill="#aaaaaa", font=("Segoe UI", 8))

        for si, sheet in enumerate(sheets):
            col = si % COLS
            row = si // COLS
            ox = PAD + col * SW
            oy = 30 + PAD + row * SH

            # Sheet background
            cv.create_rectangle(ox, oy, ox+SW, oy+SH,
                                 fill="#f8f8f8", outline="#cccccc", width=2)
            cv.create_text(ox+6, oy+5, anchor="nw",
                           text=f"Hoja {si+1}", fill="#aaaaaa",
                           font=("Segoe UI", 8))

            # Column guides (every STRIP_W)
            cols_n = int(self.SHEET_W / self.STRIP_W)
            for ci in range(1, cols_n):
                lx = ox + ci * self.STRIP_W * S
                cv.create_line(lx, oy, lx, oy+SH,
                               fill="#e0e0e0", width=1)

            # Draw strips
            for (sx, sy, sw, sh, sname, is_merma) in sheet:
                if is_merma:
                    color   = "#dddddd"
                    outline = "#cccccc"
                    txt_col = "#aaaaaa"
                else:
                    cidx    = letter_colors.get(sname, 0)
                    color   = COLORS[cidx % len(COLORS)]
                    outline = "#ffffff"
                    txt_col = "#ffffff"
                x1 = ox + sx * S
                y1 = oy + sy * S
                x2 = x1 + sw * S
                y2 = y1 + sh * S
                cv.create_rectangle(x1, y1, x2, y2,
                                    fill=color, outline=outline,
                                    width=1, stipple="gray25" if is_merma else "")
                if sh * S > 14:
                    txt = f"{'~' if is_merma else ''}{sname}\n{sh:.0f}cm"
                    cv.create_text((x1+x2)/2, (y1+y2)/2, text=txt,
                                   fill=txt_col, justify="center",
                                   font=("Segoe UI",
                                         max(6, min(8, int(sw*S/3))), "bold"))


def export_paper_svg(sign_w_cm, sign_h_cm, papel_cfg, letter_bboxes_cm, output_folder):
    """
    Export one SVG per paper sheet, with letters centered inside full sheets.
    letter_bboxes_cm: list of {name, x, y, w, h, shapes}
      shapes with type="path" carry {d, ox, oy, scale} (original SVG px coords).
      other shape types carry coords already in sign-space cm.
    """
    pw = papel_cfg.get("ancho_cm", 120)
    ph = papel_cfg.get("alto_cm",   60)

    cols_n = max(1, math.ceil(sign_w_cm / pw))
    rows_n = max(1, math.ceil(sign_h_cm / ph))

    total_w = cols_n * pw
    total_h = rows_n * ph
    logo_off_x = (total_w - sign_w_cm) / 2
    logo_off_y = (total_h - sign_h_cm) / 2

    bleed = 0.7   # cm extra around sheet for reg marks

    os.makedirs(output_folder, exist_ok=True)
    files = []

    def _letter_svg_lines(logo_ox_shift, logo_oy_shift):
        """
        Return SVG lines for all letters shifted into sheet-local space.
        logo_ox_shift = logo_off_x - col*pw  (how far the logo origin is from sheet left)
        logo_oy_shift = logo_off_y - row*ph
        """
        stroke_w = 1   # px in illustrator space — will look correct after scale
        llines = []
        for lb in letter_bboxes_cm:
            for shape in lb.get("shapes", []):
                t = shape["type"]
                if t == "path":
                    sc   = shape["scale"]   # SVG px → cm
                    ox_s = shape["ox"]      # sign origin in SVG px
                    oy_s = shape["oy"]
                    # transform: sheet-local ← sign-space ← SVG-px
                    # x_sheet = (x_svg - ox_s)*sc + logo_ox_shift
                    # = scale(sc) translate(-ox_s,-oy_s) then translate(logo_ox_shift, logo_oy_shift)
                    tf = (f"translate({logo_ox_shift:.6f},{logo_oy_shift:.6f})"
                          f" scale({sc:.10f})"
                          f" translate({-ox_s:.4f},{-oy_s:.4f})")
                    llines.append(f'<g clip-path="url(#sheet)">')
                    llines.append(f'  <g transform="{tf}" fill="none" stroke="#ff0000"'
                                  f' stroke-width="{stroke_w}">')
                    llines.append(f'    <path d="{shape["d"]}"/>')
                    llines.append('  </g></g>')
                elif t == "rect":
                    x = shape["x"] + logo_ox_shift
                    y = shape["y"] + logo_oy_shift
                    llines.append(
                        f'<rect x="{x:.4f}" y="{y:.4f}" width="{shape["w"]:.4f}"'
                        f' height="{shape["h"]:.4f}" clip-path="url(#sheet)"'
                        f' fill="none" stroke="#ff0000" stroke-width="0.05"/>')
                elif t == "circle":
                    cx = shape["cx"] + logo_ox_shift
                    cy = shape["cy"] + logo_oy_shift
                    llines.append(
                        f'<circle cx="{cx:.4f}" cy="{cy:.4f}" r="{shape["r"]:.4f}"'
                        f' clip-path="url(#sheet)" fill="none"'
                        f' stroke="#ff0000" stroke-width="0.05"/>')
                elif t == "ellipse":
                    cx = shape["cx"] + logo_ox_shift
                    cy = shape["cy"] + logo_oy_shift
                    llines.append(
                        f'<ellipse cx="{cx:.4f}" cy="{cy:.4f}"'
                        f' rx="{shape["rx"]:.4f}" ry="{shape["ry"]:.4f}"'
                        f' clip-path="url(#sheet)" fill="none"'
                        f' stroke="#ff0000" stroke-width="0.05"/>')
                elif t == "poly":
                    pts = " ".join(
                        f"{x+logo_ox_shift:.4f},{y+logo_oy_shift:.4f}"
                        for x, y in shape["coords"])
                    tag = "polygon" if shape.get("closed") else "polyline"
                    llines.append(
                        f'<{tag} points="{pts}" clip-path="url(#sheet)"'
                        f' fill="none" stroke="#ff0000" stroke-width="0.05"/>')
        return llines

    n = 0
    for row in range(rows_n):
        for col in range(cols_n):
            n += 1
            lox = logo_off_x - col * pw   # logo origin in sheet-local x (cm)
            loy = logo_off_y - row * ph   # logo origin in sheet-local y (cm)

            vx = -bleed;  vy = -bleed
            vw = pw + 2*bleed;  vh = ph + 2*bleed

            lines = [
                '<?xml version="1.0" encoding="UTF-8"?>',
                f'<svg xmlns="http://www.w3.org/2000/svg" overflow="hidden"',
                f'  width="{vw*10:.2f}mm" height="{vh*10:.2f}mm"',
                f'  viewBox="{vx:.4f} {vy:.4f} {vw:.4f} {vh:.4f}">',
                f'<title>Papel plantilla {n} de {cols_n*rows_n}</title>',
                '<defs><clipPath id="sheet">',
                f'  <rect x="0" y="0" width="{pw:.4f}" height="{ph:.4f}"/>',
                '</clipPath></defs>',
            ]
            lines += _letter_svg_lines(lox, loy)
            lines += _reg_marks_svg(pw, ph)
            lines.append('</svg>')

            fpath = os.path.join(output_folder, f"papel_{n:02d}.svg")
            with open(fpath, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            files.append(fpath)

    return files


class PaperWindow(tk.Toplevel):
    """
    Visualización de la plantilla de papel del anuncio.
    Muestra el anuncio completo (letras en su posición real) con las líneas
    de corte de los pliegos encima, sin separación entre ellos.
    """
    PAD = 30   # canvas padding (px) around sign
    MAX_S = 6.0  # max scale px/cm

    def __init__(self, parent, sign_w_cm, sign_h_cm, papel_cfg, n_papel,
                 letter_bboxes_cm=None):
        super().__init__(parent)
        self.title("Plantilla de papel")
        self.configure(bg="#f5f5f5")
        self.resizable(True, True)
        self._sign_w   = sign_w_cm
        self._sign_h   = sign_h_cm
        self._papel_cfg = papel_cfg
        self._letter_bboxes = letter_bboxes_cm or []
        self._build(sign_w_cm, sign_h_cm, papel_cfg, n_papel,
                    letter_bboxes_cm or [])

    def _build(self, sign_w, sign_h, papel_cfg, n_papel, letter_bboxes):
        PAD = self.PAD
        pw  = papel_cfg.get("ancho_cm", 120)   # sheet width  (e.g. 120 cm)
        ph  = papel_cfg.get("alto_cm",  60)    # sheet height (e.g.  60 cm)

        # Number of full sheets needed
        cols_n  = max(1, math.ceil(sign_w / pw))
        rows_n  = max(1, math.ceil(sign_h / ph))
        n_real  = cols_n * rows_n

        # Total canvas area = full sheets (always >= sign size)
        total_w = cols_n * pw   # cm
        total_h = rows_n * ph   # cm

        # Scale to fit screen nicely
        S = min(self.MAX_S,
                (1100 - 2*PAD) / max(total_w, 1),
                (600  - 2*PAD) / max(total_h, 1))
        S = max(S, 0.5)

        total_w_px = int(total_w * S)
        total_h_px = int(total_h * S)
        cw = total_w_px + 2 * PAD
        ch = total_h_px + 2 * PAD + 50   # 50px header

        # Logo offset: centered inside the sheet grid
        logo_off_x = (total_w - sign_w) / 2   # cm
        logo_off_y = (total_h - sign_h) / 2   # cm

        # ── header ────────────────────────────────────────────────────────
        hdr_row = tk.Frame(self, bg="#f5f5f5")
        hdr_row.pack(fill="x", padx=10, pady=(10, 0))
        tk.Label(
            hdr_row, bg="#f5f5f5", fg="#1a1a1a", font=("Segoe UI", 11, "bold"),
            text=(f"{n_real} pliegos {pw:.0f}×{ph:.0f} cm  │  "
                  f"anuncio {sign_w:.1f}×{sign_h:.1f} cm  │  "
                  f"centrado en {total_w:.0f}×{total_h:.0f} cm")
        ).pack(side="left")

        def _do_export():
            folder = filedialog.askdirectory(title="Carpeta de exportación SVG papel")
            if not folder:
                return
            files = export_paper_svg(
                self._sign_w, self._sign_h,
                self._papel_cfg, self._letter_bboxes, folder)
            messagebox.showinfo("Exportado",
                f"{len(files)} archivo(s) SVG guardados en:\n{folder}")

        RoundedButton(hdr_row, text="Exportar SVG…", bg="#111111", fg="#ffffff",
                      parent_bg=hdr_row.cget("bg"),
                      font=("Segoe UI", 9, "bold"), padx=12, pady=5,
                      command=_do_export).pack(side="right", padx=(8, 0))

        tk.Label(
            self, bg="#f5f5f5", fg="#666666", font=("Segoe UI", 9),
            text="Plantillas completas 120×60 cm. El anuncio está centrado. "
                 "Imprime a escala 1:1 y únelos con cinta."
        ).pack(padx=10, pady=(0, 4), anchor="w")

        # ── canvas ────────────────────────────────────────────────────────
        frame = tk.Frame(self, bg="#f5f5f5")
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        cv = tk.Canvas(frame, bg="#ffffff",
                       width=min(cw, 1200), height=min(ch, 700),
                       scrollregion=(0, 0, cw, ch))
        vsb = tk.Scrollbar(frame, orient="vertical",   command=cv.yview)
        hsb = tk.Scrollbar(frame, orient="horizontal", command=cv.xview)
        cv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right",  fill="y")
        hsb.pack(side="bottom", fill="x")
        cv.pack(side="left", fill="both", expand=True)

        # Canvas origin = top-left of the sheet grid
        ox = PAD
        oy = PAD

        # ── sheet backgrounds (one per cell) ──────────────────────────────
        for r in range(rows_n):
            for c in range(cols_n):
                sx = ox + int(c * pw * S)
                sy = oy + int(r * ph * S)
                sw = int(pw * S)
                sh = int(ph * S)
                cv.create_rectangle(sx, sy, sx + sw, sy + sh,
                                    fill="#f8f8f8", outline="#cccccc", width=2)
                # Sheet label (small, top-left of each sheet)
                lbl = f"P{r * cols_n + c + 1}  {pw:.0f}×{ph:.0f} cm"
                cv.create_text(sx + 6, sy + 6, anchor="nw", text=lbl,
                               fill="#aaaaaa", font=("Segoe UI", 7))

        # ── letters (actual shapes, offset to logo position) ──────────────
        # logo_ox/oy = canvas px origin of sign content
        logo_ox = ox + int(logo_off_x * S)
        logo_oy = oy + int(logo_off_y * S)

        for i, lb in enumerate(letter_bboxes):
            color  = COLORS[i % len(COLORS)]
            shapes = lb.get("shapes", [])
            if shapes:
                _draw_shapes_on_canvas(cv, shapes, S, logo_ox, logo_oy,
                                       fill=color, outline="#ffffff")
            else:
                lx = logo_ox + int(lb["x"] * S)
                ly = logo_oy + int(lb["y"] * S)
                lw = max(4, int(lb["w"] * S))
                lh = max(4, int(lb["h"] * S))
                cv.create_rectangle(lx, ly, lx + lw, ly + lh,
                                    fill=color, outline="#ffffff", width=1)
            # Name label at center of letter bbox
            lx     = logo_ox + int((lb["x"] + lb["w"] / 2) * S)
            ly     = logo_oy + int((lb["y"] + lb["h"] / 2) * S)
            lw_px  = max(4, int(lb["w"] * S))
            lh_px  = max(4, int(lb["h"] * S))
            if lw_px > 16 and lh_px > 10:
                cv.create_text(lx, ly, text=lb["name"],
                               fill="#ffffff", font=("Segoe UI", 8, "bold"),
                               width=lw_px - 4)

        # ── sign bounding-box outline (blue) ──────────────────────────────
        cv.create_rectangle(
            logo_ox, logo_oy,
            logo_ox + int(sign_w * S), logo_oy + int(sign_h * S),
            fill="", outline="#4f86c6", width=2)

        # ── sheet grid lines (over everything) ────────────────────────────
        for c in range(1, cols_n):
            lx = ox + int(c * pw * S)
            cv.create_line(lx, oy, lx, oy + total_h_px,
                           fill="#e07c3a", width=2, dash=(8, 4))
        for r in range(1, rows_n):
            ly = oy + int(r * ph * S)
            cv.create_line(ox, ly, ox + total_w_px, ly,
                           fill="#e07c3a", width=2, dash=(8, 4))

        # ── column width labels (below grid) ─────────────────────────────
        for c in range(cols_n):
            mid_x = ox + int((c + 0.5) * pw * S)
            cv.create_text(mid_x, oy + total_h_px + 10,
                           text=f"{pw:.0f} cm",
                           fill="#aaaaaa", font=("Segoe UI", 7))

        # ── row height labels (left of grid) ─────────────────────────────
        for r in range(rows_n):
            mid_y = oy + int((r + 0.5) * ph * S)
            cv.create_text(ox - 8, mid_y,
                           text=f"{ph:.0f} cm",
                           fill="#aaaaaa", font=("Segoe UI", 7), anchor="e")


class SettingsWindow(tk.Toplevel):
    BG  = "#f5f5f5"
    BG2 = "#e8e8e8"
    FG  = "#1a1a1a"
    ACC = "#111111"

    def __init__(self, parent, cfg, on_save):
        super().__init__(parent)
        self.title("Precios y configuración")
        self.resizable(True, True)
        self.configure(bg=self.BG)
        self.grab_set()
        self.cfg = json.loads(json.dumps(cfg))  # deep copy
        self.on_save = on_save
        self._build()

    # ── helpers ────────────────────────────────────────────────────────────
    def _lbl(self, parent, text, bold=False):
        font = ("Segoe UI", 10, "bold") if bold else ("Segoe UI", 10)
        return tk.Label(parent, text=text, bg=self.BG, fg=self.FG, font=font)

    def _entry(self, parent, value, width=12):
        var = tk.StringVar(value=str(value))
        e = RoundedEntry(parent, textvariable=var, width=width,
                         bg=self.BG2, fg=self.FG,
                         parent_bg=self.BG, font=("Segoe UI", 10))
        return e, var

    def _sep(self, parent):
        tk.Frame(parent, bg="#dddddd", height=1).pack(fill="x", pady=6)

    # ── main layout ────────────────────────────────────────────────────────
    def _build(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=12)

        # style tabs dark
        s = ttk.Style(self)
        s.configure("TNotebook",        background=self.BG, borderwidth=0)
        s.configure("TNotebook.Tab",    background=self.BG2, foreground=self.FG,
                                         padding=[10, 4])
        s.map("TNotebook.Tab",          background=[("selected", "#cccccc")])

        t1 = tk.Frame(nb, bg=self.BG); nb.add(t1, text="  Materiales  ")
        t2 = tk.Frame(nb, bg=self.BG); nb.add(t2, text="  Vinil  ")
        t3 = tk.Frame(nb, bg=self.BG); nb.add(t3, text="  Papel plantilla  ")
        t4 = tk.Frame(nb, bg=self.BG); nb.add(t4, text="  Básicos  ")
        t5 = tk.Frame(nb, bg=self.BG); nb.add(t5, text="  Fuentes  ")

        self._tab_materiales(t1)
        self._tab_vinil(t2)
        self._tab_papel(t3)
        self._tab_basicos(t4)
        self._tab_fuentes(t5)

        RoundedButton(self, text="  Guardar  ", bg=self.ACC, fg="#ffffff",
                      parent_bg=self.BG,
                      font=("Segoe UI", 11, "bold"), padx=20, pady=8,
                      command=self._save).pack(pady=(0, 14))

    def _price_row(self, parent, row, label, key, section="precios"):
        self._lbl(parent, label).grid(row=row, column=0, sticky="w",
                                      padx=14, pady=5)
        val = self.cfg.get(section, self.cfg["precios"]).get(key, 0)
        e, var = self._entry(parent, val)
        e.grid(row=row, column=1, padx=14, pady=5)
        return var

    # ── Tab 1: Materiales ──────────────────────────────────────────────────
    def _tab_materiales(self, f):
        self._lbl(f, "Materiales y mano de obra", bold=True).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12,4))
        self.mat_vars = {}
        fields = [
            ("Lámina Acrílico Z2 240×120 (MXN)",  "acrilico_lamina"),
            ("Lámina aluminio 240×120 (MXN)",   "aluminio_lamina"),
            ("Lámina PVC 6mm 240×120 (MXN)",    "pvc6_lamina"),
            ("Lámina PVC 2mm 240×120 (MXN)",    "pvc2_lamina"),
            ("Mano de obra por letra (MXN)",     "mano_obra_letra"),
            ("Rollo LED 5m (MXN)",               "led_rollo"),
            ("Instalación (MXN)",                "instalacion"),
            ("Fee asociado (MXN)",               "fee_asociado"),
            ("Espárrago unidad (MXN)",           "esparragos_unit"),
            ("Snaps unidad (MXN)",               "snaps_unit"),
            ("Tubo roscado 10cm unidad (MXN)",   "tubo_roscado_unit"),
        ]
        for i, (lbl, key) in enumerate(fields, start=1):
            self.mat_vars[key] = self._price_row(f, i, lbl, key)

    # ── Tab 2: Vinil ──────────────────────────────────────────────────────
    def _tab_vinil(self, f):
        self._lbl(f, "Precios de vinil", bold=True).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12,4))
        p = self.cfg["precios"]
        self._lbl(f, "Vinil (por unidad 120×60 cm) (MXN)").grid(
            row=1, column=0, sticky="w", padx=14, pady=5)
        _, self._vinil_unit_var = self._entry(
            f, p.get("vinil_unit", VINIL_PRECIO_UNIT))
        self._vinil_unit_var   # referenced via grid below
        # re-grid the entry
        RoundedEntry(f, textvariable=self._vinil_unit_var, width=12,
                     bg=self.BG2, fg=self.FG,
                     parent_bg=self.BG, font=("Segoe UI", 10)).grid(
            row=1, column=1, padx=14, pady=5)

        self._lbl(f, "Extra por 'con transfer' (MXN)").grid(
            row=2, column=0, sticky="w", padx=14, pady=5)
        _, self._vinil_xtra_var = self._entry(
            f, p.get("vinil_transfer_extra", VINIL_TRANSFER_EXTRA))
        RoundedEntry(f, textvariable=self._vinil_xtra_var, width=12,
                     bg=self.BG2, fg=self.FG,
                     parent_bg=self.BG, font=("Segoe UI", 10)).grid(
            row=2, column=1, padx=14, pady=5)

        self._lbl(f, "Ejemplo: plantilla 240×120 con transfer = (vinil×4) + (extra×4)",
                  ).grid(row=3, column=0, columnspan=2, sticky="w", padx=14, pady=(0,8))

    # ── Tab 3: Papel plantilla ────────────────────────────────────────────
    def _tab_papel(self, f):
        self._lbl(f, "Papel / plotter plantilla", bold=True).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12,4))
        pc = self.cfg.get("papel_plantilla", {"ancho_cm": 120, "alto_cm": 60, "precio": 15})
        rows = [
            ("Ancho del pliego (cm)",   "ancho_cm"),
            ("Alto del pliego (cm)",    "alto_cm"),
            ("Precio por pliego (MXN)", "precio"),
        ]
        self._papel_vars = {}
        for i, (lbl, key) in enumerate(rows, start=1):
            self._lbl(f, lbl).grid(row=i, column=0, sticky="w", padx=14, pady=5)
            e, var = self._entry(f, pc.get(key, 0))
            e.grid(row=i, column=1, padx=14, pady=5)
            self._papel_vars[key] = var

    # ── Tab 4: Básicos ────────────────────────────────────────────────────
    def _tab_basicos(self, f):
        self._lbl(f, "Conceptos básicos fijos", bold=True).pack(
            anchor="w", padx=14, pady=(12, 4))
        self._lbl(f, "Se suman siempre a la cotización").pack(
            anchor="w", padx=14)

        list_frame = tk.Frame(f, bg=self.BG)
        list_frame.pack(fill="both", expand=True, padx=14, pady=8)

        self._basicos_rows = []   # list of (nombre_var, precio_var, row_frame)

        self._basicos_container = tk.Frame(list_frame, bg=self.BG)
        self._basicos_container.pack(fill="x")

        for b in self.cfg.get("basicos", []):
            self._add_basico_row(b["nombre"], b["precio"])

        RoundedButton(list_frame, text="+ Agregar concepto",
                      bg=self.BG2, fg=self.ACC, parent_bg=self.BG,
                      font=("Segoe UI", 9), padx=10, pady=5,
                      command=lambda: self._add_basico_row("", 0)
                      ).pack(anchor="w", pady=(4, 0))

    def _add_basico_row(self, nombre, precio):
        row_f = tk.Frame(self._basicos_container, bg=self.BG)
        row_f.pack(fill="x", pady=2)
        nvar = tk.StringVar(value=nombre)
        pvar = tk.StringVar(value=str(precio))
        RoundedEntry(row_f, textvariable=nvar, width=24,
                     bg=self.BG2, fg=self.FG,
                     parent_bg=self.BG, font=("Segoe UI", 10)).pack(side="left", padx=(0,6))
        RoundedEntry(row_f, textvariable=pvar, width=10,
                     bg=self.BG2, fg=self.FG,
                     parent_bg=self.BG, font=("Segoe UI", 10)).pack(side="left", padx=(0,6))
        self._lbl(row_f, "MXN").pack(side="left")
        row_ref = [row_f, nvar, pvar]
        RoundedButton(row_f, text="✕", bg=self.BG2, fg="#c0392b", parent_bg=self.BG,
                      font=("Segoe UI", 9), padx=6, pady=4,
                      command=lambda: self._del_basico_row(row_ref)
                      ).pack(side="left", padx=(6, 0))
        self._basicos_rows.append(row_ref)

    def _del_basico_row(self, row_ref):
        row_ref[0].destroy()
        self._basicos_rows.remove(row_ref)

    # ── Tab 5: Fuentes ────────────────────────────────────────────────────
    def _tab_fuentes(self, f):
        self._lbl(f, "Fuentes de poder", bold=True).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12,4))
        self._fuente_vars = []
        for i, fu in enumerate(self.cfg["fuentes"]):
            self._lbl(f, f"{fu['watts']}W — precio (MXN)").grid(
                row=i+1, column=0, sticky="w", padx=14, pady=5)
            e, var = self._entry(f, fu["precio"])
            e.grid(row=i+1, column=1, padx=14, pady=5)
            self._fuente_vars.append((i, var))

    # ── Save ───────────────────────────────────────────────────────────────
    def _save(self):
        try:
            p = self.cfg["precios"]
            for key, var in self.mat_vars.items():
                p[key] = float(var.get())
            p["vinil_unit"]           = float(self._vinil_unit_var.get())
            p["vinil_transfer_extra"] = float(self._vinil_xtra_var.get())

            pc = self.cfg.setdefault("papel_plantilla", {})
            pc["ancho_cm"] = float(self._papel_vars["ancho_cm"].get())
            pc["alto_cm"]  = float(self._papel_vars["alto_cm"].get())
            pc["precio"]   = float(self._papel_vars["precio"].get())

            basicos = []
            for row_f, nvar, pvar in self._basicos_rows:
                nombre = nvar.get().strip()
                precio = float(pvar.get())
                if nombre:
                    basicos.append({"nombre": nombre, "precio": precio})
            self.cfg["basicos"] = basicos

            for i, var in self._fuente_vars:
                self.cfg["fuentes"][i]["precio"] = float(var.get())

        except ValueError:
            messagebox.showerror("Error", "Verifica que todos los valores sean números.")
            return
        self.on_save(self.cfg)
        self.destroy()


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Anuncios Luminosos LB")
        self.resizable(True, True)
        self.minsize(900, 600)
        self.geometry("1200x800")
        self.configure(bg="#111111")

        self.cfg = load_config()
        self.svg_w_px    = None
        self.svg_w_cm    = None   # ancho base del SVG en cm
        self.letters     = []
        self.svg_path    = tk.StringVar(value="")
        self._updating   = False  # guard para evitar loops en los traces

        # Client / project fields (persist across sessions)
        self.cliente_var   = tk.StringVar()
        self.empresa_c_var = tk.StringVar()
        self.direccion_var = tk.StringVar()
        self.proyecto_var  = tk.StringVar()
        self.tipo_persona_var = tk.StringVar(value="Persona Física")
        self.desc_text        = None
        self._last_r          = None
        self._desc_per_tab    = ["", ""]
        self._active_tab      = 0
        self.esparragos_var   = tk.StringVar(value="Ninguno")

        self._build()

    # ------------------------------------------------------------------
    def _build(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        BG   = "#111111"   # panel izquierdo
        BG2  = "#f5f5f5"   # panel derecho / resultados
        BG3  = "#222222"   # inputs en panel izq
        FG   = "#ffffff"   # texto en panel izq
        FG2  = "#888888"   # labels secundarios panel izq
        FGR  = "#1a1a1a"   # texto en panel derecho
        FGR2 = "#666666"   # texto secundario panel derecho
        DIVL = "#2a2a2a"   # divisor panel izq
        DIVR = "#dddddd"   # divisor panel der

        s.configure(".", background=BG2, foreground=FGR, font=("Segoe UI", 10))
        s.configure("TFrame", background=BG2)
        s.configure("TLabel", background=BG2, foreground=FGR)
        s.configure("Header.TLabel", font=("Segoe UI", 13, "bold"), foreground=FGR)
        s.configure("TEntry", fieldbackground="#ffffff", foreground=FGR)
        s.configure("TButton", background="#e0e0e0", foreground=FGR, padding=[10,5])
        s.map("TButton", background=[("active", "#cccccc")])
        s.configure("Accent.TButton", background=FGR, foreground="#ffffff", padding=[10,5])
        s.map("Accent.TButton", background=[("active", "#333333")])
        s.configure("Result.TLabel", background=BG2, foreground=FGR)
        s.configure("Total.TLabel",  background=BG2, foreground="#1a1a1a",
                    font=("Segoe UI", 13, "bold"))

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0)   # panel izq fijo
        self.grid_columnconfigure(1, weight=1)   # panel der crece

        # ══ Panel izquierdo — formulario ══════════════════════════════════
        left = tk.Frame(self, bg=BG, padx=22, pady=22)
        left.grid(row=0, column=0, sticky="ns")

        # Logo / título
        tk.Label(left, text="L+B", bg=BG, fg=FG,
                 font=("Segoe UI", 24, "bold")).pack(anchor="w")
        tk.Label(left, text="Anuncios Luminosos", bg=BG, fg=FG2,
                 font=("Segoe UI", 9)).pack(anchor="w")

        tk.Frame(left, bg=DIVL, height=1).pack(fill="x", pady=(16, 14))

        # ── SVG ───────────────────────────────────────────────────────────
        self._section_label(left, "ARCHIVO")
        svg_row = tk.Frame(left, bg=BG)
        svg_row.pack(fill="x", pady=(4, 0))
        RoundedEntry(svg_row, textvariable=self.svg_path, state="readonly",
                     bg=BG3, fg=FG2, parent_bg=BG,
                     font=("Segoe UI", 8), width=18).pack(side="left", padx=(0, 6))
        RoundedButton(svg_row, text="Abrir", bg="#ffffff", fg="#111111",
                      parent_bg=BG, font=("Segoe UI", 9, "bold"),
                      padx=10, pady=5, command=self._open_file).pack(side="left")

        tk.Frame(left, bg=BG, height=10).pack()
        dim_row = tk.Frame(left, bg=BG)
        dim_row.pack(anchor="w", fill="x")
        # Ancho
        w_col = tk.Frame(dim_row, bg=BG)
        w_col.pack(side="left", padx=(0, 8))
        tk.Label(w_col, text="Ancho real (cm)", bg=BG, fg=FG2,
                 font=("Segoe UI", 8)).pack(anchor="w")
        self.width_var = tk.StringVar()
        RoundedEntry(w_col, textvariable=self.width_var,
                     bg=BG3, fg=FG, parent_bg=BG,
                     font=("Segoe UI", 10), width=9).pack(anchor="w", pady=(3, 0))
        # Escala
        s_col = tk.Frame(dim_row, bg=BG)
        s_col.pack(side="left")
        tk.Label(s_col, text="Escala (%)", bg=BG, fg=FG2,
                 font=("Segoe UI", 8)).pack(anchor="w")
        self.escala_var = tk.StringVar(value="100")
        RoundedEntry(s_col, textvariable=self.escala_var,
                     bg=BG3, fg=FG, parent_bg=BG,
                     font=("Segoe UI", 10), width=6).pack(anchor="w", pady=(3, 0))

        # Traces bidireccionales
        def _on_width_change(*_):
            if self._updating or not self.svg_w_cm:
                return
            try:
                w = float(self.width_var.get().replace(",", "."))
                pct = round(w / self.svg_w_cm * 100, 2)
                self._updating = True
                self.escala_var.set(str(pct))
            except ValueError:
                pass
            finally:
                self._updating = False

        def _on_escala_change(*_):
            if self._updating or not self.svg_w_cm:
                return
            try:
                pct = float(self.escala_var.get().replace(",", "."))
                w = round(self.svg_w_cm * pct / 100, 3)
                self._updating = True
                self.width_var.set(str(w))
            except ValueError:
                pass
            finally:
                self._updating = False

        self.width_var.trace_add("write", _on_width_change)
        self.escala_var.trace_add("write", _on_escala_change)

        tk.Frame(left, bg=DIVL, height=1).pack(fill="x", pady=(16, 14))

        # ── Cliente ───────────────────────────────────────────────────────
        self._section_label(left, "PRESUPUESTO")

        tk.Label(left, text="Tipo de persona", bg=BG, fg=FG2,
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(8, 0))
        tipo_row = tk.Frame(left, bg=BG)
        tipo_row.pack(anchor="w", pady=(4, 0))
        for opcion in ("Persona Física", "Persona Moral"):
            tk.Radiobutton(tipo_row, text=opcion, variable=self.tipo_persona_var,
                           value=opcion, bg=BG, fg=FG, selectcolor=BG3,
                           activebackground=BG, activeforeground=FG,
                           font=("Segoe UI", 9), cursor="hand2"
                           ).pack(side="left", padx=(0, 12))

        campos = [
            ("Cliente",    self.cliente_var),
            ("Empresa",    self.empresa_c_var),
            ("Dirección",  self.direccion_var),
            ("Proyecto",   self.proyecto_var),
        ]
        for lbl, var in campos:
            tk.Label(left, text=lbl, bg=BG, fg=FG2,
                     font=("Segoe UI", 8)).pack(anchor="w", pady=(8, 0))
            RoundedEntry(left, textvariable=var, bg=BG3, fg=FG, parent_bg=BG,
                         font=("Segoe UI", 9), width=24).pack(anchor="w", pady=(2, 0))

        tk.Label(left, text="Descripción", bg=BG, fg=FG2,
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(8, 0))
        self.desc_text = RoundedText(left, bg=BG3, fg=FG, parent_bg=BG,
                                     font=("Segoe UI", 9), width=24, height=4)
        self.desc_text.pack(anchor="w", pady=(2, 0))

        tk.Frame(left, bg=DIVL, height=1).pack(fill="x", pady=(16, 14))

        # ── Opciones adicionales ──────────────────────────────────────────
        tk.Label(left, text="Fijación (4 por letra)", bg=BG, fg=FG2,
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 2))
        tk.OptionMenu(left, self.esparragos_var,
                      "Ninguno", "Espárrago", "Snaps", "Tubo roscado 10cm"
                      ).pack(anchor="w", fill="x", pady=(0, 10))

        # ── Botones acción ────────────────────────────────────────────────
        RoundedButton(left, text="Calcular cotización",
                      bg="#ffffff", fg="#111111", parent_bg=BG,
                      font=("Segoe UI", 10, "bold"), padx=12, pady=9,
                      command=self._calcular).pack(fill="x")
        tk.Frame(left, bg=BG, height=6).pack()
        RoundedButton(left, text="⚙  Configuración",
                      bg=BG3, fg=FG2, parent_bg=BG,
                      font=("Segoe UI", 9), padx=10, pady=7,
                      command=self._settings).pack(fill="x")

        # ══ Panel derecho — resultados scrollables ════════════════════════
        right = tk.Frame(self, bg=BG2)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)

        self._res_canvas = tk.Canvas(right, bg=BG2, highlightthickness=0)
        self._res_canvas.grid(row=0, column=0, sticky="nsew")

        vsb = tk.Scrollbar(right, orient="vertical",
                           command=self._res_canvas.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self._res_canvas.configure(yscrollcommand=vsb.set)

        outer = tk.Frame(self._res_canvas, bg=BG2)
        self._res_window = self._res_canvas.create_window(
            (0, 0), window=outer, anchor="nw")

        outer.bind("<Configure>",
                   lambda e: self._res_canvas.configure(
                       scrollregion=self._res_canvas.bbox("all")))
        self._res_canvas.bind("<Configure>",
                              lambda e: self._res_canvas.itemconfig(
                                  self._res_window, width=e.width))
        self._res_canvas.bind_all(
            "<MouseWheel>",
            lambda e: self._res_canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        # ── Tabs de tipos de anuncio (colores por tab) ───────────────────
        TABS = [
            {"name": "Aluminio con acrílico",  "color": "#3aaa6a", "bg": "#edfaf3"},
            {"name": "Aluminio por aluminio",   "color": "#4f86c6", "bg": "#eef4fc"},
        ]

        tab_bar = tk.Frame(outer, bg=BG2)
        tab_bar.pack(fill="x")

        self.res_frames = []
        self._tab_btns  = []

        # Crear todos los frames y apilarlos con pack; solo el activo es visible
        for t in TABS:
            f = tk.Frame(outer, bg=t["bg"], padx=24, pady=24)
            self.res_frames.append(f)

        def _aluminio_default_desc():
            if not self._last_r:
                return ""
            w_cm = self._last_r.get("sign_w_cm", 0)
            h_cm = self._last_r.get("sign_h_cm", 0)
            dims = f"{w_cm:.1f} x {h_cm:.1f} cm"
            return (
                "Fabricación de anuncio en 3d hecho de acrilico en la parte frontal "
                "y lamina de aluminio spec acabado satin clear en cantos, fijado al muro "
                f"con charolas de PVC. leds blanco neutro. medidas: {dims}"
            )

        def _switch_tab(idx):
            # Save current description to the tab we're leaving
            if self.desc_text:
                self._desc_per_tab[self._active_tab] = self.desc_text.get("1.0", "end-1c")

            for i, (f, btn_data) in enumerate(zip(self.res_frames, self._tab_btns)):
                if i == idx:
                    f.pack(fill="both", expand=True)
                    btn_data["btn"].config(
                        bg=TABS[i]["color"], fg="#ffffff",
                        relief="flat", font=("Segoe UI", 9, "bold"))
                    btn_data["bar"].config(bg=TABS[i]["color"])
                else:
                    f.pack_forget()
                    btn_data["btn"].config(
                        bg="#e0e0e0", fg="#555555",
                        relief="flat", font=("Segoe UI", 9))
                    btn_data["bar"].config(bg="#e0e0e0")

            # Restore description for the new tab
            if self.desc_text:
                saved = self._desc_per_tab[idx]
                if not saved and idx == 0:
                    saved = _aluminio_default_desc()
                    self._desc_per_tab[0] = saved
                self.desc_text.delete("1.0", "end")
                self.desc_text.insert("1.0", saved)
            self._active_tab = idx

        for i, t in enumerate(TABS):
            col = tk.Frame(tab_bar, bg=BG2)
            col.pack(side="left", padx=(0, 2))
            btn = tk.Button(col, text=f"  {t['name']}  ",
                            bg="#e0e0e0", fg="#555555",
                            relief="flat", bd=0,
                            font=("Segoe UI", 9),
                            cursor="hand2", padx=10, pady=6,
                            command=lambda idx=i: _switch_tab(idx))
            btn.pack()
            bar = tk.Frame(col, height=3, bg="#e0e0e0")
            bar.pack(fill="x")
            self._tab_btns.append({"btn": btn, "bar": bar})

        _switch_tab(0)

        # Alias para compatibilidad con código existente (tab activo)
        self.res_frame = self.res_frames[0]
        self._result_placeholder()

    def _section_label(self, parent, text):
        tk.Label(parent, text=text, bg="#111111", fg="#555555",
                 font=("Segoe UI", 7, "bold")).pack(anchor="w")

    def _result_placeholder(self):
        for rf in self.res_frames:
            for w in rf.winfo_children():
                w.destroy()
            tk.Label(
                rf,
                text="Abre un archivo SVG e ingresa el ancho real para cotizar.",
                bg=rf.cget("bg"), fg="#aaaaaa", font=("Segoe UI", 10, "italic")
            ).pack(pady=40)

    def _open_file(self):
        path = filedialog.askopenfilename(
            filetypes=[("SVG files", "*.svg"), ("All files", "*.*")]
        )
        if not path:
            return
        if not HAS_SVG:
            messagebox.showerror(
                "Dependencia faltante",
                "Instala svgpathtools:\n\npip install svgpathtools"
            )
            return
        try:
            self.svg_w_px, self.letters, self.svg_w_cm = parse_svg(path)
            self.svg_path.set(os.path.basename(path))
            # Auto-fill width and reset scale to 100%
            if self.svg_w_cm:
                self._updating = True
                self.width_var.set(f"{self.svg_w_cm:.3f}")
                self.escala_var.set("100")
                self._updating = False
            n = len(self.letters)
            names = ", ".join(l["name"] for l in self.letters[:6])
            if n > 6:
                names += f"… (+{n-6})"
            self._show_info(f"{n} letras detectadas: {names}")
        except Exception as e:
            messagebox.showerror("Error al leer SVG", str(e))

    def _show_info(self, msg):
        for rf in self.res_frames:
            for w in rf.winfo_children():
                w.destroy()
            tk.Label(rf, text=msg, bg=rf.cget("bg"), fg="#4f86c6",
                     font=("Segoe UI", 10)).pack(anchor="w")

    def _calcular(self):
        if not self.letters:
            messagebox.showwarning("Sin archivo", "Primero abre un archivo SVG.")
            return
        try:
            rw = float(self.width_var.get().replace(",", "."))
        except ValueError:
            messagebox.showerror("Error", "Ingresa un ancho válido en cm.")
            return

        # Ventana de progreso mientras corre el nesting en hilo aparte
        prog = tk.Toplevel(self)
        prog.title("Calculando…")
        prog.configure(bg="#1e1e2e")
        prog.resizable(False, False)
        prog.grab_set()
        tk.Label(prog, text="Calculando nesting óptimo…",
                 bg="#1e1e2e", fg="#cdd6f4",
                 font=("Segoe UI", 11)).pack(padx=30, pady=(20, 8))
        bar = ttk.Progressbar(prog, length=280, mode="indeterminate")
        bar.pack(padx=30, pady=(0, 20))
        bar.start(10)

        container = [None]

        def worker():
            cfg_calc = dict(self.cfg)
            cfg_calc["tipo_fijacion"] = self.esparragos_var.get()
            container[0] = calculate(self.svg_w_px, self.letters, rw, cfg_calc)
            self.after(0, done)

        def done():
            bar.stop()
            prog.destroy()
            result = container[0]
            if result is None:
                messagebox.showerror("Error", "No se pudo calcular. Verifica el archivo SVG.")
                return
            result["tipo_persona"] = self.tipo_persona_var.get()
            self._last_r = result
            # Always build the aluminio default with fresh dimensions
            w_cm = result.get("sign_w_cm", 0)
            h_cm = result.get("sign_h_cm", 0)
            dims = f"{w_cm:.1f} x {h_cm:.1f} cm"
            aluminio_desc = (
                "Fabricación de anuncio en 3d hecho de acrilico en la parte frontal "
                "y lamina de aluminio spec acabado satin clear en cantos, fijado al muro "
                f"con charolas de PVC. leds blanco neutro. medidas: {dims}"
            )
            self._desc_per_tab = [aluminio_desc, ""]
            for rf in self.res_frames:
                self._show_results(result, rf)
            # Update the visible text box for whichever tab is active
            if self.desc_text:
                self.desc_text.delete("1.0", "end")
                self.desc_text.insert("1.0", self._desc_per_tab[self._active_tab])

        threading.Thread(target=worker, daemon=True).start()

    def _show_results(self, r, res_frame=None):
        if res_frame is None:
            res_frame = self.res_frames[0]
        for w in res_frame.winfo_children():
            w.destroy()

        bg  = res_frame.cget("bg")   # hereda el color del tab
        fg  = "#1a1a1a"
        fg2 = "#666666"
        acc = "#1a1a1a"

        def row(label, value, color=fg):
            f = tk.Frame(res_frame, bg=bg)
            f.pack(fill="x", pady=2)
            tk.Label(f, text=label, bg=bg, fg=fg2, width=36, anchor="w",
                     font=("Segoe UI", 10)).pack(side="left")
            tk.Label(f, text=value, bg=bg, fg=color,
                     font=("Segoe UI", 10, "bold")).pack(side="left")

        def sep():
            tk.Frame(res_frame, bg="#dddddd", height=1).pack(fill="x", pady=6)

        desc = self.desc_text.get("1.0", "end-1c").strip() if self.desc_text else ""
        if desc:
            tk.Label(res_frame, text=desc, bg=bg, fg=fg2,
                     font=("Segoe UI", 9), wraplength=520, justify="left",
                     ).pack(anchor="w", pady=(0, 12))

        if not desc:
            tk.Label(res_frame, text="COTIZACIÓN", bg=bg, fg="#888888",
                     font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 10))

        if not desc:
            row("Letras detectadas", str(r["n_letters"]))
            row("Perímetro total", f"{r['perim_cm']:.1f} cm  ({r['perim_m']:.2f} m)")
            sep()

            n_xl   = r.get("n_xl",   0)
            n_full = r.get("n_full", r["n_pieces"])
            n_tall = r.get("n_tall", 0)
            n_half = r.get("n_half", 0)
            parts  = []
            if n_xl:   parts.append(f"{n_xl} × 240x120")
            if n_full: parts.append(f"{n_full} × 120x60")
            if n_tall: parts.append(f"{n_tall} × 60x120")
            if n_half: parts.append(f"{n_half} × 60x60")
            billing    = n_xl*4 + n_full*1 + n_tall*1 + n_half*0.5
            n_lam      = billing / 4
            piezas_txt = "  +  ".join(parts) + f"  =  {n_lam:.2f} lám."
            row("Piezas Acrílico Z2 / PVC 6mm", piezas_txt)
            row("Laminas Acrílico Z2 240x120",
                f"{r['n_acrilico']:.3f}  →  {fmt(r['c_acrilico'])}")
            row("Laminas PVC 6mm 240x120",
                f"{r['n_pvc6']:.3f}  →  {fmt(r['c_pvc6'])}")
            sep()

            row("Área Spec", f"{r['area_al_cm2']:.0f} cm2")
            row("Laminas Spec (+40% merma)",
                f"{r['n_aluminio']:.3f}  →  {fmt(r['c_aluminio'])}")
            row("Area PVC 2mm", f"{r['area_pvc2_cm2']:.0f} cm2")
            row("Laminas PVC 2mm (+40% merma)",
                f"{r['n_pvc2']:.3f}  →  {fmt(r['c_pvc2'])}")
            sep()

            row("Mano de obra", f"{r['n_letters']} letras  →  {fmt(r['c_mano'])}")
            sep()

            row("Rollos LED (5m)", f"{r['n_rollos']:.3f}  →  {fmt(r['c_leds'])}")
            row("Watts totales", f"{r['watts']} W")
            row(f"Fuente de poder ({r['fuente']['watts']}W)", fmt(r['c_fuente']))
            sep()

            row("Instalacion", fmt(r['c_instalacion']))
            pc = r.get("papel_cfg", {})
            row("Papel plantilla",
                f"Area {r['sign_w_cm']:.0f}x{r['sign_h_cm']:.0f} cm  →  "
                f"{r['n_papel']} pliegos ({pc.get('ancho_cm',90)}x{pc.get('alto_cm',120)} cm)  →  "
                f"{fmt(r['c_papel'])}")
            sep()

            tk.Label(res_frame, text="BASICOS", bg=bg, fg=acc,
                     font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(4,2))
            for nombre, precio in r.get("basicos", []):
                row(f"  {nombre}", fmt(precio))
            row("Total basicos", fmt(r['c_basicos_total']), color=fg)
            sep()

            c_vinil = r.get("c_vinil", 0.0)
            if c_vinil > 0:
                row("Vinil / Vinil con transfer", fmt(c_vinil), color=fg)
                sep()

            c_esp = r.get("c_esparragos", 0.0)
            if c_esp > 0:
                lbl_fij = r.get("tipo_fijacion", "Fijación")
                row(f"{lbl_fij} ({r.get('n_esparragos', 0)} pzas)", fmt(c_esp), color=fg)
                sep()

        # Total label
        tk.Frame(res_frame, bg="#1a1a1a", height=2).pack(fill="x", pady=(4,6))
        tk.Label(res_frame, text=f"TOTAL:  {fmt(r['total'])}", bg=bg,
                 fg="#1a1a1a", font=("Segoe UI", 15, "bold")).pack(
                 anchor="w", pady=(0, 4))

        # Buttons row
        placements = r.get("placements", [])

        def on_nesting_change(n_xl, n_full, n_half, c_vinil=0.0):
            # n_full already includes tall pieces (both bill as 1 unit)
            billing         = n_xl * PIECE_BILLING["xl"] + \
                              n_full * PIECE_BILLING["full"] + \
                              n_half * PIECE_BILLING["half"]
            r["n_xl"]       = n_xl
            r["n_full"]     = n_full
            r["n_half"]     = n_half
            r["n_pieces"]   = n_xl + n_full + n_half
            r["n_acrilico"] = billing / 4   # láminas 240x120
            r["n_pvc6"]     = r["n_acrilico"]
            r["c_acrilico"] = r["n_acrilico"] * self.cfg["precios"]["acrilico_lamina"]
            r["c_pvc6"]     = r["n_pvc6"]     * self.cfg["precios"].get("pvc6_lamina", 0)
            r["c_vinil"]    = c_vinil
            r["total"] = (r["c_acrilico"] + r["c_aluminio"] +
                          r["c_pvc6"] + r["c_pvc2"] +
                          r["c_mano"] + r["c_leds"] + r["c_fuente"] +
                          r["c_instalacion"] +
                          r["c_basicos_total"] + r["c_vinil"] +
                          r.get("c_esparragos", 0.0))
            self._show_results(r, res_frame)

        bottom = tk.Frame(res_frame, bg=bg)
        bottom.pack(fill="x", pady=(10, 0))

        def _btn(parent, text, bg, fg, cmd, r=0, c=0):
            RoundedButton(parent, text=text, bg=bg, fg=fg, command=cmd,
                          parent_bg=parent.cget("bg"),
                          font=("Segoe UI", 9, "bold"),
                          padx=12, pady=6
                          ).grid(row=r, column=c, padx=(0, 6), pady=(0, 6), sticky="w")

        _btn(bottom, "Nesting acrílico", "#111111", "#ffffff",
             lambda: NestingWindow(
                 self, r["n_pieces"], placements, r["n_acrilico"],
                 on_change=on_nesting_change,
                 piece_sizes=r["piece_sizes"],
                 piece_vinil=r.get("piece_vinil", {}),
                 vinil_prices=r.get("vinil_prices", {})),
             r=0, c=0)
        _btn(bottom, "Ver aluminio", "#e8e8e8", "#1a1a1a",
             lambda: AluminumWindow(self, r["letter_perims_cm"], r["letter_names"],
                                    r["n_aluminio"], strip_w=5.0, title="Aluminio"),
             r=0, c=1)
        _btn(bottom, "Ver PVC 2mm", "#e8e8e8", "#1a1a1a",
             lambda: AluminumWindow(self, r["letter_perims_cm"], r["letter_names"],
                                    r["n_pvc2"], strip_w=2.0, title="PVC 2mm"),
             r=0, c=2)
        _btn(bottom, "Plantilla papel", "#e8e8e8", "#1a1a1a",
             lambda: PaperWindow(self, r["sign_w_cm"], r["sign_h_cm"],
                                 r["papel_cfg"], r["n_papel"],
                                 letter_bboxes_cm=r.get("letter_bboxes_cm", [])),
             r=1, c=1)

        # r["piece_sizes"] is the shared dict — always use it for PDF too
        def _on_nesting_open():
            return NestingWindow(self, r["n_pieces"], placements, r["n_acrilico"],
                                 on_change=on_nesting_change,
                                 piece_sizes=r["piece_sizes"])

        def _export_pdf():
            ps   = r.get("piece_sizes", {})
            folio = self.cfg.get("folio", 6000)
            path = filedialog.asksaveasfilename(
                defaultextension=".pdf",
                filetypes=[("PDF", "*.pdf")],
                initialfile=f"presupuesto_{folio:04d}.pdf")
            if not path:
                return
            try:
                r["cliente"]         = self.cliente_var.get().strip()
                r["empresa_cliente"] = self.empresa_c_var.get().strip()
                r["direccion"]       = self.direccion_var.get().strip()
                r["proyecto"]        = self.proyecto_var.get().strip()
                r["tipo_persona"]    = self.tipo_persona_var.get()
                r["descripcion"]     = self.desc_text.get("1.0", "end-1c").strip() if self.desc_text else ""
                r["empresa"]         = self.cfg.get("empresa", {})
                r["folio"]           = folio
                self.cfg["folio"]    = folio + 1
                save_config(self.cfg)
                export_pdf(r, placements, ps, r["n_pieces"], path)
                messagebox.showinfo("PDF exportado", f"Guardado en:\n{path}")
                os.startfile(path)
            except Exception as e:
                messagebox.showerror("Error al exportar PDF", str(e))

        # Replace the nesting button command to track the window reference
        # (add PDF button separately so it always has latest state)
        _btn(bottom, "Exportar PDF", "#111111", "#ffffff", _export_pdf, r=1, c=2)

    def _settings(self):
        def on_save(new_cfg):
            self.cfg = new_cfg
            save_config(new_cfg)
            messagebox.showinfo("Guardado", "Precios actualizados.")

        SettingsWindow(self, self.cfg, on_save)


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = App()
    app.mainloop()
