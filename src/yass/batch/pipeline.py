import os
from functools import partial

from .new import BatchProcessor


class PipedTransformation(object):
    """
    function: function
        Function to apply
    output_name: str
        Name of the file for the output
    mode: str
        Operation mode, one of 'single_channel_one_batch' (every batch are
        all observations from a single channel), 'single_channel' (every batch
        are observations from a single channel, but can be splitted in several
        batches to avoid exceeding max_memory) or 'multi_channel' (every batch
        has observations for every channel selected, batches are splitted
        not to exceed max_memory)
    keep: bool, optional
        Whether to keep the results from this step, otherwise the file is
        deleted after the next transformation is done
    **kwargs
        Function kwargs
    """

    def __init__(self, function, output_name, mode, keep=False, **kwargs):
        self.function = function
        self.output_name = output_name
        self.mode = mode
        self._keep = keep
        self.kwargs = kwargs

    @property
    def keep(self):
        return self._keep


class BatchPipeline(object):
    """Chain batch operations

    Parameters
    ----------
    path_to_input: str
        Path to input file
    dtype: str
        Numpy dtype
    n_channels: int
        Number of channels
    data_format: str
        Data format, it can be either 'long' (observations, channels) or
        'wide' (channels, observations)
    max_memory: int or str
        Max memory to use in each batch, interpreted as bytes if int,
        if string, it can be any of {N}KB, {N}MB or {N}GB
    output_path: str
        Folder indicating where to store the files from every step
    from_time: int, optional
        Starting time, defaults to None, which means start from time 0
    to_time: int, optional
        Ending time, defaults to None, which means end at the last observation
    channels: int, tuple or str, optional
        A tuple with the channel indexes or 'all' to traverse all channels,
        defaults to 'all'

    Examples
    --------

    .. literalinclude:: ../../examples/batch/pipeline_single_channel_one_batch.py
    # noqa
    """

    def __init__(self, path_to_input, dtype, n_channels, data_format,
                 max_memory, output_path, from_time=None, to_time=None,
                 channels='all'):
        self.path_to_input = path_to_input
        self.dtype = dtype
        self.n_channels = n_channels
        self.data_format = data_format
        self.max_memory = max_memory

        self.from_time = from_time
        self.to_time = to_time
        self.channels = channels
        self.output_path = output_path
        self.tasks = []

    def add(self, tasks):
        self.tasks.extend(tasks)

    def run(self):
        """Run all tasks in the pipeline

        Returns
        -------
        list
            List with path to output files in the order they were run, if
            keep is False, path is still returned but file will not exist
        """
        path_to_input = self.path_to_input

        bp = BatchProcessor(path_to_input, self.dtype,
                            self.n_channels,
                            self.data_format, self.max_memory)

        output_paths = []

        while self.tasks:
            task = self.tasks.pop(0)
            output_path = os.path.join(self.output_path, task.output_name)
            output_paths.append(output_path)

            if task.mode == 'single_channel_one_batch':
                fn = partial(bp.single_channel_apply,
                             force_complete_channel_batch=True)
            elif task.mode == 'single_channel':
                fn = partial(bp.single_channel_apply,
                             force_complete_channel_batch=False)
            elif task.mode == 'multi_channel':
                fn = bp.multi_channel_apply
            else:
                raise ValueError("Invalid mode {}".format(task.mode))

            _, p = fn(task.function, output_path,
                      from_time=self.from_time,
                      to_time=self.to_time,
                      channels=self.channels,
                      **task.kwargs)

            # update bp
            bp = BatchProcessor(output_path, p['dtype'],
                                p['n_channels'], p['data_format'],
                                self.max_memory)

            # delete the result if needed
            if not task.keep:
                os.remove(path_to_input)

            # update path to input
            path_to_input = output_path

        return output_paths
