"""Optional PubChem raw-response cache; never guess a number from mixed-condition prose."""
from __future__ import annotations

import requests

from .io import ROOT, digest, load_library, read_json, write_json


def sync_pubchem():
    report = []
    for name, entry in load_library("properties.yaml")["solvents"].items():
        cid = entry.get("cid")
        if not cid:
            continue
        url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON?heading=Chemical%20and%20Physical%20Properties"
        path = ROOT / "data/upstream/pubchem" / (str(cid) + ".json")
        try:
            if path.exists():
                data = read_json(path)
                status = "cached"
            else:
                response = requests.get(url, timeout=20, headers={"User-Agent": "protocol-risk-research/0.1"})
                response.raise_for_status()
                data, status = response.json(), "fetched"
            if data.get("Record", {}).get("RecordNumber") != cid:
                raise ValueError("PubChem CID mismatch")
            write_json(path, data)
            report.append({"solvent": name, "cid": cid, "status": status, "url": url,
                           "sha256": digest(path.read_bytes()), "numeric_properties_updated": False})
        except (requests.RequestException, ValueError) as error:
            report.append({"solvent": name, "cid": cid, "status": "unavailable", "url": url,
                           "error_type": type(error).__name__, "numeric_properties_updated": False})
    write_json(ROOT / "reports/pubchem_availability.json", {"results": report,
               "policy": "Raw responses are cached. Numeric curated facts require source-specific review; failures never trigger guessed fallbacks."})
    return {"cached_or_fetched": sum(x["status"] != "unavailable" for x in report),
            "unavailable": sum(x["status"] == "unavailable" for x in report)}
