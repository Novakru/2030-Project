====================
Using XDL Controller
====================

As well as providing a way to capture procedures in static files, all functionality
of XDL is also available within scripts using the XDL Controller. This is useful
for playing about and quickly performing steps on your platform.

Instantiate XDL Controller
**************************

::

    # Instantiate platform controller
    from chempiler import Chempiler
    import ChemputerAPI

    platform_controller = Chempiler(
        experiment_code="example",
        output_dir="example",
        graph_file="graph.json",
        simulation=False,
        device_modules=[ChemputerAPI]
    )

    # Instantiate XDL Controller
    xdl_controller = XDLController(platform_controller, graph_f)


Use XDL Controller
******************

All XDL steps are available as methods of the controller, but with snake case
instead of pascal case, for example :code:`CleanVessel` -> :code:`clean_vessel`.
The method calls below will physically operate the platform.

.. code-block:: python

    # Example
    xdl_controller.add(
        reagent="water",
        vessel="reactor",
        volume="10 mL"
    )
    xdl_controller.add(
        reagent="1M NaOH solution",
        vessel="reactor",
        volume="10 mL"
    )
    xdl_controller.heat_chill(
        vessel="reactor",
        temp="50°C",
        time="3 hrs"
    )
