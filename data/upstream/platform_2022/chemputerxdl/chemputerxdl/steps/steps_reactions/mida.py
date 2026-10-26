"""
.. module:: steps_reactions.mida
    :platforms: Unix, Windows
    :synopsis: XDL Step to represent a MIDA Boronate coupling reaction.
                Will perform a whole reaction in single Step.

"""

from typing import Optional, List

from ..steps_synthesis import (
    Add,
    Dissolve,
    Evaporate
)
from ..steps_utility import (
    Evacuate,
    HeatChillToTemp,
    Transfer,
    Stir,
    StartStir
)

from xdl.steps import Step
from xdl.steps.special_steps import Repeat

from xdl.steps.base_steps import AbstractStep
from ..base_step import ChemputerStep

from ...utils.execution import (
    get_nearest_node, get_inert_gas_vessel, get_reagent_vessel)
from ...constants import CHEMPUTER_WASTE
from xdl.utils.misc import SanityCheck
from networkx import MultiDiGraph

# Class must inherit AbstractStep, ChemputerStep
class MIDACoupling(ChemputerStep, AbstractStep):
    """Step representing a MIDA Boronate Coupling Reaction.

    Args:
        reactor (str): Main reactor flask.

        holding_flask (str): Flask to use for holding material at certain
                            stages.

        rotavap (str): Rotavap to use.

        boronic_acid (Optional[str]): Boronic acid to use. Defaults to None.

        boronic_acid_mass (Optional[float]): Mass of Boronic Acid to use.
                                            Defaults to None.

        base (Optional[str]): Base to use. Defaults to None.

        base_mass (Optional[float]): Mass of base to use. Defaults to None.

        halide (Optional[str]): Halide source to use. Defaults to None.

        halide_mass (Optional[float]): Halide mass to use. Defaults to None.

        catalyst (Optional[str]): Which catalyst to use. Defaults to None.

        catalyst_mass (Optional[float]): Mass of catalyst to use.
                                        Defaults to None.

        solvent (Optional[str]): Main solvent to use. Defaults to 'default'.

        solvent_volume (Optional[float]): Volume of solvent to use.
                                            Defaults to 'default'.

        rxn_temp (Optional[float]): Temperature to set the reaction to.
                                    Defaults to 'default'.

        rxn_time (Optional[float]): How long to run the reaction for.
                                    Defaults to 'default'.

        addition_speed (Optional[float]): Speed of addition of material.
                                        Defaults to 'default'.

        evacuations (Optional[int]): Number of evacuations to perform.
                                    Defaults to 'default'.

        after_inert_gas_wait_time (Optional[float]): How long to wait after
                            addition of inert gas. Defaults to 'default'.

        after_vacuum_wait_time (Optional[float]): How long to wait after
                            vacuum. Defaults to 'default'.

        boronic_acid_solution_volume (Optional[float]): Volume of boronic acid
                            to add. Defaults to 'default'.

        rinses (Optional[int]): Number of rinses to perform.
                                Defaults to 'default.

        solvent_vessel (Optional[str]): Name fo the solvent vessel.
                                Defaults to None.

        waste_vessel (Optional[str]): Name of the waste vessel to use.
                                Defaults to None.

        inert_gas (Optional[str]): Inert gas to use. Defaults to None.
    """

    DEFAULT_PROPS = {
        'solvent': 'THF',
        'solvent_volume': '28 mL',
        'rxn_temp': '55°C',
        'rxn_time': '12 hrs',
        'addition_speed': '4 hrs',
        'evacuations': 3,
        'after_inert_gas_wait_time': '1 minute',
        'after_vacuum_wait_time': '1 minute',
        'boronic_acid_solution_volume': '20 mL',
        'rinses': 2,
    }

    PROP_TYPES = {
        'reactor': str,
        'holding_flask': str,
        'rotavap': str,
        'boronic_acid': str,
        'boronic_acid_mass': float,
        'base': str,
        'base_mass': float,
        'halide': str,
        'halide_mass': float,
        'catalyst': str,
        'catalyst_mass': float,
        'solvent': str,
        'solvent_volume': float,
        'rxn_temp': float,
        'rxn_time': float,
        'addition_speed': float,
        'evacuations': int,
        'after_inert_gas_wait_time': float,
        'after_vacuum_wait_time': float,
        'boronic_acid_solution_volume': float,
        'rinses': int,
        'solvent_vessel': str,
        'inert_gas': str,
        'waste_vessel': str,
    }

    INTERNAL_PROPS = [
        'waste_vessel',
        'solvent_vessel',
        'inert_gas',
    ]

    def __init__(
        self,

        # Platform vessels
        reactor: Optional[str],
        holding_flask: Optional[str],
        rotavap: Optional[str],  # obviously platform specific

        # Reagent related properties
        boronic_acid: Optional[str] = None,
        boronic_acid_mass: Optional[float] = None,  # should really be equiv.
        base: Optional[str] = None,
        base_mass: Optional[float] = None,
        halide: Optional[str] = None,
        halide_mass: Optional[float] = None,  # should have 'scale' property
        catalyst: Optional[str] = None,
        catalyst_mass: Optional[float] = None,
        solvent: Optional[str] = 'default',

        # Process related properties
        solvent_volume: Optional[float] = 'default',  # should be concentration
        rxn_temp: Optional[float] = 'default',
        rxn_time: Optional[float] = 'default',
        addition_speed: Optional[float] = 'default',
        evacuations: Optional[int] = 'default',
        after_inert_gas_wait_time: Optional[float] = 'default',
        after_vacuum_wait_time: Optional[float] = 'default',
        boronic_acid_solution_volume: Optional[float] = 'default',
        rinses: Optional[int] = 'default',

        # Internal props
        solvent_vessel: Optional[str] = None,
        waste_vessel: Optional[str] = None,
        inert_gas: Optional[str] = None,
        **kwargs
    ):
        super().__init__(locals())

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        """Prepare the current step for execution.
        Sets all relevant information before being executed.

        Args:
            graph (MultiDiGraph): Chemputer graph
        """

        self.waste_vessel = get_nearest_node(
            graph, self.reactor, CHEMPUTER_WASTE
        )

        self.inert_gas = get_inert_gas_vessel(graph, self.reactor)

        self.solvent_vessel = get_reagent_vessel(graph, self.solvent)

    def sanity_checks(self, graph: MultiDiGraph) -> List[SanityCheck]:
        """Create list of sanity checks to ensure correct behaviour

        Args:
            graph (MultiDiGraph): Chemputer graph

        Returns:
            List[SanityCheck]: List of checks to perform.
        """

        return [
            SanityCheck(
                condition=self.solvent_volume > 0,
                error_msg='Solvent volume must be > 0.'
            ),

            SanityCheck(
                condition=self.boronic_acid_mass > 0,
                error_msg='Boronic acid mass must be > 0 g.'
            ),

            SanityCheck(
                condition=self.base_mass > 0,
                error_msg='Base mass must be > 0 g.'
            ),
        ]

    def get_steps(self) -> List[Step]:
        """Get the series of steps/base steps to perform.

        Returns:
            List[Step]: Steps to be executed.
        """

        return [
            # Deoxygenate reactor
            Evacuate(
                vessel=self.reactor,
                evacuations=self.evacuations,
                after_inert_gas_wait_time=self.after_inert_gas_wait_time,
                after_vacuum_wait_time=self.after_vacuum_wait_time,
            ),

            # Deoxygenate holding flask
            Evacuate(
                vessel=self.holding_flask,
                evacuations=self.evacuations,
                after_inert_gas_wait_time=self.after_inert_gas_wait_time,
                after_vacuum_wait_time=self.after_vacuum_wait_time,
            ),

            # Deoxygenate backbone
            Transfer(
                from_vessel=self.inert_gas,
                to_vessel=self.waste_vessel,  # obviously not transferable
                volume='125 mL',
            ),

            # Add boronic acid to holding flask
            Add(
                vessel=self.holding_flask,
                reagent=self.boronic_acid,
                mass=self.boronic_acid_mass,  # obviously not general of ICC
                stir=False,
            ),

            # Add base to reactor
            Add(
                vessel=self.reactor,
                reagent=self.base,
                mass=self.base_mass,
                stir=False,
            ),

            # Add catalyst to reactor
            Add(
                vessel=self.reactor,
                reagent=self.catalyst,
                mass=self.catalyst_mass,
                stir=False,
            ),

            # Add halide to reactor
            Add(
                vessel=self.reactor,
                reagent=self.halide,
                mass=self.halide_mass,
                stir=False,
            ),

            # Dissolve boronic acid
            Dissolve(
                vessel=self.holding_flask,
                solvent=self.solvent,
                volume=self.boronic_acid_solution_volume,
            ),

            # Deoxygenate holding flask
            Evacuate(
                vessel=self.holding_flask,
                evacuations=self.evacuations,
                after_inert_gas_wait_time=self.after_inert_gas_wait_time,
                after_vacuum_wait_time=self.after_vacuum_wait_time,
            ),

            # Deoxygenate reactor
            Evacuate(
                vessel=self.reactor,
                evacuations=self.evacuations,
                after_inert_gas_wait_time=self.after_inert_gas_wait_time,
                after_vacuum_wait_time=self.after_vacuum_wait_time,
            ),

            # Add solvent to reactor
            Add(
                reagent=self.solvent,
                vessel=self.reactor,
                volume=self.solvent_volume,
                stir=True,
            ),

            # Deoxygenate reactor
            Evacuate(
                vessel=self.reactor,
                evacuations=self.evacuations,
                after_inert_gas_wait_time=self.after_inert_gas_wait_time,
                after_vacuum_wait_time=self.after_vacuum_wait_time,
            ),

            # Heat reactor to temperature
            HeatChillToTemp(
                vessel=self.reactor,
                temp=self.rxn_temp,
            ),

            # Slow addition of boronic acid to reactor
            Transfer(
                from_vessel=self.holding_flask,
                to_vessel=self.reactor,
                volume='all',
                time=self.addition_speed,
            ),

            # Rinse holding flask
            Repeat(
                repeats=self.rinses,
                children=[
                    Add(
                        reagent=self.solvent,
                        vessel=self.holding_flask,
                        volume='5 mL',
                        stir=True,
                    ),
                    Transfer(
                        from_vessel=self.holding_flask,
                        to_vessel=self.reactor,
                        volume='5 mL'
                    )
                ]
            ),

            # stir reaction mixture for length of reaction
            Stir(
                vessel=self.reactor,
                time=self.rxn_time,
            ),

            # reduce speed for in-line filtration
            StartStir(
                vessel=self.reactor,
                stir_speed=50,
            ),

            # in-line filtration
            # possibly have to add through_node='filtration_cartridge"
            Transfer(
                from_vessel=self.reactor,
                to_vessel=self.rotavap,
                volume='100 mL',  # higher than actual volume but needed
                aspiration_speed=5,
            ),

            # Rinse reactor and make sure reactor is empty
            # possibly have to add through_node='filtration_cartridge"
            Repeat(
                repeats=self.rinses,
                children=[
                    Add(
                        reagent=self.solvent,
                        vessel=self.reactor,
                        volume='10 mL',
                        stir=True,
                    ),
                    Transfer(
                        from_vessel=self.reactor,
                        to_vessel=self.rotavap,
                        volume='100 mL',
                        aspiration_speed=5,
                    ),
                ],
            ),

            # Evaporate solvent
            Evaporate(
                mode='auto',
                time='30 mins',
                pressure='249 mbar',
                temp='50°C',
                rotavap_name=self.rotavap,
            ),
        ]
