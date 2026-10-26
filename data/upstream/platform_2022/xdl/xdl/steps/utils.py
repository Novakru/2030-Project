# Std
from typing import Dict, Any, Union

# Other
import tabulate

# Relative
from ..utils.sanitisation import convert_val_to_std_units
from ..utils.prop_limits import TIME_PROP_LIMIT


class FTNDuration:
    """Fuzzy triangular number class. Simple convenience class to store FTNs.
    A fuzzy triangular number is a number consisting of a minimum possible
    value, a most likely value, and a maximum possible value. In XDL they are
    used for representing step durations, as many steps have an uncertain
    duration.

    Times can be passed in as numbers in seconds, or as strings with any of the
    XDL accepted units, e.g. '1 hr'.

    Args:
        min_value (Union[float, int, str]): Minimum possible value.
        most_likely (Union[float, int, str]): Most likely value.
        max_value (Union[float, int, str]): Maximum possible value.
    """
    def __init__(
        self,
        min_value: Union[float, int, str],
        most_likely: Union[float, int, str],
        max_value: Union[float, int, str]
    ) -> None:
        # Convert `min_value` to seconds and store in `self.min`
        if type(min_value) == str:
            TIME_PROP_LIMIT.validate(min_value)
            self.min = convert_val_to_std_units(min_value)
        else:
            self.min = min_value

        # Convert `max_value` to seconds and store in `self.max`
        if type(max_value) == str:
            TIME_PROP_LIMIT.validate(max_value)
            self.max = convert_val_to_std_units(max_value)
        else:
            self.max = max_value

        # Convert `most_likely` to seconds and store in `self.most_likely`
        if type(most_likely) == str:
            TIME_PROP_LIMIT.validate(most_likely)
            self.most_likely = convert_val_to_std_units(most_likely)
        else:
            self.most_likely = most_likely

    def __add__(self, other):
        """Allow FTNs to be added together using + operator."""
        min_value = self.min + other.min
        most_likely = self.most_likely + other.most_likely
        max_value = self.max + other.max
        return FTNDuration(
            min_value=min_value,
            most_likely=most_likely,
            max_value=max_value
        )

    def __repr__(self):
        return f'FTN({self.min:2.2f}s {self.most_likely:.2f}s {self.max:.2f}s'

def pretty_props_table(props: Dict[str, Any]) -> str:
    """Make neat props table for printing to terminal. Has no table lines but
    aligns items neatly.

    Args:
        props (Dict[str, Any]): Step properties dict

    Returns:
        str: Step properties table neatly formatted.
    """
    return tabulate.tabulate(
        [
            [k, str(v)]
            for k, v in props.items()
            if k != 'children'
        ],
        tablefmt='plain',
    )
