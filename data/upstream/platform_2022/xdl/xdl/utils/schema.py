"""There are definitely better and neater ways to generate this schema but it's
not really high priority.
"""

from ..reagents import Reagent
def add_metadata_namespace():
    schema = ""
    schema += "\n      <xs:element name=\"Metadata\" minOccurs=\"0\" maxOccurs=\"1\">"
    schema += "\n        <xs:complexType>"
    schema += "\n                <xs:simpleContent>"
    schema += "\n                  <xs:extension base=\"xs:string\">"
    schema += "\n                    <xs:attribute type=\"xs:string\" name=\"description\" use=\"optional\"/>"
    schema += "\n                    <xs:attribute type=\"xs:string\" name=\"product_inchi\" use=\"optional\"/>"
    schema += "\n                    <xs:attribute type=\"xs:string\" name=\"product_vessel\" use=\"optional\"/>"
    schema += "\n                    <xs:attribute type=\"xs:string\" name=\"product\" use=\"optional\"/>"
    schema += "\n                    <xs:attribute type=\"xs:string\" name=\"product_cas\" use=\"optional\"/>"
    schema += "\n                    <xs:attribute type=\"xs:string\" name=\"smarts\" use=\"optional\"/>"
    schema += "\n                    <xs:attribute type=\"xs:string\" name=\"publication\" use=\"optional\"/>"
    schema += "\n                    <xs:attribute type=\"xs:string\" name=\"reaction_class\" use=\"optional\"/>"
    schema += "\n                  </xs:extension>"
    schema += "\n                </xs:simpleContent>"
    schema += "\n              </xs:complexType>"
    schema += "\n      </xs:element>"
    return schema

def add_hardware_namespace():
    schema = ""
    schema += "\n      <xs:element name=\"Hardware\">"
    schema += "\n        <xs:complexType>"
    schema += "\n          <xs:sequence>"
    schema += "\n            <xs:element name=\"Component\" maxOccurs=\"unbounded\" minOccurs=\"0\">"
    schema += "\n              <xs:complexType>"
    schema += "\n                <xs:simpleContent>"
    schema += "\n                  <xs:extension base=\"xs:string\">"
    schema += "\n                    <xs:attribute type=\"xs:string\" name=\"id\" use=\"optional\"/>"
    schema += "\n                    <xs:attribute type=\"xs:string\" name=\"type\" use=\"optional\"/>"
    schema += "\n                    <xs:attribute type=\"xs:string\" name=\"chemical\" use=\"optional\"/>"
    schema += "\n                    <xs:attribute type=\"xs:string\" name=\"comment\" use=\"optional\"/>"
    schema += "\n                  </xs:extension>"
    schema += "\n                </xs:simpleContent>"
    schema += "\n              </xs:complexType>"
    schema += "\n            </xs:element>"
    schema += "\n          </xs:sequence>"
    schema += "\n        </xs:complexType>"
    schema += "\n      </xs:element>"
    return schema


def add_reagents_namespace():
    schema = ""
    schema += "\n      <xs:element name=\"Reagents\">"
    schema += "\n        <xs:complexType>"
    schema += "\n          <xs:sequence>"
    schema += "\n            <xs:element name=\"Reagent\" maxOccurs=\"unbounded\" minOccurs=\"0\">"
    schema += "\n              <xs:complexType>"
    schema += "\n                <xs:simpleContent>"
    schema += "\n                  <xs:extension base=\"xs:string\">"

    for prop_name, prop_type in Reagent.PROP_TYPES.items():
        schema += f"\n                    <xs:attribute type=\"xs:string\" name=\"{prop_name}\" use=\"optional\"/>"
    schema += "\n                    <xs:attribute type=\"xs:string\" name=\"comment\" use=\"optional\"/>"

    schema += "\n                  </xs:extension>"
    schema += "\n                </xs:simpleContent>"
    schema += "\n              </xs:complexType>"
    schema += "\n            </xs:element>"
    schema += "\n          </xs:sequence>"
    schema += "\n        </xs:complexType>"
    schema += "\n      </xs:element>"
    return schema


def add_steps(step_library):
    schema = ''
    for step_name, step in step_library.items():

        nested_steps = ['Async', 'Repeat', 'Loop']

        try:
            step.PROP_TYPES
        except AttributeError:
            continue

        if step_name not in nested_steps:
            schema += f"\n            <xs:element name=\"{step_name}\" maxOccurs=\"unbounded\" minOccurs=\"0\">"
            schema += "\n              <xs:complexType>"
            schema += "\n                <xs:simpleContent>"
            schema += "\n                  <xs:extension base=\"xs:string\">"

            add_repeat = True
            for prop_name, prop_type in step.PROP_TYPES.items():
                schema += f"\n                    <xs:attribute type=\"xs:string\" name=\"{prop_name}\" use=\"optional\"/>"
            schema += "\n                    <xs:attribute type=\"xs:string\" name=\"comment\" use=\"optional\"/>"

            schema += "\n                  </xs:extension>"
            schema += "\n                </xs:simpleContent>"
            schema += "\n              </xs:complexType>"
            schema += "\n            </xs:element>"

    for nested_step in nested_steps:
        if nested_step not in step_library:
            continue
        schema += f"\n            <xs:element name=\"{nested_step}\" maxOccurs=\"unbounded\" minOccurs=\"0\">"
        schema += "\n              <xs:complexType mixed=\"true\">"

        schema += "\n                  <xs:choice maxOccurs=\"unbounded\" minOccurs=\"0\">"
        for child_step_name, child_step in step_library.items():
            try:
                child_step.PROP_TYPES
            except AttributeError:
                continue

            if child_step_name not in nested_steps:
                schema += f"\n                  <xs:element name=\"{child_step_name}\" maxOccurs=\"unbounded\" minOccurs=\"0\" />"

        for nested_step2 in nested_steps:
            schema += f"\n            <xs:element name=\"{nested_step2}\" maxOccurs=\"unbounded\" minOccurs=\"0\" />"

        schema += "\n                  </xs:choice>"

        for prop_name, prop_type in step_library[nested_step].PROP_TYPES.items():
            schema += f"\n              <xs:attribute type=\"xs:string\" name=\"{prop_name}\" use=\"optional\"/>"

        schema += "\n              </xs:complexType>"
        schema += "\n            </xs:element>"

    return schema

def add_procedure_namespace(step_library):
    schema = ""
    schema += "\n      <xs:element name=\"Procedure\">"
    schema += "\n        <xs:complexType>"
    schema += "\n          <xs:choice maxOccurs=\"unbounded\" minOccurs=\"0\">"

    schema += add_steps(step_library)

    # Procedure sections
    for section in ['Prep', 'Reaction', 'Workup', 'Purification']:
        schema += f'<xs:element name=\"{section}\"><xs:complexType><xs:choice maxOccurs=\"unbounded\" minOccurs=\"0\">'
        schema += add_steps(step_library)
        schema += "\n          </xs:choice>"
        schema += "\n        </xs:complexType>"
        schema += "\n      </xs:element>"


    schema += "\n          </xs:choice>"
    schema += "\n        </xs:complexType>"
    schema += "\n      </xs:element>"
    return schema


def generate_schema(step_library):

    schema = "<xs:schema attributeFormDefault=\"unqualified\" elementForm"\
"Default=\"qualified\" xmlns:xs=\"http://www.w3.org/2001/XMLSchema\">"

    schema += "\n  <xs:element name=\"Synthesis\">"
    schema += "\n    <xs:complexType>"
    schema += "\n      <xs:sequence>"
    schema += add_metadata_namespace()
    schema += add_hardware_namespace()
    schema += add_reagents_namespace()
    schema += add_procedure_namespace(step_library)

    schema += "\n      </xs:sequence>"
    schema += "\n      <xs:attribute type=\"xs:string\" name=\"auto_clean\"/>"
    schema += "\n      <xs:attribute type=\"xs:string\" name=\"filter_dead_volume_method\"/>"
    schema += "\n      <xs:attribute type=\"xs:string\" name=\"organic_cleaning_solvent\"/>"
    schema += "\n    </xs:complexType>"
    schema += "\n  </xs:element>"
    schema += "\n</xs:schema>"

    return schema
