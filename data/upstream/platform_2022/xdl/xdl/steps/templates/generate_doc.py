import os
import re

UNIMPLEMENTED_STEPS = [
    'Distill',
    'FreezePumpThaw',
    'Microwave',
    'Electrolyse',
    'ReactInFlow',
    'RunColumn',
    'AddUntilColorChange',
    'HeatChillUntilColorChange',
    'AddToPH',
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

BACKGROUND_COLOR = '#fcf3ff'

template = '''
<html>
  <head>
  <link
    rel="stylesheet"
    href=
"https://stackpath.bootstrapcdn.com/bootstrap/4.4.1/css/bootstrap.min.css"
integrity="sha384-Vkoo8x4CGsO3+Hhxv8T/Q5PaXtkKtu6ug5TOeNV6gBiFeWPGFN9MuhOf23Q9Ifjh"
    crossorigin="anonymous">
  </head>
  <body class="p-4">
    <div class="container">
    <h1 class="mb-5">XDL Cross-Platform Standard 1.0 (WIP)</h1>
    <div class="p-5" style="background-color: {background_color};">
    <h2>XDL file structure</h2>
      XDL files will follow XML syntax and consist of two mandatory sections.
      <code>Reagents</code>, where all reagents that are used in the procedure are
      declared, and <code>Procedure</code>, where the synthetic actions involved in
      the procedure are linearly declared. An optional, but recommended
      <code>Metadata</code> section is also available for adding in extra information
      about the procedure. All sections are wrapped in an enclosing
      <code>Synthesis</code> tag.
      <br /><br />
      <h5>XDL file stub</h5>
      <code><pre><xmp><Synthesis>

    <Metadata>

    </Metadata>

    <Reagents>

    </Reagents>

    <Procedure>

    </Procedure>

</Synthesis></xmp></pre></code>
</div>
    <div style="background-color: {background_color}" class="my-5 p-5">
      <h2>Metadata</h2>
        This section should contain extra information about the procedure.
        {metadata}
    </div>

    <div style="background-color: {background_color}" class="my-5 p-5">
      <h2>Reagents</h2>
        The <code>Reagents</code> section contains <code>Reagent</code> elements with the props below.
        {reagent}
    </div>

    <div style="background-color: {background_color}" class="my-5 p-5">
      <h2>Procedure</h2>
      All steps included in this specification may be given within the Procedure
      block of a XDL file. Additionally, the Procedure block may be, but does
      not have to be, divided up into <code>Prep</code>, <code>Reaction</code>, <code>Workup</code> and <code>Purification</code> blocks,
      each of which can contain any of the steps in the specification.
      <br/><br/>
      <h5>Example procedure stub using optional procedure subsections.</h5>
      <code><pre><xmp>
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
      </xmp></pre></code>
      Below is a detailed breakdown of all the steps available for creating XDL procedures.
      </div>
    <div style="background-color: {background_color}" class="my-5 p-5">
      <p><h2>Steps overview</h2>{step_names}</p><br/>
      <p><h4>Steps to be implemented in future versions</h4>{unimplemented_steps}</p>
      </div>
      <h2> Full step specification</h2>
      {steps}
    </div>
  </body>
</html>
'''

step_template = '''
    <div class="row my-5">
    <div class="col">
    <h4>{name}</h4>
    <p><i>{description}</i></p>
    <table class="table table-bordered">
      <thead>
        <tr>
        <th>Property</td>
        <th>Type</td>
        <th>Description</td>
        </tr>
      </thead>
      <tbody>
        {property_rows}
      </tbody>
    </table>
    </div>
    </div>
'''

property_row_template = '''
        <tr>
          <td><code style="color: #4e4ece">{property}</code></td>
          <td><code style="color: #0b8962;">{property_type}</code></td>
          <td>{description}</td>
        </tr>
'''

HERE = os.path.abspath(os.path.dirname(__file__))

def parse_templates():
    files = [f for f in os.listdir(HERE) if f.endswith('.py')]

    # Ignore this file  __init__ and abstract template
    files = [
        f for f in files
        if not f.startswith(('abstract', 'generate', '_'))
    ]

    steps = {}

    for f in files:
        with open(os.path.join(HERE, f)) as fd:
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

def platform_compat_table():
    compat_matrix = [
        ['Add', True, True, True, False],
        ['Transfer', True, True, True, False],
        ['Stir', True, True, False, False],
        ['StartStir', True, True, False, False],
        ['StopStir', True, True, False, False],
        ['HeatChill', True, True, False, False],
        ['HeatChillToTemp', True, True, False, False],
        ['StartHeatChill', True, True, False, False],
        ['StopHeatChill', True, True, False, False],
        ['Purge', True, False, False, False],
        ['StartPurge', True, False, False, False],
        ['StopPurge', True, False, False, False],
        ['CleanVessel', True, False, False, False],
        ['Evaporate', True, False, False, False],
        ['Filter', True, False, False, False],
        ['WashSolid', True, False, False, False],
        ['Dry', True, False, False, False],
        ['Separate', True, False, False, False],
        ['Dissolve', True, False, False, False],
        ['EvacuateAndRefill', True, False, False, False],
        ['FilterThrough', True, False, False, False],
        ['Precipitate', True, False, False, False],
        ['Recrystallize', True, False, False, False],
        ['RunColumn', True, False, False, False],
        ['Separate', True, False, False, False]
    ]
    table = '''
<table class="table table-bordered">
  <thead>
    <tr>
      <th>Step</th>
      <th>Chemputer</th>
      <th>SMS</th>
      <th>N9</th>
      <th>ChemSpeed</th>
    </tr>
  </thead>
  <tbody>
    '''
    green = '#ccffcc'
    red = '#ffcccc'
    for row in compat_matrix:
        colors = []
        for flag in row[1:]:
            if flag:
                colors.append(green)
            else:
                colors.append(red)
        table += f'''
<tr>
  <td>{row[0]}</td>
  <td style="background-color: {colors[0]}"></td>
  <td style="background-color: {colors[1]}"></td>
  <td style="background-color: {colors[2]}"></td>
  <td style="background-color: {colors[3]}"></td>
</tr>
'''
    table += '</tbody></table>'
    return table

def get_step_html(step):
    """Get title and prop table for given step."""
    step_html = ''
    props_html = ''
    for prop in step['properties']:
        props_html += property_row_template.format(**{
            'property': prop['name'],
            'property_type': prop['type'],
            'description': prop['description']
        })
    props_html += property_row_template.format(**{
        'property': 'comment',
        'property_type': 'str',
        'description': 'Unrestricted comment field.'
    })
    step_html = step_template.format(**{
        'name': step['name'],
        'description': step['description'],
        'property_rows': props_html,
    })
    return step_html

def generate_doc(save=None):
    steps = parse_templates()
    steps_html = ''
    done = []
    for category, category_steps in CATEGORIES.items():
        steps_html += f'<div style="background-color: {BACKGROUND_COLOR}" class="my-5 p-5">'
        steps_html += f'<h2>{category}</h2>'
        for i, category_step in enumerate(category_steps):
            step = steps[category_step]
            done.append(category_step)
            step_html = get_step_html(step)
            steps_html += step_html
            if i < len(category_steps) - 1:
                steps_html += '<hr/>'
        steps_html += '</div>'
    html = template.format(**{
        'steps': steps_html,
        'step_names': get_steps_overview(),
        'unimplemented_steps': get_unimplemented_steps(),
        'platform_compat_table': platform_compat_table(),
        'reagent': get_step_html(steps['Reagent']),
        'metadata': get_step_html(steps['Metadata']),
        'background_color': BACKGROUND_COLOR,
    })

    # Check no steps missed
    for step in steps:
        if step not in done  and step not in ['Reagent', 'Metadata']:
            print(step, done)

    if save:
        with open(save, 'w') as fd:
            fd.write(html)
    return html

def get_steps_overview():
    html = '''
<table class="table table-bordered">
  <thead>
  <tr>
   '''
    for category in CATEGORIES:
        html += f'<th>{category}</th>'
    html += '</tr></thead><tbody>'
    max_len = max([len(steps) for _, steps in CATEGORIES.items()])
    for i in range(max_len):
        html += '<tr>'
        for category, steps in CATEGORIES.items():
            if i < len(steps):
                html += f'<td><code>{steps[i]}</code></td>'
            else:
                html += '<td />'
        html += '</tr>'
    html += '</tbody></table>'
    return html

def get_unimplemented_steps():
    html = ''
    for step in UNIMPLEMENTED_STEPS:
        html += f'<code>{step}</code><br/>'
    return html
