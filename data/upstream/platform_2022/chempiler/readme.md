# The Chempiler

This repo contains the Chempiler library, which is the base layer for operating
the Chemputer platform. It maps platform graphs to device drivers, and provides
a platform controller for ChemputerXDL to execute steps with.

### Authors

- Graham Keenan - Graham.Keenan@glasgow.ac.uk
- Sebastian Steiner - s.steiner.1@research.gla.ac.uk
- Hessam Mehr - hessam.mehr@glasgow.ac.uk
- Matthew Craven - matthew.craven@glasgow.ac.uk

### Prerequisites

- Python 3.7+
- networkx
- pyserial
- OpenCV

### Usage

```python
from chempiler import Chempiler
import ChemputerAPI

c = Chempiler(
    experiment_code="my-experiment",
    output_dir="experiments/my-experiment",
    graph_file="my-graph.json",
    simulation=False,
    device_modules=[ChemputerAPI]
)
```

### Run Tests

To run the test suite and make sure your installation is working correctly:

```python
pytest tests -rf
```

### Developing

The following instructions are intended for Chempiler developers (as opposed to Chempiler users).

To make enhancements to the Chempiler, you will want to install it in development mode. By doing this, you `chempiler` package is kept up-to-date with the changes that you make to the code so you won't have to re-install the package to make your changes visible.

```bash
git clone <git URL for this repo>
cd Chempiler
pip install -r requirements.txt
pip install -e .
```

To run the unit tests that come with the Chempiler, you will need to install the `ChemputerAPI` and `SerialLabware` packages as well.

## Project structure

This repository contains the following subfolders and files in the `chempiler` folder.

NOTE: A lot of the functionality in this repo (especially `tools.module_execution`) has been duplicated in ChemputerXDL and is no longer used. For now,
it has not been removed for legacy reasons. However, sometimes it leads to duplication of effort when making updates.
In the future it would be good to trim down this repo, so that Chempiler and ChemputerXDL have well-defined unique
purposes, and do not do each other's jobs.

Known duplicate functionality:

- Separate phases
- Wait for temp
- Set temperature
- Vent vacuum
