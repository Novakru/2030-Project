================
Making New Steps
================

All steps should inherit :code:`xdl.steps.AbstractStep`.

Attributes to implement:

- :code:`PROP_TYPES`: The types of all :code:`__init__` arguments except :code:`self` and
  :code:`**kwargs`.
- :code:`DEFAULT_PROPS`: Default values for any keyword arguments with the
  default set as :code:`'default'`.
- :code:`INTERNAL_PROPS`: Internal properties that are programmatically extracted from the graph
  in :code:`on_prepare_for_execution`. These properties are never written when
  outputting XDL files.
- :code:`PROP_LIMITS`: Limits on what values are acceptable for given properties.
  If no prop limit is supplied for a prop, then a default limit is used based
  on the prop type.
- :code:`ALWAYS_WRITE`: Usually properties are not written to file if there
  value is the same as the value defined in :code:`DEFAULT_PROPS`. If the
  property is included here, it will always be written even if it is the
  default.

Methods to implement:

- :code:`__init__`: Take properties as arguments and call :code:`super().__init__(locals())`
- :code:`get_steps`: Return a list of steps to be executed when the step is executed.
- :code:`on_prepare_for_execution`: Make any graph specific changes to the steps
  required.
- :code:`sanity_checks`: This returns a list of :code:`xdl.utils.misc.SanityCheck`
  objects which are checked at the end of :code:`prepare_for_execution`. If the
  conditions are not met then an errors are raised with the associated messages during the
  :code:`prepare_for_execution` sequence. These should raise informative errors if
  any of the final set of properties don't make sense.

Example
-------

.. code-block:: python

    from xdl.steps import AbstractStep, Add, Stir, Transfer
    from xdl.utils.prop_limits import VOLUME_PROP_LIMIT, TIME_PROP_LIMIT
    from xdl.utils.misc import SanityCheck
    from networkx import MultiDiGraph

    # Class must inherit AbstractStep
    class QuantitativeTransfer(AbstractStep):

        # Define any properties to be given if 'default' given as value.
        DEFAULT_PROPS = {
            'solvent_volume': '50 mL',
            'stir_time': '1 min'
        }

        # Types of all properties
        PROP_TYPES = {
            'from_vessel': str,
            'to_vessel': str,
            'solvent': str,
            'solvent_volume': float,
            'stir_time': float,
        }

        PROP_LIMITS = {
            'solvent_volume': VOLUME_PROP_LIMIT,
            'stir_time': TIME_PROP_LIMIT,
        }

        INTERNAL_PROPS = []

        # __init__ method should contain **kwargs.
        def __init__(
            self,
            from_vessel: str,
            to_vessel: str,
            solvent: str,
            solvent_volume: float = 'default',
            stir_time: float = 'default',
            **kwargs
        ):
            # Super call converts all args to standard units / types and creates
            # self.properties dict.
            # After this all properties supplied to __init__ will be available as
            # member variables, i.e. self.from_vessel, self.to_vessel etc.
            super().__init__(locals())

        def on_prepare_for_execution(self, graph: MultiDiGraph):
            """Fill in any properties that can only be taken from the graph."""
            # In this case nothing needs to be done.
            return

        def sanity_checks(self, graph: MultiDiGraph):
            return [
                SanityCheck(
                    condition=self.from_vessel,
                    error_msg='No from_vessel given'
                ),
                SanityCheck(
                    condition=self.to_vessel,
                    error_msg='No to_vessel given'
                ),
                SanityCheck(
                    condition=self.solvent,
                    error_msg='No solvent given',
                ),
                SanityCheck(
                    condition=self.solvent_volume > 0,
                    error_msg='Solvent volume must be > 0',
                ),
            ]

        def get_steps(self):
            """Return steps to be executed."""
            return [
                # Transfer liquid to target flask.
                Transfer(
                    to_vessel=self.to_vessel,
                    to_vessel=self.to_vessel,
                    volume='all',
                ),

                # Add solvent to source flask.
                Add(
                    vessel=self.to_vessel,
                    reagent=self.solvent,
                    volume=self.solvent_volume,
                ),

                # Stir solvent in source flask.
                Stir(
                    vessel=self.vessel,
                    time=self.stir_time,
                ),

                # Transfer solvent / washings to target flask.
                Transfer(
                    to_vessel=self.to_vessel,
                    to_vessel=self.to_vessel,
                    volume=self.solvent_volume,
                ),
            ]
