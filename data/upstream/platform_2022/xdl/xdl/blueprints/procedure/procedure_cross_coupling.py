from ...utils.prop_limits import (
    MASS_PROP_LIMIT,
    TIME_PROP_LIMIT,
    TEMP_PROP_LIMIT,
)

from ..base_blueprint import BaseProcedureBlueprint
from ..prep import CrossCouplingPrep
from ..reaction import CrossCouplingReaction
from ..workup import CrossCouplingWorkup


class CrossCouplingBlueprint(BaseProcedureBlueprint):
    """Generic cross coupling reaction blueprint. The wide variety of named
    cross coupling reactions is generally accessed by using different substrates
    """

    reaction_vessel = 'reactor'
    evaporation_vessel = 'rotavap'

    base_equivs = 1.5
    halide_equivs = 1.5

    PROP_TYPES = {
        'catalyst': str,
        'substrate': str,
        'substrate_mol': float,
        'substrate_molar_mass': float,
        'halide': str,
        'halide_molar_mass': float,
        'base': str,
        'base_molar_mass': float,

        'solvent': str,
        'quencher': str,
        'quencher_mass': float,
        'catalyst_mass': float,

        'temp': float,
        'time': float,
    }

    DEFAULT_PROPS = {
        'solvent': None,
        'catalyst_mass': '0.05 g',
        'quencher_mass': '20 g',
        'quencher': 'solid sodium carbonate',

        'temp': 100,
        'time': '1 hr',
    }

    PROP_LIMITS = {
        'catalyst_mass': MASS_PROP_LIMIT,
        'temp': TEMP_PROP_LIMIT,
        'time': TIME_PROP_LIMIT,
    }

    def __init__(
        self,
        catalyst: str,
        substrate: str,
        substrate_mol: float,
        substrate_molar_mass: float,
        base: str,
        base_molar_mass: float,
        halide: str,
        halide_molar_mass: float,

        solvent: str = 'default',
        quencher: str = 'default',
        quencher_mass: float = 'default',
        catalyst_mass: float = 'default',

        temp: float = 'default',
        time: float = 'default',
    ):
        super().__init__(locals())

    def build_prep(self):
        """Get prep steps and reagents."""
        return CrossCouplingPrep(
            catalyst=self.catalyst,
            substrate=self.substrate,
            substrate_mol=self.substrate_mol,
            substrate_molar_mass=self.substrate_molar_mass,
            base=self.base,
            base_molar_mass=self.base_molar_mass,
            halide=self.halide,
            halide_molar_mass=self.halide_molar_mass,
            solvent=self.solvent,
            catalyst_mass=self.catalyst_mass,
        ).build()

    def build_reaction(self):
        """Get reaction steps and reagents."""
        return CrossCouplingReaction(
            reaction_vessel=self.reaction_vessel,
            temp=self.temp,
            time=self.time
        ).build()

    def build_workup(self):
        """Quench reaction, filter off quenching reagent and evaporate solvent.
        """
        return CrossCouplingWorkup(
            quencher=self.quencher,
            quencher_mass=self.quencher_mass,
            reaction_vessel=self.reaction_vessel,
            evaporation_vessel=self.evaporation_vessel
        ).build()
