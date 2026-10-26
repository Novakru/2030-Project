====================
Making Dynamic Steps
====================

Dynamic steps are steps that execute differently based on live feedback from
devices. Examples of potential dynamic steps would be :code:`AddUntilColorChange`,
:code:`AddToPH`, :code:`HeatUntilComplete` etc.

Dynamic steps can be created by making subclasses of :code:`xdl.step_utils.AbstractDynamicStep`.
As an example, we will make a simple :code:`AddToPH` step that adds a given reagent
until a certain pH is reached.

1. Create dynamic step stub
***************************

Inherit :code:`AbstractDynamicStep` and implement all abstract methods.

.. code-block:: python

    from xdl.step_utils import AbstractDynamicStep

    class AddToPH(AbstractDynamicStep):
        """Add given reagent until desired pH is reached.

        Args:
            vessel (str): Vessel to add to.
            reagent (str): Reagent to add to reach target pH.
            pH (float): Target pH.
            add_increment_volume (float, optional): Volume of reagent to add
                between each pH reading. Defaults to '1 mL'.
            stir_between_additions_time (float, optional): Time to stir after
                each addition of reagent. Defaults to '10 seconds'.
        """

        def __init__(
            self,
            vessel: str,
            reagent: str,
            pH: float,
            add_increment_volume: float = '1 mL',
            stir_between_additions_time: float = '10 seconds',
        ):
            super().__init__(locals())

        def on_prepare_for_execution(self, graph):
            """Add any extra properties needed before execution using graph."""
            return

        def sanity_checks(self, graph):
            """Return list of sanity checks to perform to make sure the step
            properties make sense.
            This is called after on_prepare_for_execution.
            """
            return []

        def on_start(self):
            """Called once at start of execution and returned list of steps executed."""
            return []

        def on_continue(self):
            """Called repeatedly and returned list of steps executed until empty
            list returned.
            """
            return []

        def on_finish(self):
            """Called once after continue loop broken and return list of steps executed."""
            return []

2. Implement on_start
*********************

:code:`on_start` returns a list of steps that are executed once when the step
begins executing. This is where any initialisation etc. should be performed.

In the case of AddToPH we will want to take an initial pH reading. To do this
we will need a method that can take the pH reading and store it in a variable.
We will also determine what direction the pH is being changed in so we know
whether to use >= or <= later in the process when checking pH values.

.. code-block:: python

    def on_initial_ph_reading(self, reading):
        """Set self.current_pH and establish what direction the pH is being
        changed.
        """
        self.current_pH = reading
        if self.current_pH > self.pH:
            self.pH_direction = 'down'

        elif self.current_pH < self.pH:
            self.pH_direction = 'up'

        else:
            self.finished = True

    def on_start(self):
        """Take initial pH reading."""
        return [
            ReadPH(
                vessel=self.vessel,
                on_reading=self.on_initial_ph_reading
            ),
        ]

3. Define continue actions
**************************

Now define all the actions that your step can take during its execution as static
variables with unique integer values at the top of the class and create methods
for each one like so.

.. code-block:: python

    from xdl.step_utils import AbstractDynamicStep

    class AddToPH(AbstractDynamicStep):
        """Add given reagent until desired pH is reached.

        Args:
            vessel (str): Vessel to add to.
            reagent (str): Reagent to add to reach target pH.
            pH (float): Target pH.
            add_increment_volume (float, optional): Volume of reagent to add
                between each pH reading. Defaults to '1 mL'.
            stir_between_additions_time (float, optional): Time to stir after
                each addition of reagent. Defaults to '10 seconds'.
        """

        READ_PH = 0  # Code for pH reading option during continue loop.
        ADD_REAGENT = 1  # Code for reagent addition option during continue loop.

        def __init__(
            self,
            vessel: str,
            reagent: str,
            pH: float,
            add_increment_volume: float = '1 mL',
            stir_between_additions_time: float = '10 seconds',
        ):
            super().__init__(locals())
            self.continue_options = {
                READ_PH: self.continue_read_ph
                ADD_REAGENT: self.continue_add_reagent
            }
            self.continue_option = 1
            self.finished = False

        # ...

        def on_continue(self):
           """Continue adding reagent until desired pH is reached."""
            if self.finished:
                return []
            else:
                return self.continue_options[self.continue_option]()

        def continue_read_ph(self):
            """Read pH during continue loop."""

            # Next iteration of continue loop will be addition.
            return []

        def continue_add_reagent(self):
            """Add reagent during continue loop."""

            # Next iteration of continue loop will be pH reading.
            return []

This may seem unnecessary in this example, but this is a good way to keep
complicated dynamic steps understandable.

4. Implement continue methods
*****************************

Now implement all the continue action methods. Each method should change
:code:`self.continue_option` so that the correct action is executed on the next
iteration of the continue loop.

To exit the continue loop :code:`on_continue` must return an empty list, so make sure
you have an exit condition otherwise :code:`on_continue` will execute forever.

.. code-block:: python

    def on_continue(self):
        """Continue adding reagent until desired pH is reached."""
        if self.finished:
            return []
        else:
            return self.continue_options[self.continue_option]()

    def on_ph_reading(self, reading):
        """Callback function for pH reading in continue loop.
        Set self.finished = True if desired pH is reached.
        """
        self.current_pH = reading

        if self.pH_direction == 'up':
            if self.current_pH >= self.target_pH:
                self.finished = True

        elif self.pH_direction == 'down':
            if self.current_pH <= self.target_pH:
                self.finished = True

    def continue_read_ph(self):
        """Read pH during continue loop."""

        # Next iteration of continue loop will be addition.
        self.continue_option = self.ADD_REAGENT

        return [
            ReadPH(
                vessel=self.vessel,
                on_reading=self.on_ph_reading,
            )
        ]

    def continue_add_reagent(self):
        """Add reagent during continue loop."""

        # Next iteration of continue loop will be pH reading.
        self.continue_option = self.READ_PH

        return [
            Add(
                vessel=self.vessel,
                reagent=self.reagent,
                volume=self.add_increment_volume,
            ),
            Stir(
                vessel=self.vessel,
                time=self.stir_between_additions_time,
            ),
        ]

5. Implement on_finish
**********************

:code:`on_finish` is the place to do any final steps to tidy things up after
the continue loop. In this case we don't need to do anything so it can stay
just return an empty list.

We now have a fully functioning dynamic step. The rest of the tutorial will show
you ways in which you could improve this step and make sure it is robust.

.. code-block:: python

    from xdl.step_utils import AbstractDynamicStep

    class AddToPH(AbstractDynamicStep):
        """Add given reagent until desired pH is reached.

        Args:
            vessel (str): Vessel to add to.
            reagent (str): Reagent to add to reach target pH.
            pH (float): Target pH.
            add_increment_volume (float, optional): Volume of reagent to add
                between each pH reading. Defaults to '1 mL'.
            stir_between_additions_time (float, optional): Time to stir after
                each addition of reagent. Defaults to '10 seconds'.
        """

        READ_PH = 0  # Code for pH reading option during continue loop.
        ADD_REAGENT = 1  # Code for reagent addition option during continue loop.

        def __init__(
            self,
            vessel: str,
            reagent: str,
            pH: float,
            add_increment_volume: float = '1 mL',
            stir_between_additions_time: float = '10 seconds',
        ):
            super().__init__(locals())
            self.continue_options = {
                READ_PH: self.continue_read_ph,
                ADD_REAGENT: self.continue_add_reagent
            }
            self.continue_option = 1  # Reagent addition
            self.finished = False

        def on_prepare_for_execution(self, graph):
            """Add any extra properties needed before execution using graph."""
            return

        def sanity_checks(self, graph):
            """Return list of sanity checks to perform to make sure the step
            properties make sense.
            This is called after on_prepare_for_execution.
            """
            return []

        def on_initial_ph_reading(self, reading):
            """Set self.current_pH and establish what direction the pH is being
            changed.
            """
            self.current_pH = reading
            if self.current_pH > self.target_pH:
                self.pH_direction = 'down'

            elif self.current_pH < self.target_pH:
                self.pH_direction = 'up'

            else:
                self.finished = True

        def on_start(self):
            """Take initial pH reading."""
            return [
                ReadPH(
                    vessel=self.vessel,
                    on_reading=self.on_initial_ph_reading
                ),
            ]

        def on_continue(self):
            """Continue adding reagent until desired pH is reached."""
            if self.finished:
                return []
            else:
                return self.continue_options[self.continue_option]()

        def on_ph_reading(self, reading):
            """Callback function for pH reading in continue loop.
            Set self.finished = True if desired pH is reached.
            """
            self.current_pH = reading

            if self.pH_direction == 'up':
                if self.current_pH >= self.target_pH:
                    self.finished = True

            elif self.pH_direction == 'down':
                if self.current_pH <= self.target_pH:
                    self.finished = True

        def continue_read_ph(self):
            """Read pH during continue loop."""

            # Next iteration of continue loop will be addition.
            self.continue_option = self.ADD_REAGENT

            return [
                ReadPH(
                    vessel=self.vessel,
                    on_reading=self.on_ph_reading,
                )
            ]

        def continue_add_reagent(self):
            """Add reagent during continue loop."""

            # Next iteration of continue loop will be pH reading.
            self.continue_option = self.READ_PH

            return [
                Add(
                    vessel=self.vessel,
                    reagent=self.reagent,
                    volume=self.add_increment_volume,
                ),
                Stir(
                    vessel=self.vessel,
                    time=self.stir_between_additions_time,
                ),
            ]

        def on_finish(self):
            """Don't need to do anything after continue loop so return empty list."""
            return []

6. Implement sanity checks
**************************

It is a good idea to implement sanity check. This method should check that all
parameters passed to the step are sane before execution begins, and if bad parameters
are passed, raise informative errors.

.. code-block:: python

    from xdl.utils.sanity_checks import SanityCheck

    def sanity_checks(self, graph):
        """Return list of sanity checks to perform to make sure the step
        properties make sense.
        This is called after on_prepare_for_execution.
        """
        return [
            SanityCheck(
                condition=self.vessel,
                error_msg='vessel parameter must be given.',
            ),
            SanityCheck(
                condition=self.vessel in list(graph.nodes()),
                error_msg=f'"{self.vessel}" not found in graph',
            ),
            SanityCheck(
                condition=self.volume > 0,
                error_msg='volume parameter must be > 0.',
            ),
            SanityCheck(
                condition=self.reagent in [
                    data['chemical']
                    for node, data in graph.nodes(data=True)
                    if data['class'] == 'ChemputerFlask'
                ],
                error_msg=f'Reagent "{self.reagent}" not found in graph.',
            ),
            SanityCheck(
                condition=self.add_increment_volume  > 0,
                error_msg='add_increment_volume parameter must be > 0.',
            ),
            SanityCheck(
                condition=self.stir_between_additions_time >= 0,
                error_msg='stir_between_additions_time parameter must be >= 0.',
            )
        ]

7. Final step
*************

This is our final step. Further developments that could be implemented in this step
are a guard against overfilling the vessel if the desired pH is never reached,
and higher increment volumes when the target pH is far away.

.. code-block:: python

    from xdl.step_utils import AbstractDynamicStep
    from xdl.utils.sanity_checks import SanityCheck

    class AddToPH(AbstractDynamicStep):
        """Add given reagent until desired pH is reached.

        Args:
            vessel (str): Vessel to add to.
            reagent (str): Reagent to add to reach target pH.
            pH (float): Target pH.
            add_increment_volume (float, optional): Volume of reagent to add
                between each pH reading. Defaults to '1 mL'.
            stir_between_additions_time (float, optional): Time to stir after
                each addition of reagent. Defaults to '10 seconds'.
        """

        READ_PH = 0  # Code for pH reading option during continue loop.
        ADD_REAGENT = 1  # Code for reagent addition option during continue loop.

        def __init__(
            self,
            vessel: str,
            reagent: str,
            pH: float,
            add_increment_volume: float = '1 mL',
            stir_between_additions_time: float = '10 seconds',
        ):
            super().__init__(locals())
            self.continue_options = {
                READ_PH: self.continue_read_ph,
                ADD_REAGENT: self.continue_add_reagent
            }
            self.continue_option = 1  # Reagent addition
            self.finished = False

        def on_prepare_for_execution(self, graph):
            """Add any extra properties needed before execution using graph."""
            return

        def sanity_checks(self, graph):
            """Return list of sanity checks to perform to make sure the step
            properties make sense.
            This is called after on_prepare_for_execution.
            """
            return [
                SanityCheck(
                    condition=self.vessel,
                    error_msg='vessel parameter must be given.',
                ),
                SanityCheck(
                    condition=self.vessel in list(graph.nodes()),
                    error_msg=f'"{self.vessel}" not found in graph',
                ),
                SanityCheck(
                    condition=self.volume > 0,
                    error_msg='volume parameter must be > 0.',
                ),
                SanityCheck(
                    condition=self.reagent in [
                        data['chemical']
                        for node, data in graph.nodes(data=True)
                        if data['class'] == 'ChemputerFlask'
                    ],
                    error_msg=f'Reagent "{self.reagent}" not found in graph.',
                ),
                SanityCheck(
                    condition=self.add_increment_volume  > 0,
                    error_msg='add_increment_volume parameter must be > 0.',
                ),
                SanityCheck(
                    condition=self.stir_between_additions_time >= 0,
                    error_msg='stir_between_additions_time parameter must be >= 0.',
                )
            ]

        def on_initial_ph_reading(self, reading):
            """Set self.current_pH and establish what direction the pH is being
            changed.
            """
            self.current_pH = reading

            if self.current_pH > self.pH:
                self.pH_direction = 'down'

            elif self.current_pH < self.pH:
                self.pH_direction = 'up'

            else:
                self.finished = True

        def on_start(self):
            """Take initial pH reading."""
            return [
                ReadPH(
                    vessel=self.vessel,
                    on_reading=self.on_ph_reading
                ),
            ]

        def on_continue(self):
            """Continue adding reagent until desired pH is reached."""
            if self.finished:
                return []
            else:
                return self.continue_options[self.continue_option]()

        def on_ph_reading(self, reading):
            """Callback function for pH reading in continue loop.
            Set self.finished = True if desired pH is reached.
            """
            self.current_pH = reading

            if self.pH_direction == 'up':
                if self.current_pH >= self.pH:
                    self.finished = True

            elif self.pH_direction == 'down':
                if self.current_pH <= self.pH:
                    self.finished = True

        def continue_read_ph(self):
            """Read pH during continue loop."""

            # Next iteration of continue loop will be addition.
            self.continue_option = self.ADD_REAGENT

            return [
                ReadPH(
                    vessel=self.vessel,
                    on_reading=self.on_ph_reading,
                )
            ]

        def continue_add_reagent(self):
            """Add reagent during continue loop."""

            # Next iteration of continue loop will be pH reading.
            self.continue_option = self.READ_PH

            return [
                Add(
                    vessel=self.vessel,
                    reagent=self.reagent,
                    volume=self.add_increment_volume,
                ),
                Stir(
                    vessel=self.vessel,
                    time=self.stir_between_additions_time,
                ),
            ]

        def on_finish(self):
            """Don't need to do anything after continue loop so return empty list."""
            return []
