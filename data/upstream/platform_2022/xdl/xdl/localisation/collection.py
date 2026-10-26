"""
Load step description localisations for different languages for standard steps.
"""

import os
import json
from typing import List, Dict, Any

HERE = os.path.abspath(os.path.dirname(__file__))

def read_localisation_file(f: str) -> List[Dict[str, Any]]:
    """Reads a localisation file and loads up information

    Args:
        f (str): Name of localisation file

    Raises:
        ValueError: Language not supported

    Returns:
        List[Dict[str, Any]]: Localisation information
    """

    # Read in the file
    with open(f, encoding='utf-8') as fd:
        step_localisations = json.load(fd)

    return step_localisations

def load_localisations() -> Dict[str, Any]:
    """Load up localisations for each step

    Returns:
        Dict[str, Any]: Localisation information
    """

    # Set Filepaths to steps

    localisations = {}
    for f in os.listdir(HERE):
        if f.endswith('.json'):
            f_path = os.path.join(HERE, f)
            localisations.update(read_localisation_file(f_path))

    localisations.update(
        read_localisation_file(os.path.join(HERE, 'special_steps.json')))

    return localisations


#: Localisations for all standard steps. Dict is in form
#: ``{step_name: step_localisation...}``
LOCALISATIONS: Dict[str, Any] = load_localisations()
