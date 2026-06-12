import tkinter as tk
from tkinter import ttk, filedialog, messagebox
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
# Paths
# ---------------------------------------------------------------------------
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

    return svg_w, letters


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
    "half": ( 60.0,  60.0),   # octavo de lámina 60×60
}
# Equivalencia en unidades de 120×60 para cotización
PIECE_BILLING = {
    "xl":   4.0,
    "full": 1.0,
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
    n_aluminio = (area_al_cm2 / (240 * 120)) * 1.20   # exacto + 20% merma

    perim_m = total_perim_cm / 100.0
    n_rollos = math.ceil(perim_m / 5.0)
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
    n_pvc2 = (area_pvc2_cm2 / (240 * 120)) * 1.20   # exacto + 20% merma
    c_pvc2 = n_pvc2 * p.get("pvc2_lamina", 0)

    c_mano = n_letters * p["mano_obra_letra"]
    c_leds = n_rollos * p["led_rollo"]
    c_fuente      = fuente["precio"]
    c_instalacion = p.get("instalacion", 0)
    c_fee         = p.get("fee_asociado", 0)

    # Papel plantilla — cubre el área total del anuncio en posición final
    all_y1 = [l["bbox_px"][1] for l in letters]
    all_y2 = [l["bbox_px"][1] + l["bbox_px"][3] for l in letters]
    sign_h_cm  = (max(all_y2) - min(all_y1)) * scale
    sign_area_cm2 = real_width_cm * sign_h_cm
    papel_cfg = cfg.get("papel_plantilla", {"ancho_cm": 90, "alto_cm": 120, "precio": 15})
    papel_area_cm2 = papel_cfg["ancho_cm"] * papel_cfg["alto_cm"]
    n_papel = math.ceil(sign_area_cm2 / papel_area_cm2)
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
             c_mano + c_leds + c_fuente + c_instalacion + c_fee +
             c_basicos_total + c_papel + c_vinil)

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
        # small circle at exact corner
        cv.create_oval(cx-2, cy-2, cx+2, cy+2, fill=color, outline="")


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
    """Render nesting layout to a PIL Image (colored rectangles + names)."""
    from PIL import Image, ImageDraw, ImageFont
    COLS = 3
    GAP  = 12
    PW = int(PIECE_W * scale)
    PH = int(PIECE_H * scale)
    rows = math.ceil(n_pieces / COLS)
    W = COLS * (PW + GAP) + GAP
    H = rows * (PH + GAP) + GAP

    img  = Image.new("RGB", (W, H), "#1e1e2e")
    draw = ImageDraw.Draw(img)

    COLORS_PIL = ["#cba6f7","#89b4fa","#a6e3a1","#f38ba8","#fab387",
                  "#f9e2af","#94e2d5","#89dceb","#b4befe","#eba0ac"]

    for pi in range(n_pieces):
        col, row = pi % COLS, pi // COLS
        is_half = piece_sizes.get(pi, "full") == "half"
        pw = int((PIECE_H if is_half else PIECE_W) * scale)
        ph = PH
        ox = GAP + col * (PW + GAP)
        oy = GAP + row * (PH + GAP)
        draw.rectangle([ox, oy, ox+pw, oy+ph], fill="#313244", outline="#585b70", width=2)
        draw.text((ox+4, oy+4), f"P{pi+1} ({'60x60' if is_half else '120x60'} cm)",
                  fill="#888899")

    for i, p in enumerate(placements):
        pi   = p["piece"]
        col, row = pi % COLS, pi // COLS
        ox   = GAP + col * (PW + GAP)
        oy   = GAP + row * (PH + GAP)
        lx   = int(ox + p["x"] * scale)
        ly   = int(oy + p["y"] * scale)
        lw   = max(int(p["actual_w"] * scale), 4)
        lh   = max(int(p["actual_h"] * scale), 4)
        color = COLORS_PIL[i % len(COLORS_PIL)]
        draw.rectangle([lx, ly, lx+lw, ly+lh], fill=color, outline="#1e1e2e", width=1)
        if lw > 20 and lh > 10:
            draw.text((lx + lw//2 - len(p["name"])*3, ly + lh//2 - 6),
                      p["name"], fill="#1e1e2e")
    return img


def _pil_aluminum_image(letter_perims_cm, letter_names, strip_w, scale=3):
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
    COLORS_PIL = ["#cba6f7","#89b4fa","#a6e3a1","#f38ba8","#fab387",
                  "#f9e2af","#94e2d5","#89dceb","#b4befe","#eba0ac"]

    for perim, name in strips:
        if name not in letter_colors:
            letter_colors[name] = COLORS_PIL[color_idx % len(COLORS_PIL)]
            color_idx += 1
        remaining = perim + perim * 0.20  # include merma
        while remaining > 0.01:
            if col_y >= SHEET_H - 0.1:
                col_x += strip_w; col_y = 0.0
            if col_x + strip_w > SHEET_W + 0.1:
                sheets.append([]); col_x = col_y = 0.0
            seg = min(remaining, SHEET_H - col_y)
            is_merma = perim > 0 and remaining <= perim * 0.20
            sheets[-1].append((col_x, col_y, strip_w, seg, name, is_merma))
            col_y += seg; remaining -= seg

    n = len(sheets)
    rows = math.ceil(n / COLS)
    W = COLS * (SW + GAP) + GAP
    H = rows * (SH + GAP) + GAP
    img  = Image.new("RGB", (W, H), "#1e1e2e")
    draw = ImageDraw.Draw(img)

    for si, sheet in enumerate(sheets):
        col, row = si % COLS, si // COLS
        ox = GAP + col * (SW + GAP)
        oy = GAP + row * (SH + GAP)
        draw.rectangle([ox, oy, ox+SW, oy+SH], fill="#313244", outline="#585b70", width=2)
        draw.text((ox+4, oy+4), f"Hoja {si+1}", fill="#888899")
        for (sx, sy, sw, sh, name, is_merma) in sheet:
            color = "#444455" if is_merma else letter_colors.get(name, "#aaaaaa")
            x1, y1 = ox+int(sx*scale), oy+int(sy*scale)
            x2, y2 = x1+max(int(sw*scale)-1,2), y1+max(int(sh*scale)-1,2)
            draw.rectangle([x1, y1, x2, y2], fill=color, outline="#1e1e2e")
            if (y2-y1) > 12 and not is_merma:
                draw.text((x1+2, y1+2), name[:4], fill="#1e1e2e")
    return img


def export_pdf(r, placements, piece_sizes, n_pieces, output_path):
    import io, datetime
    from PIL import Image as PILImage
    from reportlab.lib.pagesizes import letter as PAGE
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                    Table, TableStyle, HRFlowable, Image as RLImage,
                                    PageBreak)
    from reportlab.lib.styles import ParagraphStyle

    doc   = SimpleDocTemplate(output_path, pagesize=PAGE,
                              leftMargin=2*cm, rightMargin=2*cm,
                              topMargin=2*cm, bottomMargin=2*cm)
    story = []
    PAGE_W = PAGE[0] - 4*cm  # usable width in pts

    PURPLE = colors.HexColor("#7c3aed")
    DARK   = colors.HexColor("#1e1e2e")
    GRAY   = colors.HexColor("#6c7086")
    GREEN  = colors.HexColor("#16a34a")

    T  = lambda txt, s: story.append(Paragraph(txt, s))
    SP = lambda n=8: story.append(Spacer(1, n))
    HR = lambda: story.append(HRFlowable(width="100%", color=PURPLE, thickness=1))

    title_s = ParagraphStyle("t", fontSize=18, textColor=PURPLE,
                              spaceAfter=2, fontName="Helvetica-Bold")
    sub_s   = ParagraphStyle("s", fontSize=10, textColor=GRAY, spaceAfter=10)
    sec_s   = ParagraphStyle("h", fontSize=11, textColor=PURPLE,
                              spaceBefore=12, spaceAfter=4, fontName="Helvetica-Bold")
    img_title_s = ParagraphStyle("it", fontSize=10, textColor=DARK,
                                  spaceBefore=14, spaceAfter=4, fontName="Helvetica-Bold")

    today = datetime.date.today().strftime("%d / %m / %Y")
    T("Anuncios Luminosos LB", title_s)
    T(f"Cotizacion — {today}", sub_s)
    HR(); SP(10)

    def money(v): return f"${v:,.2f}"

    def tbl(rows, widths=None):
        t = Table(rows, colWidths=widths or [11*cm, 5*cm])
        t.setStyle(TableStyle([
            ("FONTNAME",     (0,0),(-1,-1), "Helvetica"),
            ("FONTSIZE",     (0,0),(-1,-1), 9),
            ("TEXTCOLOR",    (0,0),(0,-1),  colors.HexColor("#374151")),
            ("TEXTCOLOR",    (1,0),(1,-1),  DARK),
            ("ALIGN",        (1,0),(1,-1),  "RIGHT"),
            ("LINEBELOW",    (0,-1),(-1,-1),0.5, GRAY),
            ("BOTTOMPADDING",(0,0),(-1,-1), 3),
            ("TOPPADDING",   (0,0),(-1,-1), 3),
        ]))
        story.append(t)

    def pil_to_rl(pil_img, max_w_pt):
        buf = io.BytesIO()
        pil_img.save(buf, format="PNG")
        buf.seek(0)
        ratio = pil_img.height / pil_img.width
        w = min(max_w_pt, pil_img.width * 0.75)
        return RLImage(buf, width=w, height=w * ratio)

    # ── Cotizacion ─────────────────────────────────────────────────────────
    n_full = r.get("n_full", n_pieces); n_half = r.get("n_half", 0)
    equiv  = n_full + n_half * 0.5
    piezas_txt = f"{n_full} x 120x60 cm"
    if n_half: piezas_txt += f" + {n_half} x 60x60 cm = {equiv:.1f} plantillas"

    T("Materiales", sec_s)
    tbl([
        ["Piezas acrilico / PVC 6mm", piezas_txt],
        ["Acrilico 240x120",          f"{r['n_acrilico']:.3f} lam.  →  {money(r['c_acrilico'])}"],
        ["PVC 6mm 240x120",           f"{r['n_pvc6']:.3f} lam.  →  {money(r['c_pvc6'])}"],
        ["Aluminio (+20% merma)",      f"{r['n_aluminio']:.3f} lam.  →  {money(r['c_aluminio'])}"],
        ["PVC 2mm (+20% merma)",       f"{r['n_pvc2']:.3f} lam.  →  {money(r['c_pvc2'])}"],
    ])

    T("Iluminacion", sec_s)
    tbl([
        ["Rollos LED 5m",             f"{r['n_rollos']}  →  {money(r['c_leds'])}"],
        [f"Fuente {r['fuente']['watts']}W", money(r['c_fuente'])],
    ])

    T("Mano de obra e instalacion", sec_s)
    tbl([
        ["Letras",        str(r['n_letters'])],
        ["Mano de obra",  money(r['c_mano'])],
        ["Instalacion",   money(r['c_instalacion'])],
        ["Fee asociado",  money(r['c_fee'])],
    ])

    pc = r.get("papel_cfg", {})
    T("Papel plantilla", sec_s)
    tbl([
        ["Area del anuncio",
         f"{r.get('sign_w_cm',0):.0f} x {r.get('sign_h_cm',0):.0f} cm"],
        ["Pliegos necesarios",
         f"{r.get('n_papel',0)}  ({pc.get('ancho_cm',90)}x{pc.get('alto_cm',120)} cm)  →  "
         f"{money(r.get('c_papel',0))}"],
    ])

    T("Basicos", sec_s)
    tbl([[n, money(p)] for n, p in r.get("basicos", [])] +
        [["Total basicos", money(r['c_basicos_total'])]])

    SP(14); HR()
    tot_t = Table([["TOTAL", money(r['total'])]], colWidths=[11*cm, 5*cm])
    tot_t.setStyle(TableStyle([
        ("FONTNAME", (0,0),(-1,-1), "Helvetica-Bold"), ("FONTSIZE",(0,0),(-1,-1),14),
        ("TEXTCOLOR",(1,0),(1,0), GREEN), ("ALIGN",(1,0),(1,0),"RIGHT"),
        ("TOPPADDING",(0,0),(-1,-1),8),
    ]))
    story.append(tot_t)

    # ── Graficos — nueva pagina, apilados verticalmente ────────────────────
    story.append(PageBreak())
    T("Nesting — Acrilico / PVC 6mm", sec_s)
    T("Cada color es una letra. Piezas 120x60 cm (full) o 60x60 cm (half).", img_title_s)
    img_nest = _pil_nesting_image(placements, n_pieces, piece_sizes, scale=5)
    story.append(pil_to_rl(img_nest, PAGE_W))

    SP(20)
    T("Distribucion — Aluminio (tiras 5 cm)", sec_s)
    T("Gris = merma 20%. Corte en eje 120 cm.", img_title_s)
    img_al = _pil_aluminum_image(
        r.get("letter_perims_cm", []), r.get("letter_names", []),
        strip_w=5.0, scale=2)
    story.append(pil_to_rl(img_al, PAGE_W))

    SP(20)
    T("Distribucion — PVC 2mm (tiras 2 cm)", sec_s)
    T("Gris = merma 20%. Corte en eje 120 cm.", img_title_s)
    img_pvc2 = _pil_aluminum_image(
        r.get("letter_perims_cm", []), r.get("letter_names", []),
        strip_w=2.0, scale=2)
    story.append(pil_to_rl(img_pvc2, PAGE_W))

    doc.build(story)
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
COLORS = ["#cba6f7","#89b4fa","#a6e3a1","#f38ba8","#fab387",
          "#f9e2af","#94e2d5","#89dceb","#b4befe","#eba0ac"]

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
        self.configure(bg="#1e1e2e")
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
        top = tk.Frame(self, bg="#1e1e2e")
        top.pack(fill="x", padx=10, pady=(10, 0))

        self.hdr = tk.Label(top, text="", bg="#1e1e2e", fg="#cba6f7",
                             font=("Segoe UI", 11, "bold"))
        self.hdr.pack(side="left")

        # Rotation input (visible when letter selected)
        self._angle_var = tk.StringVar(value="0")
        rot_frame = tk.Frame(top, bg="#1e1e2e")
        rot_frame.pack(side="left", padx=16)
        tk.Label(rot_frame, text="Angulo:", bg="#1e1e2e", fg="#a6adc8",
                 font=("Segoe UI", 9)).pack(side="left")
        self._angle_entry = tk.Entry(rot_frame, textvariable=self._angle_var,
                                     width=6, bg="#313244", fg="#cdd6f4",
                                     font=("Segoe UI", 10), relief="flat")
        self._angle_entry.pack(side="left", padx=4)
        tk.Label(rot_frame, text="°", bg="#1e1e2e", fg="#a6adc8",
                 font=("Segoe UI", 9)).pack(side="left")
        tk.Button(rot_frame, text="-15", bg="#313244", fg="#cdd6f4",
                  relief="flat", font=("Segoe UI", 8), cursor="hand2",
                  command=lambda: self._rotate_by(-15)).pack(side="left", padx=2)
        tk.Button(rot_frame, text="+15", bg="#313244", fg="#cdd6f4",
                  relief="flat", font=("Segoe UI", 8), cursor="hand2",
                  command=lambda: self._rotate_by(15)).pack(side="left", padx=2)
        self._angle_entry.bind("<Return>", self._on_angle_enter)
        self._angle_entry.bind("<FocusOut>", self._on_angle_enter)

        tk.Label(top, bg="#1e1e2e", fg="#6c7086", font=("Segoe UI", 9),
                 text="  Click: seleccionar  │  R: rotar  │  ←→: cambiar pieza  │  Arrastrar: mover"
                 ).pack(side="left")

        self.del_btn = tk.Button(top, text="× Eliminar última pieza",
                                  bg="#313244", fg="#f38ba8", relief="flat",
                                  font=("Segoe UI", 9), cursor="hand2",
                                  command=self._del_last_piece)
        self.del_btn.pack(side="right", padx=(4,0))
        tk.Button(top, text="+ 240x120", bg="#313244", fg="#a6e3a1",
                  relief="flat", font=("Segoe UI", 9), cursor="hand2",
                  command=lambda: self._add_piece("xl")).pack(side="right", padx=2)
        tk.Button(top, text="+ 120x60", bg="#313244", fg="#a6e3a1",
                  relief="flat", font=("Segoe UI", 9), cursor="hand2",
                  command=lambda: self._add_piece("full")).pack(side="right", padx=2)
        tk.Button(top, text="+ 60x60", bg="#313244", fg="#a6e3a1",
                  relief="flat", font=("Segoe UI", 9), cursor="hand2",
                  command=lambda: self._add_piece("half")).pack(side="right", padx=2)
        tk.Button(top, text="Exportar…", bg="#cba6f7", fg="#1e1e2e",
                  relief="flat", font=("Segoe UI", 9, "bold"), cursor="hand2",
                  command=self._export).pack(side="right", padx=8)

        cf = tk.Frame(self, bg="#1e1e2e")
        cf.pack(fill="both", expand=True, padx=10, pady=10)

        self.cv = tk.Canvas(cf, bg="#181825", width=1200, height=500)
        vsb = tk.Scrollbar(cf, orient="vertical",   command=self.cv.yview)
        hsb = tk.Scrollbar(cf, orient="horizontal", command=self.cv.xview)
        self.cv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right",  fill="y")
        hsb.pack(side="bottom", fill="x")
        self.cv.pack(side="left", fill="both", expand=True)

        self.cv.bind("<Button-1>",        self._on_click)
        self.cv.bind("<B1-Motion>",       self._on_drag)
        self.cv.bind("<ButtonRelease-1>", self._on_release)
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
        counts = {"xl": 0, "full": 0, "half": 0}
        for pi in range(self.n_pieces):
            counts[self.piece_sizes.get(pi, "full")] += 1
        billing = sum(counts[k] * PIECE_BILLING[k] for k in counts)
        n_lam   = billing / 4   # láminas 240x120
        parts   = []
        if counts["xl"]:   parts.append(f"{counts['xl']} × 240x120")
        if counts["full"]: parts.append(f"{counts['full']} × 120x60")
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
            size_lbl = {"xl": "240x120", "full": "120x60", "half": "60x60"}.get(
                self.piece_sizes.get(pi, "full"), "120x60")
            empty = not any(p["piece"] == pi for p in self.placements)
            self.cv.create_rectangle(ox, oy, ox+pw, oy+ph,
                fill="#2a2a3e" if empty else "#313244",
                outline="#585b70", width=2)
            toggle_tag = f"toggle_{pi}"
            self.cv.create_text(ox+6, oy+6, anchor="nw",
                text=f"P{pi+1} ({size_lbl})  [click para cambiar]",
                fill="#6c7086", font=("Segoe UI", 8), tags=toggle_tag)
            # invisible hit area for the toggle
            self.cv.create_rectangle(ox, oy, ox+pw, oy+18,
                fill="", outline="", tags=(toggle_tag, "piece_toggle"))
            m = PIECE_MARGIN * S
            self.cv.create_rectangle(ox+m, oy+m, ox+pw-m, oy+ph-m,
                outline="#404055", width=1, dash=(3,3))
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
                                        fill="#89b4fa", width=1, dash=(6, 3))
                    self.cv.create_text(ox + pw - 4, gy_px - 5, anchor="e",
                                        text=f"— {g_y:.0f} cm —",
                                        fill="#89b4fa", font=("Segoe UI", 7))
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

            cb_frame = tk.Frame(self.cv, bg="#1e1e2e", bd=0)
            tk.Checkbutton(cb_frame, text="Vinil",
                           variable=opts["vinil"],
                           command=_on_vinil,
                           bg="#1e1e2e", fg="#cdd6f4",
                           selectcolor="#313244", activebackground="#1e1e2e",
                           font=("Segoe UI", 8), cursor="hand2").pack(anchor="w")
            tk.Checkbutton(cb_frame, text="Vinil con transfer",
                           variable=opts["transfer"],
                           command=_on_transfer,
                           bg="#1e1e2e", fg="#cdd6f4",
                           selectcolor="#313244", activebackground="#1e1e2e",
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
        outline = "#ffffff" if selected else "#1e1e2e"
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

        # Check piece-size toggle first
        for item in self.cv.find_overlapping(x-2, y-2, x+2, y+2):
            for tag in self.cv.gettags(item):
                if tag.startswith("toggle_"):
                    pi  = int(tag[7:])
                    cur = self.piece_sizes.get(pi, "full")
                    # Ciclo: full → xl → half → full
                    cycle = {"full": "xl", "xl": "half", "half": "full"}
                    nxt   = cycle.get(cur, "full")
                    self.piece_sizes[pi] = nxt
                    # Clamp letras que queden fuera del nuevo tamaño
                    _, _, pw_cm, ph_cm = self._piece_dims(pi)
                    for pl in self.placements:
                        if pl["piece"] == pi:
                            pl["x"] = max(PIECE_MARGIN,
                                          min(pl["x"], pw_cm - PIECE_MARGIN - pl["actual_w"]))
                            pl["y"] = max(PIECE_MARGIN,
                                          min(pl["y"], ph_cm - PIECE_MARGIN - pl["actual_h"]))
                    self._render()
                    self._notify()
                    return

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
            counts = {"xl": 0, "full": 0, "half": 0}
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

            self._on_change(counts["xl"], counts["full"], counts["half"],
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

        tk.Button(win, text="Elegir carpeta y exportar",
                  bg="#cba6f7", fg="#1e1e2e", relief="flat",
                  font=("Segoe UI", 10, "bold"), cursor="hand2",
                  command=do_export).pack(pady=(12, 18), padx=24, fill="x")

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
                 strip_w=5.0, title="Aluminio"):
        super().__init__(parent)
        self.title(f"Distribucion de {title}")
        self.configure(bg="#1e1e2e")
        self.resizable(True, True)
        self.STRIP_W = strip_w
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

        # ── merma (20%) — tiras adicionales en gris ────────────────────────
        merma_remaining = sum(perims) * 0.20
        while merma_remaining > 0.01:
            if col_y >= self.SHEET_H - 0.1:
                start_new_column()
            if col_x + self.STRIP_W > self.SHEET_W + 0.1:
                start_new_sheet()
            seg_len = min(merma_remaining, self.SHEET_H - col_y)
            sheets[-1].append((col_x, col_y, self.STRIP_W, seg_len, "Merma 20%", True))
            col_y          += seg_len
            merma_remaining -= seg_len

        # ── canvas ────────────────────────────────────────────────────────
        PAD = self.PAD
        n = len(sheets)
        rows = math.ceil(n / COLS)
        cw = PAD + COLS * SW + PAD
        ch = 50 + PAD + rows * SH + PAD

        header = tk.Label(
            self, bg="#1e1e2e", fg="#fab387", font=("Segoe UI", 11, "bold"),
            text=f"{n} hojas 240x120 cm  |  tiras {self.STRIP_W} cm x max 120 cm  "
                 f"|  gris = merma 20%")
        header.pack(padx=10, pady=(10, 0), anchor="w")

        frame = tk.Frame(self, bg="#1e1e2e")
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        cv = tk.Canvas(frame, bg="#181825",
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
                       fill="#6c7086", font=("Segoe UI", 8))

        for si, sheet in enumerate(sheets):
            col = si % COLS
            row = si // COLS
            ox = PAD + col * SW
            oy = 30 + PAD + row * SH

            # Sheet background
            cv.create_rectangle(ox, oy, ox+SW, oy+SH,
                                 fill="#313244", outline="#585b70", width=2)
            cv.create_text(ox+6, oy+5, anchor="nw",
                           text=f"Hoja {si+1}", fill="#6c7086",
                           font=("Segoe UI", 8))

            # Column guides (every STRIP_W)
            cols_n = int(self.SHEET_W / self.STRIP_W)
            for ci in range(1, cols_n):
                lx = ox + ci * self.STRIP_W * S
                cv.create_line(lx, oy, lx, oy+SH,
                               fill="#404055", width=1)

            # Draw strips
            for (sx, sy, sw, sh, sname, is_merma) in sheet:
                if is_merma:
                    color   = "#444455"
                    outline = "#555566"
                    txt_col = "#888899"
                else:
                    cidx    = letter_colors.get(sname, 0)
                    color   = COLORS[cidx % len(COLORS)]
                    outline = "#1e1e2e"
                    txt_col = "#1e1e2e"
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
        self.configure(bg="#1e1e2e")
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
        hdr_row = tk.Frame(self, bg="#1e1e2e")
        hdr_row.pack(fill="x", padx=10, pady=(10, 0))
        tk.Label(
            hdr_row, bg="#1e1e2e", fg="#fab387", font=("Segoe UI", 11, "bold"),
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

        tk.Button(hdr_row, text="Exportar SVG…", bg="#cba6f7", fg="#1e1e2e",
                  relief="flat", font=("Segoe UI", 9, "bold"), cursor="hand2",
                  command=_do_export).pack(side="right", padx=(8, 0))

        tk.Label(
            self, bg="#1e1e2e", fg="#6c7086", font=("Segoe UI", 9),
            text="Plantillas completas 120×60 cm. El anuncio está centrado. "
                 "Imprime a escala 1:1 y únelos con cinta."
        ).pack(padx=10, pady=(0, 4), anchor="w")

        # ── canvas ────────────────────────────────────────────────────────
        frame = tk.Frame(self, bg="#1e1e2e")
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        cv = tk.Canvas(frame, bg="#181825",
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
                                    fill="#2a2a3e", outline="#585b70", width=2)
                # Sheet label (small, top-left of each sheet)
                lbl = f"P{r * cols_n + c + 1}  {pw:.0f}×{ph:.0f} cm"
                cv.create_text(sx + 6, sy + 6, anchor="nw", text=lbl,
                               fill="#585b70", font=("Segoe UI", 7))

        # ── letters (actual shapes, offset to logo position) ──────────────
        # logo_ox/oy = canvas px origin of sign content
        logo_ox = ox + int(logo_off_x * S)
        logo_oy = oy + int(logo_off_y * S)

        for i, lb in enumerate(letter_bboxes):
            color  = COLORS[i % len(COLORS)]
            shapes = lb.get("shapes", [])
            if shapes:
                _draw_shapes_on_canvas(cv, shapes, S, logo_ox, logo_oy,
                                       fill=color, outline="#1e1e2e")
            else:
                lx = logo_ox + int(lb["x"] * S)
                ly = logo_oy + int(lb["y"] * S)
                lw = max(4, int(lb["w"] * S))
                lh = max(4, int(lb["h"] * S))
                cv.create_rectangle(lx, ly, lx + lw, ly + lh,
                                    fill=color, outline="#1e1e2e", width=1)
            # Name label at center of letter bbox
            lx     = logo_ox + int((lb["x"] + lb["w"] / 2) * S)
            ly     = logo_oy + int((lb["y"] + lb["h"] / 2) * S)
            lw_px  = max(4, int(lb["w"] * S))
            lh_px  = max(4, int(lb["h"] * S))
            if lw_px > 16 and lh_px > 10:
                cv.create_text(lx, ly, text=lb["name"],
                               fill="#1e1e2e", font=("Segoe UI", 8, "bold"),
                               width=lw_px - 4)

        # ── sign bounding-box outline (blue) ──────────────────────────────
        cv.create_rectangle(
            logo_ox, logo_oy,
            logo_ox + int(sign_w * S), logo_oy + int(sign_h * S),
            fill="", outline="#89b4fa", width=2)

        # ── sheet grid lines (over everything) ────────────────────────────
        for c in range(1, cols_n):
            lx = ox + int(c * pw * S)
            cv.create_line(lx, oy, lx, oy + total_h_px,
                           fill="#f9e2af", width=2, dash=(8, 4))
        for r in range(1, rows_n):
            ly = oy + int(r * ph * S)
            cv.create_line(ox, ly, ox + total_w_px, ly,
                           fill="#f9e2af", width=2, dash=(8, 4))

        # ── column width labels (below grid) ─────────────────────────────
        for c in range(cols_n):
            mid_x = ox + int((c + 0.5) * pw * S)
            cv.create_text(mid_x, oy + total_h_px + 10,
                           text=f"{pw:.0f} cm",
                           fill="#6c7086", font=("Segoe UI", 7))

        # ── row height labels (left of grid) ─────────────────────────────
        for r in range(rows_n):
            mid_y = oy + int((r + 0.5) * ph * S)
            cv.create_text(ox - 8, mid_y,
                           text=f"{ph:.0f} cm",
                           fill="#6c7086", font=("Segoe UI", 7), anchor="e")


class SettingsWindow(tk.Toplevel):
    BG  = "#1e1e2e"
    BG2 = "#313244"
    FG  = "#cdd6f4"
    ACC = "#cba6f7"

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
        e = tk.Entry(parent, textvariable=var, width=width,
                     bg=self.BG2, fg=self.FG, insertbackground=self.FG,
                     relief="flat", font=("Segoe UI", 10))
        return e, var

    def _sep(self, parent):
        tk.Frame(parent, bg="#45475a", height=1).pack(fill="x", pady=6)

    # ── main layout ────────────────────────────────────────────────────────
    def _build(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=12)

        # style tabs dark
        s = ttk.Style(self)
        s.configure("TNotebook",        background=self.BG, borderwidth=0)
        s.configure("TNotebook.Tab",    background=self.BG2, foreground=self.FG,
                                         padding=[10, 4])
        s.map("TNotebook.Tab",          background=[("selected", "#45475a")])

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

        tk.Button(self, text="  Guardar  ", bg=self.ACC, fg=self.BG,
                  relief="flat", font=("Segoe UI", 11, "bold"), cursor="hand2",
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
            ("Lámina acrílico 240×120 (MXN)",  "acrilico_lamina"),
            ("Lámina aluminio 240×120 (MXN)",   "aluminio_lamina"),
            ("Lámina PVC 6mm 240×120 (MXN)",    "pvc6_lamina"),
            ("Lámina PVC 2mm 240×120 (MXN)",    "pvc2_lamina"),
            ("Mano de obra por letra (MXN)",     "mano_obra_letra"),
            ("Rollo LED 5m (MXN)",               "led_rollo"),
            ("Instalación (MXN)",                "instalacion"),
            ("Fee asociado (MXN)",               "fee_asociado"),
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
        tk.Entry(f, textvariable=self._vinil_unit_var, width=12,
                 bg=self.BG2, fg=self.FG, insertbackground=self.FG,
                 relief="flat", font=("Segoe UI", 10)).grid(
            row=1, column=1, padx=14, pady=5)

        self._lbl(f, "Extra por 'con transfer' (MXN)").grid(
            row=2, column=0, sticky="w", padx=14, pady=5)
        _, self._vinil_xtra_var = self._entry(
            f, p.get("vinil_transfer_extra", VINIL_TRANSFER_EXTRA))
        tk.Entry(f, textvariable=self._vinil_xtra_var, width=12,
                 bg=self.BG2, fg=self.FG, insertbackground=self.FG,
                 relief="flat", font=("Segoe UI", 10)).grid(
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

        tk.Button(list_frame, text="+ Agregar concepto",
                  bg=self.BG2, fg=self.ACC, relief="flat",
                  font=("Segoe UI", 9), cursor="hand2",
                  command=lambda: self._add_basico_row("", 0)
                  ).pack(anchor="w", pady=(4, 0))

    def _add_basico_row(self, nombre, precio):
        row_f = tk.Frame(self._basicos_container, bg=self.BG)
        row_f.pack(fill="x", pady=2)
        nvar = tk.StringVar(value=nombre)
        pvar = tk.StringVar(value=str(precio))
        tk.Entry(row_f, textvariable=nvar, width=24,
                 bg=self.BG2, fg=self.FG, insertbackground=self.FG,
                 relief="flat", font=("Segoe UI", 10)).pack(side="left", padx=(0,6))
        tk.Entry(row_f, textvariable=pvar, width=10,
                 bg=self.BG2, fg=self.FG, insertbackground=self.FG,
                 relief="flat", font=("Segoe UI", 10)).pack(side="left", padx=(0,6))
        self._lbl(row_f, "MXN").pack(side="left")
        row_ref = [row_f, nvar, pvar]
        tk.Button(row_f, text="✕", bg=self.BG, fg="#f38ba8", relief="flat",
                  font=("Segoe UI", 9), cursor="hand2",
                  command=lambda: self._del_basico_row(row_ref)
                  ).pack(side="left", padx=(6,0))
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
        self.resizable(False, False)
        self.configure(bg="#1e1e2e")

        self.cfg = load_config()
        self.svg_w_px = None
        self.letters = []
        self.svg_path = tk.StringVar(value="")

        # Client / project fields (persist across sessions)
        self.cliente_var   = tk.StringVar()
        self.empresa_c_var = tk.StringVar()
        self.direccion_var = tk.StringVar()
        self.proyecto_var  = tk.StringVar()
        self.desc_text     = None   # tk.Text widget, assigned in _build

        self._build()

    # ------------------------------------------------------------------
    def _build(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background="#1e1e2e", foreground="#cdd6f4", font=("Segoe UI", 10))
        s.configure("TFrame", background="#1e1e2e")
        s.configure("TLabel", background="#1e1e2e", foreground="#cdd6f4")
        s.configure("Header.TLabel", font=("Segoe UI", 13, "bold"), foreground="#cba6f7")
        s.configure("TEntry", fieldbackground="#313244", foreground="#cdd6f4")
        s.configure("TButton", background="#585b70", foreground="#cdd6f4", padding=6)
        s.map("TButton", background=[("active", "#7f849c")])
        s.configure("Accent.TButton", background="#cba6f7", foreground="#1e1e2e")
        s.map("Accent.TButton", background=[("active", "#b4befe")])
        s.configure("Result.TLabel", background="#181825", foreground="#cdd6f4")
        s.configure("Total.TLabel", background="#181825", foreground="#a6e3a1",
                    font=("Segoe UI", 13, "bold"))

        main = ttk.Frame(self, padding=20)
        main.grid(row=0, column=0)

        ttk.Label(main, text="Anuncios Luminosos LB", style="Header.TLabel").grid(
            row=0, column=0, columnspan=3, pady=(0, 16), sticky="w"
        )

        # File row
        ttk.Label(main, text="Archivo SVG:").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(main, textvariable=self.svg_path, width=38, state="readonly").grid(
            row=1, column=1, padx=8
        )
        ttk.Button(main, text="Abrir…", command=self._open_file).grid(row=1, column=2)

        # Width
        ttk.Label(main, text="Ancho real del anuncio (cm):").grid(
            row=2, column=0, sticky="w", pady=4
        )
        self.width_var = tk.StringVar()
        ttk.Entry(main, textvariable=self.width_var, width=12).grid(
            row=2, column=1, sticky="w", padx=8
        )

        # Buttons
        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=3, column=0, columnspan=3, pady=14, sticky="w")
        ttk.Button(btn_frame, text="Calcular cotización", style="Accent.TButton",
                   command=self._calcular).pack(side="left", padx=(0, 8))
        ttk.Button(btn_frame, text="⚙ Precios", command=self._settings).pack(side="left")

        # Results frame
        res = tk.Frame(main, bg="#181825", padx=16, pady=14)
        res.grid(row=4, column=0, columnspan=3, sticky="ew")
        self.res_frame = res
        self._result_placeholder()

    def _result_placeholder(self):
        for w in self.res_frame.winfo_children():
            w.destroy()
        tk.Label(
            self.res_frame,
            text="Abre un archivo SVG e ingresa el ancho real para cotizar.",
            bg="#181825", fg="#6c7086", font=("Segoe UI", 10, "italic")
        ).pack()

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
            self.svg_w_px, self.letters = parse_svg(path)
            self.svg_path.set(os.path.basename(path))
            n = len(self.letters)
            names = ", ".join(l["name"] for l in self.letters[:6])
            if n > 6:
                names += f"… (+{n-6})"
            self._show_info(f"{n} letras detectadas: {names}")
        except Exception as e:
            messagebox.showerror("Error al leer SVG", str(e))

    def _show_info(self, msg):
        for w in self.res_frame.winfo_children():
            w.destroy()
        tk.Label(self.res_frame, text=msg, bg="#181825", fg="#89b4fa",
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
            container[0] = calculate(self.svg_w_px, self.letters, rw, self.cfg)
            self.after(0, done)

        def done():
            bar.stop()
            prog.destroy()
            result = container[0]
            if result is None:
                messagebox.showerror("Error", "No se pudo calcular. Verifica el archivo SVG.")
                return
            self._show_results(result)

        threading.Thread(target=worker, daemon=True).start()

    def _show_results(self, r):
        for w in self.res_frame.winfo_children():
            w.destroy()

        bg = "#181825"
        fg = "#cdd6f4"
        fg2 = "#a6adc8"
        acc = "#cba6f7"

        def row(label, value, color=fg):
            f = tk.Frame(self.res_frame, bg=bg)
            f.pack(fill="x", pady=1)
            tk.Label(f, text=label, bg=bg, fg=fg2, width=36, anchor="w",
                     font=("Segoe UI", 10)).pack(side="left")
            tk.Label(f, text=value, bg=bg, fg=color,
                     font=("Segoe UI", 10, "bold")).pack(side="left")

        def sep():
            tk.Frame(self.res_frame, bg="#313244", height=1).pack(fill="x", pady=4)

        tk.Label(self.res_frame, text="COTIZACIÓN", bg=bg, fg=acc,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 8))

        row("Letras detectadas", str(r["n_letters"]))
        row("Perímetro total", f"{r['perim_cm']:.1f} cm  ({r['perim_m']:.2f} m)")
        sep()

        n_xl   = r.get("n_xl",   0)
        n_full = r.get("n_full", r["n_pieces"])
        n_half = r.get("n_half", 0)
        parts  = []
        if n_xl:   parts.append(f"{n_xl} × 240x120")
        if n_full: parts.append(f"{n_full} × 120x60")
        if n_half: parts.append(f"{n_half} × 60x60")
        billing    = n_xl*4 + n_full*1 + n_half*0.5
        n_lam      = billing / 4
        piezas_txt = "  +  ".join(parts) + f"  =  {n_lam:.2f} lám."
        row("Piezas acrilico / PVC 6mm", piezas_txt)
        row("Laminas acrilico 240x120",
            f"{r['n_acrilico']:.3f}  →  {fmt(r['c_acrilico'])}")
        row("Laminas PVC 6mm 240x120",
            f"{r['n_pvc6']:.3f}  →  {fmt(r['c_pvc6'])}")
        sep()

        row("Area aluminio", f"{r['area_al_cm2']:.0f} cm2")
        row("Laminas aluminio (+20% merma)",
            f"{r['n_aluminio']:.3f}  →  {fmt(r['c_aluminio'])}")
        row("Area PVC 2mm", f"{r['area_pvc2_cm2']:.0f} cm2")
        row("Laminas PVC 2mm (+20% merma)",
            f"{r['n_pvc2']:.3f}  →  {fmt(r['c_pvc2'])}")
        sep()

        row("Mano de obra", f"{r['n_letters']} letras  →  {fmt(r['c_mano'])}")
        sep()

        row("Rollos LED (5m)", f"{r['n_rollos']}  →  {fmt(r['c_leds'])}")
        row("Watts totales", f"{r['watts']} W")
        row(f"Fuente de poder ({r['fuente']['watts']}W)", fmt(r['c_fuente']))
        sep()

        row("Instalacion", fmt(r['c_instalacion']))
        row("Fee asociado", fmt(r['c_fee']))
        pc = r.get("papel_cfg", {})
        row("Papel plantilla",
            f"Area {r['sign_w_cm']:.0f}x{r['sign_h_cm']:.0f} cm  →  "
            f"{r['n_papel']} pliegos ({pc.get('ancho_cm',90)}x{pc.get('alto_cm',120)} cm)  →  "
            f"{fmt(r['c_papel'])}")
        sep()

        tk.Label(self.res_frame, text="BASICOS", bg=bg, fg=acc,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(4,2))
        for nombre, precio in r.get("basicos", []):
            row(f"  {nombre}", fmt(precio))
        row("Total basicos", fmt(r['c_basicos_total']), color="#f9e2af")
        sep()

        c_vinil = r.get("c_vinil", 0.0)
        if c_vinil > 0:
            row("Vinil / Vinil con transfer", fmt(c_vinil), color="#94e2d5")
            sep()

        # Total label
        tk.Label(self.res_frame, text=f"TOTAL:  {fmt(r['total'])}", bg=bg,
                 fg="#a6e3a1", font=("Segoe UI", 14, "bold")).pack(
                 anchor="w", pady=(4, 0))

        # Buttons row
        placements = r.get("placements", [])

        def on_nesting_change(n_xl, n_full, n_half, c_vinil=0.0):
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
                          r["c_instalacion"] + r["c_fee"] +
                          r["c_basicos_total"] + r["c_vinil"])
            self._show_results(r)

        bottom = tk.Frame(self.res_frame, bg=bg)
        bottom.pack(fill="x", pady=(10, 0))
        tk.Button(bottom, text="Nesting acrilico + PVC 6mm",
                  bg="#313244", fg="#cba6f7", relief="flat",
                  font=("Segoe UI", 10, "bold"), cursor="hand2",
                  command=lambda: NestingWindow(
                      self, r["n_pieces"], placements, r["n_acrilico"],
                      on_change=on_nesting_change,
                      piece_sizes=r["piece_sizes"],
                      piece_vinil=r.get("piece_vinil", {}),
                      vinil_prices=r.get("vinil_prices", {}))
                  ).pack(side="left", padx=(0, 8))
        tk.Button(bottom, text="Ver aluminio",
                  bg="#313244", fg="#fab387", relief="flat",
                  font=("Segoe UI", 10, "bold"), cursor="hand2",
                  command=lambda: AluminumWindow(
                      self, r["letter_perims_cm"], r["letter_names"],
                      r["n_aluminio"], strip_w=5.0, title="Aluminio")
                  ).pack(side="left", padx=(0, 8))
        tk.Button(bottom, text="Ver PVC 2mm",
                  bg="#313244", fg="#94e2d5", relief="flat",
                  font=("Segoe UI", 10, "bold"), cursor="hand2",
                  command=lambda: AluminumWindow(
                      self, r["letter_perims_cm"], r["letter_names"],
                      r["n_pvc2"], strip_w=2.0, title="PVC 2mm")
                  ).pack(side="left", padx=(0, 8))
        tk.Button(bottom, text="Ver plantilla papel",
                  bg="#313244", fg="#f9e2af", relief="flat",
                  font=("Segoe UI", 10, "bold"), cursor="hand2",
                  command=lambda: PaperWindow(
                      self,
                      r["sign_w_cm"], r["sign_h_cm"],
                      r["papel_cfg"], r["n_papel"],
                      letter_bboxes_cm=r.get("letter_bboxes_cm", []))
                  ).pack(side="left", padx=(0, 8))

        # r["piece_sizes"] is the shared dict — always use it for PDF too
        def _on_nesting_open():
            return NestingWindow(self, r["n_pieces"], placements, r["n_acrilico"],
                                 on_change=on_nesting_change,
                                 piece_sizes=r["piece_sizes"])

        def _export_pdf():
            ps = r.get("piece_sizes", {})
            path = filedialog.asksaveasfilename(
                defaultextension=".pdf",
                filetypes=[("PDF", "*.pdf")],
                initialfile="cotizacion_LB.pdf")
            if not path:
                return
            try:
                export_pdf(r, placements, ps, r["n_pieces"], path)
                messagebox.showinfo("PDF exportado", f"Guardado en:\n{path}")
                os.startfile(path)
            except Exception as e:
                messagebox.showerror("Error al exportar PDF", str(e))

        # Replace the nesting button command to track the window reference
        # (add PDF button separately so it always has latest state)
        tk.Button(bottom, text="Exportar PDF",
                  bg="#a6e3a1", fg="#1e1e2e", relief="flat",
                  font=("Segoe UI", 10, "bold"), cursor="hand2",
                  command=_export_pdf).pack(side="left", padx=(8, 0))

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
