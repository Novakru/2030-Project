Sensor Reading
==============

This page provides a guide on how to take regular sensor readings in the
background of an experiment, and save them to a file / visualise them. It is specific to the Chemputer and not relevant at the moment to any other platform.

Launch Dashboard
^^^^^^^^^^^^^^^^

.. code-block:: python

   from chempiler import Chempiler
   from chempu_dashboard import Dashboard

   # Instantiate chempiler
   chempiler = Chempiler(**params)

   # Instantiate dashboard and connect Chempiler to dashboard
   dashboard = Dashboard(chempiler)

   # Run dashboard server on localhost:8050
   dashboard.run()

After launching the dashboard as shown above, it can be accessed at `localhost:8050 <http://localhost:8050>`_.

.. image:: assets/dash-sensor-reading.png
   :width: 600


Control Sensors
^^^^^^^^^^^^^^^

The start and stop buttons can be used to start / stop sensor reading for each sensor, and the slider can be used to change the frequency of sensor reading.

.. image:: assets/dash-sensor-controls.png
   :width: 600

Chart Navigation
^^^^^^^^^^^^^^^^

* Sensors can be hidden from either chart by clicking their name in the legend.
* The static chart can be zoomed by dragging and selecting the area to be viewed. The zoom level can be reset by double clicking.
* The static chart can be panned by dragging the x axis.
* The "Refresh" button updates the static chart with the latest readings since the last refresh.
