import numpy as np
import sys, os, math
import datetime as dt
import scipy, scipy.signal
import parmap
from scipy.interpolate import splrep, splev, make_interp_spline, splder, sproot
from tqdm import tqdm

# doing imports inside module until travis is fixed
# Cat: TODO: move these to the top once Peter's workstation works
import torch
from torch import nn
#from torch.autograd import Variable

# cuda package to do GPU based spline interpolation and subtraction
import cudaSpline as deconv
import rowshift as rowshift

from yass.deconvolve.util import WaveForms


# # ****************************************************************************
# # ****************************************************************************
# # ****************************************************************************

def continuous_visible_channels(
    templates, geom, threshold=.5, neighb_threshold=1., spatial_neighbor_dist=70):
    """
    inputs:
    -------
    templates: np.ndarray with shape (#units, # channels, #time points)
    geom: np.ndarray with shape (# channel, 2)
    threshold: float
        Weaker channels threshold
    neighb_threshold: float
        Strong channel threshold
    spatial_neighbor_dist: float
        neighboring channel threshold (70 for 512 channels retinal probe)
    """
    ptps_ = templates.ptp(2)
    pdist = scipy.spatial.distance.squareform(
        scipy.spatial.distance.pdist(geom))
    vis_chan = (ptps_ >= neighb_threshold).astype(np.int32)
    neighbs = np.logical_and(
        pdist > 0,
        pdist < spatial_neighbor_dist).astype(np.int32)
    return np.logical_or(
        np.logical_and(
            np.matmul(vis_chan, neighbs) > 0,
            ptps_ >= threshold),
        ptps_ >= neighb_threshold)

def reverse_shifts(shifts):
    """Reverse the shifts so that all shifts are positive.

    params:
    -------
    shifts: np.ndarray of int
        All values should be non-negative

    returns:
    --------
    np.ndarray of non-negative integers.
    """
    return shifts.max() - shifts

def shift_channels(signal, shifts):
    """Shifts each channel of the signal according to given shifts.

    params:
    -------
    signal: np.ndarray with shape (#channels, #time)
    shifts: np.array with size #channels

    returns:
    --------
    a copy of the shifted signal according to the given shifts.
    """
    n_chan, size = signal.shape
    max_shift = shifts.max()
    shifted_signal_size = size + max_shift
    shifted_signal = np.zeros([n_chan, shifted_signal_size])
    # Getting shifted indices.
    ix1 = np.tile(np.arange(n_chan)[:, None], size)
    ix2 = np.arange(size) + shifts[:, None]
    shifted_signal[ix1, ix2] = signal
    return shifted_signal


def in_place_roll_shift(signal, shifts):
    """Shifts each channel of the signal according to given shifts.

    (IMPORTANT): This function is the equivalent of Ian's.
    params:
    -------
    signal: np.ndarray with shape (#channels, #time)
    shifts: np.array with size #channels

    returns:
    --------
    a copy of the shifted signal according to the given shifts.
    """
    idx = np.logical_not(shifts == 0)
    for i, s in zip(np.where(idx)[0], shifts[idx]):
        signal[i] = np.roll(signal[i], s)
               
        
# def continuous_visible_channels(
    # temp, geom, threshold=.5, neighb_threshold=1., spatial_neighbor_dist=70):
    # """
    # inputs:
    # -------
    # templates: np.ndarray with shape (# time points, # channels, #units)
    # geom: np.ndarray with shape (# channel, 2)
    # threshold: float
        # Weaker channels threshold
    # neighb_threshold: float
        # Strong channel threshold
    # spatial_neighbor_dist: float
        # neighboring channel threshold (70 for 512 channels retinal probe)
    # """
    # ptps_ = temp.ptp(0)
    # pdist = scipy.spatial.distance.squareform(
        # scipy.spatial.distance.pdist(geom))
    # vis_chan = (ptps_ >= neighb_threshold).astype(np.int32)
    # neighbs = np.logical_and(
        # pdist > 0,
        # pdist < spatial_neighbor_dist).astype(np.int32)
    # return np.logical_or(
        # np.logical_and(
            # np.matmul(neighbs, vis_chan) > 0,
            # ptps_ >= threshold),
        # ptps_ >= neighb_threshold)


def compute_temp_temp_svd_shifted2(rank, spike_size, n_unit, viscs, 
                                  align_shifts, aligned_temp, spat_comp,
                                  temp_comp, unit_unit_overlap):    
    
    temp_temp = [[0. for i in range(n_unit)] for j in range(n_unit)]

    for unit in tqdm(range(n_unit)):
        # Full temp is the unshifted reconstructed
        # templates for a unit that acts as the data
        # that other units get convolved by
        unshifted_temp = shift_channels(aligned_temp[unit], align_shifts[unit])
        for ounit in np.where(unit_unit_overlap[unit])[0]:
            # For all spatially overlapping templates, convolve them with
            # the outer loop template using the SVD trick
            shifts = reverse_shifts(align_shifts[ounit])
            shifted_data = shift_channels(unshifted_temp, shifts)
            transformed_data = np.matmul(spat_comp[ounit][:, :rank].T, shifted_data)
            temp_temp.append(0.)
            for r in range(rank):
                temp_temp[unit][ounit] += np.convolve(
                    transformed_data[r], temp_comp[ounit][r, ::-1])
                    
    return (temp_temp)

# def compute_temp_temp_svd_shifted(rank, spike_size, n_unit, viscs, 
                                  # align_shifts, aligned_temp, spat_comp,
                                  # temp_comp):

    # temp_temp = []
    # comb_shift_min = []
    # for i in range(n_unit):
        # temp_temp.append([])
        # comb_shift_min.append([])
        # for j in range(n_unit):
            # temp_temp[i].append(0.)
            # comb_shift_min[i].append(0.)
    # #temp_temp = [[0. for i in range(n_unit)] for j in range(n_unit)]
    # #comb_shift_min = [[0 for i in range(n_unit)] for j in range(n_unit)]
    
    # #spike_size = 61

    # for unit_i in tqdm(range(n_unit)):
        # for unit_j in range(n_unit):
            # # Check overlaps
            # overlap, intersect_ix_i, intersect_ix_j = np.intersect1d(
                # np.where(viscs[:, unit_i])[0],
                # np.where(viscs[:, unit_j])[0],
                # assume_unique=True, return_indices=True)
            # overlap_size = len(overlap)
            # if overlap_size == 0:
                # # No overlap between two units, therefore convolution is zero
                # continue
            # elif unit_i > unit_j:
                # # temp temp of pairs of units are symmetric
                # # If one is computed, the other is readily available
                # temp_temp[unit_i][unit_j] = temp_temp[unit_j][unit_i][::-1]
                # # Go to next
                # continue

            # # Negate shifts from template j and apply shifts from template i
            # combined_shifts = align_shifts[unit_i][intersect_ix_i].max() - align_shifts[unit_i][intersect_ix_i]
            # combined_shifts += align_shifts[unit_j][intersect_ix_j]
            # comb_shift_min[unit_i][unit_j] = [combined_shifts.min(), align_shifts[unit_i][intersect_ix_i].max(), align_shifts[unit_j][intersect_ix_j].max()]
            # combined_shifts -= combined_shifts.min()

            # temp_adj = np.zeros([overlap_size, spike_size + combined_shifts.max()])
            # ix1 = np.tile(np.arange(overlap_size)[:, None], spike_size)
            # ix2 = np.arange(spike_size) + combined_shifts[:, None]
            # temp_adj[ix1, ix2] = aligned_temp[unit_j][intersect_ix_j]

            # if overlap_size < rank + 1:
                # for i in range(overlap_size):
                    # temp_temp[unit_i][unit_j] += np.convolve(
                        # temp_adj[i], aligned_temp[unit_i][intersect_ix_i[i], ::-1])
            # else:
                # data_trans = np.matmul(
                    # spat_comp[unit_i][intersect_ix_i, :rank].T, temp_adj)
                # for r in range(rank):
                    # temp_temp[unit_i][unit_j] += np.convolve(
                        # data_trans[r], temp_comp[unit_i][r, ::-1])
                        
    # return (temp_temp, comb_shift_min, combined_shifts)


def parallel_conv_filter2(units, 
                          n_time,
                          up_up_map,
                          deconv_dir,
                          svd_dir,
                          chunk_id,
                          n_sec_chunk_gpu,
                          vis_chan,
                          unit_overlap,
                          approx_rank,
                          temporal,
                          singular,
                          spatial,
                          temporal_up):

    # loop over asigned units:
    conv_res_len = n_time * 2 - 1
    pairwise_conv_array = []
    for unit2 in units:
        #if unit2%100==0:
        #    print (" temp_temp: ", unit2)
        n_overlap = np.sum(unit_overlap[unit2, :])
        pairwise_conv = np.zeros([n_overlap, conv_res_len], dtype=np.float32)
        orig_unit = unit2 
        masked_temp = np.flipud(np.matmul(
                temporal_up[unit2] * singular[orig_unit][None, :],
                spatial[orig_unit, :, :]))

        for j, unit1 in enumerate(np.where(unit_overlap[unit2, :])[0]):
            u, s, vh = temporal[unit1], singular[unit1], spatial[unit1] 

            vis_chan_idx = vis_chan[:, unit1]
            mat_mul_res = np.matmul(
                    masked_temp[:, vis_chan_idx], vh[:approx_rank, vis_chan_idx].T)

            for i in range(approx_rank):
                pairwise_conv[j, :] += np.convolve(
                        mat_mul_res[:, i],
                        s[i] * u[:, i].flatten(), 'full')

        pairwise_conv_array.append(pairwise_conv)

    return pairwise_conv_array

def transform_template_parallel(template, knots=None, prepad=7, postpad=3, order=3):

    if knots is None:
        #knots = np.arange(len(template.data[0]) + prepad + postpad)
        knots = np.arange(template.shape[1] + prepad + postpad)
        #print ("template.shape[0]: ", template.shape[1])
    # loop over every channel?
    splines = [
        fit_spline_cpu(curve, knots=knots, prepad=prepad, postpad=postpad, order=order) 
        for curve in template
    ]
    coefficients = np.array([spline[1][prepad-1:-1*(postpad+1)] for spline in splines], dtype='float32')
    
    return coefficients
        
        
def fit_spline_cpu(curve, knots=None, prepad=0, postpad=0, order=3):
    if knots is None:
        knots = np.arange(len(curve) + prepad + postpad)
    return splrep(knots, np.pad(curve, (prepad, postpad), mode='symmetric'), k=order)


        
# # ****************************************************************************
# # ****************************************************************************
# # ****************************************************************************
                     
class deconvGPU(object):

    def __init__(self, CONFIG, fname_templates, out_dir):
        
        #
        self.out_dir = out_dir
        
        # initialize directory for saving
        self.seg_dir = os.path.join(self.out_dir,'segs')
        if not os.path.isdir(self.seg_dir):
            os.mkdir(self.seg_dir)
            
        self.svd_dir = os.path.join(self.out_dir,'svd')
        if not os.path.isdir(self.svd_dir):
            os.mkdir(self.svd_dir)

        self.temps_dir = os.path.join(self.out_dir,'template_updates')
        if not os.path.isdir(self.temps_dir):
            os.mkdir(self.temps_dir)

        # always copy the startng templates to initalize the process
        fname_out_temporary = os.path.join(self.temps_dir,'templates_0sec.npy')
        if os.path.exists(fname_out_temporary)==False:
            temps_temporary = np.load(fname_templates)
            np.save(fname_out_temporary, temps_temporary)


        # initalize parameters for 
        self.set_params(CONFIG, fname_templates, out_dir)

    def set_params(self, CONFIG, fname_templates, out_dir):

        # 
        self.CONFIG = CONFIG

        # set root directory for loading:
        #self.root_dir = self.CONFIG.data.root_folder
        
        #
        self.out_dir = out_dir

        #
        self.fname_templates = fname_templates

        # load geometry
        self.geom = np.loadtxt(os.path.join(CONFIG.data.root_folder, CONFIG.data.geometry))
        
        # Cat: TODO: Load sample rate from disk
        self.sample_rate = self.CONFIG.recordings.sampling_rate
        
        # Cat: TODO: unclear if this is always the case
        self.n_time = self.CONFIG.spike_size
        
        # set length of lockout window
        # Cat: TODO: unclear if this is always correct
        self.lockout_window = self.n_time-1
        #self.lockout_window = 200
        #self.lockout_window = 100

        # 
        self.fill_value = 1E4
        
        # objective function scaling for the template term;
        self.tempScaling = 2.0

        # refractory period
        # Cat: TODO: move to config
        refrac_ms = 1
        self.refractory = int(self.CONFIG.recordings.sampling_rate/1000*refrac_ms)

        # length of conv filter
        #self.n_times = torch.arange(-self.lockout_window,self.n_time,1).long().cuda()

        # set max deconv threshold
        self.deconv_thresh = self.CONFIG.deconvolution.threshold

        # svd compression flag
        #self.svd_flag = True
        
        # make a 3 point array to be used in quadratic fit below
        #self.peak_pts = torch.arange(-1,+2).cuda()
        
        
    def initialize(self):

        # length of conv filter
        #self.n_times = torch.arange(-self.lockout_window,self.n_time,1).long().cuda()
        
        # make a 3 point array to be used in quadratic fit below
        self.peak_pts = torch.arange(-1,+2).cuda()
        
        # load templates and svd componenets
        self.load_temps()
                
        # align templates
        self.align_templates2()
        
        # compute svd on shifted templates:
        self.temp_temp_shifted()

        # compute norms and move data to GPU
        self.data_to_gpu_shifted_svd()

        # OLDER FUNCTIONS
        # find vis-chans
        #self.visible_chans()
        
        # find vis-units
        #self.template_overlaps()
        
        # set all nonvisible channels to 0. to help with SVD
        #self.spatially_mask_templates()
           
        # compute template convolutions
        #if self.svd_flag:
        #    self.compress_templates()
        #    self.compute_temp_temp_svd()

        # # Cat: TODO we should dissable all non-SVD options?!
        # else:
            # self.compute_temp_temp()

        # move data to gpu
        #self.data_to_gpu()
                 
        # BSPLINE COMPUTATIONS
                
        # initialize Ian's objects
        self.initialize_cpp()

        # conver templates to bpslines
        self.templates_to_bsplines()
        
        # large units for height fit
        if self.fit_height:
            self.large_units = np.where(self.ptps > self.fit_height_ptp)[0]
            self.large_units = torch.from_numpy(self.large_units).cuda()

    def run(self, chunk_id):
        
        #
        #self.fname_templates = fname_templates

        # rest lists for each segment of time
        self.offset_array = []
        self.spike_array = []
        self.neuron_array = []
        self.shift_list = []
        self.height_list = []
        self.add_spike_temps = []
        self.add_spike_times = []
        
        # save iteration 
        self.chunk_id = chunk_id
        
        # intialize run only when templates are updated;
        #self.initialize()        

        # load raw data and templates
        self.load_data(chunk_id)
        
        # make objective function
        #self.make_objective()
        self.make_objective_shifted_svd()
               
        # run 
        self.subtraction_step()
                
        # empty cache
        torch.cuda.empty_cache()


    def initialize_cpp(self):

        # make a list of pairwise batched temp_temp and their vis_units
        # Cat: TODO: this isn't really required any longer;
        #            - the only thing required from this in parallel bsplines function is
        #              self.temp_temp_cpp.indices - is self.vis_units
        #              
        self.temp_temp_cpp = deconv.BatchedTemplates([deconv.Template(nzData, nzInd) for nzData, nzInd in zip(self.temp_temp, self.vis_units)])
        #self.temp_temp_cpp = deconv.BatchedTemplates([deconv.Template(nzData, nzInd) for nzData, nzInd in zip(self.temp_temp, self.unit_unit_overlap)])
      
        
    def templates_to_bsplines(self):

        print ("  making template bsplines")
        fname = os.path.join(self.svd_dir,'bsplines_'+
                  str((self.chunk_id+1)*self.CONFIG.resources.n_sec_chunk_gpu_deconv) + '.npy')
        
        if os.path.exists(fname)==False:
            
            # Cat; TODO: don't need to pass tensor/cuda templates to parallel function
            #            - can just pass the raw cpu templates
            # multi-core bsplines
            if self.CONFIG.resources.multi_processing:
                templates_cpu = []
                for template in self.temp_temp_cpp:
                    templates_cpu.append(template.data.cpu().numpy())

                coefficients = parmap.map(transform_template_parallel, templates_cpu, 
                                            processes=self.CONFIG.resources.n_processors,
                                            pm_pbar=False)
            # single core
            else:
                coefficients = []
                for template in self.temp_temp_cpp:
                    template_cpu = template.data.cpu().numpy()
                    coefficients.append(transform_template_parallel(template_cpu))
            
            np.save(fname, coefficients)
        else:
            print ("  ... loading coefficients from disk")
            coefficients = np.load(fname, allow_pickle=True)

        # print (" fname: ", fname)
        # print (" recomputed coefficients: ", coefficients[0].shape)
        # print (" recomputed coefficients: ", coefficients[0])

        # coefficients = np.load(fname)
        # print (" loaded coefficients: ", coefficients[0].shape)
        # print (" loaded coefficients: ", coefficients[0])
        
        
        print ("  ... moving coefficients to cuda objects")
        coefficients_cuda = []
        for p in range(len(coefficients)):
            coefficients_cuda.append(deconv.Template(torch.from_numpy(coefficients[p]).cuda(), self.temp_temp_cpp[p].indices))
            # print ('self.temp_temp_cpp[p].indices: ', self.temp_temp_cpp[p].indices)
            # print ("self.vis_units: ", self.vis_units[p])
            # coefficients_cuda.append(deconv.Template(torch.from_numpy(coefficients[p]).cuda(), self.vis_units[p]))
        
        
        self.coefficients = deconv.BatchedTemplates(coefficients_cuda)

        del self.temp_temp
        del self.temp_temp_cpp
        del coefficients_cuda
        del coefficients
        torch.cuda.empty_cache()
            
     
    # def compute_temp_temp_svd(self):

        # print ("  making temp_temp filters (todo: move to GPU)")
        # fname = os.path.join(self.svd_dir,'temp_temp_sparse_svd_'+
                  # str((self.chunk_id+1)*self.CONFIG.resources.n_sec_chunk_gpu_deconv) + '.npy')

        # if os.path.exists(fname)==False:

            # # recompute vis chans and vis units 
            # # Cat: TODO Fix this so dont' have to repeat it here
            # self.up_up_map = None
            # deconv_dir = ''

            # # 
            # units = np.arange(self.temps.shape[2])
            
            # # Cat: TODO: work on multi CPU and GPU versions
            # if self.CONFIG.resources.multi_processing:
                # units_split = np.array_split(units, self.CONFIG.resources.n_processors)
                # self.temp_temp = parmap.map(parallel_conv_filter2, 
                                              # units_split, 
                                              # self.n_time,
                                              # self.up_up_map,
                                              # deconv_dir,
                                              # self.svd_dir,
                                              # self.chunk_id,
                                              # self.CONFIG.resources.n_sec_chunk_gpu_deconv,
                                              # self.vis_chan,
                                              # self.unit_overlap,
                                              # self.RANK,
                                              # self.temporal,
                                              # self.singular,
                                              # self.spatial,
                                              # self.temporal_up,
                                              # processes=self.CONFIG.resources.n_processors,
                                              # pm_pbar=False)
            # else:
                # units_split = np.array_split(units, self.CONFIG.resources.n_processors)
                # self.temp_temp = []
                # for units_ in units_split:
                    # self.temp_temp.append(parallel_conv_filter2(units_, 
                                              # self.n_time,
                                              # self.up_up_map,
                                              # deconv_dir,
                                              # self.svd_dir,
                                              # self.chunk_id,
                                              # self.CONFIG.resources.n_sec_chunk_gpu_deconv,
                                              # self.vis_chan,
                                              # self.unit_overlap,
                                              # self.RANK,
                                              # self.temporal,
                                              # self.singular,
                                              # self.spatial,
                                              # self.temporal_up))
                                              
            # # gather results
            # temp_temp_local = [None]*units.shape[0]
            # for ctr1, u1 in enumerate(units_split):
                # for ctr2, u2 in enumerate(u1):
                    # temp_temp_local[units_split[ctr1][ctr2]] = self.temp_temp[ctr1][ctr2]

            # # transfer list to GPU
            # self.temp_temp = []
            # for k in range(len(temp_temp_local)):
                # self.temp_temp.append(torch.from_numpy(temp_temp_local[k]).float().cuda())

            # # save GPU list as numpy object
            # np.save(fname, self.temp_temp)
                                 
        # else:
            # print (".... loading temp-temp from disk")
            # self.temp_temp = np.load(fname, allow_pickle=True)
               
    
    # def visible_chans(self):
        # #if self.vis_chan is None:
        # a = np.max(self.temps, axis=1) - np.min(self.temps, 1)
        
        # # Cat: TODO: must read visible channel/unit threshold from file;
        # self.vis_chan = a > self.vis_chan_thresh

        # a_self = self.temps.ptp(1).argmax(0)
        # for k in range(a_self.shape[0]):
            # self.vis_chan[a_self[k],k]=True

        # # fname = os.path.join(self.svd_dir,'vis_chans.npy')
        # # np.save(fname, self.vis_chan)


    # def template_overlaps(self):
        # """Find pairwise units that have overlap between."""
        # vis = self.vis_chan.T
        # self.unit_overlap = np.sum(
            # np.logical_and(vis[:, None, :], vis[None, :, :]), axis=2)
        # self.unit_overlap = self.unit_overlap > 0
        # self.vis_units = self.unit_overlap

        # # # save vis_units for residual recomputation and other steps
        # # fname = os.path.join(self.svd_dir,'vis_units_'+
                      # # str((self.chunk_id+1)*self.CONFIG.resources.n_sec_chunk_gpu_deconv) + '_1.npy')
        # # np.save(fname, self.vis_units)
                        
                        
    # def spatially_mask_templates(self):
        # """Spatially mask templates so that non visible channels are zero."""
        # for k in range(self.temps.shape[2]):
            # zero_chans = np.where(self.vis_chan[:,k]==0)[0]
            # self.temps[zero_chans,:,k]=0.


    def load_temps(self):
        ''' Load templates and set parameters
        '''
        
        # load templates
        #print ("Loading template: ", self.fname_templates)
        self.temps = np.load(self.fname_templates, allow_pickle=True).transpose(2,1,0)
        self.N_CHAN, self.STIME, self.K = self.temps.shape
        #print ("   LOADED TEMPS: ", self.temps.shape)
        # this transfer to GPU is not required any longer
        # self.temps_gpu = torch.from_numpy(self.temps).float().cuda()
        
        # compute max chans for data
        #print ("Making max chans, ptps, etc. for iteration 0: ", self.temps.shape)
        self.max_chans = self.temps.ptp(1).argmax(0)

        # compute ptps for data
        # ptps for each template
        self.ptps_all_chans = self.temps.ptp(1)
        self.ptps = self.ptps_all_chans.max(0)

        if self.update_templates:
            # Robust PTP location computation; find argmax and argmin of
            self.ptp_locs = []
            for k in range(self.temps.shape[2]):
                max_temp = self.temps[self.max_chans[k],:,k].argmax(0)
                min_temp = self.temps[self.max_chans[k],:,k].argmin(0)
                self.ptp_locs.append([max_temp,min_temp])

            # find max/min ptp arguments for all channels
            max_temp = self.temps.argmax(1).T
            min_temp = self.temps.argmin(1).T

            # get relative minimum and maximum locations for each unit and each channel
            self.min_max_loc = np.concatenate(
                (min_temp[:, None], max_temp[:, None]),
                axis=1).astype('int32')

            self.max_temp_array = np.zeros((self.temps.shape[2],self.temps.shape[0]))
            self.min_temp_array = np.zeros((self.temps.shape[2],self.temps.shape[0]))
            for k in range(self.temps.shape[2]):
                for c in range(self.temps.shape[0]):
                    self.max_temp_array[k,c] = self.temps[c,max_temp[k,c],k]
                    self.min_temp_array[k,c] = self.temps[c,min_temp[k,c],k]

            # also the threhold for triage
            # get a threshold for each unit and each channel
            thresholds = self.ptps_all_chans*self.max_percent_update
            thresholds[thresholds < self.max_diff_update] = self.max_diff_update
            self.ptps_threshold = thresholds

    def align_templates2(self):

        #rank = 5
        #n_unit, n_channel = temp.shape[:2]
        
        temp = self.temps.transpose(2,0,1)
        print ("temp shape: ", temp.shape)
        #spike_size = 61
        rank  = self.RANK
        geom = self.geom
        n_unit, n_channel, spike_size = temp.shape#[:2]

        temp_pad = np.zeros((temp.shape[0],temp.shape[1],20),'float32')
        temp = np.concatenate((temp_pad, temp),2)
        temp = np.concatenate((temp, temp_pad),2)

        print ("templates shape: ", temp.shape, "[n_units, n_chan, n_time]")
        print ("   Padding 3ms temps with zeros: (TODO: reload 5ms templates)")
        print ("   Using 20 timestep jitter: (TODO: increase to 50 once 5ms templates are being loaded)")
        
        # Maked and aligned and reconstructed templates.
        aligned_temp = np.zeros([n_unit, n_channel, spike_size], dtype=np.float32)
        align_shifts = np.zeros([n_unit, n_channel], dtype=np.int32)
        spat_comp = np.zeros([n_unit, n_channel, rank], dtype=np.float32)
        temp_comp = np.zeros([n_unit, rank, spike_size], dtype=np.float32)

        viscs = continuous_visible_channels(temp, geom)
        # Computes if units are spatially overlapping
        unit_unit_overlap = np.logical_and(viscs[None], viscs[:, None]).sum(-1) > 0
        print ("raw unit_unit_overlap: ", unit_unit_overlap.shape)
        print ("   Note: inverting the temporal filters in place at computation time...")
        for unit in tqdm(range(n_unit)):
            # get vis channels only
            t = temp[unit, viscs[unit], :]
            # Instead of having 1 template with c channels
            # treat it as c teplates with 1 channels
            tobj = WaveForms(t[:, None])
            main_c = t.ptp(1).argmax()
            align, shifts_ = tobj.align(
                ref_wave_form=t[main_c][None], jitter=20, return_shifts=True)
            align = align[:, 0]
            # remove offset from shifts so that minimum is 0
            vis_chans = np.where(viscs[unit])[0]
            align_shifts[unit, vis_chans] = shifts_ - shifts_.min()
            # use reconstructed version of temp lates
            if len(align) <= rank:
                # The matrix rank is lower. Just pass
                # identity spatial component and the signal itself
                mat_rank = len(align)
                spat_comp[unit, vis_chans, :mat_rank] = np.eye(mat_rank)
                temp_comp[unit, :mat_rank] = align
                aligned_temp[unit, vis_chans] = align
                continue
            u, h, v = np.linalg.svd(align)
            spat_comp[unit, vis_chans] = u[:, :rank] * h[:rank]
            temp_comp[unit] = v[:rank]
            #temp_comp[unit] = v[:rank][:, ::-1]
            #print (temp_comp[unit].shape)
            # Reconstructed version of the unit
            aligned_temp[unit, vis_chans] = np.matmul(u[:, :rank] * h[:rank], v[:rank])
    
        # data saved in object
        self.spat_comp = spat_comp
        self.temp_comp = temp_comp
        self.aligned_temp = aligned_temp
        self.viscs = viscs
        self.align_shifts = align_shifts
        self.aligned_temp = aligned_temp
        self.unit_unit_overlap = unit_unit_overlap
   
    
    def temp_temp_shifted(self):
        
        fname = os.path.join(self.svd_dir,'temp_temp_sparse_svd_'+
                  str((self.chunk_id+1)*self.CONFIG.resources.n_sec_chunk_gpu_deconv) + '.npy')
        
        if os.path.exists(fname)==False:
            print ("   computing temp_temp shifted (TODO: parallelize)")
            temp_temp = compute_temp_temp_svd_shifted2(
                                                self.RANK, self.STIME, self.K, self.viscs, 
                                                self.align_shifts, self.aligned_temp,
                                                self.spat_comp, self.temp_comp,
                                                self.unit_unit_overlap)
                                                
            print ("   computing zero padding...")
            # Zero padding and aligning temp temp
            n_unit = self.K
            
            temp_temp_len = np.zeros([n_unit, n_unit], dtype=np.int32)
            temp_temp_argmax = np.zeros(n_unit, dtype=np.int32)
            for i in range(n_unit):
                temp_temp_argmax[i] = temp_temp[i][i].argmax()
                for j in range(n_unit):
                    if isinstance(temp_temp[i][j], np.ndarray):
                        temp_temp_len[i, j] = len(temp_temp[i][j])

            max_len = temp_temp_len.max()
            # (IMPORTANT): this variable is very important, later when you find
            # peaks, the time of each peak has to be subtracted by this value
            self.global_argmax = temp_temp_argmax.max()
            # Shift all temp_temps so that the peaks are aligned
            shifts_ = self.global_argmax  - temp_temp_argmax
            zero_padded_temp_temp = np.zeros([n_unit, n_unit, max_len])
            for i in range(n_unit):
                u_shift = shifts_[i]
                for j in range(n_unit):
                    if isinstance(temp_temp[i][j], np.ndarray):
                        #temp temp exists
                        zero_padded_temp_temp[i, j, u_shift:u_shift+temp_temp_len[i, j]] = temp_temp[i][j]

            #self.temp_temp = zero_padded_temp_temp
        
            print ("... reversing temp_temp function...")
            #print ("   zero_padded_temp_temp: ", zero_padded_temp_temp.shape)
            zero_padded_temp_temp = zero_padded_temp_temp.transpose([1, 0, 2])

            # transfer list to GPU
            self.temp_temp = []
            for k in range(len(zero_padded_temp_temp)):
                self.temp_temp.append(torch.from_numpy(zero_padded_temp_temp[k]).float().cuda())
                #self.temp_temp.append(torch.from_numpy(zero_padded_temp_temp[k][:, 45:-44]).float().cuda())
            
            # save GPU list as numpy object
            np.save(fname, self.temp_temp)
                                 
        else:
            print (".... loading temp-temp from disk")
            self.temp_temp = np.load(fname, allow_pickle=True)
            
        print ("len: self.temptemp gpu: ", len(self.temp_temp))

        
        # save GPU list as numpy object
        #np.save(fname, self.temp_temp)                                
                                                                  
        #self.comb_shift_min = comb_shift_min
        #self.combined_shifts = combined_shifts
    
        
    def compress_templates(self):
        """Compresses the templates using SVD and upsample temporal compoents."""

        print ("   making SVD data... (todo: move to GPU)")
        ## compute everythign using SVD
        # Cat: TODO: is this necessary?  
        #      can just overwrite all the svd stuff every template update
        fname = os.path.join(self.svd_dir,'templates_svd_'+
                      str((self.chunk_id+1)*self.CONFIG.resources.n_sec_chunk_gpu_deconv) + '.npz')

            
        if os.path.exists(fname)==False:
            #print ("self.temps: ", self.temps.shape)
            #np.save("/home/cat/temps.npy", self.temps)
            
            self.temporal, self.singular, self.spatial = np.linalg.svd(
                np.transpose(np.flipud(np.transpose(self.temps,(1,0,2))),(2, 0, 1)))
            
            # Keep only the strongest components
            self.temporal = self.temporal[:, :, :self.RANK]
            self.singular = self.singular[:, :self.RANK]
            self.spatial = self.spatial[:, :self.RANK, :]

            # Upsample the temporal components of the SVD
            # in effect, upsampling the reconstruction of the
            # templates.
            
            # Cat: TODO: No upsampling is needed; to remove temporal_up from code
            self.temporal_up = self.temporal
           
            np.savez(fname, temporal=self.temporal, singular=self.singular, 
                     spatial=self.spatial, temporal_up=self.temporal_up)
            
        else:
            print ("   loading SVD from disk...") 
            # load data for for temp_temp computation
            data = np.load(fname, allow_pickle=True)
            self.temporal_up = data['temporal_up']
            self.temporal = data['temporal']
            self.singular = data['singular']
            self.spatial = data['spatial']                                     
            
    
    def data_to_gpu_shifted_svd(self):
        
        # hoosh' new norms.
        norm = np.square(self.aligned_temp).sum(-1).sum(-1)

        #move data to gpu
        self.norms = torch.from_numpy(norm).float().cuda()
        
        #self.vis_units = torch.FloatTensor(self.unit_unit_overlap).long().cuda()
        #self.vis_units = torch.LongTensor(self.unit_unit_overlap).long().cuda()
        self.vis_units = torch.BoolTensor(self.unit_unit_overlap).long().cuda()
        
        print ("self.vis_units: ", self.vis_units.shape)

        # Old method to track drift + svd compression
        # Cat: TODO: delete/remove
        # if False:
            # if self.update_templates:
                # self.ptps_all_chans = torch.from_numpy(self.ptps_all_chans).float().cuda()
                # self.min_max_loc = torch.from_numpy(self.min_max_loc).long().cuda()
                # self.ptps_threshold = torch.from_numpy(self.ptps_threshold).float().cuda()

            # # move svd items to gpu
            # if self.svd_flag:
                # self.n_rows = self.temps.shape[2] * self.RANK
                # self.spatial_gpu = torch.from_numpy(self.spatial.reshape([self.n_rows, -1])).float().cuda()
                # self.singular_gpu = torch.from_numpy(self.singular.reshape([-1, 1])).float().cuda()
                # self.temporal_gpu = np.flip(self.temporal,1)
                # self.filters_gpu = torch.from_numpy(self.temporal_gpu.transpose([0, 2, 1]).reshape([self.n_rows, -1])).float().cuda()[None,None]
          
            
    def load_data(self, chunk_id):
        '''  Function to load raw data 
        '''
        
        try:
            del self.data 
            torch.cuda.empty_cache()
        except:
            pass
            
        start = dt.datetime.now().timestamp()

        # read dat using reader class
        self.data_cpu = self.reader.read_data_batch(
            chunk_id, add_buffer=True).T
        
        self.offset = self.reader.idx_list[chunk_id, 0] - self.reader.buffer
        self.data = torch.from_numpy(self.data_cpu).float().cuda()

        #print (" self.data: ", self.data.shape, ", size: ", sys.getsizeof(self.data.storage()))

        if self.verbose:

            print ("Input size: ",self.data.shape, int(sys.getsizeof(self.data)), "MB")
            print ("Load raw data (run every chunk): ", np.round(dt.datetime.now().timestamp()-start,2),"sec")
            print ("---------------------------------------")
            print ('')
                

    def make_objective_shifted_svd(self):
        start = dt.datetime.now().timestamp()
        if self.verbose:
            print ("Computing objective ")       
       
        #obj_function = np.zeros([NUNIT, data.shape[1] + 61 - 1])
        self.obj_gpu = torch.zeros((self.K, self.data.shape[1]+self.STIME-1),
                                    dtype=torch.float).cuda()
                                    
        spat_comp_gpu = torch.from_numpy(self.spat_comp.transpose([0,2,1])).float().cuda()
        #print ("self.temp_comp: ", self.temp_comp.shape)
        # transfer temp_comp and reverse the time 
        print (" check if need to inverse (NOTE: Already inverted at computation time")
        #temp_comp_gpu = torch.from_numpy(self.temp_comp[:,:,::-1]).float().cuda()        
        temp_comp_gpu = torch.from_numpy(self.temp_comp).float().cuda()        
        
        if False:
            np.save('/media/cat/2TB/liam/49channels/data1_allset_shifted_svd/tmp/block_2/deconv/data.npy', self.data.cpu().data.numpy())
            np.save('/media/cat/2TB/liam/49channels/data1_allset_shifted_svd/tmp/block_2/deconv/align_shifts.npy', self.align_shifts)
            np.save('/media/cat/2TB/liam/49channels/data1_allset_shifted_svd/tmp/block_2/deconv/spat_comp.npy', self.spat_comp)
            np.save('/media/cat/2TB/liam/49channels/data1_allset_shifted_svd/tmp/block_2/deconv/temp_comp.npy',self.temp_comp)
            np.save('/media/cat/2TB/liam/49channels/data1_allset_shifted_svd/tmp/block_2/deconv/norms.npy', self.norms.cpu().data.numpy())
        
        for unit in tqdm(range(self.temps.shape[2])):
            # Do the shifts that was required for aligning template
            shifts = reverse_shifts(self.align_shifts[unit])
            #print ("shifts: ", shifts.shape)
            
            # this needs to be taken out of this loop and done single time
            shifts_gpu = torch.from_numpy(shifts).long().cuda()
            
            # CUDA code
            rowshift.forward(self.data, shifts_gpu)

            # multiplication step
            mm = torch.mm(spat_comp_gpu[unit], self.data)
                    
            # Sum over Rank
            for i in range(self.temp_comp.shape[1]):
                temp_out = nn.functional.conv1d(mm[i][None,None,:],
                                               temp_comp_gpu[unit,i][None,None,:], 
                                               padding = self.STIME-1)[0][0]
                #print ("Convolution result: ", temp_out.shape)
                self.obj_gpu[unit,:]+=temp_out
                                        
            # Undo the shifts that we did earlier
            #in_place_roll_shift(data, -shifts)
            rowshift.backward(self.data, shifts_gpu)

        #obj_function = 2 * obj_function - temp_norms[:NUNIT][:, None]  #drop NUNIT;  # drop additional dimensions;
        print ("obj_function: ", self.obj_gpu.shape)
        print ("self.norms: ", self.norms.shape)
        self.obj_gpu = 2 * self.obj_gpu - self.norms[:,None]  #drop NUNIT;  # drop additional dimensions;

        del mm
        del temp_out
        torch.cuda.empty_cache()
        torch.cuda.synchronize()
        

    def save_spikes(self):
        # # save offset of chunk time; spiketimes and neuron ids
        self.offset_array.append(self.offset)
        self.spike_array.append(self.spike_times[:,0])
        self.neuron_array.append(self.neuron_ids[:,0])
        self.shift_list.append(self.xshifts)
        self.height_list.append(self.heights)
                
                
    def subtraction_step(self):
        
        start = dt.datetime.now().timestamp()

        # initialize arrays
        self.n_iter=0
        
        # tracks the number of addition steps during SCD
        self.add_iteration_counter=0
        self.save_spike_flag=True
        
        for k in range(self.max_iter):
            if False:
                #if k < 30:
                np.save(self.out_dir+'/objectives/chunk'+
                        str(self.chunk_id)+"_iter_"+str(self.n_iter)+'.npy', self.obj_gpu.cpu().data.numpy())
                
                # if k>0:
                    # np.save(self.out_dir+'/objectives/spike_times_'+
                            # str(self.chunk_id)+"_iter_"+str(self.n_iter)+'.npy', self.spike_times.squeeze().cpu().data.numpy())
                    # np.save(self.out_dir+'/objectives/spike_ids_'+
                            # str(self.chunk_id)+"_iter_"+str(self.n_iter)+'.npy', self.neuron_ids.squeeze().cpu().data.numpy())
        
                if k>1:
                    quit()
 
            # **********************************************
            # *********** SCD ADDITION STEP ****************
            # **********************************************
            # Note; this step needs to be carried out before peak search + subtraction to make logic simpler
            if self.scd:
                # # old scd method where every 10 iterations, there's a random addition step of spikes from up to 5 prev iterations
                # if False:
                    # if (k%2==10) and (k>0):
                        # if False:
                            # # add up to spikes from up to 5 previous iterations
                            # idx_iter = np.random.choice(np.arange(min(len(self.spike_array),self.scd_max_iteration)),
                                                        # size=min(self.n_iter,self.scd_n_additions),
                                                        # replace=False)
                            # for idx_ in idx_iter: 
                                # self.add_cpp(idx_)
                    
                # # newer scd method: inject spikes from top 10 iterations and redeconvolve 
                # updated exhuastive SCD over top 10 deconv iterations
                # This conditional checks that loop is in an iteration that should be an addition step
                if ((k%(self.n_scd_iterations*2))>=self.n_scd_iterations and \
                    (k%(self.n_scd_iterations*2))<(self.n_scd_iterations*2)) and \
                    (k<self.n_scd_stages*self.n_scd_iterations*2):

                    # turn off saving spikes flag so that new spikes aren't appended
                    #       - instead they are inserted back into the original lcoation see conditional below
                    self.save_spike_flag=False

                    self.tempScaling_array = self.shift_list[self.add_iteration_counter]*0.0 + 2.0

                    
                    # add spikes back in; then run forward deconv below
                    self.add_cpp_allspikes()                

                  
            # **********************************************
            # **************** FIND PEAKS ******************
            # **********************************************
            search_time = self.find_peaks()

            if self.spike_times.shape[0]==0:
                if self.verbose:
                    print ("... no detected spikes, exiting...")
                break                
            
            # **********************************************
            # **************** FIND SHIFTS *****************
            # **********************************************
            shift_time = self.find_shifts()
            
            # **********************************************
            # **************** FIT HEIGHT *****************
            # **********************************************
            fit_height_time = self.compute_height()

            # **********************************************
            # **************** SUBTRACTION STEP ************
            # **********************************************
            total_time = self.subtract_cpp()           
           

            # **********************************************
            # ************** SCD FINISHING UP **************
            # **********************************************
            # Note; after adding spikes back in - and running peak discover+subtraction
            #       - need to reassign rediscovered spikes back to the original list where they came from
            if self.scd:
                #if ((k>=10) and (k<=19)) or ((k>=30) and (k<40)) or ((k>=50) and (k<60)):
                if ((k%(self.n_scd_iterations*2))>=self.n_scd_iterations and \
                    (k%(self.n_scd_iterations*2))<(self.n_scd_iterations*2)) and \
                    (k<self.n_scd_stages*self.n_scd_iterations*2):
                        
                    # insert spikes back to original iteration - no need to add append them as a new list
                    self.spike_array[self.add_iteration_counter] = self.spike_times[:,0]
                    self.neuron_array[self.add_iteration_counter] = self.neuron_ids[:,0]
                    self.shift_list[self.add_iteration_counter] = self.xshifts
                    self.height_list[self.add_iteration_counter] = self.heights
                    self.add_iteration_counter+=1

            # reset regular spike save after finishing SCD (note: this should be done after final addition/subtraction
            #       gets added to the list of spikes;
            #       otherwise the spieks are saved twice
            if (k%(self.n_scd_iterations*2)==0):
                self.save_spike_flag=True
                self.add_iteration_counter=0

            # **********************************************
            # ************** POST PROCESSING ***************
            # **********************************************
            # save spiketimes only when doing deconv outside SCD loop
            if self.save_spike_flag:
                self.save_spikes()
                                
            # increase index
            self.n_iter+=1
        
            # post-processing steps;

            # np.savez('/media/cat/4TBSSD/liam/512channels/2005-04-26-0/data002/tmp/final_deconv/icd/'+
                    # str(k)+'.npz',
                    # k = k,
                    # save_spike_flag = self.save_spike_flag,
                    # spike_array = self.spike_array,
                    # neuron_array = self.neuron_array,
                    # shift_list = self.shift_list
                    # )
            
        
        #rint ("# of iterations; ", k)
        #quit()
        if self.verbose:
            print ("Total subtraction step: ", np.round(dt.datetime.now().timestamp()-start,3))
        
        #quit()
        #np.save('/home/cat/saved_array.npy', self.saved_gpu_array)
        
    def find_shifts(self):
        '''  Function that fits quadratic to 3 points centred on each peak of obj_func 
        '''
        
        start1 = dt.datetime.now().timestamp()
        #print (self.neuron_ids.shape, self.spike_times.shape)
        if self.neuron_ids.shape[0]>1:
            idx_tripler = (self.neuron_ids, self.spike_times.squeeze()[:,None]+self.peak_pts)
        else:
            idx_tripler = (self.neuron_ids, self.spike_times+self.peak_pts)
        
       # print ("idx tripler: ", idx_tripler)
        self.threePts = self.obj_gpu[idx_tripler]
        #np.save('/home/cat/trips.npy', self.threePts.cpu().data.numpy())
        self.shift_from_quad_fit_3pts_flat_equidistant_constants(self.threePts.transpose(0,1))

        return (dt.datetime.now().timestamp()- start1)

    # compute shift for subtraction in objective function space
    def shift_from_quad_fit_3pts_flat_equidistant_constants(self, pts):
        ''' find x-shift after fitting quadratic to 3 points
            Input: [n_peaks, 3] which are values of three points centred on obj_func peak
            Assumes: equidistant spacing between sample times (i.e. the x-values are hardcoded below)
        '''

        self.xshifts = ((((pts[1]-pts[2])*(-1)-(pts[0]-pts[1])*(-3))/2)/
                  (-2*((pts[0]-pts[1])-(((pts[1]-pts[2])*(-1)-(pts[0]-pts[1])*(-3))/(2)))))-1        

    def compute_height(self):
        '''  Function that fits quadratic to 3 points centred on each peak of obj_func 
        '''
        
        start1 = dt.datetime.now().timestamp()

        if self.fit_height:
            # get peak value
            peak_vals = self.quad_interp_3pt(self.threePts.transpose(1,0), self.xshifts)

            # height
            height = 0.5*(peak_vals/self.norm[self.neuron_ids[:,0], 0] + 1)
            height[height < 1 - self.max_height_diff] = 1 - self.max_height_diff
            height[height > 1 + self.max_height_diff] = 1 + self.max_height_diff
            
            idx_small_ = ~torch.any(self.neuron_ids == self.large_units[None],1)
            height[idx_small_] = 1
            
            self.heights = height
            
        else:
            self.heights = torch.ones(len(self.xshifts)).cuda()

        return (dt.datetime.now().timestamp()- start1)


    def quad_interp_3pt(self, vals, shift):
        a = 0.5*vals[0] + 0.5*vals[2] - vals[1]
        b = -0.5*vals[0] + 0.5*vals[2]
        c = vals[1]

        return a*shift**2 + b*shift + c

    def find_peaks(self):
        ''' Function to use torch.max and an algorithm to find peaks
        '''
        
        # Cat: TODO: make sure you can also deconvolve ends of data;
        #      currently using padding here...

        # First step: find peaks across entire energy function across dimension 0
        #       input: (n_neurons, n_times)
        #       output:  n_times (i.e. the max energy function value at each point in time)
        #       note: windows are padded
        start = dt.datetime.now().timestamp()
        torch.cuda.synchronize()
        self.gpu_max, self.neuron_ids = torch.max(self.obj_gpu, 0)
        torch.cuda.synchronize()
        end_max = dt.datetime.now().timestamp()-start

        #np.save('/media/cat/2TB/liam/49channels/data1_allset_shifted_svd/tmp/block_2/deconv/neuron_ids_'+
        #         str(self.n_iter)+'.npy', 
        #         self.neuron_ids.cpu().data.numpy())

        # Second step: find relative peaks across max function above for some lockout window
        #       input: n_times (i.e. values of energy at each point in time)
        #       output:  1D array = relative peaks across time for given lockout_window
        # Cat: TODO: this may atually crash if a spike is located in exactly the 1 time step bewteen buffer and 2 xlockout widnow
        window_maxima = torch.nn.functional.max_pool1d_with_indices(self.gpu_max.view(1,1,-1), 
                                                                    self.lockout_window, 1, 
                                                                    padding=self.lockout_window//2)[1].squeeze()
        candidates = window_maxima.unique()
        self.spike_times = candidates[(window_maxima[candidates]==candidates).nonzero()]
       
        # Third step: only deconvolve spikes where obj_function max > threshold
        # Cat: TODO: also, seems like threshold might get stuck on artifact peaks
        idx = torch.where(self.gpu_max[self.spike_times]>self.deconv_thresh, 
                          self.gpu_max[self.spike_times]*0+1, 
                          self.gpu_max[self.spike_times]*0)
        idx = torch.nonzero(idx)[:,0]
        self.spike_times = self.spike_times[idx]

        # Fourth step: exclude spikes that occur in lock_outwindow at start;
        # Cat: TODO: check that this is correct, 
        #      unclear whetther spikes on edge of window get correctly excluded
        #      Currently we lock out first ~ 60 timesteps (for 3ms wide waveforms)
        #       and last 120 timesteps
        #      obj function is usually rec_len + buffer*2 + lockout_window
        #                   e.g. 100000 + 200*2 + 60 = 100460
        
        # original window
        if False:
            idx1 = torch.where((self.spike_times>self.lockout_window) &
                           #(self.spike_times<(self.obj_gpu.shape[1]-self.lockout_window)),
                           (self.spike_times<(self.obj_gpu.shape[1]-self.lockout_window*2)),
                           self.spike_times*0+1, 
                           self.spike_times*0)
        else:
            idx1 = torch.where((self.spike_times>self.lockout_window) &
                                (self.spike_times<(self.obj_gpu.shape[1]-self.lockout_window)),
                                self.spike_times*0+1, 
                                self.spike_times*0)


        idx2 = torch.nonzero(idx1)[:,0]
        #self.spike_times = self.spike_times[idx2]
        self.spike_times = self.spike_times[idx2]
        #print ("self.spke_times: ", self.spike_times[-10:], self.obj_gpu.shape)

        # save only neuron ids for spikes to be deconvolved
        self.neuron_ids = self.neuron_ids[self.spike_times]
        np.save('/media/cat/2TB/liam/49channels/data1_allset_shifted_svd/tmp/block_2/deconv/neuron_ids_'+str(self.n_iter)+
                 '_postpeak.npy', 
                 self.neuron_ids.cpu().data.numpy())
        
        return (dt.datetime.now().timestamp()-start)         
    
        
    def subtract_cpp(self):
        
        start = dt.datetime.now().timestamp()
        
        torch.cuda.synchronize()
        
        if False:
            self.spike_times = self.spike_times[:1]
            self.neuron_ids = self.neuron_ids[:1]
            self.xshifts = self.xshifts[:1]
            self.heights = self.heights[:1]
            self.obj_gpu *=0.

        spike_times = self.spike_times.squeeze()-self.lockout_window
        spike_temps = self.neuron_ids.squeeze()
        
        # zero out shifts if superres shift turned off
        # Cat: TODO: remove this computation altogether if not required;
        #           will save some time.
        if self.superres_shift==False:
            self.xshifts = self.xshifts*0
        
        # if single spike, wrap it in list
        # Cat: TODO make this faster/pythonic

        if self.spike_times.size()[0]==1:
            spike_times = spike_times[None]
            spike_temps = spike_temps[None]

        # save metadata
        if self.n_iter<2:
            self.objectives_dir = os.path.join(self.out_dir,'objectives')
            if not os.path.isdir(self.objectives_dir):
                os.mkdir(self.objectives_dir)
                
            np.save(self.out_dir+'/objectives/spike_times_inside_'+ 
                               str(self.chunk_id)+"_iter_"+str(self.n_iter)+'.npy', 
                               spike_times.squeeze().cpu().data.numpy())
            np.save(self.out_dir+'/objectives/spike_ids_inside_'+
                               str(self.chunk_id)+"_iter_"+str(self.n_iter)+'.npy', 
                               spike_temps.squeeze().cpu().data.numpy())
            np.save(self.out_dir+'/objectives/obj_gpu_'+
                               str(self.chunk_id)+"_iter_"+str(self.n_iter)+'.npy', 
                               self.obj_gpu.cpu().data.numpy())
            np.save(self.out_dir+'/objectives/shifts_'+
                               str(self.chunk_id)+"_iter_"+str(self.n_iter)+'.npy', 
                               self.xshifts.cpu().data.numpy())
            np.save(self.out_dir+'/objectives/tempScaling_'+
                               str(self.chunk_id)+"_iter_"+str(self.n_iter)+'.npy', 
                               self.tempScaling)
            np.save(self.out_dir+'/objectives/heights_'+
                               str(self.chunk_id)+"_iter_"+str(self.n_iter)+'.npy', 
                               self.heights.cpu().data.numpy())
            for k in range(len(self.coefficients)):
                np.save(self.out_dir+'/objectives/coefficients_'+str(k)+"_"+
                               str(self.chunk_id)+"_iter_"+str(self.n_iter)+'.npy', 
                               self.coefficients[k].data.cpu().numpy())
        
        
            print ("spike_times: ", spike_times.shape)
            print ("spike_temps: ", spike_temps.shape)
            print ("self.obj_gpu: ", self.obj_gpu.shape)
            print ("self.xshifts: ", self.xshifts.shape)
            print ("self.tempScaling: ", self.tempScaling)
            print ("self.heights: ", self.heights.shape)
            print ("self.coefficients[k]: ", self.coefficients[k].data.shape)
        else:
            quit()
            
        #spike_times = spike_times -99
        deconv.subtract_splines(
                    self.obj_gpu,
                    spike_times,
                    self.xshifts,
                    spike_temps,
                    self.coefficients,
                    self.tempScaling*self.heights)
        
        if self.n_iter<2: 
            np.save(self.out_dir+'/objectives/obj_gpu_post_subtract_'+
                               str(self.chunk_id)+"_iter_"+str(self.n_iter)+'.npy', 
                               self.obj_gpu.cpu().data.numpy())
                               
        torch.cuda.synchronize()
        
        # also fill in self-convolution traces with low energy so the
        #   spikes cannot be detected again (i.e. enforcing refractoriness)
        # Cat: TODO: read from CONFIG
        
        if self.refractoriness:
            #print ("filling in timesteps: ", self.n_time)
            deconv.refrac_fill(energy=self.obj_gpu,
                                  spike_times=spike_times,
                                  spike_ids=spike_temps,
                                  #fill_length=self.n_time,  # variable fill length here
                                  #fill_offset=self.n_time//2,       # again giving flexibility as to where you want the fill to start/end (when combined with preceeding arg
                                  fill_length=self.refractory*2+1,  # variable fill length here
                                  fill_offset=self.n_time//2+self.refractory//2,       # again giving flexibility as to where you want the fill to start/end (when combined with preceeding arg
                                  fill_value=-self.fill_value)

        torch.cuda.synchronize()
            
        return (dt.datetime.now().timestamp()-start)
                     
    def sample_spikes(self,idx_iter):
        """
            OPTION 1: pick 10% (or more) of spikes from a particular iteration and add back in;
                      - advantage: don't need to worry about spike overlap;
                      - disadvantage: not as diverse as other injection steps
        
            OPTION 2: Same as OPTION 1 but also loop over a few other iterations           
            
            ------------------------ SLOWER OPTIONS -------------------------------------------            
        
            OPTION 3: pick 10% of spikes from first 10 iterations and preserve lockout
                      - advantage, more diverse 
                      - disadvantage: have to find fast algorithm to remove spikes too close together
            OPTION 4: pick 10% of spikes from any of the previous iterations and preserve lockout
                      - disadvantage: have to find fast algorithm to remove spikes too close together
        
        """
        
        # OPTION 1: pick a single previous iteration index; for now only use the first 10 iterations
        #           - one issue is that later iterations have few spikes and //10 yeilds 0 for example
        #           - to dsicuss 

        # pick 10 % random spikes from the selected iteration
        # Cat: TODO: maybe more pythonic ways (i.e. faster); but not clear
        idx_inject = np.random.choice(np.arange(self.spike_array[idx_iter].shape[0]), 
                                size = self.spike_array[idx_iter].shape[0]//2, replace=False)
        
        # Cat: TODO: this is a bit hacky way to stop picking from some iteration:
        if idx_inject.shape[0]<10:
            return ([], [], [], False)
            
        idx_not = np.delete(np.arange(self.spike_array[idx_iter].shape[0]),idx_inject)

        # pick spikes from those lists
        spike_times_list = self.spike_array[idx_iter][idx_inject]-self.lockout_window
        spike_ids_list = self.neuron_array[idx_iter][idx_inject]
        spike_shifts_list= self.shift_list[idx_iter][idx_inject]

        # delete spikes, ids etc that were selected above; 
        self.spike_array[idx_iter] = self.spike_array[idx_iter][idx_not]
        self.neuron_array[idx_iter] = self.neuron_array[idx_iter][idx_not]
        self.shift_list[idx_iter] = self.shift_list[idx_iter][idx_not]
        
        # return lists for addition below
        return spike_times_list, spike_ids_list, spike_shifts_list, True


    def sample_spikes_allspikes(self):
        """
            Same as sample_spikes() but picking all spikes from a previous iteration,
        """

        spike_times_list = self.spike_array[self.add_iteration_counter]-self.lockout_window
        spike_ids_list = self.neuron_array[self.add_iteration_counter]
        spike_shifts_list= self.shift_list[self.add_iteration_counter]
        spike_height_list = self.height_list[self.add_iteration_counter]

        return spike_times_list, spike_ids_list, spike_shifts_list, spike_height_list
        
        
    # def add_cpp(self, idx_iter):
        # #start = dt.datetime.now().timestamp()
        
        # torch.cuda.synchronize()
                        
        # # select randomly 10% of spikes from previous deconv; 
        # spike_times, spike_temps, spike_shifts, flag = self.sample_spikes(idx_iter)

        # # Cat: TODO is this flag required still?
        # if flag == False:
            # return 
            
        # # also fill in self-convolution traces with low energy so the
        # #   spikes cannot be detected again (i.e. enforcing refractoriness)
        # # Cat: TODO: investgiate whether putting the refractoriness back in is viable
        # if self.refractoriness:
            # deconv.refrac_fill(energy=self.obj_gpu,
                              # spike_times=spike_times,
                              # spike_ids=spike_temps,
                              # #fill_length=self.n_time,  # variable fill length here
                              # #fill_offset=self.n_time//2,       # again giving flexibility as to where you want the fill to start/end (when combined with preceeding arg
                              # fill_length=self.refractory*2+1,  # variable fill length here
                              # fill_offset=self.n_time//2+self.refractory//2,       # again giving flexibility as to where you want the fill to start/end (when combined with preceeding arg
                              # fill_value=self.fill_value)
                              
            # # deconv.subtract_spikes(data=self.obj_gpu,
                                   # # spike_times=spike_times,
                                   # # spike_temps=spike_temps,
                                   # # templates=self.templates_cpp_refractory_add,
                                   # # do_refrac_fill = False,
                                   # # refrac_fill_val = -1e10)

        # torch.cuda.synchronize()
        
        # # Add spikes back in;
        # deconv.subtract_splines(
                            # self.obj_gpu,
                            # spike_times,
                            # spike_shifts,
                            # spike_temps,
                            # self.coefficients,
                            # #-self.tempScaling
                            # -self.tempScaling_array
                            # )

        # torch.cuda.synchronize()
        
        # return 
        
        
    def add_cpp_allspikes(self):
        #start = dt.datetime.now().timestamp()
        
        torch.cuda.synchronize()
                        
        # select randomly 10% of spikes from previous deconv; 
        #spike_times, spike_temps, spike_shifts, flag = self.sample_spikes(idx_iter)
        
        # select all spikes from a previous iteration
        spike_times, spike_temps, spike_shifts, spike_heights = self.sample_spikes_allspikes()

        torch.cuda.synchronize()

        # if flag == False:
            # return 
            
        # also fill in self-convolution traces with low energy so the
        #   spikes cannot be detected again (i.e. enforcing refractoriness)
        # Cat: TODO: investgiate whether putting the refractoriness back in is viable
        if self.refractoriness:
            deconv.refrac_fill(energy=self.obj_gpu,
                              spike_times=spike_times,
                              spike_ids=spike_temps,
                              #fill_length=self.n_time,  # variable fill length here
                              #fill_offset=self.n_time//2,       # again giving flexibility as to where you want the fill to start/end (when combined with preceeding arg
                              fill_length=self.refractory*2+1,  # variable fill length here
                              fill_offset=self.n_time//2+self.refractory//2,       # again giving flexibility as to where you want the fill to start/end (when combined with preceeding arg
                              fill_value=self.fill_value)
                              
                              
            # deconv.subtract_spikes(data=self.obj_gpu,
                                   # spike_times=spike_times,
                                   # spike_temps=spike_temps,
                                   # templates=self.templates_cpp_refractory_add,
                                   # do_refrac_fill = False,
                                   # refrac_fill_val = -1e10)

        torch.cuda.synchronize()
        
        # Add spikes back in;
        deconv.subtract_splines(
                            self.obj_gpu,
                            spike_times,
                            spike_shifts,
                            spike_temps,
                            self.coefficients,
                            -self.tempScaling*spike_heights)

        torch.cuda.synchronize()
        
        return 


    def compute_average_ptps(self):
        spike_times = torch.cat(self.spike_array)
        neuron_ids = torch.cat(self.neuron_array)

        min_max_loc_spikes = self.min_max_loc[neuron_ids] + spike_times[:, None, None] - self.STIME + 1
        chan_loc_spikes = (torch.arange(self.N_CHAN).cuda()[None, None].repeat(min_max_loc_spikes.shape[0], 2, 1))
        min_max_vals_spikes = self.data[chan_loc_spikes, min_max_loc_spikes]
        ptps_spikes = (min_max_vals_spikes[:, 1] - min_max_vals_spikes[:, 0]).transpose(0,1)

        spike_chan_keep = (torch.abs(ptps_spikes - self.ptps_all_chans[:, neuron_ids]) <
                           self.ptps_threshold[:, neuron_ids])
        ptps_spikes[~spike_chan_keep] = 0
        spike_chan_keep = spike_chan_keep.long()

        ptps_spikes = ptps_spikes.transpose(0,1)
        spike_chan_keep = spike_chan_keep.transpose(0,1)

        ptps_average = torch.zeros((self.K, self.N_CHAN)).float().cuda()
        n_spikes = torch.zeros((self.K, self.N_CHAN)).cuda()
        for k in range(self.K):
            idx_ = neuron_ids == k
            ptps_average[k] += torch.sum(ptps_spikes[idx_], 0)
            n_spikes[k] = torch.sum(spike_chan_keep[idx_], 0)

        n_spikes[n_spikes==0] = 1
        ptps_average = ptps_average/n_spikes

        return ptps_average, n_spikes


# # ****************************************************************************
# # ****************************************************************************
# # ****************************************************************************


class deconvGPU2(object):
                   
   #'''  Greedy + exhaustive deconv - TO BE IMPLEMNETED
   #'''   
   
    def __init__(self, CONFIG, fname_templates, out_dir):
        
        #
        self.out_dir = out_dir
        
        # initialize directory for saving
        self.seg_dir = os.path.join(self.out_dir,'segs')
        if not os.path.isdir(self.seg_dir):
            os.mkdir(self.seg_dir)

        # initalize parameters for 
        self.set_params(CONFIG, fname_templates, out_dir)
        
