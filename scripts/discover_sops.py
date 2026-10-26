"""Download primary SOP sources once; pin successful responses without changing existing pins."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import subprocess

import requests

from protocol_risk.io import ROOT, digest, read_json, write_json


SOURCES = {
    "epa_baaqmd": "https://www.epa.gov/system/files/documents/2022-09/baaqmd-sip-manual-of-procedures.pdf",
    "epa_to8": "https://www3.epa.gov/ttn/amtic/files/ambient/airtox/to-8.pdf",
    "epa_hudson_archive": "https://19january2021snapshot.epa.gov/sites/static/files/2020-01/documents/2004_05_28_bmp_qapp_appendices_book2.pdf",
    "epa_4204": "https://www.epa.gov/sites/default/files/2015-08/documents/method_420-4_1993.pdf",
    "epa_5151": "https://www.epa.gov/sites/default/files/2015-08/documents/method_515-1_1989.pdf",
    "nus_heating": "https://chemistry.nus.edu.sg/health-safety/more-safety-information/prepared-risk-assessment-for-equipment-and-procedures/use-of-laboratory-heating-equipment/",
    "jodc_jgofs": "https://www.jodc.go.jp/info/ioc_doc120810/Manual/m029.pdf",
    "iwea_qa2019": "https://indianawea.org/wp-content/uploads/2021/11/QA_QC_Manual_August_2019_3.pdf",
    "usgs_water1965": "https://pubs.usgs.gov/wsp/1822/report.pdf",
    "epa_qc2018": "https://19january2021snapshot.epa.gov/sites/static/files/2018-11/documents/quality_control_report_erg_csd-may_june2018_complete_002_redacted.pdf",
    "epa_crossett": "https://19january2021snapshot.epa.gov/sites/static/files/2017-12/documents/appendix_b-epa_hydrogen_sulfide_monitoring_qapp.pdf",
    "epa_hudson": "https://www3.epa.gov/hudson/baseline_may2004/2004_05_28_bmp_qapp_appendices_book2.pdf",
    "epa_40cfr136": "https://www.epa.gov/sites/default/files/2015-06/documents/40cfr136_03.pdf",
    "avantor_dmso": "https://avantor-prod.cxoneexpert.ai/Pharmaceutical_Product_Information/Product_Freezing/Dimethyl_Sulfoxide_Freezing/Freezing_of_Dimethyl_Sulfoxide",
    "goettingen_ethanol": "https://www.unterrichtsmaterialien-chemie.uni-goettingen.de/exp_neu.php?id=2",
}


def download(item):
    identifier, url = item
    try:
        response = requests.get(url, timeout=(15, 50))
        response.raise_for_status()
        is_pdf = response.content.startswith(b"%PDF-")
        suffix = ".pdf" if is_pdf else ".html"
        path = ROOT / "data/upstream/sop" / (identifier + suffix)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
        result = {"id": identifier, "url": url, "path": path.relative_to(ROOT).as_posix(),
                  "sha256": digest(response.content), "bytes": len(response.content), "admission": "discovery_only"}
        if is_pdf and shutil.which("pdftotext"):
            target = ROOT / "data/intermediate/sop_text" / (identifier + ".txt")
            target.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run([shutil.which("pdftotext"), "-layout", "-enc", "UTF-8", str(path), str(target)], check=True, capture_output=True)
            result.update(text_path=target.relative_to(ROOT).as_posix(), text_sha256=digest(target.read_bytes()),
                          extraction_tool="pdftotext -layout -enc UTF-8")
        return result
    except (requests.RequestException, subprocess.CalledProcessError) as error:
        return {"id": identifier, "url": url, "error": type(error).__name__, "admission": "unavailable"}


if __name__ == "__main__":
    manifest_path = ROOT / "data/sop_sources.lock.json"
    manifest = read_json(manifest_path)
    previous = {row["id"] for row in manifest["sources"] if row.get("sha256")}
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(download, ((k, v) for k, v in SOURCES.items() if k not in previous)))
    replacements = {row["id"] for row in results}
    manifest["sources"] = [row for row in manifest["sources"] if row["id"] not in replacements] + results
    write_json(manifest_path, manifest)
    print(json.dumps(results, indent=2))
