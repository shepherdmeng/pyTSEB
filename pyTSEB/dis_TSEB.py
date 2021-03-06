#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Created on Mon Mar 26 11:10:34 2018

@author: hector
"""
import numpy as np
import pandas as pd

import pyTSEB.TSEB as TSEB

from scipy.ndimage.filters import gaussian_filter
from scipy.signal import convolve2d
from scipy.ndimage import uniform_filter
#==============================================================================
# List of constants used in dis_TSEB model and sub-routines
#==============================================================================
ITERATIONS_OUT = 50
DIS_TSEB_ITERATIONS = 50
NO_VALID_FLAG = 255
VALID_FLAG = 0

def dis_TSEB(constant_ratio_LR,
             scale,
             Tr_K,
             vza,
             T_A_K,
             u,
             ea,
             p,
             Sn_C,
             Sn_S,
             L_dn,
             LAI,
             h_C,
             emis_C,
             emis_S,
             z_0M,
             d_0,
             z_u,
             z_T,
             leaf_width=0.1,
             z0_soil=0.01,
             alpha_PT=1.26,
             x_LAD=1,
             f_c=1.0,
             f_g=1.0,
             w_C=1.0,
             resistance_form=[0, {}],
             calcG_params=[
                          [1],
                          0.35],
             UseL=False,
             massman_profile=[0,[]],
             correct_LST = True):
                 
    '''Priestley-Taylor TSEB

    Calculates the Priestley Taylor TSEB fluxes using a single observation of
    composite radiometric temperature and using resistances in series.

    Parameters
    ----------
    Tr_K : float
        Radiometric composite temperature (Kelvin).
    vza : float
        View Zenith Angle (degrees).
    T_A_K : float
        Air temperature (Kelvin).
    u : float
        Wind speed above the canopy (m s-1).
    ea : float
        Water vapour pressure above the canopy (mb).
    p : float
        Atmospheric pressure (mb), use 1013 mb by default.
    Sn_C : float
        Canopy net shortwave radiation (W m-2).
    Sn_S : float
        Soil net shortwave radiation (W m-2).
    L_dn : float
        Downwelling longwave radiation (W m-2).
    LAI : float
        Effective Leaf Area Index (m2 m-2).
    h_C : float
        Canopy height (m).
    emis_C : float
        Leaf emissivity.
    emis_S : flaot
        Soil emissivity.
    z_0M : float
        Aerodynamic surface roughness length for momentum transfer (m).
    d_0 : float
        Zero-plane displacement height (m).
    z_u : float
        Height of measurement of windspeed (m).
    z_T : float
        Height of measurement of air temperature (m).
    leaf_width : float, optional
        average/effective leaf width (m).
    z0_soil : float, optional
        bare soil aerodynamic roughness length (m).
    alpha_PT : float, optional
        Priestley Taylor coeffient for canopy potential transpiration,
        use 1.26 by default.
    x_LAD : float, optional
        Campbell 1990 leaf inclination distribution function chi parameter.
    f_c : float, optional
        Fractional cover.
    f_g : float, optional
        Fraction of vegetation that is green.
    w_C : float, optional
        Canopy width to height ratio.
    resistance_form : int, optional
        Flag to determine which Resistances R_x, R_S model to use.

            * 0 [Default] Norman et al 1995 and Kustas et al 1999.
            * 1 : Choudhury and Monteith 1988.
            * 2 : McNaughton and Van der Hurk 1995.

    calcG_params : list[list,float or array], optional
        Method to calculate soil heat flux,parameters.

            * [1],G_ratio]: default, estimate G as a ratio of Rn_S, default Gratio=0.35.
            * [0],G_constant] : Use a constant G, usually use 0 to ignore the computation of G.
            * [[2,Amplitude,phase_shift,shape],time] : estimate G from Santanello and Friedl with G_param list of parameters (see :func:`~TSEB.calc_G_time_diff`).
    UseL : float or None, optional
        If included, its value will be used to force the Moning-Obukhov stability length.

    Returns
    -------
    flag : int
        Quality flag, see Appendix for description.
    T_S : float
        Soil temperature  (Kelvin).
    T_C : float
        Canopy temperature  (Kelvin).
    T_AC : float
        Air temperature at the canopy interface (Kelvin).
    L_nS : float
        Soil net longwave radiation (W m-2)
    L_nC : float
        Canopy net longwave radiation (W m-2)
    LE_C : float
        Canopy latent heat flux (W m-2).
    H_C : float
        Canopy sensible heat flux (W m-2).
    LE_S : float
        Soil latent heat flux (W m-2).
    H_S : float
        Soil sensible heat flux (W m-2).
    G : float
        Soil heat flux (W m-2).
    R_S : float
        Soil aerodynamic resistance to heat transport (s m-1).
    R_x : float
        Bulk canopy aerodynamic resistance to heat transport (s m-1).
    R_A : float
        Aerodynamic resistance to heat transport (s m-1).
    u_friction : float
        Friction velocity (m s-1).
    L : float
        Monin-Obuhkov length (m).
    n_iterations : int
        number of iterations until convergence of L.

    References
    ----------
    .. [Norman1995] J.M. Norman, W.P. Kustas, K.S. Humes, Source approach for estimating
        soil and vegetation energy fluxes in observations of directional radiometric
        surface temperature, Agricultural and Forest Meteorology, Volume 77, Issues 3-4,
        Pages 263-293,
        http://dx.doi.org/10.1016/0168-1923(95)02265-Y.
    .. [Kustas1999] William P Kustas, John M Norman, Evaluation of soil and vegetation heat
        flux predictions using a simple two-source model with radiometric temperatures for
        partial canopy cover, Agricultural and Forest Meteorology, Volume 94, Issue 1,
        Pages 13-29,
        http://dx.doi.org/10.1016/S0168-1923(99)00005-2.
    '''
    # Create a pixel map which maps every HR pixel to a corresponding LR pixel
    dims_LR = constant_ratio_LR.shape
    #dims_HR = Tr_K.shape
   
    pixel_map = np.arange(np.size(constant_ratio_LR)).reshape(dims_LR)
    pixel_map = downscale_image(pixel_map, scale, Tr_K.shape)
    
    const_ratio = downscale_image(constant_ratio_LR, scale, Tr_K.shape)
    
    # Create mask that masks high-res pixels where low-res constant ratio
    # does not exist or is invalid
    mask = np.ones(const_ratio.shape, dtype=bool)
    mask[np.logical_or(np.isnan(const_ratio),
                        Tr_K <= 0)] = False                   

    
    #######################################################################
    # For all the pixels in the high res. TSEB
    # WHILE high-res contant ration != low-res constant ratio
    #   mask pixels where ratios aggree
    #   adjust Tair for other pixels
    #   run high-res TSBE for unmaksed pixels
    #   claculate high-res consant ratio
    counter = 1
    T_offset = np.zeros(const_ratio.shape) 
    Tr_K_modified = Tr_K[:]
    T_A_K_modified = T_A_K[:]
    
    const_ratio_diff = np.zeros(const_ratio.shape)+1000
    const_ratio_HR = np.ones(const_ratio.shape)*np.nan
    
    # Initialize output variables
    [flag, 
     T_S,
     T_C, 
     T_AC, 
     Ln_S, 
     Ln_C, 
     LE_C, 
     H_C, 
     LE_S, 
     H_S, 
     G, 
     R_S, 
     R_x, 
     R_A, 
     u_friction, 
     L, 
     n_iterations] = map(np.zeros, 17*[Tr_K.shape])    

    [T_S[:], 
     T_C[:], 
     T_AC[:], 
     Ln_S[:], 
     Ln_C[:], 
     LE_C[:], 
     H_C[:], 
     LE_S[:], 
     H_S[:], 
     G[:], 
     R_S[:],
     R_x[:], 
     R_A[:], 
     u_friction[:], 
     L[:]] = 15*[np.nan]        
    
    n_iterations[:] = 0
    flag[:] = NO_VALID_FLAG
        
    print('Forcing low resolution MO stability length as starting point in the iteration')
    L = np.ones(Tr_K.shape) * UseL
    rho = TSEB.met.calc_rho(p, ea, T_A_K)  # Air density
    c_p = TSEB.met.calc_c_p(p, ea)  # Heat capacity of air
    
    del UseL

    while np.any(mask) and counter < DIS_TSEB_ITERATIONS:
        if correct_LST:
            Tr_K_modified[mask] = Tr_K[mask] - T_offset[mask]
        else:
            T_A_K_modified[mask] = T_A_K[mask] + T_offset[mask]
            
        flag[mask] = VALID_FLAG
        # Run high-res TSEB on all unmasked pixels

        # First process bare soil cases
        print('First process bare soil cases')
        i = np.array(np.logical_and(LAI == 0, mask))
        
        [flag[i],
         Ln_S[i],
         LE_S[i],
         H_S[i],
         G[i],
         R_A[i],
         u_friction[i],
         L[i],
         n_iterations[i]] = TSEB.OSEB(Tr_K_modified[i],
                                  T_A_K_modified[i],
                                  u[i],
                                  ea[i],
                                  p[i],
                                  Sn_S[i],
                                  L_dn[i],
                                  emis_S[i],
                                  z_0M[i],
                                  d_0[i],
                                  z_u[i],
                                  z_T[i],
                                  calcG_params = calcG_params,
                                  UseL = L[i])
        
        
        T_S[i] = Tr_K_modified[i]
        T_AC[i] = T_A_K_modified[i]
        # Set canopy fluxes to 0
        Sn_C[i] = 0.0                                          
        Ln_C[i] = 0.0
        LE_C[i] = 0.0
        H_C[i] = 0.0
        
        # Then process vegetated pixels
        print('Then process vegetated pixels')
        i = np.array(np.logical_and(LAI > 0, mask))
        if resistance_form[0] == 0:
            resistance_flag = [resistance_form[0], 
                           {k: resistance_form[1][k][i] for k in resistance_form[1]}]
                           
        else:
            resistance_flag = [resistance_form[0],{}]
    
        [flag[i], 
         T_S[i],
         T_C[i], 
         T_AC[i], 
         Ln_S[i], 
         Ln_C[i], 
         LE_C[i], 
         H_C[i], 
         LE_S[i], 
         H_S[i], 
         G[i], 
         R_S[i], 
         R_x[i], 
         R_A[i], 
         u_friction[i], 
         L[i], 
         n_iterations[i]] = TSEB.TSEB_PT(Tr_K_modified[i],
                                 vza[i],
                                 T_A_K_modified[i],
                                 u[i],
                                 ea[i],
                                 p[i],
                                 Sn_C[i],
                                 Sn_S[i],
                                 L_dn[i],
                                 LAI[i],
                                 h_C[i],
                                 emis_C[i],
                                 emis_S[i],
                                 z_0M[i],
                                 d_0[i],
                                 z_u[i],
                                 z_T[i],
                                 leaf_width = leaf_width[i],
                                 z0_soil = z0_soil[i],
                                 alpha_PT = alpha_PT[i],
                                 x_LAD = x_LAD[i],
                                 f_c = f_c[i],
                                 f_g = f_g[i],
                                 w_C = w_C[i],
                                 resistance_form = resistance_flag,
                                 calcG_params = calcG_params,
                                 UseL = L[i],
                                 massman_profile = massman_profile)
        
        LE_HR = LE_C + LE_S
        H_HR = H_C + H_S

        print('Recalculating MO stability length')
        L = TSEB.MO.calc_L(u_friction, T_A_K_modified, rho, c_p, H_HR, LE_HR)
        
        #Rn_HR = Sn_C + Sn_S + Ln_C + Ln_S
        valid = np.logical_and(mask, flag != NO_VALID_FLAG)
        # Calculate high-res constant ratio
        const_ratio_HR[valid] = LE_HR[valid] / (LE_HR[valid] + H_HR[valid])
        
        # Calculate average constant ratio for each LR pixel from all HR
        # pixels it contains
        print('Calculating average constant ratio for each LR pixel using valid HR pixels')
        unique = np.unique(pixel_map[mask])
        pd_dataframe = pd.DataFrame({'const_ratio': const_ratio_HR.reshape(-1),
                                     'pixel_map':pixel_map.reshape(-1)})
                                     
        const_ratio_LR = np.asarray(pd_dataframe.groupby('pixel_map')['const_ratio'].mean())
        
        const_ratio_HR = downscale_image(const_ratio_LR.reshape(dims_LR),
                                         scale, 
                                         Tr_K.shape)
        
        const_ratio_HR[~mask] = np.nan
#==============================================================================
#         for pix in unique:
#             ind = pixel_map == pix
#             const_ratio_HR[ind] = np.nanmean(const_ratio_HR[ind])
#         
#==============================================================================
        
        # Mask the low-res pixels for which constant ratio of hig-res and 
        # low-res runs agree.
        const_ratio_diff = const_ratio_HR - const_ratio
        const_ratio_diff[np.logical_or(np.isnan(const_ratio_HR), 
                                       np.isnan(const_ratio))] = 0
        
        mask = np.abs(const_ratio_diff)>0.01
        # For other pixels, adjust Ta.        
        # If high-res H is too high (diff is -ve) -> increase air temperature to reduce H
        # If high-res H is too low (diff is +ve) -> decrease air temperature to increase H         
        step = np.clip(const_ratio_diff*5, -1, 1)
        counter +=  1
        print('disTSEB iteration %s'%counter)
        #print(np.max(const_ratio_diff[mask]))
        #print(np.min(const_ratio_diff[mask]))
        print('Recalculating over %s high resolution pixels'%np.size(Tr_K[mask]))
        print('representing %s low resolution pixels'%np.size(unique))
        T_offset[mask] -= step[mask]
        T_offset = np.clip(T_offset, -5.0, 5.0)

    ####################################################################
    # When constant ratios for all pixels match, smooth the resulting Ta adjustment
    # with a moving window size of 2x2 km and perform a final run of high-res model
    mask = np.ones(const_ratio.shape, dtype=bool)
    mask[np.isnan(const_ratio)] = False                   
    
    T_offset_orig = T_offset[:]
    #T_offset[~mask] = 0 
    #T_offset = moving_mean_filter_2(T_offset, (int(3* scale[0]), int(3* scale[1])))

    T_offset = moving_gaussian_filter(T_offset, 3*float(scale[0]))

    # Smooth MO length
    L = moving_gaussian_filter(L, 20)
    #L[~mask] = 0 
    #L = moving_mean_filter_2(L, (5, 5))
    
    if correct_LST:     
        Tr_K_modified = Tr_K - T_offset    
    else:     
        T_A_K_modified = T_A_K + T_offset    
    
    flag[mask] = VALID_FLAG
    
    # Run high-res TSEB on all unmasked pixels
    TSEB.ITERATIONS = ITERATIONS_OUT
    print('Final run of TSEB at high resolution with adjusted temperature')

    # First process bare soil cases
    print('First process bare soil cases')
    i = np.array(np.logical_and(LAI == 0, mask))
    [flag[i],
     Ln_S[i],
     LE_S[i],
     H_S[i],
     G[i],
     R_A[i],
     u_friction[i],
     L[i],
     n_iterations[i]] = TSEB.OSEB(Tr_K_modified[i],
                              T_A_K_modified[i],
                              u[i],
                              ea[i],
                              p[i],
                              Sn_S[i],
                              L_dn[i],
                              emis_S[i],
                              z_0M[i],
                              d_0[i],
                              z_u[i],
                              z_T[i],
                              calcG_params = calcG_params,
                              UseL = L[i])
    
    
    T_S[i] = Tr_K_modified[i]
    T_AC[i] = T_A_K_modified[i]
    # Set canopy fluxes to 0
    Sn_C[i] = 0.0                                          
    Ln_C[i] = 0.0
    LE_C[i] = 0.0
    H_C[i] = 0.0
    
    # Then process vegetated pixels
    print('Then process vegetated pixels')
    i = np.array(np.logical_and(LAI > 0, mask))
    
    if resistance_form[0] == 0:
        resistance_flag = [resistance_form[0], 
                       {k: resistance_form[1][k][i] for k in resistance_form[1]}]
                       
    else:
        resistance_flag = [resistance_form[0],{}]
    
    [flag[i], 
     T_S[i],
     T_C[i], 
     T_AC[i], 
     Ln_S[i], 
     Ln_C[i], 
     LE_C[i], 
     H_C[i], 
     LE_S[i], 
     H_S[i], 
     G[i], 
     R_S[i], 
     R_x[i], 
     R_A[i], 
     u_friction[i], 
     L[i], 
     n_iterations[i]] = TSEB.TSEB_PT(Tr_K_modified[i],
                                     vza[i],
                                     T_A_K_modified[i],
                                     u[i],
                                     ea[i],
                                     p[i],
                                     Sn_C[i],
                                     Sn_S[i],
                                     L_dn[i],
                                     LAI[i],
                                     h_C[i],
                                     emis_C[i],
                                     emis_S[i],
                                     z_0M[i],
                                     d_0[i],
                                     z_u[i],
                                     z_T[i],
                                     leaf_width = leaf_width[i],
                                     z0_soil = z0_soil[i],
                                     alpha_PT = alpha_PT[i],
                                     x_LAD = x_LAD[i],
                                     f_c = f_c[i],
                                     f_g = f_g[i],
                                     w_C = w_C[i],
                                     resistance_form = resistance_flag,
                                     calcG_params = calcG_params,
                                     UseL = L[i],
                                     massman_profile = massman_profile)
    


    return [flag, 
            T_S, 
            T_C, 
            T_AC, 
            Ln_S,
            Ln_C, 
            LE_C, 
            H_C, 
            LE_S, 
            H_S, 
            G, 
            R_S, 
            R_x, 
            R_A, 
            u_friction, 
            L, 
            n_iterations, 
            T_offset, 
            counter,
            T_offset_orig]

def moving_gaussian_filter(data, window):
    # 95% of contribution is from within the window
    sigma = window / 4.0    
    
    V = data.copy()
    V[data != data] = 0
    VV = gaussian_filter(V, sigma)
    
    W = 0*data.copy() + 1
    W[data != data] = 0
    WW = gaussian_filter(W, sigma)
    
    return VV/WW

def moving_mean_filter(data, window):
    
    ''' window is a 2 element tuple with the moving window dimensions (rows, columns)'''
    kernel = np.ones(window)/np.prod(np.asarray(window))
    data = convolve2d(data, kernel, mode = 'same', boundary = 'symm')
    
    return data
    
def moving_mean_filter_2(data, window):

    ''' window is a 2 element tuple with the moving window dimensions (rows, columns)'''
    data = uniform_filter(data, size = window, mode = 'mirror')

    return data
    
def downscale_image(image, scale, shape_hr):
    
    for i, sc in enumerate(scale):
        image = np.repeat(image, sc, axis=i)
        
    return image[:shape_hr[0],:shape_hr[1]]