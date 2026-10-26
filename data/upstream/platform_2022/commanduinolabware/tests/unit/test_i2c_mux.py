import pytest
import random
import logging

@pytest.mark.hardware
def test_set_i2c_mux_name(sensorhub):

    if hasattr(sensorhub, "i2c_mux"):
        assert sensorhub.set_i2c_mux_name("whatever") is None
    else:
        # Grab random virtual device & let it be new reference to mux
        mux_name, mux_object = random.choice(list(sensorhub.devices.items()))
        sensorhub.set_i2c_mux_name(mux_name)
        assert sensorhub.i2c_mux is mux_object


@pytest.mark.hardware
@pytest.mark.parametrize("mask, lst", [(0, [0, 0, 0, 0, 0, 0, 0, 0]),
                                        (1, [1, 0, 0, 0, 0, 0, 0, 0]),
                                        (55, [1, 1, 1, 0, 1, 1, 0, 0]),
                                        (128, [0, 0, 0, 0, 0, 0, 0, 1]),
                                        (222, [0, 1, 1, 1, 1, 0, 1, 1]),
                                        (255, [1, 1, 1, 1, 1, 1, 1, 1]),
                                        ])
def test_pca9548a_mask2list(sensorhub, mask, lst):

    assert sensorhub._pca9548a_mask_to_list(mask) == lst


@pytest.mark.hardware
@pytest.mark.parametrize("mask, lst", [(0, [0, 0, 0, 0, 0, 0, 0, 0]),
                                        (1, [1, 0, 0, 0, 0, 0, 0, 0]),
                                        (63, [1, 1, 1, 1, 1, 1, 0, 0]),
                                        (144, [0, 0, 0, 0, 1, 0, 0, 1]),
                                        (201, [1, 0, 0, 1, 0, 0, 1, 1]),
                                        (255, [1, 1, 1, 1, 1, 1, 1, 1]),
                                        ])
def test_pca9548a_list2mask(sensorhub, mask, lst):

    assert sensorhub._pca9548a_list_to_mask(lst) == mask


@pytest.mark.hardware
@pytest.mark.parametrize("channels, onoff, result", [([1, 3, 5, 8], True, 191),
                                                     ([2, 4, 6, 7], False, 0),
                                                     ([3, 8], True, 174)
                                                     ])
def test_switch_pca9548a_channels(sensorhub, caplog, channels, onoff, result):

    if sensorhub._simulation is True:
        caplog.set_level(logging.INFO)
        sensorhub._switch_pca9548a_channels(channels, onoff)
        assert f"set_channels({result})" in caplog.text



