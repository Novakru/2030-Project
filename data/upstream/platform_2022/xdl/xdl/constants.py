from typing import List, Dict, Any

#: XDL version number. Used in header at top of outputted XDL files.
XDL_VERSION: str = '0.5.0'

########
# MISC #
########

#: Chemify API URL
CHEMIFY_API_URL: str = 'https://api.chemification.com'

#: Chemicals that will be recognised as inert gas.
INERT_GAS_SYNONYMS: List[str] = ['nitrogen', 'n2', 'ar', 'argon']

#: Chemical name if found in graph to be used as air source.
AIR: str = 'air'

#: Room temperature in °C
ROOM_TEMPERATURE: int = 25

#: Keywords that if found in reagent name signify that the reagent is aqueous.
AQUEOUS_KEYWORDS: List[str] = ['water', 'aqueous', 'acid', ' m ', 'hydroxide']

#: Attributes of the ``<Synthesis>`` element. This is kind of a relic from when
#: there were multiple attributes that could be included in the ``Synthesis``
#: tag. Might be sensible to just handle ``graph_sha256`` attribute specifically
#: rather than have this one element list.
SYNTHESIS_ATTRS: List[Dict[str, Any]] = [
    {
        'name': 'graph_sha256',
        'type': str,
        'default': '',
    }
]

#: Prop type if property is reagent declared in Reagent section.
REAGENT_PROP_TYPE: str = 'reagent'

#: Prop type if property is reaction mixture vessel.
VESSEL_PROP_TYPE: str = 'vessel'

#: JSON string prop type.
JSON_PROP_TYPE: str = 'json'
