# XDL

XDL is a chemical description language for representing chemical procedures in a machine and human-readable way. This package provides an abstract framework for linking this representation to execution on automated synthesis platforms.

## Installation

```
git clone https://gitlab.com/croningroup/chemputer/xdl.git
pip install -e xdl
```

## Usage

This is a basic usage example. For more detailed usage instructions, see [the documentation](https://croningroup.gitlab.io/chemputer/xdl).

```python
from xdl import XDL

# Load XDL procedure
x = XDL('procedure.xdl')

# Compile XDL procedure to run on specific platform graph
x.prepare_for_execution('procedure_graph.json')

# This line depends which platform you are doing so is just written here as pseudocode.
platform_controller = instantiate_platform_controller(**params)

# Execute XDL procedure on automated platform
x.execute(platform_controller)
```

## Contributing

If you wish to contribute a change to XDL, please follow this process.

1. Submit an issue describing the proposed change and reasons for the change.
2. Discuss with the project maintainers until an agreement is reached on the proposed implementation.
3. Fork the repo and make your change.
4. Add new tests as appropriate, make sure all tests still pass, and make sure the `flake8` lint still passes.
5. Submit a merge request back to the main repo, and reference the corresponding issue in the merge request.

## Resources

- [Original Publication](https://doi.org/10.1126/science.abc2986)
- [XDL Documentation](https://croningroup.gitlab.io/chemputer/xdl)
- [ChemIDE (Integrated Development Environment for XDL)](https://croningroup.gitlab.io/chemputer/xdlapp)
