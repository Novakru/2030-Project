"""Build gold ProcGraph references (assistant draft; needs expert review).

Each gold is written in the same model-facing JSON form the extractor emits, then
passed through the production coercer and validator, so a gold that does not
satisfy the IR contract fails the build. Q-ids are frozen together with their
character spans; the evaluator aligns by span, so tagger changes do not break golds.

Run:  python evaluation/procgraph_gold/build_gold.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mosaic.pg.ir import coerce, validate  # noqa: E402
from mosaic.pg.preprocess import prepare  # noqa: E402


def M(i, name, *aliases, kind="substance"):
    return {"id": i, "name": name, "aliases": list(aliases), "kind": kind}


def EQ(i, name, type_="tool", **props):
    return {"id": i, "name": name, "type": type_, "props": {k: {"q": v} for k, v in props.items()}}


def I(ref, *qs, role="", note=""):
    return {"ref": ref, "amounts": list(qs), "role": role, "note": note}


def T(id_, op, sent, target=None, inputs=(), out=None, origin="action", vessel=None, equipment=(), surface="",
      label="", outputs=None, **params):
    p = {}
    for k, v in params.items():
        p[k] = {"q": v} if isinstance(v, list) else {"text": v}
    outs = outputs if outputs is not None else ([{"id": out, "role": "main", "label": label}] if out else [])
    return {"id": id_, "op": op, "origin": origin, "sentences": sent if isinstance(sent, list) else [sent],
            "surface": surface, "target": target, "inputs": list(inputs), "params": p, "vessel": vessel,
            "equipment": list(equipment), "outputs": outs}


def OUT(id_, role, label=""):
    return {"id": id_, "role": role, "label": label}


GOLD = {}

# ----------------------------------------------------------------------------- minimal pairs
SYN = {
    "syn-into-suspension": (
        "A solution of compound A (1.00 g, 4.0 mmol) in THF (10 mL) was added dropwise to a suspension of "
        "compound B (2.00 g) and compound C (0.50 g) in toluene (20 mL) at 0 °C. The mixture was stirred for 2 h."),
    "syn-reversed-roles": (
        "A suspension of compound B (2.00 g) and compound C (0.50 g) in toluene (20 mL) was added dropwise to a "
        "solution of compound A (1.00 g, 4.0 mmol) in THF (10 mL) at 0 °C. The mixture was stirred for 2 h."),
    "syn-explicit-prep": (
        "Compound B (2.00 g) and compound C (0.50 g) were suspended in toluene (20 mL). Separately, compound A "
        "(1.00 g, 4.0 mmol) was dissolved in THF (10 mL). The THF solution was added dropwise to the suspension "
        "at 0 °C and the mixture was stirred for 2 h."),
    "syn-filter-branch": (
        "The reaction mixture was filtered through Celite. The filter cake was washed with ethyl acetate (2 x 10 mL) "
        "and discarded. The combined filtrate was washed with brine (20 mL), dried over Na2SO4 and concentrated to "
        "give the crude product (1.2 g)."),
}
_mat_abc = [M("mA", "compound A"), M("mB", "compound B"), M("mC", "compound C"), M("mT", "THF"), M("mTol", "toluene")]
GOLD["syn-into-suspension"] = {
    "materials": _mat_abc,
    "steps": [
        T("t1", "prepare", "S1", inputs=[I("mA", "Q1", "Q2", role="solute"), I("mT", "Q3", role="solvent")], out="x1",
          origin="described", label="solution of A in THF", surface="A solution of"),
        T("t2", "prepare", "S1", inputs=[I("mB", "Q4"), I("mC", "Q5"), I("mTol", "Q6", role="solvent")], out="x2",
          origin="described", label="suspension of B and C", surface="a suspension of"),
        T("t3", "add", "S1", target="x2", inputs=[I("x1")], out="x3", surface="was added dropwise", method="dropwise",
          temperature=["Q7"]),
        T("t4", "stir", "S2", target="x3", out="x4", duration=["Q8"]),
    ],
}
GOLD["syn-reversed-roles"] = {
    "materials": _mat_abc,
    "steps": [
        T("t1", "prepare", "S1", inputs=[I("mB", "Q1"), I("mC", "Q2"), I("mTol", "Q3", role="solvent")], out="x1",
          origin="described", label="suspension of B and C"),
        T("t2", "prepare", "S1", inputs=[I("mA", "Q4", "Q5", role="solute"), I("mT", "Q6", role="solvent")], out="x2",
          origin="described", label="solution of A in THF"),
        T("t3", "add", "S1", target="x2", inputs=[I("x1")], out="x3", method="dropwise", temperature=["Q7"]),
        T("t4", "stir", "S2", target="x3", out="x4", duration=["Q8"]),
    ],
}
GOLD["syn-explicit-prep"] = {
    "materials": _mat_abc,
    "steps": [
        T("t1", "prepare", "S1", inputs=[I("mB", "Q1"), I("mC", "Q2"), I("mTol", "Q3", role="solvent")], out="x1",
          label="suspension", surface="were suspended"),
        T("t2", "prepare", "S2", inputs=[I("mA", "Q4", "Q5", role="solute"), I("mT", "Q6", role="solvent")], out="x2",
          label="THF solution", surface="was dissolved"),
        T("t3", "add", "S3", target="x1", inputs=[I("x2")], out="x3", method="dropwise", temperature=["Q7"]),
        T("t4", "stir", "S3", target="x3", out="x4", duration=["Q8"]),
    ],
}
GOLD["syn-filter-branch"] = {
    "materials": [M("m1", "reaction mixture", kind="unknown"), M("m2", "Celite"), M("m3", "ethyl acetate"),
                  M("m4", "brine"), M("m5", "Na2SO4"), M("m6", "crude product", kind="unknown")],
    "steps": [
        T("t1", "filter", "S1", target="m1", outputs=[OUT("x1", "solid", "filter cake"), OUT("x2", "filtrate")],
          method="through Celite"),
        T("t2", "wash", "S2", target="x1", inputs=[I("m3", "Q2")], outputs=[OUT("x3", "main"), OUT("x4", "washings")],
          repeat=["Q1"]),
        T("t3", "discard", "S2", target="x3"),
        T("t4", "wash", "S3", target="x2", inputs=[I("m4", "Q3")], out="x5", note="combined with washings"),
        T("t5", "dry", "S3", target="x5", inputs=[I("m5")], out="x6"),
        T("t6", "concentrate", "S3", target="x6", out="x7"),
    ],
    "products": [{"ref": "m6", "state": "x7", "amounts": ["Q4"], "sentences": ["S3"]}],
}

# ----------------------------------------------------------------------------- ORD samples
GOLD["ord-8841b6b409c7485da9c83fc3053ea8a7"] = {
    "materials": [M("m1", "sodium methylate"), M("m2", "methanol"),
                  M("m3", "3,7-dichloro-8-triphenylphosphoniummethylquinoline chloride"),
                  M("m4", "3,7-dichloro-8-formylquinoline"), M("m5", "ethanol"), M("m6", "water")],
    "steps": [
        T("t1", "prepare", "S1", inputs=[I("m1", role="solute"), I("m2", role="solvent")], out="x1", origin="described",
          label="15% sodium methylate in methanol", concentration=["Q2"], surface="solution of sodium methylate in methanol"),
        T("t2", "prepare", "S1", inputs=[I("m3", "Q3"), I("m4", "Q4"), I("m5", "Q5", role="solvent")], out="x2",
          origin="described", label="suspension", surface="a suspension of"),
        T("t3", "add", "S1", target="x2", inputs=[I("x1", "Q1")], out="x3", method="dropwise",
          temperature="room temperature", surface="were added dropwise"),
        T("t4", "stir", "S2", target="x3", out="x4", duration=["Q6"]),
        T("t5", "filter", "S2", target="x4", outputs=[OUT("x5", "solid", "yellow precipitate")], method="under suction"),
        T("t6", "wash", "S2", target="x5", inputs=[I("m6")], out="x6", surface="treated with water"),
        T("t7", "filter", "S2", target="x6", outputs=[OUT("x7", "solid")], method="under suction"),
    ],
    "observations": [{"sentences": ["S2"], "text": "yellow precipitate", "step": "t5"}],
}
GOLD["ord-0eefa53de79e45e78ff547734006edb6"] = {
    "materials": [M("m1", "bromine"), M("m2", "2,3-dihydro-2-methylbenzo[b]furan"), M("m3", "sodium bicarbonate"),
                  M("m4", "methylene chloride"), M("m5", "water"), M("m6", "sodium sulfate"),
                  M("m7", "5-bromo-2,3-dihydro-2-methylbenzo[b]furan"),
                  M("m8", "5,7-dibromo-2,3-dihydro-2-methylbenzo[b]furan")],
    "steps": [
        T("t1", "prepare", "S1", inputs=[I("m2", "Q4", "Q5"), I("m3", "Q6", "Q7"), I("m4", "Q8"), I("m5", "Q9")],
          out="x1", origin="described", label="mixture", surface="a mixture of"),
        T("t2", "add", "S1", target="x1", inputs=[I("m1", "Q1", "Q2")], out="x2", method="dropwise",
          temperature=["Q3"], stirring="efficient stirring", surface="are added dropwise"),
        T("t3", "stir", "S2", target="x2", out="x3", duration=["Q10"], temperature=["Q11"]),
        T("t4", "separate_phases", "S3", target="x3", outputs=[OUT("x4", "organic")]),
        T("t5", "dry", "S3", target="x4", inputs=[I("m6")], out="x5"),
        T("t6", "concentrate", "S3", target="x5", out="x6"),
        T("t7", "distill", "S3", target="x6", out="x7", pressure="in vacuo", surface="fractionated in vacuo"),
    ],
    "products": [{"ref": "m7", "state": "x7", "amounts": ["Q12"], "yield": ["Q13"], "sentences": ["S4"]},
                 {"ref": "m8", "state": "x7", "amounts": ["Q14"], "yield": ["Q15"], "sentences": ["S4"]}],
}
GOLD["ord-158931abc49c434a86a39a133b41a3f5"] = {
    "materials": [M("m1", "(Nα,Nε -ditertbutoxycarbonyl-L-lysyl)-N-(4-bromo-2-picolinoylphenyl)glycinamide"),
                  M("m2", "hydrogen chloride"), M("m3", "dioxan"), M("m4", "diethyl ether"), M("m5", "methanol"),
                  M("m6", "ethyl acetate"), M("m7", "water"), M("m8", "chloroform"),
                  M("m9", "L-lysyl-N-(4-bromo-2-picolinoylphenyl)glycinamide trihydrochloride 1.5 H2O")],
    "steps": [
        T("t1", "prepare", "S1", inputs=[I("m2", role="solute"), I("m3", role="solvent")], out="x1", origin="described",
          label="HCl in dioxan", concentration=["Q3"]),
        T("t2", "add", "S1", target="x1", inputs=[I("m1", "Q1")], out="x2", origin="described",
          surface="was stirred for 1 hour in"),
        T("t3", "stir", "S1", target="x2", out="x3", duration=["Q2"]),
        T("t4", "add", "S2", target="x3", inputs=[I("m4")], out="x4"),
        T("t5", "filter", "S2", target="x4", outputs=[OUT("x5", "solid", "solid which separated")]),
        T("t6", "wash", "S2", target="x5", inputs=[I("m4")], out="x6"),
        T("t7", "dry", "S2", target="x6", out="x7"),
        T("t8", "dissolve", "S3", target="x7", inputs=[I("m5")], out="x8"),
        T("t9", "precipitate", "S3", target="x8", inputs=[I("m6")], out="x9"),
        T("t10", "dissolve", "S4", target="x9", inputs=[I("m7", "Q4")], out="x10"),
        T("t11", "extract", "S4", target="x10", inputs=[I("m8")], outputs=[OUT("x11", "aqueous")]),
        T("t12", "lyophilize", "S4", target="x11", out="x12"),
    ],
    "products": [{"ref": "m9", "state": "x12", "amounts": ["Q5"], "yield": ["Q6"], "sentences": ["S4"]}],
}
GOLD["ord-e37c8de956f142e4847689cfe2cae743"] = {
    "materials": [M("m1", "ethanol"), M("m2", "nitrogen"), M("m3", "3,4-Diethylpyrrole F2", "F2"),
                  M("m4", "2-acetoxymethyl-5-benzyloxycarbonyl-4-methyl-3 -methoxycarbonylethylpyrrole F1", "F1"),
                  M("m5", "p-Toluenesulfonic acid"), M("m6", "F3", "product")],
    "equipment": [EQ("e1", "round bottom flask", "vessel", capacity=["Q1"]), EQ("e2", "rotary evaporator", "instrument"),
                  EQ("e3", "freezer", "instrument")],
    "steps": [
        T("t1", "add", "S2", inputs=[I("m1", "Q2")], out="x1", vessel="e1", surface="was placed"),
        T("t2", "inert", "S2", target="x1", inputs=[I("m2")], out="x2", duration=["Q3"], surface="purged with dry nitrogen"),
        T("t3", "add", "S3", target="x2", inputs=[I("m3", "Q4", "Q5"), I("m4", "Q6", "Q7")], out="x3"),
        T("t4", "heat", "S3", target="x3", out="x4", until="all of the pyrroles dissolved"),
        T("t5", "add", "S4", target="x4", inputs=[I("m5", "Q8")], out="x5"),
        T("t6", "heat", "S4", target="x5", out="x6", temperature=["Q9"], duration=["Q10"], surface="maintained at"),
        T("t7", "cool", "S6", target="x6", out="x7", temperature="room temperature"),
        T("t8", "concentrate", "S6", target="x7", out="x8", equipment=["e2"], volume_target="one half"),
        T("t9", "store", "S6", target="x8", out="x9", equipment=["e3"], duration="several hours"),
        T("t10", "filter", "S7", target="x9", outputs=[OUT("x10", "solid")], surface="collected by filtration"),
        T("t11", "wash", "S7", target="x10", inputs=[I("m1", note="small amount, cold")], out="x11", temperature="cold"),
    ],
    "products": [{"ref": "m6", "state": "x11", "amounts": ["Q11"], "yield": ["Q12"], "form": "off-white fine powder",
                  "sentences": ["S7"]}],
    "observations": [{"sentences": ["S5"], "text": "color changed from clear yellow to dark red; product precipitated",
                      "step": "t6"}],
}
GOLD["ord-8a5039f60afa42afa6418534e0bb4e31"] = {
    "materials": [M("m1", "fructose"), M("m2", "sodium 4-hydroxybutyrate"),
                  M("m3", "3-hydroxybutyrate-4-hydroxybutyrate copolymer"),
                  M("m4", "aqueous solution of sodium hypochroride", "sodium hypochroride"), M("m5", "distilled water")],
    "steps": [
        T("t1", "reference_procedure", "S1", inputs=[I("m2")], out="x1", label="copolymer",
          note="procedure of Example 2 repeated with sodium 4-hydroxybutyrate instead of fructose"),
        T("t2", "prepare", "S2", inputs=[I("m4", "Q4"), I("m5", "Q5")], out="x2", origin="described",
          total_volume=["Q3"], label="100 ml solution"),
        T("t3", "add", "S2", target="x2", inputs=[I("x1")], out="x3", label="suspension"),
        T("t4", "heat", "S2", target="x3", out="x4", temperature=["Q6"], duration=["Q7"]),
    ],
    "products": [{"ref": "m3", "state": "x1", "amounts": ["Q1"], "sentences": ["S1"]}],
    "observations": [{"sentences": ["S1"], "text": "copolymer comprises 20% by mole 4-hydroxybutyrate unit; Mn 467,000",
                      "quantities": ["Q2"]},
                     {"sentences": ["S3"], "text": "Mn of resulting product 182,000", "step": "t4"}],
}
GOLD["ord-38cadda2a33648a9ad5bbd9f93ac95f2"] = {
    "materials": [M("m1", "3,4,7,8-tetramethyl-1,10-phenanthroline"), M("m2", "[Ir(OMe)(cod)]2"), M("m3", "cyclohexane"),
                  M("m4", "N-Cyclopropylpivalamide", "1a"), M("m5", "4,4,5,5-tetramethyl-1,3,2-dioxaborolane", "HBpin"),
                  M("m6", "N2"), M("m7", "2a", "product 2a", "boronate 2a")],
    "equipment": [EQ("e1", "Schlenk flask", "vessel")],
    "steps": [
        T("t1", "prepare", "S1", inputs=[I("m1", "Q1", "Q2"), I("m2", "Q3", "Q4"), I("m3", "Q5", role="solvent")],
          out="x1", origin="described", vessel="e1", label="mixture"),
        T("t2", "stir", "S1", target="x1", out="x2", vessel="e1", duration=["Q6"], temperature="room temperature",
          atmosphere="N2"),
        T("t3", "add", "S2", target="x2", inputs=[I("m4", "Q7", "Q8"), I("m5", "Q9", "Q10"), I("m3", "Q11")], out="x3",
          atmosphere="N2 flow"),
        T("t4", "heat", "S3", target="x3", out="x4", temperature=["Q12"], duration=["Q13"], atmosphere="N2"),
        T("t5", "concentrate", "S4", target="x4", out="x5", pressure="in vacuo", label="residue"),
        T("t6", "chromatograph", "S5", target="x5", out="x6", eluent="chloroform/acetone", eluent_ratio=["Q14"],
          stationary_phase="silica gel", label="collected fractions"),
        T("t7", "chromatograph", "S6", target="x6", out="x7", eluent="hexane/ether", eluent_ratio=["Q15"],
          stationary_phase="silica gel"),
    ],
    "products": [{"ref": "m7", "state": "x7", "amounts": ["Q16"], "yield": ["Q17"], "form": "white solid",
                  "sentences": ["S6"]}],
    "observations": [{"sentences": ["S7"], "text": "NOE observed between H1 and H2"},
                     {"sentences": ["S8"], "text": "boronate 2a has cis configuration"}],
    "optional_materials": ["chloroform", "acetone", "hexane", "ether", "silica gel"],
}
GOLD["ord-dd820c31fef4456fb96fcbe0cfbfed80"] = {
    "materials": [M("m1", "Tris(dibenzylideneacetone)dipalladium(0)"),
                  M("m2", "2-Dicyclohexylphosphino-2',4',6'-triisopropylbiphenyl"), M("m3", "butyl acetate"),
                  M("m4", "argon"),
                  M("m5", "5-fluoro-4-(2-methyl-1-(tetrahydro-2H-pyran-4-yl)-1H-imidazol-5-yl)pyrimidin-2-amine"),
                  M("m6", "4-(4-bromobenzyl)morpholine"), M("m7", "Sodium tert-pentoxide")],
    "equipment": [EQ("e1", "Schlenk tube", "vessel", capacity=["Q6"])],
    "steps": [
        T("t1", "prepare", "S1", inputs=[I("m1", "Q1", "Q2"), I("m2", "Q3", "Q4"), I("m3", "Q5", role="solvent")],
          out="x1", vessel="e1", surface="were dissolved"),
        T("t2", "heat", "S1", target="x1", out="x2", temperature=["Q7"], duration=["Q8"], atmosphere="argon",
          surface="activated"),
        T("t3", "add", "S2", target="x2", inputs=[I("m5", "Q9", "Q10"), I("m6", "Q11", "Q12"), I("m7", "Q13", "Q14")],
          out="x3"),
        T("t4", "inert", "S3", target="x3", out="x4", method="degassed", surface="degassed again"),
        T("t5", "stir", "S3", target="x4", out="x5", temperature=["Q15"], atmosphere="argon"),
        T("t6", "monitor", "S4", target="x5", out="x6", method="HPLC"),
        T("t7", "discard", "S6", target="x6"),
    ],
    "observations": [{"sentences": ["S5"], "text": "no conversion observed after 4.5 h", "step": "t6",
                      "quantities": ["Q16"]}],
}
GOLD["ord-8a61495c860141f1a8046698b9543528"] = {
    "materials": [M("m1", "[Ir(cod)(OMe)]2"), M("m2", "L1 ligand"), M("m3", "B2pin2"), M("m4", "KOtBu"),
                  M("m5", "dry THF", "THF"), M("m6", "benzamide"), M("m7", "argon")],
    "equipment": [EQ("e1", "wheaton microreactor", "vessel", capacity=["Q1"]), EQ("e2", "glove box", "location"),
                  EQ("e3", "teflon pressure cap", "consumable"), EQ("e4", "aluminum block", "instrument")],
    "steps": [
        T("t1", "add", "S1", inputs=[I("m1", "Q2", "Q3"), I("m2", "Q4", "Q5"), I("m3", "Q6", "Q7"), I("m4", "Q8", "Q9"),
                                     I("m5", "Q10")], out="x1", vessel="e1", equipment=["e2"],
          atmosphere="argon filled glove box", surface="was charged with"),
        T("t2", "stir", "S2", target="x1", out="x2", duration=["Q11"], temperature="room temperature"),
        T("t3", "add", "S3", target="x2", inputs=[I("m6", "Q12", "Q13")], out="x3"),
        T("t4", "seal", "S4", target="x3", out="x4", equipment=["e3"], surface="capped"),
        T("t5", "heat", "S4", target="x4", out="x5", equipment=["e4"], temperature=["Q14"], duration=["Q15"],
          surface="placed into pre-heated aluminum block"),
    ],
    "observations": [{"sentences": ["S5"], "text": "conversion 23%, meta/para ratio 1/1.5 (GC/MS)", "step": "t5",
                      "quantities": ["Q16"]}],
}
GOLD["ord-000048416f294ed38b3a5181fc1060bf"] = {
    "materials": [M("m1", "catalysts"), M("m2", "solid bases"), M("m3", "1,2-dichloroethane"), M("m4", "sulfonamide"),
                  M("m5", "boronic acid"), M("m6", "reaction solvent", "MeCN, MeOH, DCE, or EtOAc"),
                  M("m7", "liquid bases"), M("m8", "biphenyl"), M("m9", "MeCN")],
    "equipment": [EQ("e1", "glass vial inserts", "vessel", dimensions=["Q1"]),
                  EQ("e2", "96 well-plate Para-dox Aluminum Reaction Blocks", "instrument"),
                  EQ("e3", "single-channel pipette", "tool"), EQ("e4", "Genevac EZ-2 evaporator", "instrument"),
                  EQ("e5", "Parylene-coated stir bars", "consumable", dimensions=["Q9"]),
                  EQ("e6", "stir bar dispenser", "tool"), EQ("e7", "3-Position Magnetic Tumble Stirrer", "instrument"),
                  EQ("e8", "96-well 1 mL polypropylene plate", "vessel", capacity=["Q22"]),
                  EQ("e9", "multi-channel pipettor", "tool"), EQ("e10", "PlateLoc Thermal Microplate Sealer", "instrument")],
    "steps": [
        T("t1", "prepare", "S3", inputs=[I("m1"), I("m3", role="solvent")], out="x1", origin="described",
          label="catalyst stock solution", concentration=["Q5"]),
        T("t2", "prepare", "S3", inputs=[I("m2"), I("m3", role="solvent")], out="x2", origin="described",
          label="base stock solution", concentration=["Q6"]),
        T("t3", "add", "S3", inputs=[I("x1", "Q2", "Q4"), I("x2", "Q3", note="50 uL each")], out="x3", vessel="e1",
          equipment=["e3"], scope="per vial", method="single-channel pipette"),
        T("t4", "concentrate", "S4", target="x3", out="x4", equipment=["e4"], method="centrifugal evaporation",
          temperature=["Q7"], duration=["Q8"]),
        T("t5", "setup", "S5", target="x4", out="x5", equipment=["e5", "e6"], surface="were loaded"),
        T("t6", "prepare", "S6", inputs=[I("m4"), I("m5"), I("m6", role="solvent")], out="x6",
          concentration=["Q10", "Q11"], label="sulfonamide/boronic acid stock", surface="were prepared"),
        T("t7", "add", "S6", target="x5", inputs=[I("x6", "Q12")], out="x7", surface="were dosed"),
        T("t8", "add", "S7", target="x7", inputs=[I("m7")], out="x8", equipment=["e3"], method="manually via pipette",
          surface="dispensed"),
        T("t9", "seal", "S8", target="x8", out="x9"),
        T("t10", "stir", "S8", target="x9", out="x10", equipment=["e7"], stir_speed=["Q13"], duration=["Q14"],
          temperature=["Q15"], surface="tumble-stirred"),
        T("t11", "setup", "S9", target="x10", out="x11", surface="removed from the heat"),
        T("t12", "cool", "S10", target="x11", out="x12"),
        T("t13", "prepare", "S10", inputs=[I("m8"), I("m9", role="solvent")], out="x13", origin="described",
          concentration=["Q17"], label="biphenyl stock solution"),
        T("t14", "add", "S10", target="x12", inputs=[I("x13", "Q16", "Q18")], out="x14", scope="each well"),
        T("t15", "seal", "S11", target="x14", out="x15"),
        T("t16", "stir", "S11", target="x15", out="x16", method="inverted", repeat=["Q19"], surface="inverted"),
        T("t17", "centrifuge", "S11", target="x16", out="x17", duration=["Q20"]),
        T("t18", "transfer", "S12", inputs=[I("x17", "Q21")], out="x18", vessel="e8", equipment=["e9"],
          scope="from each well", surface="was sampled"),
        T("t19", "dilute", "S13", target="x18", inputs=[I("m9", "Q23")], out="x19"),
        T("t20", "seal", "S13", target="x19", out="x20", equipment=["e10"]),
        T("t21", "analyze", "S13", target="x20", method="UPLC-MS"),
    ],
}
GOLD["ord-0281c64afe8a4dee8619538b12e034d0"] = {
    "materials": [M("m1", "pre-plated ligand", "ligand"), M("m2", "(cod)Pd(CH2TMS)2"), M("m3", "nBu3N"), M("m4", "MeCN"),
                  M("m5", "hydroxamic ether 3"), M("m6", "trimethoxybenzene")],
    "equipment": [EQ("e1", "vials", "vessel"), EQ("e2", "96-well reaction block", "instrument"),
                  EQ("e3", "glovebox", "location"), EQ("e4", "magnetic stirbars", "consumable"),
                  EQ("e5", "micropipettor", "tool"), EQ("e6", "temperature-controlled metal block", "instrument"),
                  EQ("e7", "stir plate", "instrument"), EQ("e8", "analysis collection plate", "vessel")],
    "steps": [
        T("t1", "setup", "S1", inputs=[I("m1", note="pre-plated in vials")], out="x1", vessel="e2",
          equipment=["e1", "e4", "e3"], surface="were added to a 96-well reaction block"),
        T("t2", "setup", "S2", out="", equipment=["e1"], surface="filled with empty vials"),
        T("t3", "prepare", "S2", inputs=[I("m2", "Q1", "Q2", "Q3"), I("m3", "Q4", "Q5", "Q6"), I("m4", "Q7", role="solvent")],
          out="x2", origin="described", label="Pd/nBu3N solution in MeCN"),
        T("t4", "add", "S2", target="x1", inputs=[I("x2")], out="x3", equipment=["e5"], scope="each of the 24 wells"),
        T("t5", "prepare", "S3", inputs=[I("m5", "Q8", "Q9", "Q10"), I("m4", "Q11", role="solvent")], out="x4",
          origin="described", label="hydroxamic ether solution"),
        T("t6", "add", "S3", target="x3", inputs=[I("x4")], out="x5", equipment=["e5"]),
        T("t7", "seal", "S4", target="x5", out="x6", surface="covered"),
        T("t8", "heat", "S5", target="x6", out="x7", equipment=["e6", "e7"], temperature=["Q12"], duration=["Q13"],
          stirring="stirred", surface="stirred at"),
        T("t9", "setup", "S6", target="x7", out="x8", surface="removed from the glovebox"),
        T("t10", "cool", "S6", target="x8", out="x9", temperature="rt"),
        T("t11", "open", "S6", target="x9", out="x10", atmosphere="air"),
        T("t12", "prepare", "S7", inputs=[I("m6", "Q14", "Q15", "Q16"), I("m4", "Q17", role="solvent")], out="x11",
          origin="described", label="internal standard solution"),
        T("t13", "add", "S7", target="x10", inputs=[I("x11")], out="x12", equipment=["e5"], scope="each of the 24 vials"),
        T("t14", "centrifuge", "S8", target="x12", out="x13"),
        T("t15", "transfer", "S8", inputs=[I("x13", "Q18")], out="x14", vessel="e8", equipment=["e5"]),
        T("t16", "seal", "S9", target="x14", out="x15"),
        T("t17", "centrifuge", "S9", target="x15", out="x16", duration=["Q19"]),
        T("t18", "analyze", "S10", target="x16", method="LC-MS"),
        T("t19", "analyze", "S11", target="x16", method="1H NMR"),
    ],
}

GOLD_STATUS = "assistant_draft_needs_expert_review"


def sources():
    out = dict(SYN)
    for f in ("examples/chemistry_pilot/sources.json", "examples/chemistry_holdout/sources.json"):
        for r in json.loads((ROOT / f).read_text(encoding="utf-8")):
            out[r["id"]] = r["procedure"]
    return out


def build(check=True):
    texts = sources()
    report = {}
    for sid, raw in GOLD.items():
        prepared = prepare(sid, texts[sid])
        raw = {k: v for k, v in raw.items() if k != "optional_materials"}
        for s in raw["steps"]:
            s["outputs"] = [o for o in s["outputs"] if o["id"]]
        graph, log = coerce(raw, prepared)
        errors, warnings = validate(graph, prepared)
        report[sid] = {"errors": errors, "warnings": warnings, "coercion": log}
        doc = {
            "schema": "mosaic.procgraph-gold/1", "source_id": sid, "status": GOLD_STATUS, "text": prepared.text,
            "tagger_version": prepared.tagger_version,
            "quantities": [{"id": q.id, "text": q.text, "start": q.start, "end": q.end} for q in prepared.quantities],
            "optional_materials": GOLD[sid].get("optional_materials", []),
            "graph": graph,
        }
        (HERE / f"{sid}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if check:
        bad = {k: v["errors"] for k, v in report.items() if v["errors"]}
        if bad:
            raise SystemExit(json.dumps(bad, ensure_ascii=False, indent=1))
    return report


if __name__ == "__main__":
    rep = build()
    for sid, r in rep.items():
        print(f"{sid}: errors={len(r['errors'])} warnings={[w['code'] + ':' + w['where'] for w in r['warnings']]}")
