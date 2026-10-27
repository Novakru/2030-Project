"""Source acquisition only. Dataset construction has one entry: python -m mosaic."""
import argparse
import json


def main(argv=None):
    from .api import probe
    from .ingest import fetch_locked, ingest
    from .publications import audit_publications, collect_chemputer
    from .props import sync_pubchem

    actions = {"api-check": probe, "fetch": fetch_locked, "ingest": ingest,
               "collect-chemputer": collect_chemputer, "audit-publications": audit_publications,
               "props-sync": sync_pubchem}
    parser = argparse.ArgumentParser(prog="protocol-risk", description=__doc__)
    parser.add_argument("command", choices=sorted(actions))
    args = parser.parse_args(argv)
    result = actions[args.command]()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not isinstance(result, dict) or result.get("passed", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
