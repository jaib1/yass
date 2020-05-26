import os

try:
    from pathlib2 import Path
except ImportError:
    from pathlib import Path

from yass.preprocess.util import _butterworth
from yass.util import load_yaml

import yass
from yass import preprocess


def test_can_apply_butterworth_filter(data):
    _butterworth(data[:, 0], low_frequency=300, high_factor=0.1,
                 order=3, sampling_frequency=20000)


def test_can_preprocess(path_to_config, make_tmp_folder):
    yass.set_config(path_to_config, make_tmp_folder)
    (standardized_path,
     standardized_params) = preprocess.run(
        os.path.join(make_tmp_folder, 'preprocess'))


def test_preprocess_saves_result_in_the_right_folder(path_to_config,
                                                     make_tmp_folder):
    yass.set_config(path_to_config, make_tmp_folder)
    (standardized_path,
     standardized_params) = preprocess.run(
        os.path.join(make_tmp_folder, 'preprocess'))

    expected = Path(make_tmp_folder, 'preprocess', 'standardized.bin')

    assert str(expected) == standardized_path
    assert expected.is_file()


def test_can_preprocess_in_parallel(path_to_config, make_tmp_folder):
    CONFIG = load_yaml(path_to_config)
    CONFIG['resources']['processes'] = 'max'

    yass.set_config(CONFIG, make_tmp_folder)

    (standardized_path,
     standardized_params) = preprocess.run(
        os.path.join(make_tmp_folder, 'preprocess'))


# FIXME: reference testing was deactivated
# def test_preprocess_returns_expected_results(path_to_config,
#                                              path_to_output_reference,
#                                              make_tmp_folder):
#     yass.set_config(path_to_config, make_tmp_folder)
#     standardized_path, standardized_params, whiten_filter = preprocess.run()

#     # load standardized data
#     standardized = np.fromfile(standardized_path,
#                                dtype=standardized_params['dtype'])

#     path_to_standardized = path.join(path_to_output_reference,
#                                      'preprocess_standardized.npy')
#     path_to_whiten_filter = path.join(path_to_output_reference,
#                                       'preprocess_whiten_filter.npy')

#     ReferenceTesting.assert_array_almost_equal(standardized,
#                                                path_to_standardized)
#     ReferenceTesting.assert_array_almost_equal(whiten_filter,
#                                                path_to_whiten_filter)


def test_can_preprocess_without_filtering(path_to_config,
                                          make_tmp_folder):
    CONFIG = load_yaml(path_to_config)
    CONFIG['preprocess'] = dict(apply_filter=False)

    yass.set_config(CONFIG, make_tmp_folder)

    (standardized_path,
     standardized_params) = preprocess.run(
        os.path.join(make_tmp_folder, 'preprocess'))
