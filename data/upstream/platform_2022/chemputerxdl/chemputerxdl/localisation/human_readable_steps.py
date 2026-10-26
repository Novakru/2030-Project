"""
.. module:: localisation.human_readable_steps
    :platforms: Unix, Windows
    :synopsis: Designed to load localisations for different languages

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
    steps_utility = os.path.join(HERE, 'steps_utility')
    steps_synthesis = os.path.join(HERE, 'steps_synthesis')
    steps_base = os.path.join(HERE, 'steps_base')

    localisations = {}
    for folder in [steps_utility, steps_synthesis, steps_base]:
        for f in os.listdir(folder):
            f_path = os.path.join(folder, f)
            localisations.update(read_localisation_file(f_path))

    localisations.update(
        read_localisation_file(
            os.path.join(HERE, 'unimplemented_steps.json')))
    localisations.update(
        read_localisation_file(os.path.join(HERE, 'special_steps.json')))

    return localisations


HUMAN_READABLE_STEPS = load_localisations()
