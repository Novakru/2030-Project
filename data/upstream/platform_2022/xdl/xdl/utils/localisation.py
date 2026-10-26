"""This modules contains utilities for generating human readable strings
describing the actions taken by different steps.

Human readable strings are generated from templates, of which there are
two types: regular and conditional.

Regular template strings are simple f-strings which are formatted using the
steps properties dict, e.g. ``'{reagent} was added'`` formatted with a
``Add(reagent='water', ...)`` step's properties dict would give the human
readable string `'water was added'`.

Conditional template dicts are more complicated and allow greater control over
sentence formation. To explain this a basic example for the ``Filter`` step is
shown below.

.. code-block:: json

    {
        "filtrate_vessel_fragment": {
            "filtrate_vessel": {
                "any": "sending filtrate to {filtrate_vessel}",
                "else": "discarding filtrate"
            },
        },
        "full": "Filter contents of {vessel}, {filtrate_vessel_fragment}"
    }

The value corresponding to the ``"full"`` key is almost the same as a regular
template string, it is an f-string formatted using the step properties dict.
However, in addition to the step properties dict it is also formatted with the
conditional sentence fragments defined above.

So in this example the outer key ``"filtrate_vessel_fragment"`` defines the
variable name of a value that will be supplied to the ``"full"`` template
string during formatting.

The inner ``"filtrate_vessel"`` key defines the prop which the value of
``filtrate_vessel_fragment`` will depend on. The inner dict specifies
sentence fragments for different values of ``filtrate_vessel``. These sentence
fragments can themselves be template strings and will be formatted using the
step properties dict. The keys of the inner dict can be specific values, or
``"any"`` signifying any value that is not ``None``, or ``"else"`` signifying
``None``.

So in this example ``<Filter vessel="filter" filtrate_vessel="rotavap" />``
would give the human readable string `"Filter contents of filter, sending
filtrate to rotavap."`

``<Filter vessel="filter" />`` would give the human readable string `"Filter
contents of filter, discarding filtrate."`
"""

from typing import List, Dict

def get_available_languages(localisation: Dict) -> List[str]:
    """Get list of languages that are available for outputting human readable
    procedure descriptions.

    Args:
        Dict: Localisation collection, e.g. ``PlatformClass().localisation``

    Returns:
        List[str]: List of language codes, e.g. ['en', 'zh']
    """
    available_languages = ['en']
    for _, human_readables in localisation.items():
        for language in human_readables:
            if language not in available_languages:
                available_languages.append(language)
    return available_languages

def conditional_human_readable(step, language_human_readable):
    """Convert step and given conditional human readable Dict to human readable
    string. A full description of the conditional template system is given in
    the module docstring at the top of this file.

    Args:
        step (Step): Step to generate human readable for.
        language_human_readable (Dict): Conditional human readable template to
            generate step human readable from.

    Returns:
        str: Human readable sentence describing step.
    """
    # Get overall template str
    template_str = language_human_readable['full']

    # Get formatted properties
    formatted_properties = step.formatted_properties()

    # Resolve conditional template fragments and apply to full
    # template str
    for fragment_identifier, condition_prop_dict\
            in language_human_readable.items():

        # Ignore full template str
        if fragment_identifier != 'full':

            # Match prop conditions
            for condition_prop, condition_val_dict\
                    in condition_prop_dict.items():

                # Get actual val
                condition_actual_val = step.properties[
                    condition_prop]
                condition_actual_val_str =\
                    str(condition_actual_val).lower()

                sub_val = ''

                # Exact match
                if (condition_actual_val_str
                        in condition_val_dict):
                    sub_val = condition_val_dict[
                        condition_actual_val_str]

                # Any match
                elif (condition_actual_val is not None
                        and 'any' in condition_val_dict):
                    sub_val = condition_val_dict['any']

                # Else match
                else:
                    sub_val = condition_val_dict['else']

                # Fragment identifier is not a property, add it
                # to formatted properties.
                if fragment_identifier not in step.properties:
                    formatted_properties[fragment_identifier] =\
                        sub_val

                # Fragment identifier is a property, replace
                # the property in the template_str with the new
                # fragment, so .format is called on the new
                # fragment.
                template_str = template_str.replace(
                    '{' + fragment_identifier + '}', sub_val)

    # Postprocess
    human_readable = template_str.format(**formatted_properties)
    human_readable = postprocess_human_readable(human_readable)
    return human_readable

def postprocess_human_readable(human_readable: str) -> str:
    """Fix whitespace issues created by conditional template system.
    Specifically ``' ,'``, ``'  '`` and ``' .'``.
    """
    while '  ' in human_readable:
        human_readable = human_readable.replace('  ', ' ')
    human_readable = human_readable.replace(' ,', ',')
    human_readable = human_readable.replace(' .', '.')
    human_readable = human_readable.rstrip('. ')
    human_readable += '.'
    return human_readable
