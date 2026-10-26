=================
Submitting Issues
=================

XDL is a work in progress so when you use it you will find bugs and
missing features that you need.

These should be submitted as issues on the `XDL repository <https://gitlab.com/croningroup/chemputer/xdl/issues>`_.
Please use the labels described below, and make sure you follow the relevant issue
template, also described below. Issues adhering to this guide will generally be resolved much
faster than ones that don't.

******
Labels
******

When submitting an issue please assign two labels, a type and a priority.
These can be selected on the right sidebar.

+-----------------------+------------------------------------------------------------------------------+
| Label                 | Description                                                                  |
+=======================+==============================================================================+
| **Priority: High**    | Needs urgent attention, XDL breaking with no workaround.                     |
+-----------------------+------------------------------------------------------------------------------+
| **Priority: Medium**  | Definitely needs addressed but not breaking. Workaround available.           |
+-----------------------+------------------------------------------------------------------------------+
| **Priority: Low**     | Should be implemented at some point but not needed in the near future.       |
+-----------------------+------------------------------------------------------------------------------+
| **Type: Bug**         | Something not behaving as expected.                                          |
+-----------------------+------------------------------------------------------------------------------+
| **Type: Enhancement** | New feature or improvement to existing feature.                              |
+-----------------------+------------------------------------------------------------------------------+

Issue Templates
***************

Bug report
^^^^^^^^^^

Bug reports should contain all the information necessary to reproduce the issue.

1. Script that reproduces the issue.
2. Associated XDL / graph files used by the script.
3. Description of the issue being faced. If you don't understand the error feel free to say so.
4. Full traceback (if bug involves error being thrown).

If the bug cannot be reproduced using only the information in the bug report, the issue should be updated with more information.

Feature request
^^^^^^^^^^^^^^^

Feature requests should contain a detailed description of the feature being proposed.

1. Clear description of feature / improvement.
2. Rigorous specification of way that feature should behave.
3. Values for any default values associated with feature, e.g. for a new Purge step, you would provide times for how long purging should take place, number of vacuum / inert gas cycles etc.

Graph generation issues
^^^^^^^^^^^^^^^^^^^^^^^

Issues related to graph generation should follow the bug report / feature request guides above.
Additionally, it is very helpful to provide screenshots and .json graph files to show
what you mean.

Example: https://gitlab.com/croningroup/chemputer/xdl/issues/171
