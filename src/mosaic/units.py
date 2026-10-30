"""Small explicit dimensional adapter. Unknown units survive without conversion."""
from decimal import Decimal
import unicodedata
import re

# dimension, multiplier to a comparison unit, offset. No mass/mol inference.
_UNITS = {
    "ng": ("mass", "0.000001", "0"), "ug": ("mass", ".001", "0"), "mg": ("mass", "1", "0"),
    "g": ("mass", "1000", "0"), "kg": ("mass", "1000000", "0"),
    "nL": ("volume", ".000001", "0"), "uL": ("volume", ".001", "0"), "mL": ("volume", "1", "0"), "L": ("volume", "1000", "0"),
    "umol": ("substance_amount", ".001", "0"), "mmol": ("substance_amount", "1", "0"), "mol": ("substance_amount", "1000", "0"),
    "s": ("time", "1", "0"), "min": ("time", "60", "0"), "h": ("time", "3600", "0"), "d": ("time", "86400", "0"),
    "degC": ("temperature", "1", "0"), "K": ("temperature", "1", "-273.15"),
    "rpm": ("rotation_speed", "1", "0"), "rcf": ("relative_centrifugal_force", "1", "0"),
    "bar": ("pressure", "1", "0"), "mbar": ("pressure", ".001", "0"), "Pa": ("pressure", ".00001", "0"),
    "M": ("concentration", "1", "0"), "mM": ("concentration", ".001", "0"),
    "mol%": ("relative_loading", "1", "0"), "equiv": ("equivalents", "1", "0"), "%": ("percent", "1", "0"),
    "nm": ("length", "1", "0"), "mm": ("length", "1000000", "0"),
}
_ALIASES = {"sec": "s", "seconds": "s", "minutes": "min", "hours": "h", "hr": "h", "mins": "min",
            "°C": "degC", "oC": "degC", "C": "degC", "eq": "equiv", "equivalents": "equiv", "xg": "rcf", "×g": "rcf",
            "ml": "mL", "ul": "uL", "milligrams": "mg", "milliliters": "mL"}
_KINDS = {"nominal_volume": "volume", "device_volume": "volume", "capacity": "volume", "working_volume": "volume", "dose_volume": "volume",
          "duration": "time", "elapsed_time": "time", "molar_amount": "substance_amount", "amount_of_substance": "substance_amount",
          "heater_setpoint": "temperature", "sample_temperature": "temperature", "yield": "percent", "conversion": "percent"}


def normalized_quantity(value):
    unit = unit_name(value["unit"])
    kind = _KINDS.get(value["quantity_kind"], value["quantity_kind"])
    dimension, scale, offset = _UNITS.get(unit, ("unit:" + unit, "1", "0"))
    # "g" only means relative force when the quantity kind explicitly says so.
    if kind == "relative_centrifugal_force" and unit == "g":
        dimension, scale, offset = kind, "1", "0"
    known_dimensions = {entry[0] for entry in _UNITS.values()}
    if kind in known_dimensions and dimension in known_dimensions and kind != dimension:
        raise ValueError("Incompatible quantity kind/unit: " + value["quantity_kind"] + "/" + value["unit"])
    def convert(number):
        return str(Decimal(number) * Decimal(scale) + Decimal(offset))
    return {"dimension": dimension, "quantity_kind": kind, "value": convert(value["value"]),
            "upper_value": convert(value["upper_value"]) if value.get("upper_value") is not None else None,
            "basis_ref": value.get("basis_ref"), "basis_status": value.get("basis_status", "not_applicable")}


def unit_name(unit):
    unit = re.sub(r"\s+", "", unicodedata.normalize("NFKC", unit)).replace("μ", "u").replace("µ", "u")
    return _ALIASES.get(unit, unit)


def source_quantity_present(value, quotes):
    """Require printed number and associated unit; no scientific conversion here."""
    expected = unit_name(value["unit"])
    spellings = {value["unit"], expected, *(u for u in (*_UNITS, *_ALIASES) if unit_name(u) == expected)}
    pattern = r"(?<![\d.])" + re.escape(value["value"]) + r"(?![\d.])\s*"
    if value.get("upper_value") is not None:
        pattern += r"(?:[–−-]|to)\s*" + re.escape(value["upper_value"]) + r"\s*"
    normalize = lambda text: unicodedata.normalize("NFKC", text).replace("µ", "u").replace("μ", "u")
    units = [r"\s*".join(re.escape(c) for c in normalize(spelling)) for spelling in spellings]
    pattern += "(?:" + "|".join(sorted(units, key=len, reverse=True)) + r")(?![a-zA-Zµμ%])"
    return any(re.search(pattern, normalize(quote)) for quote in quotes)


def equivalent(a, b):
    if a["value_type"] != b["value_type"] or a["status"] != b["status"]:
        return False
    if a["value_type"] == "missing":
        return True  # A free-text explanation is not the unknown state itself.
    if a["value_type"] != "quantity":
        return a == b
    left, right = normalized_quantity(a), normalized_quantity(b)
    same_upper = left["upper_value"] is right["upper_value"] is None or left["upper_value"] is not None and right["upper_value"] is not None and Decimal(left["upper_value"]) == Decimal(right["upper_value"])
    return all(left[k] == right[k] for k in ("dimension", "quantity_kind", "basis_ref", "basis_status")) and same_upper and Decimal(left["value"]) == Decimal(right["value"])
