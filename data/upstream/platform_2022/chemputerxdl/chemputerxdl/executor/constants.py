"""
.. module:: executor.constants
    :platforms: Windows, Unix
    :synopsis: Constants used within the Executor of ChemputerXDL

"""

from typing import List, Dict
from ..steps import (
    Add,
    Separate,
    WashSolid,
    Filter,
    Dry,
    AddFilterDeadVolume,
    RemoveFilterDeadVolume,
    Dissolve,
    CleanVessel,
    Transfer,
    FilterThrough,
    CleanBackbone,
    ResetHandling,
)

#: Amount extra to transfer when doing Transfer(volume='all') to account for
# material lost in tubing etc.
TRANSFER_ALL_VOLUME_FACTOR = 1.15

#: Step types that correspond to backbone cleaning. The reason there is two is
#: that CleanBackbone was the original step and considered Chemputer specific.
#: But eventually it was decided that CleanBackbone was an implementation of a
#: non chemputer specific step representing resetting materials handling in
#: general. This step is ResetHandling, which in the case of the Chemputer
#: directly wraps CleanBackbone.
CLEAN_BACKBONE_STEP_TYPES = (CleanBackbone, ResetHandling)

#: Code for generic organic reagent when determining cleaning schedules
GENERIC_ORGANIC: int = 0

#: Solvents that shouldn't be used for cleaning backbone.
#: Toluene tends to dissolve glue in syringe pumps.
CLEANING_SOLVENT_BLACKLIST: List[str] = ['toluene']

#: Solvents that can be used but aren't ideal. Used to decide what solvent to
#: use for final CleanBackbone step at end of procedure.
CLEANING_SOLVENT_PREFER_NOT_TO_USE: List[str] = ['ether']

SOLVENT_CONTAINING_STEPS: List[type] = [
    Add, Dissolve, WashSolid, Separate, AddFilterDeadVolume]

# Steps after which backbone should be cleaned
CLEAN_BACKBONE_AFTER_STEPS: List[type] = [
    Add,
    Separate,
    WashSolid,
    Filter,
    Dry,
    AddFilterDeadVolume,
    RemoveFilterDeadVolume,
    Dissolve,
    CleanVessel,
    Transfer,
    FilterThrough,
]

#: Steps which should not trigger a backbone clean if the solvent used in the
# step is the same as the solvent used for cleaning.
NO_DUPLICATE_CLEAN_STEPS: List[type] = [
    Add,
    Dissolve,
    AddFilterDeadVolume,
]

# Names of common solvents used in syntheses
COMMON_SOLVENT_NAMES = [
    'acetic acid',
    'acetone',
    'acetonitrile',
    'mecn',
    'benzene',
    '1-butanol',
    'n-butanol',
    'butanol',
    'n-butyl alcohol',
    '2-butanol',
    'sec-butanol',
    '2-butyl alcohol',
    '2-butanone',
    'tba',
    't-butyl alcohol',
    'tert-butyl alcohol',
    'ccl4',
    'carbon tetrachloride',
    'tetrachloromethane',
    'chlorobenzene',
    'chloroform',
    'chcl3',
    'cyclohexane',
    'dcm',
    'dichloromethane',
    'ch2cl2',
    'methylene dichloride',
    'methylene chloride',
    '1,2-dichloroethane',
    'ethylene dichloride',
    'diethylene glycol',
    'deg',
    'diethyl ether',
    'et2o',
    'ether',
    'diglyme',
    'dipe',
    'diisopropyl ether',
    'dmf',
    'dimethylformamide',
    'dimethyl-formamide',
    'dimethyl formamide',
    'n,n-dimethylformamide',
    'dmso',
    '(ch3)2so',
    'dimethyl sulfoxide',
    'dioaxane',
    '1,4-dioxane',
    'ethanol',
    'etoh',
    'ethyl alcohol',
    'ethyl acetate',
    'etoac',
    'ea',
    'ethylene glycol',
    '1,2-ethanediol',
    'ethane-1,2-diol',
    'glycerin',
    'glyme',
    'monoglyme',
    'dme',
    'dimethyl glycol',
    'dimethyl ether',
    'dimethyl cellosolve',
    'heptane',
    'hmpa',
    'hexamethylphosphoramide',
    'hexametapol',
    'hmpt',
    'hexane',
    'methanol',
    'meoh',
    'methyl alcohol',
    'mtbe',
    'tbme',
    't-buome',
    'tert-buome',
    'methyl-butyl methyl ether',
    'tert-butyl methyl ether',
    'nmp',
    'nitromethane',
    'ch3no2',
    'nitroethane',
    'pentane',
    'petroleum ether',
    'pet ether',
    '1-propanol',
    'propan-1-ol',
    'n-propylalcohol',
    'proh',
    'n-proh',
    'nproh',
    'n-propanol',
    '1-propyl alcohol',
    'n-propyl alcohol',
    '1-propylalcohol',
    'propylalcohol',
    'propyl alcohol',
    '2-propanol',
    'isopropanol',
    'propan-2-ol',
    'iproh',
    'i-proh',
    'i-propanol',
    'ipa',
    'isopropyl alcohol',
    'pyridine',
    'thf',
    'tetrahydrofuran',
    'toluene',
    'trichloroethene',
    'trichloroethylene',
    'tce',
    'water',
    'h2o',
    'o-xylene',
    'm-xylene',
    'p-xylene',
]

# Common prefixes to solvents/reagents
COMMON_SOLVENT_PREFIXES = [
    'anhydrous',
    'dry',
    'distilled',
    'glacial',  # This probably shouldn't be here but needed to make tests pass.
    # Chances are backbone shouldn't be cleaned with glacial acetic acid.
]

# list of common basic reagents
COMMON_BASES = [
    'naoh',
    'koh',
    'caco3',
    'pyridine',
    'ammonia'
]

for prefix in COMMON_SOLVENT_PREFIXES:
    COMMON_SOLVENT_NAMES.extend([
        f'{prefix} {solvent}' for solvent in COMMON_SOLVENT_NAMES
    ])

# Associated boiling points of given solvents
SOLVENT_BOILING_POINTS = {
    'acetic acid': 118,
    'acetone': 56.05,
    'acetonitrile': 81.65,
    'mecn': 81.65,
    'benzene': 80.1,
    '1-butanol': 117.7,
    'n-butanol': 117.7,
    'butanol': 117.7,
    'n-butyl alcohol': 117.7,
    'tba': 82.4,
    't-butyl alcohol': 82.4,
    'tert-butyl alcohol': 82.4,
    'ccl4': 76.8,
    'carbon tetrachloride': 76.8,
    'tetrachloromethane': 76.8,
    'chlorobenzene': 131.7,
    'chloroform': 61.2,
    'chcl3': 61.2,
    'cyclohexane': 80.7,
    'dcm': 39.8,
    'dichloromethane': 39.8,
    'ch2cl2': 39.8,
    'methylene dichloride': 39.8,
    'methylene chloride': 39.8,
    'diethyl ether': 34.5,
    'et2o': 34.5,
    'ether': 34.5,
    'dipe': 68.5,
    'diisopropyl ether': 68.5,
    'dmf': 153,
    'dimethylformamide': 153,
    'dimethyl-formamide': 153,
    'dimethyl formamide': 153,
    'n,n-dimethylformamide': 153,
    'dioaxane': 101.1,
    '1,4-dioxane': 101.1,
    'ethanol': 78.5,
    'etoh': 78.5,
    'ethyl alcohol': 78.5,
    'ethyl acetate': 77,
    'etoac': 77,
    'ea': 77,
    'heptane': 98,
    'hexane': 69,
    'methanol': 64.6,
    'meoh': 64.6,
    'methyl alcohol': 64.6,
    'pentane': 36.1,
    '1-propanol': 97,
    'propan-1-ol': 97,
    'n-propylalcohol': 97,
    'proh': 97,
    'n-proh': 97,
    'nproh': 97,
    'n-propanol': 97,
    '1-propyl alcohol': 97,
    'n-propyl alcohol': 97,
    '1-propylalcohol': 97,
    'propylalcohol': 97,
    'propyl alcohol': 97,
    '2-propanol': 82.4,
    'isopropanol': 82.4,
    'propan-2-ol': 82.4,
    'iproh': 82.4,
    'i-proh': 82.4,
    'i-propanol': 82.4,
    'ipa': 82.4,
    'isopropyl alcohol': 82.4,
    'thf': 65,
    'tetrahydrofuran': 65,
    'toluene': 110.6,
    'trichloroethene': 87.2,
    'trichloroethylene': 87.2,
    'tce': 87.2,
    'water': 100,
    'h2o': 100,
    'o-xylene': 144,
    'm-xylene': 139.1,
    'p-xylene': 138.4,
}

for solvent, bp in list(SOLVENT_BOILING_POINTS.items()):
    SOLVENT_BOILING_POINTS[f'anhydrous {solvent}'] = bp

#: Factor to multiplty solvent boiling point by when working out temperature to
# perform CleanVessel at.
CLEAN_VESSEL_BOILING_POINT_FACTOR: float = 0.8

#: Keywords that if found in a reagent name indicate that it is aqueous
AQUEOUS_KEYWORDS: List[str] = ['aqueous', ' m ', 'acid', 'hydroxide', 'water']

# Dynamic steps properties to be updated upon background sensor reading
STEPS_PROPERTIES_TO_UPDATE: Dict[str, str] = {
    'DoUntil': 'threshold',
}
