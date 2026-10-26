=================
Testing New Steps
=================

*Note: The following is very specific to Chemputer development and not general to XDL
integration with other platforms. Although if you find this development workflow
useful, feel free to copy it.*

All new features/bug fixes should be accommpanied by a unit test.

Unit test functions should be written in `tests/unit` and imported in
`tests/unit/all_unit_tests.py`

Example
-------

This example is for the :code:`QuantitativeTransfer` step shown in the "Making New Steps"
tutorial.


`tests/chemputer/unit/liquid_handling/test_quantitative_transfer.py`

.. code-block:: python

    import os
    import pytest
    from xdl import XDL
    from ..utils import generic_chempiler_test

    HERE = os.path.abspath(os.path.dirname(__file__))
    FOLDER = os.path.join(HERE, '..', 'files')

    # This decorator must be used for the test to be picked up by the CI.
    @pytest.mark.unit
    def test_quantitative_transfer():
        """Test QuantitativeTransfer step."""
        # Instantiate XDL object from test XDL file and generic `bigrig.json` graph.
        xdl_f = os.path.join(FOLDER, 'quantitative_transfer.xdl')
        graph_f = os.path.join(FOLDER, 'bigrig.json')
        x = XDL(xdl_f)
        x.prepare_for_execution(graph_f)

        # Test that steps are as expected.
        for step in x.steps:
            if step.name == 'QuantitativeTransfer':
                substeps = step.steps

                assert len(substeps) == 3

                # Initial liquid transfer
                assert substeps[0].name == 'Transfer'
                assert substeps[0].from_vessel == step.from_vessel
                assert substeps[0].to_vessel == step.to_vessel
                assert substeps[0].volume == 'all'

                # Adding solvent
                assert substeps[1].name == 'Add'
                assert substeps[1].reagent == step.solvent
                assert substeps[1].vessel == step.from_vessel
                assert substeps[1].volume == step.solvent_volume

                # Stir solvent
                assert substeps[2].name == 'Stir'
                assert substeps[2].vessel == step.from_vessel
                assert substeps[2].time == step.stir_time

                # Transfer solvent
                assert substeps[3].name == 'Transfer'
                assert substeps[3].from_vessel == step.from_vessel
                assert substeps[3].to_vessel == step.to_vessel
                assert substeps[3].volume == step.solvent_volume

        # Run Chempiler simulation to make sure step executes without error.
        generic_chempiler_test(xdl_f, graph_f)


`tests/chemputer/unit/files/quantitative_transfer.xdl`

.. code-block:: xml

    <Synthesis auto_clean="false">
      <Hardware>
        <Component
          id="reactor"
          type="reactor"
        />
        <Component
          id="filter"
          type="filter"
        />
      </Hardware>

      <Reagents>
        <Reagent id="water" />
      </Reagents>

      <Procedure>
        <!-- With solvent volume and stir_time explicity given. -->
        <QuantitativeTransfer
          from_vessel="reactor"
          to_vessel="separator"
          solvent="water"
          solvent_volume="30 mL"
          stir_time="2 mins"
        />
        <!-- Without solvent volume and stir time explicity given. -->
        <QuantitativeTransfer
          from_vessel="reactor"
          to_vessel="separator"
          solvent="water"
        />
      </Procedure>

    </Synthesis>
