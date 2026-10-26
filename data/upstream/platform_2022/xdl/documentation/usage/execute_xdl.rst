
Simulate / Execute XDL
======================

Python
******

Before executing you may wish to inspect the .xdlexe to make sure that is it planning
to do what you want it to do. This can be done by opening it in your text editor
of choice, or in ChemIDE by clicking the three-dot menu icon next to any step,
and then clicking "View XDLEXE".

.. image:: assets/chemide-view-xdlexe.png
   :width: 600

Once you are ready to run the xdlexe, it is just a matter of
instantiating the platform controller, and passing it to the xdlexe execute method.

It is highly advisable to first execute in simulation mode, before running on a physical
platform, to avoid any unexpected runtime errors. Simulation is toggled within the platform controller.

.. code-block:: python

    from xdl import XDL

    xdlexe = XDL('procedure.xdlexe')

    xdlexe.execute(platform_controller)

Instantiating the Platform Controller
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This depends on the platform being used, but as an example, the Chemputer
platform controller instantiation is shown here.

::

    from chempiler import Chempiler
    import ChemputerAPI

    platform_controller = Chempiler(
        experiment_code="procedure",
        output_dir="/path/to/experiment_folder",
        graph_file="procedure_graph.json",
        device_modules=[ChemputerAPI],
        simulation=True,
    )

ChemIDE
*******

Simulation
^^^^^^^^^^

Simulation can be done by going to the Actions menu and clicking "Simulate".

.. image:: assets/chemide-simulate-menu.png
   :width: 600

You will then have the option to upload a .xdlexe file and a graph if they are not
already loaded. You can run a simulation by clicking "Simulate". Simulation logs will be
shown with the option to download as a .txt file.

.. image:: assets/chemide-simulation-modal.png
   :width: 600

Execution
^^^^^^^^^
Execution of a procedure can be carried out in the execution mode of ChemIDE.

.. image:: assets/execution-mode-button.png
   :width: 600

Before execution, you must have loaded a graph and xdlexe file. This can be done
using the simulation tool described above, or by compiling a procedure in
ChemIDE.

To connect ChemIDE to your platform, you must run the
execution client script on the computer that will be used to control your
platform. In the case of the Chemputer, the command would be ``python chemputerxdl/scripts/execution-client.py``.
This will print a unique key to the screen, which you then need to paste into
ChemIDE execution mode and click "Connect".

.. image:: assets/execution-mode-connect.jpg
   :width: 600

Now the execution client is connected to ChemIDE, you can send it the experiment
you wish to run. To do this, click "Load Experiment". This should display a
list of all the steps in the procedure as shown below. If it does not, you can
look at the terminal running the execution client to see what the error is.

.. image:: assets/execution-mode-experiment-loaded.jpg
   :width: 600

From here, the interface should be pretty intuitive. The top play/pause/stop
controls will play the whole procedure, and the individual step play/pause/stop
controls will play individual steps. Logs are shown next to individual steps, and can be collapsed and expanded using
the arrow dropdown on the left of the step description.

The pause/stop buttons wait for the current XDL base step to finish before
stopping, so there will usually be a delay between pressing pause/stop and
actually stopping. In the case that you want to stop execution immediately,
with no possibility of resuming the execution, you can click the "Emergency Stop" button.
