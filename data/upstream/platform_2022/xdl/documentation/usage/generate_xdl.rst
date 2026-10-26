=================
Generate XDL file
=================

XDL files can be written manually, but the easiest way to produce them is using
`ChemIDE <https://croningroup.gitlab.io/chemputer/xdlapp>`_.

ChemIDE has two methods of adding steps to XDL procedures, manually, and using SynthReader.

To add a step using SynthReader, type in the text area on the right, and click
"Translate and Add" to append the steps produced by SynthReader to the procedure on the left,
or "Translate" to replace the procedure on the left with the steps produced by SynthReader.

.. image:: assets/synthreader-chemide.png
   :width: 900

To add a step manually go to the Edit menu and click New Step.

.. image:: assets/add-step-manually.png
   :width: 900

This will bring up a list of all available step types that you can search by
typing in the search bar.

.. image:: assets/add-step-manually-search.png
   :width: 900

Click the step type you wish to add and you will be presented with a form
where you can select the step properties either by editing the sentence at the
top or by changing values in the properties table.

.. image:: assets/add-step-manually-properties.png
   :width: 900

To add the step to the procedure click the "Submit" button.

SynthReader Examples
********************

Here are some working examples of ways that different synthetic sequences can be
obtained in XDL using SynthReader. General advice for using SynthReader is
to always use past tense, and keep sentences simple.

Addition of multiple reagents
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

"*2,6-Dimethylaniline (3.0 mL, 2.9 g, 24.4 mmol) is added to 15 mL of glacial
acetic acid followed by chloroacetyl chloride (2.0 mL, 2.85 g, 25.1 mmol) and
25 mL of half-saturated aqueous sodium acetate.*"

OR

"*2,6-Dimethylaniline (3.0 mL, 2.9 g, 24.4 mmol), chloroacetyl chloride
(2.0 mL, 2.85 g, 25.1 mmol) and 25 mL of half-saturated aqueous sodium acetate
were added to 15 mL of glacial acetic acid.*"

.. code-block:: xml

    <Add
      stir="False"
      volume="15 mL"
      vessel="reactor"
      reagent="glacial acetic acid" />
    <Add
      stir="True"
      volume="3 mL"
      vessel="reactor"
      reagent="2,6-Dimethylaniline" />
    <Add
      stir="True"
      volume="2 mL"
      vessel="reactor"
      reagent="chloroacetyl chloride" />
    <Add
      stir="True"
      volume="25 mL"
      vessel="reactor"
      reagent="half-saturated aqueous sodium acetate" />

Addition at temperature
^^^^^^^^^^^^^^^^^^^^^^^

"*THF (50 mL) was added at -20°C*."

.. code-block:: xml

    <HeatChillToTemp
      temp="-20°C"
      vessel="reactor" />
    <Add
      stir="False"
      volume="50"
      vessel="reactor"
      reagent="THF" />
    <StopHeatChill
      vessel="reactor" />

Addition over time
^^^^^^^^^^^^^^^^^^

"*THF (50 mL) was added over 20 minutes.*"

.. code-block:: xml

    <Add
      stir="False"
      time="20 mins"
      volume="50 mL"
      vessel="reactor"
      reagent="THF" />

Addition dropwise
^^^^^^^^^^^^^^^^^

"*...THF (50 mL) was added dropwise.*"

.. code-block:: xml

    <!-- ... -->
    <Add
      stir="True"
      dispense_speed="3"
      volume="50 mL"
      vessel="reactor"
      reagent="THF" />

Addition of viscous reagent
^^^^^^^^^^^^^^^^^^^^^^^^^^^

"*A viscous 50% aqueous solution of sodium hydroxide (NaOH) (12.0 g, 0.30 mol in 12 mL of H2O) (Note 6) is added.*"

.. code-block:: xml

    <Add
      stir="False"
      viscous="True"
      volume="12 mL"
      vessel="reactor"
      reagent="sodium hydroxide(NaOH) (12.0 g , 0.30 mol in 12 mL of H2O) water solution" />

Evaporation
^^^^^^^^^^^

"*The solvent was evaporated (50 mmHg, 40°C).*"

.. code-block:: xml

    <Evaporate
      mode="auto"
      time="30 mins"
      pressure="66.661 mbar"
      temp="40°C"
      rotavap_name="rotavap" />

Heat for a fixed time
^^^^^^^^^^^^^^^^^^^^^

"*The reaction mixture was heated at 80°C for 3 hrs.*"

.. code-block:: xml

    <HeatChill
      time="3 hrs"
      temp="80°C"
      vessel="reactor" />

Heat indefinitely
^^^^^^^^^^^^^^^^^

"*The reaction mixture was heated to 80°C.*"

.. code-block:: xml

    <HeatChillToTemp
      temp="80°C"
      vessel="reactor" />

Heat with vigorous stirring
^^^^^^^^^^^^^^^^^^^^^^^^^^^

"*The reaction mixture was heated at 70°C for 12 hrs with vigorous stirring.*"

.. code-block:: xml

    <HeatChill
      stir_speed="600 RPM"
      time="12 hrs"
      temp="70°C"
      vessel="reactor" />

Allow to cool to room temperature
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

"*The reaction mixture was allowed to cool to room temperature.*"

.. code-block:: xml

    <HeatChillToTemp
      continue_heatchill="False"
      active="False"
      temp="25°C"
      vessel="reactor" />

Actively cool to room temperature
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

"*The reaction mixture was cooled to room temperature.*"

.. code-block:: xml

    <HeatChillToTemp
      temp="25°C"
      vessel="reactor" />

Quantitative transfer
^^^^^^^^^^^^^^^^^^^^^

"*...The reaction mixture was transferred to a separating funnel. Water (50 mL) was
used to rinse the flask. The mixture was then extracted with ethyl acetate
(20 mL).*"

.. code-block:: xml

    <!-- ... -->
    <Transfer
      volume="all"
      to_vessel="separator"
      from_vessel="reactor" />
    <Add
      stir="True"
      volume="50 mL"
      vessel="reactor"
      reagent="water" />
    <Transfer
      volume="all"
      to_vessel="separator"
      from_vessel="reactor" />
    <Separate
      n_separations="1"
      solvent_volume="20 mL"
      solvent="ethyl acetate"
      product_bottom="False"
      to_vessel="reactor"
      separation_vessel="separator"
      from_vessel="separator"
      purpose="extract" />

Extraction
^^^^^^^^^^

"*The product was extracted with ethyl acetate (3 x 50 mL).*"

.. code-block:: xml

    <Separate
      n_separations="3"
      solvent_volume="50 mL"
      solvent="ethyl acetate"
      product_bottom="False"
      to_vessel="reactor"
      separation_vessel="separator"
      from_vessel="reactor"
      purpose="extract" />

Washing
^^^^^^^

"*The product was washed with water (3 x 50 mL).*"

.. code-block:: xml

    <Separate
      n_separations="3"
      solvent_volume="50 mL"
      solvent="water"
      product_bottom="False"
      to_vessel="reactor"
      separation_vessel="separator"
      from_vessel="reactor"
      purpose="wash" />

Separate organic phase, extract aqueous phase, and dry combined organic phases
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

"*The mixture is shaken and the organic layer is separated from the
aqueous layer. The aqueous layer is extracted with dichloromethane
(3 × 60 mL) (Note 9). The combined organic extracts are dried with
approximately 2 g of anhydrous magnesium sulfate (MgSO4) (Note 10).*"

.. code-block:: xml

    <Separate
      waste_phase_to_vessel="separator"
      n_separations="1"
      through="anhydrous magnesium sulfate(MgSO4)"
      solvent=""
      product_bottom="False"
      to_vessel="reactor"
      separation_vessel="separator"
      from_vessel="reactor"
      purpose="extract" />
    <Separate
      n_separations="3"
      solvent_volume="60 mL"
      through="anhydrous magnesium sulfate(MgSO4)"
      solvent="dichloromethane"
      product_bottom="True"
      to_vessel="reactor"
      separation_vessel="separator"
      from_vessel="separator"
      purpose="extract" />

Separate organic phase, extract aqueous phase, and wash combined organic phases
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

"*...The mixture is transferred to a separatory funnel and the organic phase is separated. The aqueous phase is extracted with dichloromethane (2 × 50 mL), and the combined organic layers are washed with deionized water (200 mL).*"

.. code-block:: xml

    <Transfer
      volume="all"
      to_vessel="separator"
      from_vessel="reactor" />
    <Separate
      waste_phase_to_vessel="separator"
      n_separations="1"
      solvent=""
      product_bottom="False"
      to_vessel="buffer_flask"
      separation_vessel="separator"
      from_vessel="separator"
      purpose="extract" />
    <Separate
      n_separations="2"
      solvent_volume="50 mL"
      solvent="dichloromethane"
      product_bottom="True"
      to_vessel="separator"
      separation_vessel="separator"
      from_vessel="separator"
      purpose="extract" />
    <Transfer
      volume="all"
      to_vessel="separator"
      from_vessel="buffer_flask" />
    <Separate
      n_separations="1"
      solvent_volume="200 mL"
      solvent="deionized water"
      product_bottom="True"
      to_vessel="reactor"
      separation_vessel="separator"
      from_vessel="separator"
      purpose="wash" />

Filter, Wash and Dry
^^^^^^^^^^^^^^^^^^^^

"*The solid was filtered, washed with ethyl acetate (3 x 50 mL) and dried for 3 hrs.*"

.. code-block:: xml

    <Filter
      filter_vessel="filter" />
    <WashSolid
      volume="50 mL"
      solvent="ethyl acetate"
      vessel="filter"
      repeat="3" />
    <Dry
      time="3 hrs"
      vessel="filter" />

Wash solid and dry at temperature
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

"*The solid was filtered, washed with THF (3 x 50 mL) at -20°C and dried for 3 hrs.*"

.. code-block:: xml

    <Filter
      filter_vessel="filter" />
    <WashSolid
      temp="-20°C"
      volume="50 mL"
      solvent="THF"
      vessel="filter"
      repeat="3" />
    <Dry
      temp="-20°C"
      time="3 hrs"
      vessel="filter" />

Dry at specific pressure
^^^^^^^^^^^^^^^^^^^^^^^^

"*The solid was dried at 75 mbar.*"

.. code-block:: xml

    <Dry
      vacuum_pressure="75 mbar"
      vessel="reactor" />
