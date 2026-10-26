from ..constants import JSON_PROP_TYPE
from .base_blueprint import BaseProcedureBlueprint
from ..steps import placeholders
from ..reagents import Reagent

DEFAULT_VESSEL: str = 'reactor'
DEFAULT_SEPARATION_VESSEL: str = 'separator'
DEFAULT_EVAPORATION_VESSEL: str = 'rotavap'

class Chasm2(BaseProcedureBlueprint):

    PROP_TYPES = {
        'chasm2': JSON_PROP_TYPE,
    }

    def __init__(self, chasm2):
        super().__init__(locals())

    def build_reaction(self):
        steps, reagents = [], []
        current_temp = None
        for reaction_id, reaction_chasm2 in self.chasm2['reaction'].items():
            for i, item in enumerate(sorted(reaction_chasm2)):
                item_chasm2 = reaction_chasm2[item]
                if 'temp' in item_chasm2 and item_chasm2['temp'] is not None:
                    heating_step = placeholders.HeatChillToTemp(
                        temp=item_chasm2['temp'],
                        vessel=DEFAULT_VESSEL,
                        continue_heatchill=True,
                        active=True
                    )
                    if heating_step.temp != current_temp:
                        current_temp = item_chasm2['temp']
                        steps.append(heating_step)
                item_steps, item_reagents = converters[item](
                    item_chasm2, position=i)
                steps.extend(item_steps)
                reagents.extend(item_reagents)

        quench_steps, quench_reagents = chasm2_quench(self.chasm2['quench'])
        steps.extend(quench_steps)
        reagents.extend(quench_reagents)
        return steps, reagents

    def build_workup(self):
        steps, reagents = [], []
        i = 0
        for separation_id, separation_chasm2 in self.chasm2['workup'].items():
            item_steps, item_reagents = converters[separation_id](
                separation_chasm2, position=i, workup_steps=steps)
            steps.extend(item_steps)
            reagents.extend(item_reagents)
            i += 1

        evaporation_steps, _ =\
            chasm2_evaporation(self.chasm2['evaporation'])

        if evaporation_steps:
            for step in steps:
                if step.to_vessel == 'product':
                    step.to_vessel = DEFAULT_EVAPORATION_VESSEL

        steps.extend(evaporation_steps)

        return steps, reagents

    def build_purification(self):
        return chasm2_purification(self.chasm2['purification'])

def chasm2_quench(chasm2):
    steps, reagents = [], []
    if chasm2['reagent']:
        steps.append(
            placeholders.Add(
                vessel=DEFAULT_VESSEL,
                reagent=chasm2['reagent'],
                volume=chasm2['volume'],
                temp=chasm2['temp'],
            )
        )
        reagents.append(Reagent(chasm2['reagent']))
    return steps, reagents

def chasm2_reaction(chasm2, position):
    steps, reagents = [], []
    if chasm2['time'] is None and chasm2['temp'] is None:
        return steps, reagents
    steps.append(
        placeholders.HeatChill(
            vessel=DEFAULT_VESSEL,
            temp=chasm2['temp'],
            time=chasm2['time'],
        )
    )
    return steps, reagents

def chasm2_addition(chasm2, position):
    if not chasm2['reagent']:
        return [], []
    steps, reagents = [], [Reagent(chasm2['reagent'])]
    stir = True if position > 0 else False
    if chasm2['reagent_type'] == 'solid':
        step = placeholders.AddSolid(
            vessel=DEFAULT_VESSEL,
            reagent=chasm2['reagent'],
            mass=chasm2['amount'],
            stir=stir
        )
        if chasm2['speed']:
            step.time = f'{step.mass / float(chasm2["speed"])} min'
        steps = [step]
    else:
        steps = [
            placeholders.Add(
                vessel=DEFAULT_VESSEL,
                reagent=chasm2['reagent'],
                volume=chasm2['amount'],
                speed=chasm2['speed'],
                stir=stir
            )
        ]

    return steps, reagents

def chasm2_separation(chasm2, position, workup_steps):
    steps, reagents = [], []
    if not chasm2['solvent']:
        return steps, reagents

    if position == 0:
        from_vessel = DEFAULT_VESSEL
    else:
        from_vessel = workup_steps[-1].to_vessel

    waste_phase_to_vessel = None
    if chasm2['waste_phase_dest'] != 'waste':
        waste_phase_to_vessel = chasm2['waste_phase_dest']

    steps.append(
        placeholders.Separate(
            solvent=chasm2['solvent'],
            solvent_volume=chasm2['solvent_volume'],
            product_phase=chasm2['product_phase'],
            from_vessel=from_vessel,
            separation_vessel=DEFAULT_SEPARATION_VESSEL,
            to_vessel=chasm2['product_phase_dest'],
            waste_phase_to_vessel=waste_phase_to_vessel,
            purpose=chasm2['purpose'],
        )
    )
    reagents.append(Reagent(chasm2['solvent']))
    return steps, reagents

def chasm2_evaporation(chasm2):
    steps, reagents = [], []
    steps.append(
        placeholders.Evaporate(
            vessel=DEFAULT_EVAPORATION_VESSEL,
            pressure=chasm2['pressure'],
            temp=chasm2['temp'],
            time=chasm2['time'],
        )
    )
    if chasm2['dry']:
        steps.append(
            placeholders.Dry(
                vessel=DEFAULT_EVAPORATION_VESSEL,
            )
        )
    return steps, reagents

def chasm2_purification(chasm2):
    steps, reagents = [], []
    return steps, reagents


converters = {
    'addition1': chasm2_addition,
    'addition2': chasm2_addition,
    'addition3': chasm2_addition,
    'addition4': chasm2_addition,
    'addition5': chasm2_addition,
    'addition6': chasm2_addition,
    'addition7': chasm2_addition,
    'addition8': chasm2_addition,
    'addition9': chasm2_addition,
    'addition10': chasm2_addition,
    'reaction': chasm2_reaction,
    'separation1': chasm2_separation,
    'separation2': chasm2_separation,
    'separation3': chasm2_separation,
    'separation4': chasm2_separation,
    'separation5': chasm2_separation,
    'evaporation': chasm2_evaporation,
    'purification': chasm2_purification,
}
