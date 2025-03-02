import torch
import torch.nn.functional as F
from torch import Tensor

import itertools

from typing          import Optional, Callable, Tuple, Dict, Any, Union

from einops          import rearrange

from ..sigmas        import get_sigmas
from ..helper        import ExtraOptions, initialize_or_scale, get_extra_options_kv, extra_options_flag, is_video_model
from ..latents       import normalize_zscore, get_cosine_similarity, normalize_latent, hard_light_blend

from .rk_method_beta import RK_Method_Beta
from .constants      import MAX_STEPS

#from ..latents import hard_light_blend, normalize_latent




class LatentGuide:
    def __init__(self,
                model,
                sigmas,
                UNSAMPLE,
                LGW_MASK_RESCALE_MIN,
                extra_options,
                device            = 'cpu',
                dtype             = torch.float64,
                frame_weights_grp = None
                ):
        
        self.dtype                    = dtype
        self.device                   = device
        self.model                    = model

        if hasattr(model, "model"):
            model_sampling = model.model.model_sampling
        elif hasattr(model, "inner_model"):
            model_sampling = model.inner_model.inner_model.model_sampling
        
        self.sigma_min                = model_sampling.sigma_min.to(dtype=dtype, device=device)
        self.sigma_max                = model_sampling.sigma_max.to(dtype=dtype, device=device)
        self.sigmas                   = sigmas                  .to(dtype=dtype, device=device)
        self.UNSAMPLE                 = UNSAMPLE
        self.VIDEO                    = is_video_model(model)
        self.SAMPLE                   = (sigmas[0] > sigmas[1])
        self.y0                       = None
        self.y0_inv                   = None
        self.guide_mode               = ""
        self.max_steps                = MAX_STEPS
        self.mask                     = None
        self.mask_inv                 = None
        self.x_lying_                 = None
        self.s_lying_                 = None
        self.LGW_MASK_RESCALE_MIN     = LGW_MASK_RESCALE_MIN
        self.HAS_LATENT_GUIDE         = False
        self.HAS_LATENT_GUIDE_INV     = False
        self.lgw                      = torch.full_like(sigmas, 0., dtype=dtype) 
        self.lgw_inv                  = torch.full_like(sigmas, 0., dtype=dtype)
        self.guide_cossim_cutoff_     = 1.0
        self.guide_bkg_cossim_cutoff_ = 1.0
        self.frame_weights            = frame_weights_grp[0] if frame_weights_grp is not None else None
        self.frame_weights_inv        = frame_weights_grp[1] if frame_weights_grp is not None else None
        
        self.extra_options            = extra_options
        self.EO                       = ExtraOptions(extra_options)


    def init_guides(self, x : torch.Tensor, RK_IMPLICIT, guides=None, noise_sampler=None):
        latent_guide_weight      = 0.0
        latent_guide_weight_inv  = 0.0
        latent_guide_weights     = torch.zeros_like(self.sigmas, dtype=self.dtype, device=self.device)
        latent_guide_weights_inv = torch.zeros_like(self.sigmas, dtype=self.dtype, device=self.device)
        latent_guide             = None
        latent_guide_inv         = None

        if guides is not None:
            (self.guide_mode, 
            latent_guide_weight, 
            latent_guide_weight_inv, 
            latent_guide_weights, 
            latent_guide_weights_inv, 
            latent_guide, 
            latent_guide_inv, 
            self.mask, 
            self.mask_inv, 
            scheduler_, 
            scheduler_inv_, 
            start_steps_, 
            start_steps_inv_, 
            steps_, 
            steps_inv_, 
            self.guide_cossim_cutoff_, 
            self.guide_bkg_cossim_cutoff_) = guides

            if self.guide_mode.startswith("fully_") and not RK_IMPLICIT:
                self.guide_mode = self.guide_mode[6:]   # fully_pseudoimplicit is only supported for implicit samplers, default back to pseudoimplicit
            
            if latent_guide_weights is None:
                total_steps          = steps_ - start_steps_
                latent_guide_weights = get_sigmas(self.model, scheduler_, total_steps, 1.0).to(dtype=self.dtype, device=self.device) / self.sigma_max
                prepend              = torch.zeros(start_steps_,                               dtype=self.dtype, device=self.device)
                latent_guide_weights = torch.cat((prepend, latent_guide_weights), dim=0)
                
            
            if latent_guide_weights_inv is None:
                total_steps              = steps_inv_ - start_steps_inv_
                latent_guide_weights_inv = get_sigmas(self.model, scheduler_inv_, total_steps, 1.0).to(dtype=self.dtype, device=self.device) / self.sigma_max
                prepend                  = torch.zeros(start_steps_inv_,                               dtype=self.dtype, device=self.device) 
                latent_guide_weights     = torch.cat((prepend, latent_guide_weights_inv), dim=0)
                
            latent_guide_weights     = initialize_or_scale(latent_guide_weights,     latent_guide_weight,     self.max_steps)
            latent_guide_weights_inv = initialize_or_scale(latent_guide_weights_inv, latent_guide_weight_inv, self.max_steps)

            latent_guide_weights    [steps_     - 1:] = 0
            latent_guide_weights_inv[steps_inv_ - 1:] = 0
                
        self.lgw     = F.pad(latent_guide_weights,     (0, self.max_steps), value=0.0)
        self.lgw_inv = F.pad(latent_guide_weights_inv, (0, self.max_steps), value=0.0)
        
        mask, self.LGW_MASK_RESCALE_MIN = prepare_mask(x, self.mask, self.LGW_MASK_RESCALE_MIN)
        self.mask = mask.to(dtype=self.dtype, device=self.device)

        if self.mask_inv is not None:
            mask_inv, self.LGW_MASK_RESCALE_MIN = prepare_mask(x, self.mask_inv, self.LGW_MASK_RESCALE_MIN)
            self.mask_inv = mask_inv.to(dtype=self.dtype, device=self.device)
        else:
            self.mask_inv = (1-self.mask)
    
        if latent_guide is not None:
            self.HAS_LATENT_GUIDE = True
            if type(latent_guide) is dict:
                latent_guide_samples = self.model.inner_model.inner_model.process_latent_in(latent_guide['samples']).clone().to(dtype=self.dtype, device=self.device)
            elif type(latent_guide) is torch.Tensor:
                latent_guide_samples = latent_guide.to(dtype=self.dtype, device=self.device)
            else:
                raise ValueError(f"Invalid latent type: {type(latent_guide)}")

            if self.VIDEO and latent_guide_samples.shape[2] == 1:
                latent_guide_samples = latent_guide_samples.repeat(1, 1, x.shape[2], 1, 1)

            if self.SAMPLE:
                self.y0 = latent_guide_samples
            elif self.UNSAMPLE: # and self.mask is not None:
                mask = self.mask.to(x.device)
                x = (1-mask) * x + mask * latent_guide_samples.to(x.device)
            else:
                x = latent_guide_samples.to(x.device)
        else:
            self.y0 = torch.zeros_like(x, dtype=self.dtype, device=self.device)

        if latent_guide_inv is not None:
            self.HAS_LATENT_GUIDE_INV = True
            if type(latent_guide_inv) is dict:
                latent_guide_inv_samples = self.model.inner_model.inner_model.process_latent_in(latent_guide_inv['samples']).clone().to(dtype=self.dtype, device=self.device)
            elif type(latent_guide_inv) is torch.Tensor:
                latent_guide_inv_samples = latent_guide_inv.to(dtype=self.dtype, device=self.device)
            else:
                raise ValueError(f"Invalid latent type: {type(latent_guide_inv)}")

            if self.VIDEO and latent_guide_inv_samples.shape[2] == 1:
                latent_guide_inv_samples = latent_guide_inv_samples.repeat(1, 1, x.shape[2], 1, 1)

            if self.SAMPLE:
                self.y0_inv = latent_guide_inv_samples
            elif self.UNSAMPLE: # and self.mask is not None:
                mask_inv = self.mask_inv.to(x.device)
                x = (1-mask_inv) * x + mask_inv * latent_guide_inv_samples.to(x.device) #fixed old approach, which was mask, (1-mask)
            else:
                x = latent_guide_inv_samples.to(x.device)   #THIS COULD LEAD TO WEIRD BEHAVIOR! OVERWRITING X WITH LG_INV AFTER SETTING TO LG above!
        else:
            self.y0_inv = torch.zeros_like(x, dtype=self.dtype, device=self.device)

        if self.frame_weights is not None:
            self.frame_weights     = initialize_or_scale(self.frame_weights,     1.0, self.max_steps).to(dtype=self.dtype, device=self.device)
            self.frame_weights     = F.pad              (self.frame_weights,     (0,  self.max_steps), value=0.0)
        if self.frame_weights_inv is not None:
            self.frame_weights_inv = initialize_or_scale(self.frame_weights_inv, 1.0, self.max_steps).to(dtype=self.dtype, device=self.device)
            self.frame_weights_inv = F.pad              (self.frame_weights_inv, (0,  self.max_steps), value=0.0)

        if self.UNSAMPLE and not self.SAMPLE: #sigma_next > sigma:
            self.y0     = noise_sampler(sigma=self.sigma_max, sigma_next=self.sigma_min).to(dtype=self.dtype, device=self.device)
            self.y0     = normalize_zscore(self.y0,     channelwise=True, inplace=True)
            self.y0_inv = noise_sampler(sigma=self.sigma_max, sigma_next=self.sigma_min).to(dtype=self.dtype, device=self.device)
            self.y0_inv = normalize_zscore(self.y0_inv, channelwise=True, inplace=True)
            
        x, self.y0, self.y0_inv = self.normalize_inputs(x, self.y0, self.y0_inv) #, self.extra_options)

        return x

    def prepare_weighted_masks(self, step):
        lgw_     = self.lgw    [step]
        lgw_inv_ = self.lgw_inv[step]
        
        mask     = torch.ones_like(self.y0) if self.mask     is None else self.mask
        mask_inv = torch.zeros_like(mask  ) if self.mask_inv is None else self.mask_inv

        if self.LGW_MASK_RESCALE_MIN: 
            lgw_mask     =    mask  * (1-lgw_)     + lgw_
            lgw_mask_inv = (1-mask) * (1-lgw_inv_) + lgw_inv_
        else:
            if self.HAS_LATENT_GUIDE:
                lgw_mask = mask * lgw_
            else:
                lgw_mask = torch.zeros_like(mask)
            
            if self.HAS_LATENT_GUIDE_INV:
                if mask_inv is not None:
                    lgw_mask_inv = torch.minimum(mask_inv, (1-mask) * lgw_inv_)
                    #lgw_mask_inv = torch.minimum(1-mask_inv, (1-mask) * lgw_inv_)
                else:
                    lgw_mask_inv = (1-mask) * lgw_inv_
            else:
                lgw_mask_inv = torch.zeros_like(mask)

        return lgw_mask, lgw_mask_inv


    def get_masks_for_step(self, step):
        lgw_mask, lgw_mask_inv = self.prepare_weighted_masks(step)
        if self.VIDEO:
            if self.frame_weights     is not None:
                apply_frame_weights(lgw_mask,     self.frame_weights)
            if self.frame_weights_inv is not None:
                apply_frame_weights(lgw_mask_inv, self.frame_weights_inv)

        return lgw_mask.to(self.device), lgw_mask_inv.to(self.device)



    def get_cossim_adjusted_lgw_masks(self, data, step):
        
        if self.HAS_LATENT_GUIDE:
            y0     = self.y0.clone()
        else:
            y0     = torch.zeros_like(data)
            
        if self.HAS_LATENT_GUIDE_INV:
            y0_inv = self.y0_inv.clone()
        else:
            y0_inv = torch.zeros_like(data)

        if y0.shape[0] > 1:                                    # this is for changing the guide on a per-step basis
            y0 = y0[min(step, y0.shape[0]-1)].unsqueeze(0)
        
        lgw_mask, lgw_mask_inv = self.get_masks_for_step(step)
        
        data_norm         = data   - data  .mean(dim=(-2,-1), keepdim=True)
        
        if self.HAS_LATENT_GUIDE:
            y0_norm       = y0     - y0    .mean(dim=(-2,-1), keepdim=True)
            y0_cossim     = get_cosine_similarity(data_norm * lgw_mask,     y0_norm     * lgw_mask)
        else:
            y0_cossim     = 1.0
        
        if self.HAS_LATENT_GUIDE_INV:
            y0_inv_norm   = y0_inv - y0_inv.mean(dim=(-2,-1), keepdim=True)
            y0_cossim_inv = get_cosine_similarity(data_norm * lgw_mask_inv, y0_inv_norm * lgw_mask_inv)
        else:
            y0_cossim_inv = 1.0
        
        #if y0_cossim < self.guide_cossim_cutoff_ or y0_cossim_inv < self.guide_bkg_cossim_cutoff_:
        if y0_cossim     >= self.guide_cossim_cutoff_:
            lgw_mask     *= 0
        if y0_cossim_inv >= self.guide_bkg_cossim_cutoff_:
            lgw_mask_inv *= 0
        
        return y0, y0_inv, lgw_mask, lgw_mask_inv



    @torch.no_grad
    def process_pseudoimplicit_guides_substep(self,
                                            x_0,
                                            x_,
                                            eps_,
                                            eps_prev_,
                                            data_,
                                            denoised_prev,
                                            row,
                                            step,
                                            sigmas,
                                            NS,
                                            RK,
                                            pseudoimplicit_row_weights,
                                            pseudoimplicit_step_weights,
                                            full_iter,
                                            BONGMATH,
                                            extra_options,
                                            ):
        
        if "pseudoimplicit" not in self.guide_mode or (self.lgw[step] == 0 and self.lgw_inv[step] == 0):
            return x_0, x_, eps_, None, None
        
        sigma = sigmas[step]

        if self.s_lying_ is not None:
            if row >= len(self.s_lying_):
                return x_0, x_, eps_, None, None
        
        if self.guide_mode.startswith("fully_"):
            data_cossim_test = denoised_prev
        else:
            data_cossim_test = data_[row]
            
        y0, y0_inv, lgw_mask, lgw_mask_inv = self.get_cossim_adjusted_lgw_masks(data_cossim_test, step)
        
        if not (lgw_mask.any() != 0 or lgw_mask_inv.any() != 0):  # cossim score too similar! deactivate guide for this step
            return x_0, x_, eps_, None, None


        if "fully_pseudoimplicit" in self.guide_mode:
            if self.x_lying_ is None:
                return x_0, x_, eps_, None, None        
            else:
                x_row_pseudoimplicit     = self.x_lying_[row]
                sub_sigma_pseudoimplicit = self.s_lying_[row]
        
        
        
        if RK.IMPLICIT:
            x_ = RK.update_substep(x_0,
                                    x_,
                                    eps_,
                                    eps_prev_,
                                    row,
                                    RK.row_offset,
                                    NS.h_new,
                                    NS.h_new_orig,
                                    )
            
            x_[row] = NS.rebound_overshoot_substep(x_0, x_[row])
            
            if row > 0:
                x_[row] = NS.swap_noise_substep(x_0, x_[row])
                if BONGMATH and step < sigmas.shape[0]-1 and not self.EO("disable_pseudoimplicit_bongmath", extra_options):
                    x_0, x_, eps_ = RK.bong_iter(x_0,
                                                x_,
                                                eps_,
                                                eps_prev_,
                                                data_,
                                                sigma,
                                                NS.s_,
                                                row,
                                                RK.row_offset,
                                                NS.h,
                                                )
        else:
            eps_[row] = RK.get_epsilon(x_0, x_[row], denoised_prev, sigma, NS.s_[row])
            
        if self.EO("pseudoimplicit_denoised_prev", extra_options):
            eps_[row] = RK.get_epsilon(x_0, x_[row], denoised_prev, sigma, NS.s_[row])
 
        eps_substep_guide     = torch.zeros_like(x_0)
        eps_substep_guide_inv = torch.zeros_like(x_0)
        
        if self.HAS_LATENT_GUIDE:
            eps_substep_guide     = RK.get_guide_epsilon(x_0, x_[row], y0,     sigma, NS.s_[row], NS.sigma_down, None)  
        if self.HAS_LATENT_GUIDE_INV:
            eps_substep_guide_inv = RK.get_guide_epsilon(x_0, x_[row], y0_inv, sigma, NS.s_[row], NS.sigma_down, None)  



        if self.guide_mode in {"pseudoimplicit", "pseudoimplicit_cw", "pseudoimplicit_projection", "pseudoimplicit_projection_cw"}:
            maxmin_ratio = (NS.sub_sigma - RK.sigma_min) / NS.sub_sigma
            
            if   self.EO("guide_pseudoimplicit_power_substep_flip_maxmin_scaling", extra_options):
                maxmin_ratio *= (RK.rows-row) / RK.rows
            elif self.EO("guide_pseudoimplicit_power_substep_maxmin_scaling", extra_options):
                maxmin_ratio *= row / RK.rows
            
            sub_sigma_2 = NS.sub_sigma - maxmin_ratio * (NS.sub_sigma * pseudoimplicit_row_weights[row] * pseudoimplicit_step_weights[full_iter] * self.lgw[step])

            eps_tmp_ = eps_.clone()

            eps_ = self.process_channelwise(x_0,
                                            eps_,
                                            data_,
                                            row,
                                            eps_substep_guide,
                                            eps_substep_guide_inv,
                                            y0,
                                            y0_inv,
                                            lgw_mask,
                                            lgw_mask_inv,
                                            use_projection = self.guide_mode in {"pseudoimplicit_projection", "pseudoimplicit_projection_cw"},
                                            channelwise    = self.guide_mode in {"pseudoimplicit_cw",         "pseudoimplicit_projection_cw"},
                                            )

            x_row_tmp = x_[row] + RK.h_fn(sub_sigma_2, NS.sub_sigma) * eps_[row]
            
            eps_                     = eps_tmp_
            x_row_pseudoimplicit     = x_row_tmp
            sub_sigma_pseudoimplicit = sub_sigma_2


        if RK.IMPLICIT and BONGMATH and step < sigmas.shape[0]-1 and not self.EO("disable_pseudobongmath", extra_options):
            x_[row] = NS.sigma_from_to(x_0, x_row_pseudoimplicit, sigma, sub_sigma_pseudoimplicit, NS.s_[row])
            
            x_0, x_, eps_ = RK.bong_iter(x_0,
                                        x_,
                                        eps_,
                                        eps_prev_,
                                        data_,
                                        sigma,
                                        NS.s_,
                                        row,
                                        RK.row_offset,
                                        NS.h,
                                        ) 
            
        return x_0, x_, eps_, x_row_pseudoimplicit, sub_sigma_pseudoimplicit



    @torch.no_grad
    def prepare_fully_pseudoimplicit_guides_substep(self,
                                                    x_0,
                                                    x_,
                                                    eps_,
                                                    eps_prev_,
                                                    data_,
                                                    denoised_prev,
                                                    row,
                                                    step,
                                                    sigmas,
                                                    eta_substep,
                                                    overshoot_substep,
                                                    s_noise_substep,
                                                    NS,
                                                    RK,
                                                    pseudoimplicit_row_weights,
                                                    pseudoimplicit_step_weights,
                                                    full_iter,
                                                    BONGMATH,
                                                    extra_options,
                                                    ):
        
        if "fully_pseudoimplicit" not in self.guide_mode or (self.lgw[step] == 0 and self.lgw_inv[step] == 0):
            return x_0, x_, eps_ 
        
        sigma = sigmas[step]
        
        y0, y0_inv, lgw_mask, lgw_mask_inv = self.get_cossim_adjusted_lgw_masks(denoised_prev, step)
        
        if not (lgw_mask.any() != 0 or lgw_mask_inv.any() != 0):  # cossim score too similar! deactivate guide for this step
            return x_0, x_, eps_
        

        # PREPARE FULLY PSEUDOIMPLICIT GUIDES
        if self.guide_mode in {"fully_pseudoimplicit", "fully_pseudoimplicit_cw", "fully_pseudoimplicit_projection", "fully_pseudoimplicit_projection_cw"} and (self.lgw[step] > 0 or self.lgw_inv[step] > 0):
            x_lying_   = x_.clone()
            eps_lying_ = eps_.clone()
            s_lying_   = []
            
            for r in range(RK.rows):
                
                NS.set_sde_substep(r, RK.multistep_stages, eta_substep, overshoot_substep, s_noise_substep)

                maxmin_ratio      = (NS.sub_sigma - RK.sigma_min) / NS.sub_sigma
                fully_sub_sigma_2 =  NS.sub_sigma - maxmin_ratio * (NS.sub_sigma * pseudoimplicit_row_weights[r] * pseudoimplicit_step_weights[full_iter] * self.lgw[step])
                
                s_lying_.append(fully_sub_sigma_2)

                if RK.IMPLICIT:
                    x_ = RK.update_substep(x_0,
                                            x_,
                                            eps_,
                                            eps_prev_,
                                            r,
                                            RK.row_offset,
                                            NS.h_new,
                                            NS.h_new_orig,
                                            ) 
                    
                    x_[r] = NS.rebound_overshoot_substep(x_0, x_[r])

                    if r > 0:
                        x_[r] = NS.swap_noise_substep(x_0, x_[r])
                        if BONGMATH and step < sigmas.shape[0]-1 and not self.EO("disable_fully_pseudoimplicit_bongmath", extra_options):
                            x_0, x_, eps_ = RK.bong_iter(x_0,
                                                        x_,
                                                        eps_,
                                                        eps_prev_,
                                                        data_,
                                                        sigma,
                                                        NS.s_,
                                                        r,
                                                        RK.row_offset,
                                                        NS.h,
                                                        )
                            
                if self.EO("fully_pseudoimplicit_denoised_prev", extra_options):
                    eps_[r] = RK.get_epsilon(x_0, x_[r], denoised_prev, sigma, NS.s_[r])
                
                eps_substep_guide     = torch.zeros_like(x_0)
                eps_substep_guide_inv = torch.zeros_like(x_0)
                
                if self.HAS_LATENT_GUIDE:
                    eps_substep_guide     = RK.get_guide_epsilon(x_0, x_[r], y0,     sigma, NS.s_[r], NS.sigma_down, None)  
                if self.HAS_LATENT_GUIDE_INV:
                    eps_substep_guide_inv = RK.get_guide_epsilon(x_0, x_[r], y0_inv, sigma, NS.s_[r], NS.sigma_down, None)  
                
                eps_ = self.process_channelwise(x_0,
                                                eps_,
                                                data_,
                                                row,
                                                eps_substep_guide,
                                                eps_substep_guide_inv,
                                                y0,
                                                y0_inv,
                                                lgw_mask,
                                                lgw_mask_inv,
                                                use_projection = self.guide_mode in {"fully_pseudoimplicit_projection", "fully_pseudoimplicit_projection_cw"},
                                                channelwise    = self.guide_mode in {"fully_pseudoimplicit_cw",         "fully_pseudoimplicit_projection_cw"},
                                                )

                x_lying_[r]   = x_[r] + RK.h_fn(fully_sub_sigma_2, NS.sub_sigma) * eps_[r]
                data_lying    = x_[r] + RK.h_fn(0,                 NS.s_[r])     * eps_[r] 
                
                eps_lying_[r] = RK.get_epsilon(x_0, x_[r], data_lying, sigma, NS.s_[r])
                
            if not self.EO("pseudoimplicit_disable_eps_lying", extra_options):
                eps_ = eps_lying_
            
            if not self.EO("pseudoimplicit_disable_newton_iter", extra_options):
                x_, eps_ = RK.newton_iter(x_0,
                                        x_,
                                        eps_,
                                        eps_prev_,
                                        data_,
                                        NS.s_,
                                        0,
                                        NS.h,
                                        sigmas,
                                        step,
                                        "lying",
                                        )
            
            self.x_lying_ = x_lying_
            self.s_lying_ = s_lying_

        return x_0, x_, eps_ 



    @torch.no_grad
    def process_guides_substep(self,
                                x_0,
                                x_,
                                eps_,
                                data_,
                                row,
                                step,
                                sigma,
                                sigma_next,
                                sigma_down,
                                s_,
                                epsilon_scale,
                                RK,
                                extra_options,
                                ):

        y0, y0_inv, lgw_mask, lgw_mask_inv = self.get_cossim_adjusted_lgw_masks(data_[row], step)
        
        if not (lgw_mask.any() != 0 or lgw_mask_inv.any() != 0):  # cossim score too similar! deactivate guide for this step
            return eps_, x_ 

        eps_orig = eps_.clone()
        
        if self.EO("dynamic_guides_mean_std", extra_options):
            y_shift, y_inv_shift = normalize_latent([y0, y0_inv], [data_, data_])
            y0 = y_shift
            if self.EO("dynamic_guides_inv", extra_options):
                y0_inv = y_inv_shift

        if self.EO("dynamic_guides_mean", extra_options):
            y_shift, y_inv_shift = normalize_latent([y0, y0_inv], [data_, data_], std=False)
            y0 = y_shift
            if self.EO("dynamic_guides_inv", extra_options):
                y0_inv = y_inv_shift


        if "data" == self.guide_mode:
            y0_tmp = y0.clone()
            if self.HAS_LATENT_GUIDE:
                y0_tmp = (1-lgw_mask) * data_[row] + lgw_mask * y0
                y0_tmp = (1-lgw_mask_inv) * y0_tmp + lgw_mask_inv * y0_inv
            x_[row+1] = y0_tmp + eps_[row]
            
        if self.guide_mode == "data_projection":

            d_lerp             = data_[row]   +   lgw_mask * (y0-data_[row])   +   lgw_mask_inv * (y0_inv-data_[row])
            
            d_collinear_d_lerp = get_collinear(data_[row], d_lerp)  
            d_lerp_ortho_d     = get_orthogonal(d_lerp, data_[row])  
            
            data_[row]         = d_collinear_d_lerp + d_lerp_ortho_d
            
            x_[row+1]          = data_[row] + eps_[row] * sigma
            


        elif (self.UNSAMPLE or self.guide_mode in {"epsilon", "epsilon_cw", "epsilon_projection", "epsilon_projection_cw"}) and (self.lgw[step] > 0 or self.lgw_inv[step] > 0):
            if sigma_down < sigma   or   s_[row] < RK.sigma_max:
                                
                eps_substep_guide     = torch.zeros_like(x_0)
                eps_substep_guide_inv = torch.zeros_like(x_0)
                
                if self.HAS_LATENT_GUIDE:
                    eps_substep_guide     = RK.get_guide_epsilon(x_0, x_[row], y0,     sigma, s_[row], sigma_down, epsilon_scale)  
                    
                if self.HAS_LATENT_GUIDE_INV:
                    eps_substep_guide_inv = RK.get_guide_epsilon(x_0, x_[row], y0_inv, sigma, s_[row], sigma_down, epsilon_scale)  

                tol_value = self.EO("tol", -1.0)
                if tol_value >= 0:
                    for b, c in itertools.product(range(x_0.shape[0]), range(x_0.shape[1])):
                        current_diff       = torch.norm(data_[row][b][c] - y0    [b][c]) 
                        current_diff_inv   = torch.norm(data_[row][b][c] - y0_inv[b][c]) 
                        
                        lgw_scaled         = torch.nan_to_num(1-(tol_value/current_diff),     0)
                        lgw_scaled_inv     = torch.nan_to_num(1-(tol_value/current_diff_inv), 0)
                        
                        lgw_tmp            = min(self.lgw[step]    , lgw_scaled)
                        lgw_tmp_inv        = min(self.lgw_inv[step], lgw_scaled_inv)

                        lgw_mask_clamp     = torch.clamp(lgw_mask,     max=lgw_tmp)
                        lgw_mask_clamp_inv = torch.clamp(lgw_mask_inv, max=lgw_tmp_inv)

                        eps_[row][b][c]    = eps_[row][b][c] + lgw_mask_clamp[b][c] * (eps_substep_guide[b][c] - eps_[row][b][c]) + lgw_mask_clamp_inv[b][c] * (eps_substep_guide_inv[b][c] - eps_[row][b][c])
                
                elif self.guide_mode in {"epsilon"}: 
                    eps_[row] = eps_[row] + lgw_mask * (eps_substep_guide - eps_[row]) + lgw_mask_inv * (eps_substep_guide_inv - eps_[row])
                    
                elif self.guide_mode in {"epsilon_projection"}:
                    eps_row_lerp           = eps_[row]   +   self.mask * (eps_substep_guide-eps_[row])   +   (1-self.mask) * (eps_substep_guide_inv-eps_[row])

                    eps_collinear_eps_lerp = get_collinear(eps_[row], eps_row_lerp)
                    eps_lerp_ortho_eps     = get_orthogonal(eps_row_lerp, eps_[row])

                    eps_sum                = eps_collinear_eps_lerp + eps_lerp_ortho_eps

                    eps_[row]              = eps_[row] + lgw_mask * (eps_sum - eps_[row]) + lgw_mask_inv * (eps_sum - eps_[row])
                    
                elif self.guide_mode in {"epsilon_cw", "epsilon_projection_cw"}:
                    eps_ = self.process_channelwise(x_0,
                                                    eps_,
                                                    data_,
                                                    row,
                                                    eps_substep_guide,
                                                    eps_substep_guide_inv,
                                                    y0,
                                                    y0_inv,
                                                    lgw_mask,
                                                    lgw_mask_inv,
                                                    use_projection = self.guide_mode == "epsilon_projection_cw",
                                                    channelwise    = True
                                                    )

        temporal_smoothing = self.EO("temporal_smoothing", 0.0)
        if temporal_smoothing > 0:
            eps_[row] = apply_temporal_smoothing(eps_[row], temporal_smoothing)
            
        if self.EO("substep_eps_ch_mean_std", extra_options):
            eps_[row] = normalize_latent(eps_[row], eps_orig[row])
        if self.EO("substep_eps_ch_mean", extra_options):
            eps_[row] = normalize_latent(eps_[row], eps_orig[row], std=False)
        if self.EO("substep_eps_ch_std", extra_options):
            eps_[row] = normalize_latent(eps_[row], eps_orig[row], mean=False)
        if self.EO("substep_eps_mean_std", extra_options):
            eps_[row] = normalize_latent(eps_[row], eps_orig[row], channelwise=False)
        if self.EO("substep_eps_mean", extra_options):
            eps_[row] = normalize_latent(eps_[row], eps_orig[row], std=False, channelwise=False)
        if self.EO("substep_eps_std", extra_options):
            eps_[row] = normalize_latent(eps_[row], eps_orig[row], mean=False, channelwise=False)
        return eps_, x_


    def process_channelwise(self,
                            x_0,
                            eps_,
                            data_,
                            row,
                            eps_substep_guide,
                            eps_substep_guide_inv,
                            y0,
                            y0_inv,
                            lgw_mask,
                            lgw_mask_inv,
                            use_projection = False,
                            channelwise    = False
                            ):
        
        avg, avg_inv = 0, 0
        for b, c in itertools.product(range(x_0.shape[0]), range(x_0.shape[1])):
            avg     += torch.norm(lgw_mask    [b][c] * data_[row][b][c]   -   lgw_mask    [b][c] * y0    [b][c])
            avg_inv += torch.norm(lgw_mask_inv[b][c] * data_[row][b][c]   -   lgw_mask_inv[b][c] * y0_inv[b][c])
            
        avg     /= x_0.shape[1]
        avg_inv /= x_0.shape[1]
        
        for b, c in itertools.product(range(x_0.shape[0]), range(x_0.shape[1])):
            if channelwise:
                ratio     = torch.nan_to_num(torch.norm(lgw_mask    [b][c] * data_[row][b][c] - lgw_mask    [b][c] * y0    [b][c])   /   avg,     0)
                ratio_inv = torch.nan_to_num(torch.norm(lgw_mask_inv[b][c] * data_[row][b][c] - lgw_mask_inv[b][c] * y0_inv[b][c])   /   avg_inv, 0)
            else:
                ratio     = 1.
                ratio_inv = 1.
                    
            eps_[row][b][c]            = eps_[row][b][c]   +   ratio * lgw_mask[b][c] * (eps_substep_guide[b][c] - eps_[row][b][c])   +   ratio_inv * lgw_mask_inv[b][c] * (eps_substep_guide_inv[b][c] - eps_[row][b][c])
            
            if use_projection:
                eps_row_lerp           = eps_[row][b][c]   +          self.mask[b][c] * (eps_substep_guide[b][c] - eps_[row][b][c])   +              (1-self.mask[b][c]) * (eps_substep_guide_inv[b][c] - eps_[row][b][c]) # should this ever be self.mask_inv?

                eps_collinear_eps_lerp = get_collinear (eps_[row][b][c], eps_row_lerp)
                eps_lerp_ortho_eps     = get_orthogonal(eps_row_lerp   , eps_[row][b][c])

                eps_sum                = eps_collinear_eps_lerp + eps_lerp_ortho_eps

                eps_[row][b][c]        = eps_[row][b][c]   +   ratio * lgw_mask[b][c] * (eps_sum                 - eps_[row][b][c])   +   ratio_inv * lgw_mask_inv[b][c] * (eps_sum                     - eps_[row][b][c])
            else:
                eps_[row][b][c]        = eps_[row][b][c]   +   ratio * lgw_mask[b][c] * (eps_substep_guide[b][c] - eps_[row][b][c])   +   ratio_inv * lgw_mask_inv[b][c] * (eps_substep_guide_inv[b][c] - eps_[row][b][c])
                
        return eps_


    @torch.no_grad
    def process_guides_poststep(self, x, denoised, eps, step, extra_options):
        x_orig = x.clone()
        mean_weight = self.EO("mean_weight", 0.01)

        y0, y0_inv, lgw_mask, lgw_mask_inv = self.get_cossim_adjusted_lgw_masks(denoised, step)
        
        if not (lgw_mask.any() != 0 or lgw_mask_inv.any() != 0):  # cossim score too similar! deactivate guide for this step
            return x
        
        mask = self.mask #needed for bitwise mask below
        
        if self.guide_mode in {"epsilon_dynamic_mean_std", "epsilon_dynamic_mean", "epsilon_dynamic_std", "epsilon_dynamic_mean_from_bkg"}:
        
            denoised_masked     = denoised * ((mask==1)*   mask)
            denoised_masked_inv = denoised * ((mask==0)*(1-mask))
            
            
            d_shift, d_shift_inv = torch.zeros_like(x), torch.zeros_like(x)
            
            for b, c in itertools.product(range(x.shape[0]), range(x.shape[1])):
                denoised_mask     = denoised[b][c][mask[b][c] == 1]
                denoised_mask_inv = denoised[b][c][mask[b][c] == 0]
                
                if self.guide_mode == "epsilon_dynamic_mean_std":
                    d_shift[b][c] = (denoised_masked[b][c] - denoised_mask.mean()) / denoised_mask.std()
                    d_shift[b][c] = (d_shift[b][c] * denoised_mask_inv.std()) + denoised_mask_inv.mean()
                    
                elif self.guide_mode == "epsilon_dynamic_mean":
                    d_shift[b][c]     = denoised_masked[b][c]     - denoised_mask.mean()     + denoised_mask_inv.mean()
                    d_shift_inv[b][c] = denoised_masked_inv[b][c] - denoised_mask_inv.mean() + denoised_mask.mean()

                elif self.guide_mode == "epsilon_dynamic_mean_from_bkg":
                    d_shift[b][c] = denoised_masked[b][c] - denoised_mask.mean() + denoised_mask_inv.mean()

            if self.guide_mode in {"epsilon_dynamic_mean_std", "epsilon_dynamic_mean_from_bkg"}:
                denoised_shifted = denoised   +   mean_weight * lgw_mask * (d_shift - denoised_masked) 
            elif self.guide_mode == "epsilon_dynamic_mean":
                denoised_shifted = denoised   +   mean_weight * lgw_mask * (d_shift - denoised_masked)   +   mean_weight * lgw_mask_inv * (d_shift_inv - denoised_masked_inv)
                
            x = denoised_shifted + eps
        
        
        if self.UNSAMPLE is False and (self.HAS_LATENT_GUIDE or self.HAS_LATENT_GUIDE_INV) and self.guide_mode in ("hard_light", "blend", "blend_projection", "mean_std", "mean", "mean_tiled", "std"):
            if self.guide_mode == "hard_light":
                d_shift, d_shift_inv = hard_light_blend(y0, denoised), hard_light_blend(y0_inv, denoised)
            elif self.guide_mode == "blend":
                d_shift, d_shift_inv = y0, y0_inv
                
            elif self.guide_mode == "blend_projection":
                d_lerp = denoised   +   lgw_mask * (y0-denoised)   +   lgw_mask_inv * (y0_inv-denoised)
                
                d_collinear_d_lerp = get_collinear(denoised, d_lerp)  
                d_lerp_ortho_d     = get_orthogonal(d_lerp, denoised)  
                
                denoised_shifted = d_collinear_d_lerp + d_lerp_ortho_d
                x = denoised_shifted + eps
                return x


            elif self.guide_mode == "mean_std":
                d_shift, d_shift_inv = normalize_latent([denoised, denoised], [y0, y0_inv])
            elif self.guide_mode == "mean":
                d_shift, d_shift_inv = normalize_latent([denoised, denoised], [y0, y0_inv], std=False)
            elif self.guide_mode == "std":
                d_shift, d_shift_inv = normalize_latent([denoised, denoised], [y0, y0_inv], mean=False)
            elif self.guide_mode == "mean_tiled":
                mean_tile_size = self.EO("mean_tile", 8)
                y0_tiled       = rearrange(y0,       "b c (h t1) (w t2) -> (t1 t2) b c h w", t1=mean_tile_size, t2=mean_tile_size)
                y0_inv_tiled   = rearrange(y0_inv,   "b c (h t1) (w t2) -> (t1 t2) b c h w", t1=mean_tile_size, t2=mean_tile_size)
                denoised_tiled = rearrange(denoised, "b c (h t1) (w t2) -> (t1 t2) b c h w", t1=mean_tile_size, t2=mean_tile_size)
                d_shift_tiled, d_shift_inv_tiled = torch.zeros_like(y0_tiled), torch.zeros_like(y0_tiled)
                for i in range(y0_tiled.shape[0]):
                    d_shift_tiled[i], d_shift_inv_tiled[i] = normalize_latent([denoised_tiled[i], denoised_tiled[i]], [y0_tiled[i], y0_inv_tiled[i]], std=False)
                d_shift     = rearrange(d_shift_tiled,     "(t1 t2) b c h w -> b c (h t1) (w t2)", t1=mean_tile_size, t2=mean_tile_size)
                d_shift_inv = rearrange(d_shift_inv_tiled, "(t1 t2) b c h w -> b c (h t1) (w t2)", t1=mean_tile_size, t2=mean_tile_size)


            if self.guide_mode in ("hard_light", "blend", "mean_std", "mean", "mean_tiled", "std"):
                if self.HAS_LATENT_GUIDE_INV:
                    denoised_shifted = denoised   +   lgw_mask * (d_shift - denoised)
                else:
                    denoised_shifted = denoised   +   lgw_mask * (d_shift - denoised)   +   lgw_mask_inv * (d_shift_inv - denoised)
            
                if self.EO("poststep_denoised_ch_mean_std"):
                    denoised_shifted = normalize_latent(denoised_shifted, denoised)
                if self.EO("poststep_denoised_ch_mean"):
                    denoised_shifted = normalize_latent(denoised_shifted, denoised, std=False)
                if self.EO("poststep_denoised_ch_std"):
                    denoised_shifted = normalize_latent(denoised_shifted, denoised, mean=False)
                if self.EO("poststep_denoised_mean_std"):
                    denoised_shifted = normalize_latent(denoised_shifted, denoised, channelwise=False)
                if self.EO("poststep_denoised_mean"):
                    denoised_shifted = normalize_latent(denoised_shifted, denoised, std=False, channelwise=False)
                if self.EO("poststep_denoised_std"):
                    denoised_shifted = normalize_latent(denoised_shifted, denoised, mean=False, channelwise=False)

                x = denoised_shifted + eps

        if self.EO("poststep_x_ch_mean_std"):
            x = normalize_latent(x, x_orig)
        if self.EO("poststep_x_ch_mean"):
            x = normalize_latent(x, x_orig, std=False)
        if self.EO("poststep_x_ch_std"):
            x = normalize_latent(x, x_orig, mean=False)
        if self.EO("poststep_x_mean_std"):
            x = normalize_latent(x, x_orig, channelwise=False)
        if self.EO("poststep_x_mean"):
            x = normalize_latent(x, x_orig, std=False, channelwise=False)
        if self.EO("poststep_x_std"):
            x = normalize_latent(x, x_orig, mean=False, channelwise=False)
        return x
    
    
    def normalize_inputs(self, x:Tensor, y0:Tensor, y0_inv:Tensor):
        
        if self.guide_mode == "epsilon_guide_mean_std_from_bkg":
            y0 = normalize_latent(y0, y0_inv)

        input_norm = self.EO("input_norm", "")
        input_std  = self.EO("input_std", 1.0)
                
        if input_norm == "input_ch_mean_set_std_to":
            x = normalize_latent(x, set_std=input_std)

        if input_norm == "input_ch_set_std_to":
            x = normalize_latent(x, set_std=input_std, mean=False)
                
        if input_norm == "input_mean_set_std_to":
            x = normalize_latent(x, set_std=input_std, channelwise=False)
            
        if input_norm == "input_std_set_std_to":
            x = normalize_latent(x, set_std=input_std, mean=False, channelwise=False)
        
        return x, y0, y0_inv



def apply_frame_weights(mask, frame_weights):
    if frame_weights is not None:
        for f in range(mask.shape[2]):
            frame_weight = frame_weights[f]
            mask[..., f:f+1, :, :] *= frame_weight


def prepare_mask(x, mask, LGW_MASK_RESCALE_MIN) -> tuple[torch.Tensor, bool]:
    if mask is None:
        mask = torch.ones_like(x)
        LGW_MASK_RESCALE_MIN = False
        return mask, LGW_MASK_RESCALE_MIN
    
    spatial_mask = mask.unsqueeze(1)
    target_height = x.shape[-2]
    target_width = x.shape[-1]
    spatial_mask = F.interpolate(spatial_mask, size=(target_height, target_width), mode='bilinear', align_corners=False)

    while spatial_mask.dim() < x.dim():
        spatial_mask = spatial_mask.unsqueeze(2)
    
    repeat_shape = [1] #batch
    for i in range(1, x.dim() - 2):
        repeat_shape.append(x.shape[i])
    repeat_shape.extend([1, 1]) #height and width

    mask = spatial_mask.repeat(*repeat_shape).to(x.dtype)
    
    del spatial_mask
    return mask, LGW_MASK_RESCALE_MIN
    
def apply_temporal_smoothing(tensor, temporal_smoothing):
    if temporal_smoothing <= 0 or tensor.dim() != 5:
        return tensor

    kernel_size = 5
    padding = kernel_size // 2
    temporal_kernel = torch.tensor(
        [0.1, 0.2, 0.4, 0.2, 0.1],
        device=tensor.device, dtype=tensor.dtype
    ) * temporal_smoothing
    temporal_kernel[kernel_size//2] += (1 - temporal_smoothing)
    temporal_kernel = temporal_kernel / temporal_kernel.sum()

    # resahpe for conv1d
    b, c, f, h, w = tensor.shape
    data_flat = tensor.permute(0, 1, 3, 4, 2).reshape(-1, f)

    # apply smoohting
    data_smooth = F.conv1d(
        data_flat.unsqueeze(1),
        temporal_kernel.view(1, 1, -1),
        padding=padding
    ).squeeze(1)

    return data_smooth.view(b, c, h, w, f).permute(0, 1, 4, 2, 3)

def get_guide_epsilon_substep(x_0, x_, y0, y0_inv, s_, row, row_offset, rk_type, b=None, c=None):
    s_in = x_0.new_ones([x_0.shape[0]])
    
    if b is not None and c is not None:  
        index = (b, c)
    elif b is not None: 
        index = (b,)
    else: 
        index = ()

    if RK_Method_Beta.is_exponential(rk_type):
        eps_row     =  y0    [index] -  x_0[index]
        eps_row_inv =  y0_inv[index] -  x_0[index]
    else:
        eps_row     = (x_[row][index] - y0    [index]) / (s_[row] * s_in) # was row+row_offset before for x_!!   not right...     also? potential issues here with x_[row+1] being RK.rows+2 with gauss-legendre_2s 1 imp step 1 imp substep
        eps_row_inv = (x_[row][index] - y0_inv[index]) / (s_[row] * s_in)
    
    return eps_row, eps_row_inv

def get_guide_epsilon(x_0, x_, y0, sigma, rk_type, b=None, c=None):
    s_in = x_0.new_ones([x_0.shape[0]])
    
    if b is not None and c is not None:  
        index = (b, c)
    elif b is not None: 
        index = (b,)
    else: 
        index = ()

    if RK_Method_Beta.is_exponential(rk_type):
        eps     = y0    [index] - x_0[index]
    else:
        eps     = (x_[index] - y0    [index]) / (sigma * s_in)
    
    return eps



@torch.no_grad
def noise_cossim_guide_tiled(x_list, guide, cossim_mode="forward", tile_size=2, step=0):

    guide_tiled = rearrange(guide, "b c (h t1) (w t2) -> b (t1 t2) c h w", t1=tile_size, t2=tile_size)

    x_tiled_list = [
        rearrange(x, "b c (h t1) (w t2) -> b (t1 t2) c h w", t1=tile_size, t2=tile_size)
        for x in x_list
    ]
    x_tiled_stack = torch.stack([x_tiled[0] for x_tiled in x_tiled_list])  # [n_x, n_tiles, c, h, w]

    guide_flat = guide_tiled[0].view(guide_tiled.shape[1], -1).unsqueeze(0)  # [1, n_tiles, c*h*w]
    x_flat = x_tiled_stack.view(x_tiled_stack.size(0), x_tiled_stack.size(1), -1)  # [n_x, n_tiles, c*h*w]

    cossim_tmp_all = F.cosine_similarity(x_flat, guide_flat, dim=-1)  # [n_x, n_tiles]

    if cossim_mode == "forward":
        indices = cossim_tmp_all.argmax(dim=0) 
    elif cossim_mode == "reverse":
        indices = cossim_tmp_all.argmin(dim=0) 
    elif cossim_mode == "orthogonal":
        indices = torch.abs(cossim_tmp_all).argmin(dim=0) 
    elif cossim_mode == "forward_reverse":
        if step % 2 == 0:
            indices = cossim_tmp_all.argmax(dim=0)
        else:
            indices = cossim_tmp_all.argmin(dim=0)
    elif cossim_mode == "reverse_forward":
        if step % 2 == 1:
            indices = cossim_tmp_all.argmax(dim=0)
        else:
            indices = cossim_tmp_all.argmin(dim=0)
    elif cossim_mode == "orthogonal_reverse":
        if step % 2 == 0:
            indices = torch.abs(cossim_tmp_all).argmin(dim=0)
        else:
            indices = cossim_tmp_all.argmin(dim=0)
    elif cossim_mode == "reverse_orthogonal":
        if step % 2 == 1:
            indices = torch.abs(cossim_tmp_all).argmin(dim=0)
        else:
            indices = cossim_tmp_all.argmin(dim=0)
    else:
        target_value = float(cossim_mode)
        indices = torch.abs(cossim_tmp_all - target_value).argmin(dim=0)  

    x_tiled_out = x_tiled_stack[indices, torch.arange(indices.size(0))]  # [n_tiles, c, h, w]

    x_tiled_out = x_tiled_out.unsqueeze(0) 
    x_detiled = rearrange(x_tiled_out, "b (t1 t2) c h w -> b c (h t1) (w t2)", t1=tile_size, t2=tile_size)

    return x_detiled


@torch.no_grad
def noise_cossim_eps_tiled(x_list, eps, noise_list, cossim_mode="forward", tile_size=2, step=0):

    eps_tiled = rearrange(eps, "b c (h t1) (w t2) -> b (t1 t2) c h w", t1=tile_size, t2=tile_size)
    x_tiled_list = [
        rearrange(x, "b c (h t1) (w t2) -> b (t1 t2) c h w", t1=tile_size, t2=tile_size)
        for x in x_list
    ]
    noise_tiled_list = [
        rearrange(noise, "b c (h t1) (w t2) -> b (t1 t2) c h w", t1=tile_size, t2=tile_size)
        for noise in noise_list
    ]

    noise_tiled_stack = torch.stack([noise_tiled[0] for noise_tiled in noise_tiled_list])  # [n_x, n_tiles, c, h, w]
    eps_expanded = eps_tiled[0].view(eps_tiled.shape[1], -1).unsqueeze(0)  # [1, n_tiles, c*h*w]
    noise_flat = noise_tiled_stack.view(noise_tiled_stack.size(0), noise_tiled_stack.size(1), -1)  # [n_x, n_tiles, c*h*w]
    cossim_tmp_all = F.cosine_similarity(noise_flat, eps_expanded, dim=-1)  # [n_x, n_tiles]

    if cossim_mode == "forward":
        indices = cossim_tmp_all.argmax(dim=0)  
    elif cossim_mode == "reverse":
        indices = cossim_tmp_all.argmin(dim=0) 
    elif cossim_mode == "orthogonal":
        indices = torch.abs(cossim_tmp_all).argmin(dim=0) 
    elif cossim_mode == "orthogonal_pos":
        positive_mask = cossim_tmp_all > 0
        positive_tmp = torch.where(positive_mask, cossim_tmp_all, torch.full_like(cossim_tmp_all, float('inf')))
        indices = positive_tmp.argmin(dim=0)
    elif cossim_mode == "orthogonal_neg":
        negative_mask = cossim_tmp_all < 0
        negative_tmp = torch.where(negative_mask, cossim_tmp_all, torch.full_like(cossim_tmp_all, float('-inf')))
        indices = negative_tmp.argmax(dim=0)
    elif cossim_mode == "orthogonal_posneg":
        if step % 2 == 0:
            positive_mask = cossim_tmp_all > 0
            positive_tmp = torch.where(positive_mask, cossim_tmp_all, torch.full_like(cossim_tmp_all, float('inf')))
            indices = positive_tmp.argmin(dim=0)
        else:
            negative_mask = cossim_tmp_all < 0
            negative_tmp = torch.where(negative_mask, cossim_tmp_all, torch.full_like(cossim_tmp_all, float('-inf')))
            indices = negative_tmp.argmax(dim=0)
    elif cossim_mode == "orthogonal_negpos":
        if step % 2 == 1:
            positive_mask = cossim_tmp_all > 0
            positive_tmp = torch.where(positive_mask, cossim_tmp_all, torch.full_like(cossim_tmp_all, float('inf')))
            indices = positive_tmp.argmin(dim=0)
        else:
            negative_mask = cossim_tmp_all < 0
            negative_tmp = torch.where(negative_mask, cossim_tmp_all, torch.full_like(cossim_tmp_all, float('-inf')))
            indices = negative_tmp.argmax(dim=0)
    elif cossim_mode == "forward_reverse":
        if step % 2 == 0:
            indices = cossim_tmp_all.argmax(dim=0)
        else:
            indices = cossim_tmp_all.argmin(dim=0)
    elif cossim_mode == "reverse_forward":
        if step % 2 == 1:
            indices = cossim_tmp_all.argmax(dim=0)
        else:
            indices = cossim_tmp_all.argmin(dim=0)
    elif cossim_mode == "orthogonal_reverse":
        if step % 2 == 0:
            indices = torch.abs(cossim_tmp_all).argmin(dim=0)
        else:
            indices = cossim_tmp_all.argmin(dim=0)
    elif cossim_mode == "reverse_orthogonal":
        if step % 2 == 1:
            indices = torch.abs(cossim_tmp_all).argmin(dim=0)
        else:
            indices = cossim_tmp_all.argmin(dim=0)
    else:
        target_value = float(cossim_mode)
        indices = torch.abs(cossim_tmp_all - target_value).argmin(dim=0)
    #else:
    #    raise ValueError(f"Unknown cossim_mode: {cossim_mode}")

    x_tiled_stack = torch.stack([x_tiled[0] for x_tiled in x_tiled_list])  # [n_x, n_tiles, c, h, w]
    x_tiled_out = x_tiled_stack[indices, torch.arange(indices.size(0))]  # [n_tiles, c, h, w]

    x_tiled_out = x_tiled_out.unsqueeze(0)  # restore batch dim
    x_detiled = rearrange(x_tiled_out, "b (t1 t2) c h w -> b c (h t1) (w t2)", t1=tile_size, t2=tile_size)
    return x_detiled



@torch.no_grad
def noise_cossim_guide_eps_tiled(x_0, x_list, y0, noise_list, cossim_mode="forward", tile_size=2, step=0, sigma=None, rk_type=None):

    x_tiled_stack = torch.stack([
        rearrange(x, "b c (h t1) (w t2) -> b (t1 t2) c h w", t1=tile_size, t2=tile_size)[0]
        for x in x_list
    ])  # [n_x, n_tiles, c, h, w]
    eps_guide_stack = torch.stack([
        rearrange(x - y0, "b c (h t1) (w t2) -> b (t1 t2) c h w", t1=tile_size, t2=tile_size)[0]
        for x in x_list
    ])  # [n_x, n_tiles, c, h, w]
    del x_list

    noise_tiled_stack = torch.stack([
        rearrange(noise, "b c (h t1) (w t2) -> b (t1 t2) c h w", t1=tile_size, t2=tile_size)[0]
        for noise in noise_list
    ])  # [n_x, n_tiles, c, h, w]
    del noise_list

    noise_flat = noise_tiled_stack.view(noise_tiled_stack.size(0), noise_tiled_stack.size(1), -1)  # [n_x, n_tiles, c*h*w]
    eps_guide_flat = eps_guide_stack.view(eps_guide_stack.size(0), eps_guide_stack.size(1), -1)  # [n_x, n_tiles, c*h*w]

    cossim_tmp_all = F.cosine_similarity(noise_flat, eps_guide_flat, dim=-1)  # [n_x, n_tiles]
    del noise_tiled_stack, noise_flat, eps_guide_stack, eps_guide_flat

    if cossim_mode == "forward":
        indices = cossim_tmp_all.argmax(dim=0) 
    elif cossim_mode == "reverse":
        indices = cossim_tmp_all.argmin(dim=0) 
    elif cossim_mode == "orthogonal":
        indices = torch.abs(cossim_tmp_all).argmin(dim=0) 
    elif cossim_mode == "orthogonal_pos":
        positive_mask = cossim_tmp_all > 0
        positive_tmp = torch.where(positive_mask, cossim_tmp_all, torch.full_like(cossim_tmp_all, float('inf')))
        indices = positive_tmp.argmin(dim=0)
    elif cossim_mode == "orthogonal_neg":
        negative_mask = cossim_tmp_all < 0
        negative_tmp = torch.where(negative_mask, cossim_tmp_all, torch.full_like(cossim_tmp_all, float('-inf')))
        indices = negative_tmp.argmax(dim=0)
    elif cossim_mode == "orthogonal_posneg":
        if step % 2 == 0:
            positive_mask = cossim_tmp_all > 0
            positive_tmp = torch.where(positive_mask, cossim_tmp_all, torch.full_like(cossim_tmp_all, float('inf')))
            indices = positive_tmp.argmin(dim=0)
        else:
            negative_mask = cossim_tmp_all < 0
            negative_tmp = torch.where(negative_mask, cossim_tmp_all, torch.full_like(cossim_tmp_all, float('-inf')))
            indices = negative_tmp.argmax(dim=0)
    elif cossim_mode == "orthogonal_negpos":
        if step % 2 == 1:
            positive_mask = cossim_tmp_all > 0
            positive_tmp = torch.where(positive_mask, cossim_tmp_all, torch.full_like(cossim_tmp_all, float('inf')))
            indices = positive_tmp.argmin(dim=0)
        else:
            negative_mask = cossim_tmp_all < 0
            negative_tmp = torch.where(negative_mask, cossim_tmp_all, torch.full_like(cossim_tmp_all, float('-inf')))
            indices = negative_tmp.argmax(dim=0)
    elif cossim_mode == "forward_reverse":
        if step % 2 == 0:
            indices = cossim_tmp_all.argmax(dim=0)
        else:
            indices = cossim_tmp_all.argmin(dim=0)
    elif cossim_mode == "reverse_forward":
        if step % 2 == 1:
            indices = cossim_tmp_all.argmax(dim=0)
        else:
            indices = cossim_tmp_all.argmin(dim=0)
    elif cossim_mode == "orthogonal_reverse":
        if step % 2 == 0:
            indices = torch.abs(cossim_tmp_all).argmin(dim=0)
        else:
            indices = cossim_tmp_all.argmin(dim=0)
    elif cossim_mode == "reverse_orthogonal":
        if step % 2 == 1:
            indices = torch.abs(cossim_tmp_all).argmin(dim=0)
        else:
            indices = cossim_tmp_all.argmin(dim=0)
    else:
        target_value = float(cossim_mode)
        indices = torch.abs(cossim_tmp_all - target_value).argmin(dim=0)  

    x_tiled_out = x_tiled_stack[indices, torch.arange(indices.size(0))]  # [n_tiles, c, h, w]
    del x_tiled_stack

    x_tiled_out = x_tiled_out.unsqueeze(0)  
    x_detiled = rearrange(x_tiled_out, "b (t1 t2) c h w -> b c (h t1) (w t2)", t1=tile_size, t2=tile_size)

    return x_detiled



def get_collinear(x, y):

    y_flat = y.view(y.size(0), -1).clone()
    x_flat = x.view(x.size(0), -1).clone()

    y_flat /= y_flat.norm(dim=-1, keepdim=True)
    x_proj_y = torch.sum(x_flat * y_flat, dim=-1, keepdim=True) * y_flat

    return x_proj_y.view_as(x)


def get_orthogonal(x, y):

    y_flat = y.view(y.size(0), -1).clone()
    x_flat = x.view(x.size(0), -1).clone()

    y_flat /= y_flat.norm(dim=-1, keepdim=True)
    x_proj_y = torch.sum(x_flat * y_flat, dim=-1, keepdim=True) * y_flat
    
    x_ortho_y = x_flat - x_proj_y 

    return x_ortho_y.view_as(x)



def get_orthogonal_noise_from_channelwise(*refs, max_iter=500, max_score=1e-15):
    noise, *refs = refs
    noise_tmp = noise.clone()
    #b,c,h,w = noise.shape
    if (noise.dim() == 4):
        b,ch,h,w = noise.shape
    elif (noise.dim() == 5):
        b,ch,t,h,w = noise.shape
    
    for i in range(max_iter):
        noise_tmp = gram_schmidt_channels_optimized(noise_tmp, *refs)
        
        cossim_scores = []
        for ref in refs:
            #for c in range(noise.shape[-3]):
            for c in range(ch):
                cossim_scores.append(get_cosine_similarity(noise_tmp[0][c], ref[0][c]).abs())
            cossim_scores.append(get_cosine_similarity(noise_tmp[0], ref[0]).abs())
            
        if max(cossim_scores) < max_score:
            break
    
    return noise_tmp



def gram_schmidt_channels_optimized(A, *refs):
    if (A.dim() == 4):
        b,c,h,w = A.shape
    elif (A.dim() == 5):
        b,c,t,h,w = A.shape

    A_flat = A.view(b, c, -1)  
    
    for ref in refs:
        ref_flat = ref.view(b, c, -1).clone()  

        ref_flat /= ref_flat.norm(dim=-1, keepdim=True) 

        proj_coeff = torch.sum(A_flat * ref_flat, dim=-1, keepdim=True)  
        projection = proj_coeff * ref_flat 

        A_flat -= projection

    return A_flat.view_as(A)



class NoiseStepHandlerOSDE:
    def __init__(self, x, eps=None, data=None, x_init=None, guide=None, guide_bkg=None):
        self.noise = None
        self.x = x
        self.eps = eps
        self.data = data
        self.x_init = x_init
        self.guide = guide
        self.guide_bkg = guide_bkg
        
        self.eps_list = None

        self.noise_cossim_map = {
            "eps_orthogonal":              [self.noise, self.eps],
            "eps_data_orthogonal":         [self.noise, self.eps, self.data],

            "data_orthogonal":             [self.noise, self.data],
            "xinit_orthogonal":            [self.noise, self.x_init],
            
            "x_orthogonal":                [self.noise, self.x],
            "x_data_orthogonal":           [self.noise, self.x, self.data],
            "x_eps_orthogonal":            [self.noise, self.x, self.eps],

            "x_eps_data_orthogonal":       [self.noise, self.x, self.eps, self.data],
            "x_eps_data_xinit_orthogonal": [self.noise, self.x, self.eps, self.data, self.x_init],
            
            "x_eps_guide_orthogonal":      [self.noise, self.x, self.eps, self.guide],
            "x_eps_guide_bkg_orthogonal":  [self.noise, self.x, self.eps, self.guide_bkg],
            
            "noise_orthogonal":            [self.noise, self.x_init],
            
            "guide_orthogonal":            [self.noise, self.guide],
            "guide_bkg_orthogonal":        [self.noise, self.guide_bkg],
        }

    def check_cossim_source(self, source):
        return source in self.noise_cossim_map

    def get_ortho_noise(self, noise, prev_noises=None, max_iter=100, max_score=1e-7, NOISE_COSSIM_SOURCE="eps_orthogonal"):
        
        if NOISE_COSSIM_SOURCE not in self.noise_cossim_map:
            raise ValueError(f"Invalid NOISE_COSSIM_SOURCE: {NOISE_COSSIM_SOURCE}")
        
        self.noise_cossim_map[NOISE_COSSIM_SOURCE][0] = noise

        params = self.noise_cossim_map[NOISE_COSSIM_SOURCE]
        
        noise = get_orthogonal_noise_from_channelwise(*params, max_iter=max_iter, max_score=max_score)
        
        return noise


# NOTE: NS AND SUBSTEP ADDED!
def handle_tiled_etc_noise_steps(
                                x_0,
                                x,
                                x_prenoise,
                                x_init,
                                eps,
                                denoised,
                                y0,
                                y0_inv,
                                step,
                                rk_type,
                                RK,
                                NS,
                                SUBSTEP,
                                sigma_up,
                                sigma,
                                sigma_next,
                                alpha_ratio,
                                s_noise,
                                noise_mode,
                                SDE_NOISE_EXTERNAL,
                                sde_noise_t,
                                NOISE_COSSIM_SOURCE,
                                NOISE_COSSIM_MODE,
                                noise_cossim_tile_size,
                                noise_cossim_iterations,
                                extra_options):
    
    EO = ExtraOptions(extra_options)
    
    x_tmp          = []
    cossim_tmp     = []
    noise_tmp_list = []
    
    #if step > int(get_extra_options_kv("noise_cossim_end_step", "10000", extra_options)):
    if step > EO("noise_cossim_end_step", MAX_STEPS):
        NOISE_COSSIM_SOURCE = EO("noise_cossim_takeover_source", "eps")
        NOISE_COSSIM_MODE   = EO("noise_cossim_takeover_mode", "forward", extra_options)
        noise_cossim_tile_size   = EO("noise_cossim_takeover_tile", noise_cossim_tile_size, extra_options)
        noise_cossim_iterations   = EO("noise_cossim_takeover_iterations", noise_cossim_iterations, extra_options)
        
    for i in range(noise_cossim_iterations):
        #x_tmp.append(NS.swap_noise(x_0, x, sigma, sigma, sigma_next, ))
        x_tmp.append(NS.add_noise_post(x, sigma_up, sigma, sigma_next, alpha_ratio, s_noise, noise_mode, SDE_NOISE_EXTERNAL, sde_noise_t)    )#y0, lgw, sigma_down are currently unused
        noise_tmp = x_tmp[i] - x
        if extra_options_flag("noise_noise_zscore_norm", extra_options):
            noise_tmp = (noise_tmp - noise_tmp.mean()) / noise_tmp.std()
        if extra_options_flag("noise_eps_zscore_norm", extra_options):
            eps = (eps - eps.mean()) / eps.std()
        if   NOISE_COSSIM_SOURCE in ("eps_tiled", "guide_epsilon_tiled", "guide_bkg_epsilon_tiled", "iig_tiled"):
            noise_tmp_list.append(noise_tmp)
        if   NOISE_COSSIM_SOURCE == "eps":
            cossim_tmp.append(get_cosine_similarity(eps, noise_tmp))
        if   NOISE_COSSIM_SOURCE == "eps_ch":
            cossim_total = torch.zeros_like(eps[0][0][0][0])
            for ch in range(eps.shape[1]):
                cossim_total += get_cosine_similarity(eps[0][ch], noise_tmp[0][ch])
            cossim_tmp.append(cossim_total)
        elif NOISE_COSSIM_SOURCE == "data":
            cossim_tmp.append(get_cosine_similarity(denoised, noise_tmp))
        elif NOISE_COSSIM_SOURCE == "latent":
            cossim_tmp.append(get_cosine_similarity(x_prenoise, noise_tmp))
        elif NOISE_COSSIM_SOURCE == "x_prenoise":
            cossim_tmp.append(get_cosine_similarity(x_prenoise, x_tmp[i]))
        elif NOISE_COSSIM_SOURCE == "x":
            cossim_tmp.append(get_cosine_similarity(x, x_tmp[i]))
        elif NOISE_COSSIM_SOURCE == "x_data":
            cossim_tmp.append(get_cosine_similarity(denoised, x_tmp[i]))
        elif NOISE_COSSIM_SOURCE == "x_init_vs_noise":
            cossim_tmp.append(get_cosine_similarity(x_init, noise_tmp))
        elif NOISE_COSSIM_SOURCE == "mom":
            cossim_tmp.append(get_cosine_similarity(denoised, x + sigma_next*noise_tmp))
        elif NOISE_COSSIM_SOURCE == "guide":
            cossim_tmp.append(get_cosine_similarity(y0, x_tmp[i]))
        elif NOISE_COSSIM_SOURCE == "guide_bkg":
            cossim_tmp.append(get_cosine_similarity(y0_inv, x_tmp[i]))
            
    if step < int(get_extra_options_kv("noise_cossim_start_step", "0", extra_options)):
        x = x_tmp[0]

    elif (NOISE_COSSIM_SOURCE == "eps_tiled"):
        x = noise_cossim_eps_tiled(x_tmp, eps, noise_tmp_list, cossim_mode=NOISE_COSSIM_MODE, tile_size=noise_cossim_tile_size, step=step)
    elif (NOISE_COSSIM_SOURCE == "guide_epsilon_tiled"):
        x = noise_cossim_guide_eps_tiled(x_0, x_tmp, y0, noise_tmp_list, cossim_mode=NOISE_COSSIM_MODE, tile_size=noise_cossim_tile_size, step=step, sigma=sigma, rk_type=rk_type)
    elif (NOISE_COSSIM_SOURCE == "guide_bkg_epsilon_tiled"):
        x = noise_cossim_guide_eps_tiled(x_0, x_tmp, y0_inv, noise_tmp_list, cossim_mode=NOISE_COSSIM_MODE, tile_size=noise_cossim_tile_size, step=step, sigma=sigma, rk_type=rk_type)
    elif (NOISE_COSSIM_SOURCE == "guide_tiled"):
        x = noise_cossim_guide_tiled(x_tmp, y0, cossim_mode=NOISE_COSSIM_MODE, tile_size=noise_cossim_tile_size, step=step)
    elif (NOISE_COSSIM_SOURCE == "guide_bkg_tiled"):
        x = noise_cossim_guide_tiled(x_tmp, y0_inv, cossim_mode=NOISE_COSSIM_MODE, tile_size=noise_cossim_tile_size)
    else:
        for i in range(len(x_tmp)):
            if   (NOISE_COSSIM_MODE == "forward") and (cossim_tmp[i] == max(cossim_tmp)):
                x = x_tmp[i]
                break
            elif (NOISE_COSSIM_MODE == "reverse") and (cossim_tmp[i] == min(cossim_tmp)):
                x = x_tmp[i]
                break
            elif (NOISE_COSSIM_MODE == "orthogonal") and (abs(cossim_tmp[i]) == min(abs(val) for val in cossim_tmp)):
                x = x_tmp[i]
                break
            elif (NOISE_COSSIM_MODE != "forward") and (NOISE_COSSIM_MODE != "reverse") and (NOISE_COSSIM_MODE != "orthogonal"):
                x = x_tmp[0]
                break
    return x





def get_masked_epsilon_projection(x_0, x_, eps_, y0, y0_inv, s_, row, row_offset, rk_type, LG, step):
    
    eps_row, eps_row_inv = get_guide_epsilon_substep(x_0, x_, y0, y0_inv, s_, row, row_offset, rk_type)
    eps_row_lerp = eps_[row]   +   LG.mask * (eps_row-eps_[row])   +   (1-LG.mask) * (eps_row_inv-eps_[row])
    eps_collinear_eps_lerp = get_collinear(eps_[row], eps_row_lerp)
    eps_lerp_ortho_eps     = get_orthogonal(eps_row_lerp, eps_[row])
    eps_sum = eps_collinear_eps_lerp + eps_lerp_ortho_eps
    lgw_mask, lgw_mask_inv = LG.get_masks_for_step(step)
    eps_substep_guide = eps_[row] + lgw_mask * (eps_sum - eps_[row]) + lgw_mask_inv * (eps_sum - eps_[row])
    return eps_substep_guide



