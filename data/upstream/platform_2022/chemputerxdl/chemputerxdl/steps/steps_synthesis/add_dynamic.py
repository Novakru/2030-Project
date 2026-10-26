"""
Dynamic XDL step for exothermic additions using the RTD sensor
to keep the internal reaction temperature below a specified threshold.
"""
import time

from typing import Optional, List
from networkx import MultiDiGraph

from xdl.steps.base_steps import AbstractDynamicStep
from xdl.utils.misc import SanityCheck
from xdl.constants import VESSEL_PROP_TYPE, REAGENT_PROP_TYPE
from xdl.steps.base_steps import Step

from ..steps_base import ReadRTDSensor
from ..steps_utility import (
    Transfer, PrimePumpForAdd, Wait,
    StopStir, StartStir, FlushTubing
)
from ...constants import PORT_PROP_TYPE, DEFAULT_AFTER_ADD_WAIT_TIME

from ...utils.execution import (
    get_aspiration_pump,
    get_pump_max_volume,
    get_waste_vessel,
    get_reagent_vessel,
    get_cartridge,
    get_rtd_sensor
)


class AddDynamic(AbstractDynamicStep):
    """Add given reagent until desired temp is reached.

    Args:
        vessel (str): Vessel to add to.
        reagent (str): Reagent to add.
        volume (float): Volume to add.
        max_temp (float): Maximum temp that should not be exceeded.
        safety_margin (float, optional): Safety margin deducted from max_temp
        aliquot_volume (float, optional): Volume of reagent to add
            between each temp reading. Defaults to '1 mL'.
        wait_after_addition (float, optional): Time to stir after
            each addition of reagent. Defaults to '10 seconds'.
        wait_after_reading (float, optional): sleep time between
            sensor readings.
    """

    READ_TEMP = 0  # Code for temp reading option during continue loop.
    ADD_REAGENT = 1  # Code for reagent addition option during continue loop.

    DEFAULT_PROPS = {
        'safety_margin': 10.0,  # degree celsius
        'aliquot_volume': '1 mL',
        'wait_after_addition': DEFAULT_AFTER_ADD_WAIT_TIME,
        'wait_after_reading': 1.0,  # second,
        'stir': True,
        'stir_speed': '250 RPM',
        'purpose': None,
        'port': None,
        'through': None,
        'prime_n_times': 1,
        'priming_volume': '3 mL',
        'move_speed': 40,  # mL / min
        'aspiration_speed': 10,  # mL / min
        'dispense_speed': 40,  # mL / min
    }

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'reagent': REAGENT_PROP_TYPE,
        'volume': float,
        'max_temp': float,
        'safety_margin': float,
        'aliquot_volume': float,
        'wait_after_addition': float,
        'wait_after_reading': float,
        'sensor': str,
        'aspiration_pump': str,
        'aspiration_pump_max_volume': float,
        'reagent_vessel': str,
        'waste_vessel': str,
        'stir': bool,
        'stir_speed': float,
        'purpose': str,
        'port': PORT_PROP_TYPE,
        'through': str,
        'through_cartridge': str,
        'prime_n_times': int,
        'priming_volume': float,
        'move_speed': float,  # mL / min
        'aspiration_speed': float,  # mL / min
        'dispense_speed': float,  # mL / min
    }

    INTERNAL_PROPS = [
        'sensor',
        'aspiration_pump',
        'aspiration_pump_max_volume',
        'reagent_vessel',
        'waste_vessel',
        'through_cartridge',
    ]

    def __init__(
            self,
            # Mandatory properties
            vessel: str,
            reagent: str,
            volume: float,
            max_temp: float,
            # Optional properties
            stir: Optional[bool] = 'default',
            safety_margin: Optional[float] = 'default',
            aliquot_volume: Optional[float] = 'default',
            wait_after_addition: Optional[float] = 'default',
            wait_after_reading: Optional[float] = 'default',
            speed: Optional[float] = 'default',
            port: Optional[str] = 'default',
            through: Optional[str] = 'default',
            purpose: str = None,
            move_speed: Optional[float] = 'default',
            aspiration_speed: Optional[float] = 'default',
            dispense_speed: Optional[float] = 'default',
            stir_speed: Optional[float] = 'default',
            prime_n_times: Optional[int] = 'default',
            priming_volume: Optional[float] = 'default',

            # Internal properties
            sensor: Optional[str] = None,
            aspiration_pump: Optional[str] = None,
            aspiration_pump_max_volume: Optional[float] = None,
            through_cartridge: Optional[str] = None,
            reagent_vessel: Optional[str] = None,
            vessel_type: Optional[str] = None,
            waste_vessel: Optional[str] = None,
            **kwargs
    ):
        super().__init__(locals())
        self.continue_options = {
            AddDynamic.READ_TEMP: self.continue_read_temp,
            AddDynamic.ADD_REAGENT: self.continue_add_reagent,
        }
        self.aliquot_volume = round(self.aliquot_volume, 3)
        self.volume_left = self.volume
        self.volume_in_pump = 0.0
        self.continue_option = AddDynamic.ADD_REAGENT
        self.current_temp = None
        self.finished = False

    def on_prepare_for_execution(self, graph):
        """Add any extra properties needed before execution using graph."""

        # get temp sensor
        self.sensor = get_rtd_sensor(
            graph=graph,
            vessel=self.vessel

        )

        # Get the aspiration pump and its maximum volume
        self.aspiration_pump = get_aspiration_pump(
            graph=graph,
            src_vessel=self.vessel,
            # src_port=self.from_port
        )
        self.aspiration_pump_max_volume = get_pump_max_volume(
            graph,
            self.aspiration_pump
        )

        # Obtain the waste vessel if not defined
        if not self.waste_vessel:
            self.waste_vessel = get_waste_vessel(
                graph, self.vessel
            )

        # Obtain the through cartridge if through nodes have been defined
        if not self.through_cartridge and self.through:
            self.through_cartridge = get_cartridge(graph, self.through)

        # Obtain the reagent vessel if not defined
        if not self.reagent_vessel:
            self.reagent_vessel = get_reagent_vessel(graph, self.reagent)

    def sanity_checks(self, graph: MultiDiGraph) -> List[SanityCheck]:
        """Gets a list of Sanity checks to perform for the step

        Args:
            graph (MultiDiGraph): Chemputer graph to check

        Returns:
            List[SanityCheck]: List of checks to perform
        """
        return [
            SanityCheck(
                condition=self.vessel,
                error_msg=f'{self.vessel} cannot be None.'
            ),
            SanityCheck(
                condition=self.volume is not None,
                error_msg='Volume must be given.'
            ),
            SanityCheck(
                condition=(self.aliquot_volume < self.volume),
                error_msg='Aliquot volume must be smaller than addition volume.'
            ),
            SanityCheck(
                condition=(
                    self.aliquot_volume <= self.aspiration_pump_max_volume),
                error_msg='Aliquot volume must be <= max. pump volume.'
            ),
            SanityCheck(
                condition=not self.through or self.through_cartridge,
                error_msg=f'Trying to add through "{self.through}" but cannot\
 find cartridge containing {self.through}.'
            ),

        ]

    def on_start(self):
        """Prime Pump."""
        self.logger.debug('Priming reagent for dynamic addition.')
        start_steps = [
            PrimePumpForAdd(
                reagent=self.reagent,
                volume=self.priming_volume,
                waste_vessel=self.waste_vessel,
                prime_n_times=self.prime_n_times,
                move_speed=self.move_speed,
                aspiration_speed=self.aspiration_speed,
            ),
        ]

        if self.stir:
            start_steps.append(
                StartStir(
                    vessel=self.vessel,
                    stir_speed=self.stir_speed,
                )
            )

        return start_steps

    def on_continue(self):
        """Continue adding reagent until desired temp is reached."""
        if self.finished:
            self.logger.debug('Dynamic Addition completed.')
            return []
        else:
            return self.continue_options[self.continue_option]()

    def continue_read_temp(self):
        """Read temp during continue loop."""
        self.logger.debug('Reading RTD sensor.')
        return [
            ReadRTDSensor(
                rtd_sensor=self.sensor,
                on_reading=self.on_temp_reading,
            )
        ]

    def on_temp_reading(self, reading):
        """
        Callback function for temp reading in continue loop.
        Next action is either reagent addition or waiting if temp is too high.
        """
        self.current_temp = reading

        self.logger.info('Current temperature: %s °C', reading)

        if self.current_temp < self.max_temp - self.safety_margin:
            self.logger.info('Continue with reagent addition.')
            self.continue_option = AddDynamic.ADD_REAGENT
        else:
            self.logger.info('Temperature above threshold. Waiting.')
            time.sleep(self.wait_after_reading)
            self.continue_option = AddDynamic.READ_TEMP

    def continue_add_reagent(self):
        """
        Add reagent during continue loop.

        If the syringe is empty, fill the syringe with appropriate volume.
        This is either a multiple the aliquot volume or the remainder left.

        After syringe has been filled, get addition steps.
        For the final addition, adjust the volume and set finished flag.
        """

        # Next iteration of continue loop will be temp reading.
        self.continue_option = AddDynamic.READ_TEMP

        steps = []

        if self.volume_in_pump == 0:
            self.logger.debug("Filling syringe.")
            # fill syringe
            if self.volume_left > self.aspiration_pump_max_volume:
                self.logger.debug("Fill syringe with n aliquots that fit.")
                # fill with n aliquots that fit in pump.
                n_aliquots = (self.aspiration_pump_max_volume
                              // self.aliquot_volume)

                steps.extend(self._get_fill_syringe_steps(
                    volume=n_aliquots * self.aliquot_volume))
            else:
                # fill syringe with small remaining volume
                self.logger.debug("Fill syringe with small remaining volume.")
                steps.extend(self._get_fill_syringe_steps(
                    volume=self.volume_left))

            # update volume left, abs & round needed to not violate prop limit
            # else you might get -0.0 or 4.78E-16
            self.volume_left = abs(
                round(self.volume_left - self.volume_in_pump, 3))

            self.logger.debug(
                "Volume left (excl. volume in syringe): %s mL",
                self.volume_left
            )

        # handle special case of the final addition
        if self.volume_in_pump < self.aliquot_volume:
            self.logger.debug("Final addition.")
            self.aliquot_volume = self.volume_in_pump
            self.finished = True

        steps.extend(self._get_addition_steps())

        return steps

    def _get_fill_syringe_steps(self, volume):
        "Fills syringe with the specified volume."
        self.volume_in_pump = round(volume, 3)
        self.logger.debug("Volume in syringe: %s mL.", self.volume_in_pump)
        return [
            Transfer(
                from_vessel=self.reagent_vessel,
                to_vessel=self.aspiration_pump,
                volume=self.volume_in_pump,
                through=self.through_cartridge,
                move_speed=self.move_speed,
                aspiration_speed=self.aspiration_speed,
                dispense_speed=self.dispense_speed
            )
        ]

    def _get_addition_steps(self):
        """
        Transfers from aspiration pump to vessel & waits.
        Flushes tubing for final addition.
        """
        self.volume_in_pump -= self.aliquot_volume

        self.logger.debug(
            "Adding %s mL to vessel.", self.aliquot_volume)
        self.logger.debug(
            "Remaining volume in syringe: %s mL", self.volume_in_pump)

        return [
            Transfer(
                from_vessel=self.aspiration_pump,
                to_vessel=self.vessel,
                volume=self.aliquot_volume,
                through=self.through_cartridge,
                move_speed=self.move_speed,
                aspiration_speed=self.aspiration_speed,
                dispense_speed=self.dispense_speed
            ),
            Wait(
                time=self.wait_after_addition,
            ),
        ]

    def get_simulation_steps(self) -> List[Step]:
        """ In simulation no sensor readings. Just transfer + stirring."""
        volume = self.aspiration_pump_max_volume
        return self._get_fill_syringe_steps(volume) + self._get_addition_steps()

    def scale(self, scale: float):
        """Scale volumes by a given factor

        Args:
            scale (float): Scaling factor
        """

        if self.volume is not None:
            self.volume *= scale

    def on_finish(self):
        """Stop stir and flush tubing"""
        self.logger.debug("Flushing tubing.")
        finish_steps = [
            FlushTubing(
                to_vessel=self.vessel
            )
        ]

        if self.stir:
            finish_steps.append(StopStir(vessel=self.vessel))

        return finish_steps
