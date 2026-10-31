"""Deterministic quantity tagger.

The LLM never retypes numbers. Every number+unit literal in the procedure is
found here, parsed into a value/unit/kind triple and given an ID (Q1, Q2, ...).
Extraction agents only *reference* these IDs, so value transcription errors,
unit punctuation (``0°-5° C.``), fractions (``1/2 hour``) and hyphenated
concentrations (``4-M``) are handled once, in code, not repaired by prompts.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from fractions import Fraction

WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "sixty": 60, "a half": 0.5, "half an": 0.5, "half": 0.5,
}

# canonical unit -> (kind, factor to base unit, base unit). Temperature handled specially.
UNITS = {
    "ng": ("mass", 1e-6, "mg"), "ug": ("mass", 1e-3, "mg"), "mg": ("mass", 1, "mg"),
    "g": ("mass", 1e3, "mg"), "kg": ("mass", 1e6, "mg"),
    "nL": ("volume", 1e-6, "mL"), "uL": ("volume", 1e-3, "mL"), "mL": ("volume", 1, "mL"),
    "dL": ("volume", 100, "mL"), "L": ("volume", 1e3, "mL"),
    "nmol": ("amount", 1e-6, "mmol"), "umol": ("amount", 1e-3, "mmol"), "mmol": ("amount", 1, "mmol"),
    "mol": ("amount", 1e3, "mmol"),
    "nM": ("concentration", 1e-9, "M"), "uM": ("concentration", 1e-6, "M"), "mM": ("concentration", 1e-3, "M"),
    "M": ("concentration", 1, "M"), "N": ("concentration", 1, "N"), "mol/L": ("concentration", 1, "M"),
    "mg/mL": ("mass_concentration", 1, "mg/mL"), "g/L": ("mass_concentration", 1, "mg/mL"),
    "wt%": ("percent", 1, "%"), "w/w%": ("percent", 1, "%"), "v/v%": ("percent", 1, "%"),
    "%": ("percent", 1, "%"), "mol%": ("relative_loading", 1, "mol%"),
    "equiv": ("equivalents", 1, "equiv"),
    "s": ("time", 1, "s"), "min": ("time", 60, "s"), "h": ("time", 3600, "s"), "d": ("time", 86400, "s"),
    "week": ("time", 604800, "s"),
    "degC": ("temperature", 1, "degC"), "K": ("temperature", 1, "degC"), "degF": ("temperature", 1, "degC"),
    "deg": ("angle", 1, "deg"),
    "rpm": ("rotation_speed", 1, "rpm"), "xg": ("centrifugal_force", 1, "xg"),
    "bar": ("pressure", 1e3, "mbar"), "mbar": ("pressure", 1, "mbar"), "atm": ("pressure", 1013.25, "mbar"),
    "psi": ("pressure", 68.9476, "mbar"), "Torr": ("pressure", 1.33322, "mbar"), "mmHg": ("pressure", 1.33322, "mbar"),
    "Pa": ("pressure", 0.01, "mbar"), "kPa": ("pressure", 10, "mbar"), "MPa": ("pressure", 1e4, "mbar"),
    "mL/min": ("flow_rate", 1, "mL/min"), "uL/min": ("flow_rate", 1e-3, "mL/min"), "mL/h": ("flow_rate", 1 / 60, "mL/min"),
    "nm": ("length", 1e-6, "mm"), "um": ("length", 1e-3, "mm"), "mm": ("length", 1, "mm"), "cm": ("length", 10, "mm"),
    "MHz": ("frequency", 1, "MHz"), "W": ("power", 1, "W"), "V": ("voltage", 1, "V"), "mA": ("current", 1, "mA"),
    "times": ("count", 1, "times"), "volume": ("relative_volume", 1, "volume"), "part": ("relative_volume", 1, "part"),
    "ratio": ("ratio", 1, "ratio"),
}

# surface spelling -> canonical unit. Longest match wins (sorted below).
SPELLINGS = {
    "ng": "ng", "µg": "ug", "μg": "ug", "ug": "ug", "mcg": "ug", "mg": "mg", "milligrams": "mg", "milligram": "mg",
    "g": "g", "gm": "g", "grams": "g", "gram": "g", "kg": "kg",
    "nL": "nL", "µL": "uL", "μL": "uL", "uL": "uL", "ul": "uL", "µl": "uL", "μl": "uL", "mL": "mL", "ml": "mL",
    "milliliters": "mL", "millilitres": "mL", "cc": "mL", "dL": "dL", "L": "L", "liters": "L", "litres": "L", "liter": "L",
    "nmol": "nmol", "µmol": "umol", "μmol": "umol", "umol": "umol", "mmol": "mmol", "mmole": "mmol", "mmoles": "mmol",
    "millimoles": "mmol", "millimole": "mmol", "mol": "mol", "mole": "mol", "moles": "mol",
    "nM": "nM", "µM": "uM", "μM": "uM", "uM": "uM", "mM": "mM", "M": "M", "N": "N", "mol/L": "mol/L", "mol L-1": "mol/L",
    "mg/mL": "mg/mL", "mg/ml": "mg/mL", "g/L": "g/L",
    "wt%": "wt%", "wt.%": "wt%", "% w/w": "w/w%", "% v/v": "v/v%", "%": "%", "mol%": "mol%", "mol %": "mol%",
    "equiv.": "equiv", "equiv": "equiv", "equivs": "equiv", "eq.": "equiv", "eq": "equiv", "equivalents": "equiv", "equivalent": "equiv",
    "s": "s", "sec": "s", "secs": "s", "second": "s", "seconds": "s",
    "min": "min", "mins": "min", "minute": "min", "minutes": "min",
    "h": "h", "hr": "h", "hrs": "h", "hour": "h", "hours": "h",
    "d": "d", "day": "d", "days": "d", "week": "week", "weeks": "week",
    "°C": "degC", "° C": "degC", "ºC": "degC", "℃": "degC", "oC": "degC", "deg C": "degC", "degrees C": "degC",
    "degrees Celsius": "degC", "C": "degC", "K": "K", "°F": "degF", "° F": "degF",
    "rpm": "rpm", "x g": "xg", "×g": "xg", "× g": "xg", "xg": "xg",
    "bar": "bar", "mbar": "mbar", "atm": "atm", "psi": "psi", "Torr": "Torr", "torr": "Torr", "mmHg": "mmHg", "mm Hg": "mmHg",
    "Pa": "Pa", "kPa": "kPa", "MPa": "MPa",
    "mL/min": "mL/min", "ml/min": "mL/min", "µL/min": "uL/min", "uL/min": "uL/min", "mL/h": "mL/h",
    "nm": "nm", "µm": "um", "μm": "um", "mm": "mm", "cm": "cm", "MHz": "MHz", "W": "W", "V": "V", "mA": "mA",
    "times": "times", "x": "times", "×": "times",
    "volume": "volume", "volumes": "volume", "vol": "volume", "vols": "volume", "part": "part", "parts": "part",
    # Chinese
    "毫克": "mg", "克": "g", "千克": "kg", "微升": "uL", "毫升": "mL", "升": "L", "微摩尔": "umol", "毫摩尔": "mmol",
    "摩尔": "mol", "秒": "s", "分钟": "min", "小时": "h", "天": "d", "摄氏度": "degC", "当量": "equiv",
}
# Spellings that are only units when attached to a number with a word boundary and
# which are frequently ordinary letters; guarded by the regex lookahead below.
_TEMP_DEGREE = r"(?:°|º|˚)\s*"

_NUM = r"(?:\d+(?:[.,]\d+)?(?:\s*/\s*\d+)?|\.\d+)"
_WORDNUM = "|".join(sorted((re.escape(k) for k in WORD_NUMBERS), key=len, reverse=True))
_APPROX = r"(?:(?:ca\.|approx\.|approximately|about|around|~|≈|>|<|≥|≤)\s*)?"
_RANGE_SEP = r"\s*(?:-|–|—|−|~|to|and)\s*"


def _unit_alternation():
    spellings = sorted(SPELLINGS, key=len, reverse=True)
    parts = []
    for s in spellings:
        esc = re.escape(s).replace(r"\ ", r"\s*")
        parts.append(esc)
    return "|".join(parts)


_UNIT = _unit_alternation()
# Unit must not continue into a word (e.g. "g" in "gave", "M" in "MHz" handled by order, "C" in "C4").
_UNIT_END = r"(?![A-Za-zµμ0-9])"

QUANTITY_RE = re.compile(
    r"(?P<approx>" + _APPROX + r")"
    r"(?P<sign>(?<![\w)\]°.])[-−–](?=\d))?"
    r"(?P<lo>" + _NUM + r"|(?i:" + _WORDNUM + r"))"
    r"\s*(?:" + _TEMP_DEGREE + r")?"
    r"(?:" + _RANGE_SEP + r"(?P<hi>" + _NUM + r")\s*(?:" + _TEMP_DEGREE + r")?)?"
    r"(?:\s*-\s*(?=[A-Za-zµμ]))?"            # hyphenated: 4-M, 5-min
    r"\s*(?P<deg>" + _TEMP_DEGREE + r")?"
    r"(?P<unit>" + _UNIT + r")" + _UNIT_END + r"(?P<dot>\.(?=\s*[a-z(,;]))?",
)
RATIO_RE = re.compile(r"(?<![\w.])(?P<a>\d+(?:\.\d+)?)\s*:\s*(?P<b>\d+(?:\.\d+)?)(?:\s*:\s*(?P<c>\d+(?:\.\d+)?))?"
                      r"(?:\s*(?:to|-|–)\s*(?P<a2>\d+(?:\.\d+)?)\s*:\s*(?P<b2>\d+(?:\.\d+)?))?(?![\w])")
COUNT_RE = re.compile(r"(?<![\w.])(?P<n>\d+)\s*(?:x|×)(?![\w])|(?<![\w.])(?:x|×)\s*(?P<m>\d+)(?![\w.])|"
                      r"(?i:\b(?P<w>once|twice|thrice)\b)")
DEGREE_ONLY_RE = re.compile(r"(?<![\w.])(?P<v>[+-]?\d+(?:\.\d+)?)\s*°(?!\s*[CFcf])")

# Contexts in which a bare "C"/"M"/"N"/"K"/"s"/"d"/"x" is NOT a unit.
_FALSE_FOLLOW = re.compile(r"^\s*(?:NMR|H\b|-NMR)")


@dataclass
class Quantity:
    id: str
    text: str
    start: int
    end: int
    value: float | None
    upper: float | None
    unit: str
    kind: str
    approx: str = ""
    base_value: float | None = None
    base_upper: float | None = None
    base_unit: str = ""
    sentence: str = ""
    flags: list = field(default_factory=list)

    def as_dict(self):
        return asdict(self)

    def short(self):
        return self.text


def _num(text):
    text = text.strip().lower()
    if text in WORD_NUMBERS:
        return float(WORD_NUMBERS[text])
    text = text.replace(" ", "")
    if "/" in text:
        whole = text.split("/")
        try:
            return float(Fraction(int(whole[0]), int(whole[1])))
        except (ValueError, ZeroDivisionError):
            return None
    if "," in text and "." not in text:
        # European decimal "2,5" vs thousands "1,000": thousands only when 3 digits follow.
        head, tail = text.split(",", 1)
        text = head + tail if len(tail) == 3 else head + "." + tail
    try:
        return float(text)
    except ValueError:
        return None


def _to_base(value, unit):
    if value is None:
        return None
    if unit == "K":
        return round(value - 273.15, 6)
    if unit == "degF":
        return round((value - 32) * 5 / 9, 6)
    kind, factor, _ = UNITS[unit]
    return round(value * factor, 9)


def _overlaps(spans, start, end):
    return any(not (end <= s or start >= e) for s, e in spans)


def tag_quantities(text, sentence_of=None, skip_spans=()):
    """Return [Quantity] in text order. ``skip_spans`` (characterization data) is not tagged."""
    found = []
    taken = list(skip_spans)

    for m in QUANTITY_RE.finditer(text):
        start, end = m.start(), m.end()
        surface_unit = re.sub(r"\s+", " ", m.group("unit"))
        unit = SPELLINGS.get(surface_unit) or SPELLINGS.get(surface_unit.replace(" ", "")) or SPELLINGS.get(m.group("unit"))
        if unit is None:
            continue
        lo_raw, hi_raw = m.group("lo"), m.group("hi")
        if start > 0 and (text[start - 1].isalnum() or text[start - 1] in "_") and not m.group("approx") and not m.group("sign"):
            continue  # inside an identifier such as "C4-9" or "1a"
        if m.group("deg") and unit in ("C", "degC") or unit == "degC":
            pass
        # Guard single-letter units that are usually not units.
        if surface_unit in ("C",) and not ("°" in m.group(0) or "º" in m.group(0) or "˚" in m.group(0)
                                           or re.search(r"\d\s*C\b", m.group(0))):
            continue
        if surface_unit == "C" and _FALSE_FOLLOW.match(text[end:]):
            continue
        if surface_unit in ("C", "K", "N", "M", "s", "d", "x", "L", "V", "W") and _FALSE_FOLLOW.match(text[end:]):
            continue
        if surface_unit in ("d", "s", "x", "V", "W", "N", "K") and re.match(r"\s*[-(]", text[end:end + 2]) and surface_unit != "x":
            # "2 d-glucose", "3 s-trans" etc.
            pass
        if surface_unit.lower() in ("x", "×"):
            continue  # handled by COUNT_RE
        if surface_unit in ("volume", "volumes", "vol", "vols", "part", "parts") and lo_raw.lower() in WORD_NUMBERS and lo_raw.lower() not in ("one", "two", "three", "four", "five", "ten"):
            continue
        if lo_raw.lower() in WORD_NUMBERS and UNITS[unit][0] not in ("time", "relative_volume", "count", "amount", "volume", "mass"):
            continue
        if unit == "M" and re.match(r"\s*[+\-]\s*H", text[end:end + 5]):
            continue  # (M+H)+
        if _overlaps(taken, start, end):
            continue
        if m.group("dot"):
            end -= 0  # keep "g." dot out of the literal unless it is part of an abbreviation
        lo, hi = _num(lo_raw), _num(hi_raw) if hi_raw else None
        if lo is None:
            continue
        if hi is not None and hi < lo and not m.group("sign"):
            # "pH 7 - 5 mL": not a range; keep only the number that carries the unit.
            start, lo, hi = m.start("hi"), hi, None
        if m.group("sign"):
            if UNITS[unit][0] != "temperature":
                start += 1  # a dash before a non-temperature is punctuation, not a sign
            else:
                lo = -lo
        literal_end = m.end("unit") if not m.group("dot") else m.end("dot")
        text_lit = text[start:literal_end].strip()
        start += len(text[start:literal_end]) - len(text[start:literal_end].lstrip())
        q = Quantity(id="", text=text_lit, start=start, end=start + len(text_lit), value=lo, upper=hi, unit=unit,
                     kind=UNITS[unit][0], approx=(m.group("approx") or "").strip())
        found.append(q)
        taken.append((q.start, q.end))

    for m in RATIO_RE.finditer(text):
        if _overlaps(taken, m.start(), m.end()):
            continue
        # avoid times like 10:30 that are preceded by "at"
        if re.search(r"\bat\s*$", text[max(0, m.start() - 4):m.start()]):
            continue
        q = Quantity(id="", text=m.group(0), start=m.start(), end=m.end(), value=None, upper=None, unit="ratio", kind="ratio")
        found.append(q)
        taken.append((m.start(), m.end()))

    for m in COUNT_RE.finditer(text):
        if _overlaps(taken, m.start(), m.end()):
            continue
        raw = m.group("n") or m.group("m")
        word = (m.group("w") or "").lower()
        value = float(raw) if raw else {"once": 1, "twice": 2, "thrice": 3}.get(word)
        # "8 x 30 mm" is a dimension, not a count: skip if a length follows.
        if raw and re.match(r"\s*\d+(?:\.\d+)?\s*(?:mm|cm|µm|um|m)\b", text[m.end():]):
            continue
        q = Quantity(id="", text=m.group(0), start=m.start(), end=m.end(), value=value, upper=None, unit="times", kind="count")
        found.append(q)
        taken.append((m.start(), m.end()))

    # "3 times", "three times" are caught by QUANTITY_RE with unit "times". Dimensions "8 x 30 mm":
    for m in re.finditer(r"(?<![\w.])\d+(?:\.\d+)?\s*[x×]\s*\d+(?:\.\d+)?\s*(?:mm|cm|µm|um)\b", text):
        if _overlaps([(q.start, q.end) for q in found if q.kind != "length"], m.start(), m.end()):
            continue
        found = [q for q in found if not (q.start >= m.start() and q.end <= m.end())]
        found.append(Quantity(id="", text=m.group(0), start=m.start(), end=m.end(), value=None, upper=None,
                              unit=m.group(0).split()[-1] if " " in m.group(0) else "mm", kind="dimensions"))

    for m in DEGREE_ONLY_RE.finditer(text):
        if _overlaps([(q.start, q.end) for q in found] + list(skip_spans), m.start(), m.end()):
            continue
        found.append(Quantity(id="", text=m.group(0), start=m.start(), end=m.end(), value=float(m.group("v")),
                              upper=None, unit="deg", kind="angle"))

    found.sort(key=lambda q: q.start)
    for i, q in enumerate(found, 1):
        q.id = f"Q{i}"
        if q.unit in UNITS:
            q.base_unit = UNITS[q.unit][2]
            q.base_value = _to_base(q.value, q.unit)
            q.base_upper = _to_base(q.upper, q.unit)
        if sentence_of:
            q.sentence = sentence_of(q.start)
    return found


def normalize_unit_text(text):
    return unicodedata.normalize("NFKC", text).replace("μ", "µ")


def parse_literal(literal):
    """Parse a quantity literal supplied by a model (fallback when the tagger missed it)."""
    qs = tag_quantities(literal)
    return qs[0] if len(qs) == 1 else None
