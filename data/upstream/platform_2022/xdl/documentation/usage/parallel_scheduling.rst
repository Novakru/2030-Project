Parallel Scheduling
===================

NOTE: This currently only applies to the Chemputer implementation of XDL. In theory,
it should be extendable to other platforms, but for the time being it has been
developed as part of the ``chemputerxdl`` package.

Basic Usage
***********

Basic usage of the parallel scheduling is as follows.

.. code-block:: python

   # Load XDL objects
   x1 = XDL('procedure1.xdl')
   x2 = XDL('procedure2.xdl')

   graph_f = 'procedure_graph.json'

   # Create parallel schedule for execution of XDL objects
   xdl_schedule = get_schedule(
       [x1, x2],
       graph_f,
   )

   xdl_schedule.save_json('procedure-schedule.json')
   xdl_schedule.save_xdl('parallel-procedure.xdl')
   xdl_schedule.save_xdlexe('parallel-procedure.xdlexe')


Outputs
*******

There are three possible output files from a ``XDLSchedule`` object: an uncompiled ``.xdl`` file that
can be easily inspected; a compiled ``.xdlexe`` file ready for execution; and a
``.json`` file that contains a detailed description of the schedule. These schedule
JSON files can be visualized using this `schedule visualization app <https://croningroup.gitlab.io/chemputer/schedule-visualiser/>`_.

If you wish to work with objects rather than files, there are two methods ``XDLSchedule.to_json``
and ``XDLSchedule.to_xdl`` for this. There is no ``to_xdlexe`` method as the ``XDL``
object returned by ``XDLSchedule.to_xdl`` is already compiled.

Solver methods
**************

There are currently three solver algorithms available, with a plan to add simulated
annealing in the future.

1. ``grid_search``: Search every possible schedule. Slow, but sure to find the best schedule.
2. ``random_search``: Search schedules randomly for a given number of generations. Faster than grid search depending on number of generations. Should find good schedule but may not find the best schedule.
3. ``genetic_algorithm``: Faster than grid search depending on number of generations. Should find good schedule but may not find the best schedule.

To specify the solver method to use there is the ``solver`` argument in ``get_schedule``.
In the case of ``random_search`` and ``genetic_algorithm`` you can also give the ``generations`` argument, which defaults to ``50`` and ``10`` respectively.

.. code-block:: python

   # Create parallel schedule using grid search
   xdl_schedule = get_schedule(
       [x1, x2],
       graph_f,
   )

   # Create parallel schedule using random search with 30 generations
   xdl_schedule = get_schedule(
       [x1, x2],
       graph_f,
       solver='random_search',
       generations=30
   )

   # Create parallel schedule using genetic algorithm with 30 generations
   xdl_schedule = get_schedule(
       [x1, x2],
       graph_f,
       solver='genetic_algorithm',
       generations=30
   )
