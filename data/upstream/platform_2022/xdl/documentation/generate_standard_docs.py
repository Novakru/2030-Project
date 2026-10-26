import os
import re
from xdl.constants import XDL_VERSION
from xdl.platforms import PlaceholderPlatform
from xdl.utils.schema import generate_schema

UNIMPLEMENTED_STEPS = [
    'Distill',
    'FreezePumpThaw',
    'Microwave',
    'Electrolyse',
    'ReactInFlow',
    'RunColumn',
    'DoUntil',
]

CATEGORIES = {
    'Liquid Handling': [
        'Add',
        'Transfer',
        'FilterThrough',
    ],
    'Stirring': [
        'StartStir',
        'StopStir',
        'Stir',
    ],
    'Temperature Control': [
        'HeatChill',
        'HeatChillToTemp',
        'StartHeatChill',
        'StopHeatChill',
        'Precipitate',
        'Crystallize',
        'Dissolve',
        'CleanVessel',
    ],
    'Inert Gas': [
        'StartPurge',
        'StopPurge',
        'Purge',
        'EvacuateAndRefill',
    ],
    'Filtration': [
        'Filter',
        'WashSolid',
        'Dry',
    ],
    'Other': [
        'Separate',
        'Evaporate',
        'AddSolid',
        'Irradiate',
    ]
}

# File Paths
HERE = os.path.abspath(os.path.dirname(__file__))
STEPS_TEMPLATE_FOLDER = os.path.join(
    os.path.dirname(HERE), 'xdl', 'steps', 'templates')

STEPS_OVERVIEW_RST_PATH = os.path.join(HERE, 'standard', 'steps-overview.rst')
FULL_STEPS_SPECIFICATION_RST_PATH = os.path.join(
    HERE, 'standard', 'full-steps-specification.rst')
STATIC_FOLDER = os.path.join(HERE, '_static')
SCHEMA_XSD_PATH = os.path.join(STATIC_FOLDER, 'xdl-schema.xsd')
XDL_FILE_STRUCTURE_RST_PATH = os.path.join(
    HERE, 'standard', 'xdl-file-structure.rst')

def get_title(text, underline):
    """Return RST header with given text and underline."""
    return f'{text}\n{underline * len(text)}\n\n'


def generate_steps_overview_rst() -> str:
    """Generate RST for steps overview page of XDL standard.

    Saves to RST file in docs source. Should be called before build in
    Sphinx Makefile.
    """
    rst = ''

    # Add title
    rst += get_title('Steps Overview', '=')

    # Add description
    rst += 'Here is an overview of all the steps implemented in this version of\
 the XDL standard.\n\n'

    # Add table
    table = '.. csv-table:: Implemented Steps\n'
    table += '   :header: ' + ','.join([f'"{item}"' for item in CATEGORIES])
    table += '\n\n'
    table_length = max([len(CATEGORIES[cat]) for cat in CATEGORIES])
    for i in range(table_length):
        table += '   '
        for category in CATEGORIES:
            category_steps = CATEGORIES[category]
            try:
                table += f'"{category_steps[i]}", '
            except IndexError:
                table += f'"",'
        table = table[:-1] + '\n'

    rst += table

    # Save RST
    with open(STEPS_OVERVIEW_RST_PATH, 'w') as fd:
        fd.write(rst)

    return rst

def generate_full_steps_specification_rst(steps) -> str:
    """Generate RST for full steps specification page of XDL standard.

    Saves to RST file in docs source. Should be called before build in
    Sphinx Makefile.
    """
    rst = ''

    # Add title
    rst += get_title('Full Steps Specification', '=')

    # Add steps
    for category_name, category_steps in CATEGORIES.items():

        # Add category
        rst += get_title(category_name, '*')
        for step_name in category_steps:
            rst += generate_step_specification_rst(steps[step_name])
            rst += '\n\n'

        rst += '\n\n'

    # Save RST
    with open(FULL_STEPS_SPECIFICATION_RST_PATH, 'w') as fd:
        fd.write(rst)

    return rst

def generate_step_specification_rst(step) -> str:
    """Generate step specification RST for step from ``parse_templates`` dict.
    """
    rst = ''
    rst += get_title(step['name'], '^')
    rst += f'{step["description"]}\n\n'
    rst += generate_props_table_rst(step['properties'])
    return rst

def generate_props_table_rst(props_table) -> str:
    """Generate props table for step specification. ``props_table`` must be from
    step from ``parse_templates``.
    """
    rst = ''
    rst += '.. csv-table::\n'
    rst += '   :quote: $\n'
    rst += '   :header: "Property", "Type", "Description"\n\n'
    for prop in props_table:
        prop_description = prop['description'].replace('"', '\\"')
        rst += f'   $``{prop["name"]}``$, $``{prop["type"]}``$, ${prop_description}$\n'
    return rst

def generate_xdl_file_structure_rst(steps) -> str:
    """Generate RST for xdl file structure page of XDL standard.

    Saves to RST file in docs source. Should be called before build in
    Sphinx Makefile.
    """
    rst = f'''
==================
XDL File Structure
==================

XDL files will follow XML syntax and consist of three mandatory sections: ``Hardware``, where virtual vessels that the reaction mixture can reside in are declared. ``Reagents``, where all reagents that are used in the procedure are declared, and ``Procedure``, where the synthetic actions involved in the procedure are linearly declared. An optional, but recommended Metadata section is also available for adding in extra information about the procedure. All sections are wrapped in an enclosing ``Synthesis`` tag.

XDL File Stub
*************

.. code-block:: xml

   <Synthesis>

    <Metadata>

    </Metadata>

    <Hardware>

    </Hardware>

    <Reagents>

    </Reagents>

    <Procedure>

    </Procedure>

   </Synthesis>

Metadata
********

The optional ``Metadata`` section should contain extra information about the procedure.

{generate_step_specification_rst(steps["Metadata"])}

Reagents
********

The ``Reagents`` section contains ``Reagent`` elements with the props below.

{generate_step_specification_rst(steps["Reagent"])}

Procedure
*********
All steps included in the :doc:`/standard/full-steps-specification` may be given within the
``Procedure`` block of a XDL file. Additionally, the ``Procedure`` block may be, but does not have to be, divided up into ``Prep``, ``Reaction``, ``Workup`` and ``Purification`` blocks, each of which can contain any of the steps in the specification.

Example XDL snippet using optional Procedure subsections
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: xml

    <Procedure>

        <Prep>
            <!-- Preparation steps here, reagent additions etc. -->
        </Prep>

        <Reaction>
            <!-- Reaction steps here, heating and stirring etc. -->
        </Reaction>

        <Workup>
            <!-- Workup steps here, separation, evaporation etc. -->
        </Workup>

        <Purification>
            <!-- Purification steps here, column, distillation etc. -->
        </Purification>

    </Procedure>

    '''

    with open(XDL_FILE_STRUCTURE_RST_PATH, 'w') as fd:
        fd.write(rst)

    return rst


def parse_templates():
    """Parse ``xdl.steps.templates`` to extract information of all steps, and
    ``Reagent`` and ``Metadata``.

    Returns:
        Dict[str, Dict[str, str]]: Returns dict of step names and step details
        {
            step_name: {
                name: step_name,
                description: step_description,
                properties: [
                    {
                        name: prop_name,
                        type: prop_type,
                        description: prop_description
                    },
                    ...
                ]
            },
            ...
        }
    """
    files = [f for f in os.listdir(STEPS_TEMPLATE_FOLDER) if f.endswith('.py')]

    # Ignore generate_docs  __init__ and abstract template
    files = [
        f for f in files
        if not f.startswith(('abstract', 'generate', '_'))
    ]

    steps = {}

    for f in files:
        with open(os.path.join(STEPS_TEMPLATE_FOLDER, f)) as fd:
            lines = fd.readlines()
        name = ''
        description = ''
        append_description = False
        read_props = False
        current_prop = {}
        properties = []
        read_default_props = False
        default_props = []
        for line in lines:

            # Starting new class, append and reset
            if line.startswith('class Abstract') and name:
                steps[name] = {
                    'name': name,
                    'description': description,
                    'properties': properties,
                }
                name = ''
                description = ''
                append_description = False
                read_props = False
                current_prop = {}
                properties = []
                default_props = []

            line = line.strip()

            # Get name
            if line.startswith('MANDATORY_NAME = '):
                name = re.search(r"MANDATORY_NAME = '([a-zA-Z]+)'", line)[1]

            # Description finished
            if line.startswith('Name: '):
                append_description = False

            # Append multiple lines to description.
            if append_description and line:
                description += ' ' + line

            # Get description
            if line.startswith('"""'):
                if not description:
                    description += line.split('"""')[1]
                    append_description = True
                elif read_props:
                    if current_prop:
                        properties.append(current_prop)
                    read_props = False

            # End of dictionary, not reading default props
            if line.startswith('}'):
                if default_props:
                    for prop in properties:
                        if prop['name'] in default_props:
                            prop['description'] =\
                                'Optional. ' + prop['description']
                    default_props = []
                read_default_props = False

            if read_default_props:
                default_props.append(re.match(r"'([a-z_]+)': ", line)[1])

            # Read properties
            if read_props:

                # Allow 'str', 'int', 'Union[List, str]' etc
                prop_type_pattern = r'[,\[\] a-zA-Z]'

                # Search for "var_name (var_type):" pattern
                new_prop = re.match(
                    r'([a-z_]+) \((' + prop_type_pattern + r'+)\):', line)
                if new_prop:
                    if current_prop:
                        properties.append(current_prop)

                    # Search for description coming after "var_name (var_type):"
                    description_pattern = r'[a-z_]+ \(' + prop_type_pattern\
                        + r'+\): (.*)$'
                    current_prop = {
                        'name': new_prop[1],
                        'type': new_prop[2],
                        'description': re.match(description_pattern, line)[1]
                    }

                # Append multiline description
                elif current_prop:
                    current_prop['description'] += ' ' + line

            if line.startswith('Mandatory props:'):
                read_props = True

            if line.startswith('MANDATORY_DEFAULT_PROPS ='):
                read_default_props = True

        steps[name] = {
            'name': name,
            'description': description,
            'properties': properties,
        }

    return steps

def generate_schema_xsd():
    """Write schema to XSD file for docs."""
    schema = generate_schema(PlaceholderPlatform().step_library)
    # Need to make static folder as empty folder is not committed to Git, so CI
    # fails.
    os.makedirs(STATIC_FOLDER, exist_ok=True)
    with open(SCHEMA_XSD_PATH, 'w') as fd:
        fd.write(schema)


if __name__ == '__main__':
    print('Generating XDL Standard RST files...')
    steps = parse_templates()
    generate_xdl_file_structure_rst(steps)
    generate_steps_overview_rst()
    generate_full_steps_specification_rst(steps)
    generate_schema_xsd()
