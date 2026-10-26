Execution Clients
=================

Levels of Execution Client
**************************

In the case of the Chemputer, both the XDL bindings (chemputerxdl) and the platform controller (chempiler) expose an execution client. The reason for this, is to allow
certain functionality of the chempiler to be used on the platform controller level without having to get XDL involved. The Chempiler execution client allows background sensor readings and live device control from ChemIDE.
The chemputerxdl execution client allows entire procedure execution and XDL step device live control from ChemIDE.

Uncontrolled Usage
******************

In other sections of the docs, running the execution client for the Chemputer is shown as simply running a script ``python chemputerxdl/scripts/execution_client.py``.
When the execution client is used in this way, the platform controller (Chempiler for Chemputer) object is created internally as required.
The user has no control over the platform controller object. This is referred to as "Uncontrolled" execution client usage.

However, there are cases when it is useful to retain full control over the platform controller object (referred to as "Controlled" usage).
For example, if you want to use a Chempiler object (or execution client) while using the chemputerxdl execution client, you will need to use a controlled execution client to avoid instantiating multiple Chempiler instances.

Controlled Usage
****************

To make an execution client controlled, you need to bind your platform controller instance to it as shown below.

.. code-block:: python

   from chemputerxdl.execution_client import ChemputerExecutionClient

   execution_client = ChemputerExecutionClient()

   platform_controller = Chempiler(...)

   execution_client.bind_platform_controller(platform_controller)

Once a platform controller is bound, the execution client will use this rather
than creating its own platform controller objects. The execution client can go back to Uncontrolled behaviour with the following method.

.. code-block:: python

   execution_client.unbind_platform_controller()
