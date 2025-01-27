import torch
import copy
import math

from .extra_samplers_helpers import get_deis_coeff_list
from .phi_functions import *

from .helper import get_extra_options_kv, extra_options_flag


from itertools import permutations, combinations
import random



RK_SAMPLER_NAMES_BETA = ["none",
                    "res_2m",
                    "res_3m",
                    "res_2s_rkmk2e", 
                    "res_2s", 
                    "res_3s",
                    "res_3s_alt",
                    "res_3s_cox_matthews",
                    "res_3s_lie",

                    "res_3s_strehmel_weiner",
                    "res_4s_krogstad",
                    "res_4s_strehmel_weiner",
                    "res_4s_cox_matthews",
                    "res_4s_cfree4",
                    "res_4s_friedli",
                    "res_4s_minchev",
                    "res_4s_munthe-kaas",

                    "res_5s",
                    "res_6s",
                    "res_8s",
                    "res_8s_alt",

                    "res_10s",
                    "res_15s",
                    "res_16s",
                    
                    "etdrk2_2s",
                    "etdrk3_a_3s",
                    "etdrk3_b_3s",
                    "etdrk4_4s",
                    
                    "pec423_2h2s",
                    "pec433_2h3s",
                    
                    "abnorsett2_1h2s",
                    "abnorsett3_2h2s",
                    "abnorsett4_3h2s",

                    "abnorsett_2m",
                    "abnorsett_3m",
                    "abnorsett_4m",


                    "deis_2m",
                    "deis_3m", 
                    "deis_4m",
                    
                    "ralston_2s",
                    "ralston_3s",
                    "ralston_4s", 
                    
                    "dpmpp_2m",
                    "dpmpp_3m",
                    "dpmpp_2s",
                    "dpmpp_sde_2s",
                    "dpmpp_3s",
                    
                    "lawson2a_2s",
                    "lawson2b_2s",

                    "lawson4_4s",
                    "lawson41-gen_4s",
                    "lawson41-gen-mod_4s",
                    
                    "lawson42-gen-mod_1h4s",
                    "lawson43-gen-mod_2h4s",
                    "lawson44-gen-mod_3h4s",
                    "lawson45-gen-mod_4h4s",
                    
                    "midpoint_2s",
                    "heun_2s", 
                    "heun_3s", 
                    
                    "houwen-wray_3s",
                    "kutta_3s", 
                    "ssprk3_3s",
                    "ssprk4_4s",
                    
                    "rk38_4s",
                    "rk4_4s", 
                    "rk5_7s",
                    "rk6_7s",

                    "bogacki-shampine_4s",
                    "bogacki-shampine_7s",

                    "dormand-prince_6s", 
                    "dormand-prince_13s", 

                    "tsi_7s",
                    #"verner_robust_16s",

                    "ddim",
                    "euler",
                    ]


IRK_SAMPLER_NAMES_BETA = ["none",
                    "use_explicit", 
                    
                    "irk_exp_diag_2s",
                    
                    "gauss-legendre_2s",
                    "gauss-legendre_3s", 
                    "gauss-legendre_4s",
                    "gauss-legendre_5s",
                    
                    "radau_ia_2s",
                    "radau_ia_3s",
                    "radau_iia_2s",
                    "radau_iia_3s",
                    
                    "lobatto_iiia_2s",
                    "lobatto_iiia_3s",
                    "lobatto_iiia_4s",
                    "lobatto_iiib_2s",
                    "lobatto_iiib_3s",
                    "lobatto_iiib_4s",

                    "lobatto_iiic_2s",
                    "lobatto_iiic_3s",
                    "lobatto_iiic_4s",

                    "lobatto_iiic_star_2s",
                    "lobatto_iiic_star_3s",
                    "lobatto_iiid_2s",
                    "lobatto_iiid_3s",
                    
                    "kraaijevanger_spijker_2s",
                    "qin_zhang_2s",
                    
                    "pareschi_russo_2s",
                    "pareschi_russo_alt_2s",
                    
                    "crouzeix_2s",
                    "crouzeix_3s",
                    "crouzeix_3s_alt",

                    ]

alpha_crouzeix  = (2/(3**0.5)) * math.cos(math.pi / 18)
gamma_crouzeix = (1/(3**0.5)) * math.cos(math.pi / 18) + 1/2 # Crouzeix & Raviart 1980; A-stable; pg 100 in Solving Ordinary Differential Equations II
delta_crouzeix = 1 / (6 * (2 * gamma_crouzeix - 1)**2)       # Crouzeix & Raviart 1980; A-stable; pg 100 in Solving Ordinary Differential Equations II

rk_coeff = {
    "gauss-legendre_5s": (
    [
        [4563950663 / 32115191526, 
         (310937500000000 / 2597974476091533 + 45156250000 * (739**0.5) / 8747388808389), 
         (310937500000000 / 2597974476091533 - 45156250000 * (739**0.5) / 8747388808389),
         (5236016175 / 88357462711 + 709703235 * (739**0.5) / 353429850844),
         (5236016175 / 88357462711 - 709703235 * (739**0.5) / 353429850844)],
         
        [(4563950663 / 32115191526 - 38339103 * (739**0.5) / 6250000000),
         (310937500000000 / 2597974476091533 + 9557056475401 * (739**0.5) / 3498955523355600000),
         (310937500000000 / 2597974476091533 - 14074198220719489 * (739**0.5) / 3498955523355600000),
         (5236016175 / 88357462711 + 5601362553163918341 * (739**0.5) / 2208936567775000000000),
         (5236016175 / 88357462711 - 5040458465159165409 * (739**0.5) / 2208936567775000000000)],
         
        [(4563950663 / 32115191526 + 38339103 * (739**0.5) / 6250000000),
         (310937500000000 / 2597974476091533 + 14074198220719489 * (739**0.5) / 3498955523355600000),
         (310937500000000 / 2597974476091533 - 9557056475401 * (739**0.5) / 3498955523355600000),
         (5236016175 / 88357462711 + 5040458465159165409 * (739**0.5) / 2208936567775000000000),
         (5236016175 / 88357462711 - 5601362553163918341 * (739**0.5) / 2208936567775000000000)],
         
        [(4563950663 / 32115191526 - 38209 * (739**0.5) / 7938810),
         (310937500000000 / 2597974476091533 - 359369071093750 * (739**0.5) / 70145310854471391),
         (310937500000000 / 2597974476091533 - 323282178906250 * (739**0.5) / 70145310854471391),
         (5236016175 / 88357462711 - 470139 * (739**0.5) / 1413719403376),
         (5236016175 / 88357462711 - 44986764863 * (739**0.5) / 21205791050640)],
         
        [(4563950663 / 32115191526 + 38209 * (739**0.5) / 7938810),
         (310937500000000 / 2597974476091533 + 359369071093750 * (739**0.5) / 70145310854471391),
         (310937500000000 / 2597974476091533 + 323282178906250 * (739**0.5) / 70145310854471391),
         (5236016175 / 88357462711 + 44986764863 * (739**0.5) / 21205791050640),
         (5236016175 / 88357462711 + 470139 * (739**0.5) / 1413719403376)],
    ],
    [
        
        [4563950663 / 16057595763,
         621875000000000 / 2597974476091533,
         621875000000000 / 2597974476091533,
         10472032350 / 88357462711,
         10472032350 / 88357462711]
    ],
    [
        1 / 2,
        1 / 2 - 99 * (739**0.5) / 10000,
        1 / 2 + 99 * (739**0.5) / 10000,
        1 / 2 - (739**0.5) / 60,
        1 / 2 + (739**0.5) / 60
    ]
    ),
    "gauss-legendre_4s": (
        [
            [1/4, 1/4 - 15**0.5 / 6, 1/4 + 15**0.5 / 6, 1/4],            
            [1/4 + 15**0.5 / 6, 1/4, 1/4 - 15**0.5 / 6, 1/4],          
            [1/4, 1/4 + 15**0.5 / 6, 1/4, 1/4 - 15**0.5 / 6],            
            [1/4 - 15**0.5 / 6, 1/4, 1/4 + 15**0.5 / 6, 1/4],       
        ],
        [    
            [1/8, 3/8, 3/8, 1/8]                                        
        ],
        [
            1/2 - 15**0.5 / 10,                                     
            1/2 + 15**0.5 / 10,                                         
            1/2 + 15**0.5 / 10,                                        
            1/2 - 15**0.5 / 10                                         
        ]
    ),
    "gauss-legendre_3s": (
        [
            [5/36, 2/9 - 15**0.5 / 15, 5/36 - 15**0.5 / 30],
            [5/36 + 15**0.5 / 24, 2/9, 5/36 - 15**0.5 / 24],
            [5/36 + 15**0.5 / 30, 2/9 + 15**0.5 / 15, 5/36],
        ],
        [
            [5/18, 4/9, 5/18]
        ],
        [1/2 - 15**0.5 / 10, 1/2, 1/2 + 15**0.5 / 10]
    ),
    "gauss-legendre_2s": (
        [
            [1/4, 1/4 - 3**0.5 / 6],
            [1/4 + 3**0.5 / 6, 1/4],
        ],
        [
            [1/2, 1/2],
        ],
        [1/2 - 3**0.5 / 6, 1/2 + 3**0.5 / 6]
    ),
    
    
    "radau_iia_4s": (
        [    
            [],
            [],
            [],
            [],
        ],
        [
            [1/4, 1/4, 1/4, 1/4],
        ],
        [(1/11)*(4-6**0.5), (1/11)*(4+6**0.5), 1/2, 1]
    ),
    
    
    "radau_iia_3s": (
        [    
            [11/45 - 7*6**0.5 / 360, 37/225 - 169*6**0.5 / 1800, -2/225 + 6**0.5 / 75],
            [37/225 + 169*6**0.5 / 1800, 11/45 + 7*6**0.5 / 360, -2/225 - 6**0.5 / 75],
            [4/9 - 6**0.5 / 36, 4/9 + 6**0.5 / 36, 1/9],
        ],
        [
            [4/9 - 6**0.5 / 36, 4/9 + 6**0.5 / 36, 1/9],
        ],
        [2/5 - 6**0.5 / 10, 2/5 + 6**0.5 / 10, 1.]
    ),
    "radau_iia_2s": (
        [    
            [5/12, -1/12],
            [3/4, 1/4],
        ],
        [
            [3/4, 1/4],
        ],
        [1/3, 1]
    ),
    "radau_ia_3s": (
        [    
            [1/9, (-1-6**0.5)/18, (-1+6**0.5)/18],
            [1/9, 11/45 + 7*6**0.5/360, 11/45-43*6**0.5/360],
            [1/9, 11/45-43*6**0.5/360, 11/45 + 7*6**0.5/360],
        ],
        [
            [1/9, 4/9 + 6**0.5/36, 4/9 - 6**0.5/36],
        ],
        [0, 3/5-6**0.5/10, 3/5+6**0.5/10]
    ),
    "radau_ia_2s": (
        [    
            [1/4, -1/4],
            [1/4, 5/12],
        ],
        [
            [1/4, 3/4],
        ],
        [0, 2/3]
    ),
    "lobatto_iiia_4s": ( #6th order
        [    
            [0, 0, 0, 0],
            [(11+5**0.5)/120,   (25-5**0.5)/120, (25-13*5**0.5)/120, (-1+5**0.5)/120],
            [(11-5**0.5)/120,   (25+13*5**0.5)/120, (25+5**0.5)/120, (-1-5**0.5)/120],
            [1/12, 5/12, 5/12, 1/12],
        ],
        [
            [1/12, 5/12, 5/12, 1/12],
        ],
        [0, (5-5**0.5)/10, (5+5**0.5)/10, 1]
    ),
    "lobatto_iiib_4s": ( #6th order
        [    
            [1/12, (-1-5**0.5)/24, (-1+5**0.5)/24, 0],
            [1/12,   (25+5**0.5)/120, (25-13*5**0.5)/120, 0],
            [1/12,   (25+13*5**0.5)/120, (25-5**0.5)/120, 0],
            [1/12, (11-5**0.5)/24, (11+5**0.5)/24, 0],
        ],
        [
            [1/12, 5/12, 5/12, 1/12],
        ],
        [0, (5-5**0.5)/10, (5+5**0.5)/10, 1]
    ),
    "lobatto_iiic_4s": ( #6th order
        [    
            [1/12, (-5**0.5)/12, (5**0.5)/12, -1/12],
            [1/12,   1/4, (10-7*5**0.5)/60, (5**0.5)/60],
            [1/12,   (10+7*5**0.5)/60, 1/4, (-5**0.5)/60],
            [1/12, 5/12, 5/12, 1/12],
        ],
        [
            [1/12, 5/12, 5/12, 1/12],
        ],
        [0, (5-5**0.5)/10, (5+5**0.5)/10, 1]
    ),
    "lobatto_iiia_3s": (
        [    
            [0, 0, 0],
            [5/24, 1/3, -1/24],
            [1/6, 2/3, 1/6],
        ],
        [
            [1/6, 2/3, 1/6],
        ],
        [0, 1/2, 1]
    ),
    "lobatto_iiia_2s": (
        [    
            [0, 0],
            [1/2, 1/2],
        ],
        [
            [1/2, 1/2],
        ],
        [0, 1]
    ),
    
    
    
    "lobatto_iiib_3s": (
        [    
            [1/6, -1/6, 0],
            [1/6, 1/3, 0],
            [1/6, 5/6, 0],
        ],
        [
            [1/6, 2/3, 1/6],
        ],
        [0, 1/2, 1]
    ),
    "lobatto_iiib_2s": (
        [    
            [1/2, 0],
            [1/2, 0],
        ],
        [
            [1/2, 1/2],
        ],
        [0, 1]
    ),

    "lobatto_iiic_3s": (
        [    
            [1/6, -1/3, 1/6],
            [1/6, 5/12, -1/12],
            [1/6, 2/3, 1/6],
        ],
        [
            [1/6, 2/3, 1/6],
        ],
        [0, 1/2, 1]
    ),
    "lobatto_iiic_2s": (
        [    
            [1/2, -1/2],
            [1/2, 1/2],
        ],
        [
            [1/2, 1/2],
        ],
        [0, 1]
    ),
    

    "lobatto_iiic_star_3s": (
        [    
            [0, 0, 0],
            [1/4, 1/4, 0],
            [0, 1, 0],
        ],
        [
            [1/6, 2/3, 1/6],
        ],
        [0, 1/2, 1]
    ),
    "lobatto_iiic_star_2s": (
        [    
            [0, 0],
            [1, 0],
        ],
        [
            [1/2, 1/2],
        ],
        [0, 1]
    ),
    
    "lobatto_iiid_3s": (
        [    
            [1/6, 0, -1/6],
            [1/12, 5/12, 0],
            [1/2, 1/3, 1/6],
        ],
        [
            [1/6, 2/3, 1/6],
        ],
        [0, 1/2, 1]
    ),
    "lobatto_iiid_2s": (
        [    
            [1/2, 1/2],
            [-1/2, 1/2],
        ],
        [
            [1/2, 1/2],
        ],
        [0, 1]
    ),
    

    
    "kraaijevanger_spijker_2s": (
        [    
            [1/2, 0],
            [-1/2, 2],
        ],
        [
            [-1/2, 3/2],
        ],
        [1/2, 3/2]
    ),
    
    "qin_zhang_2s": (
        [    
            [1/4, 0],
            [1/2, 1/4],
        ],
        [
            [1/2, 1/2],
        ],
        [1/4, 3/4]
    ),

    "pareschi_russo_2s": (
        [    
            [(1-2**0.5/2), 0],
            [1-2*(1-2**0.5/2), (1-2**0.5/2)],
        ],
        [
            [1/2, 1/2],
        ],
        [(1-2**0.5/2), 1-(1-2**0.5/2)]
    ),


    "pareschi_russo_alt_2s": (
        [    
            [(1-2**0.5/2), 0],
            [1-(1-2**0.5/2), (1-2**0.5/2)],
        ],
        [
            [1-(1-2**0.5/2), (1-2**0.5/2)],
        ],
        [(1-2**0.5/2), 1]
    ),

    "crouzeix_3s_alt": ( # Crouzeix & Raviart 1980; A-stable; pg 100 in Solving Ordinary Differential Equations II
        [
            [gamma_crouzeix, 0, 0],
            [1/2 - gamma_crouzeix, gamma_crouzeix, 0],
            [2*gamma_crouzeix, 1-4*gamma_crouzeix, gamma_crouzeix],
        ],
        [
            [delta_crouzeix, 1-2*delta_crouzeix, delta_crouzeix],
        ],
        [gamma_crouzeix,   1/2,   1-gamma_crouzeix],
    ),
    
    "crouzeix_3s": (
        [
            [(1+alpha_crouzeix)/2, 0, 0],
            [-alpha_crouzeix/2, (1+alpha_crouzeix)/2, 0],
            [1+alpha_crouzeix, -(1+2*alpha_crouzeix), (1+alpha_crouzeix)/2],
        ],
        [
            [1/(6*alpha_crouzeix**2), 1-(1/(3*alpha_crouzeix**2)), 1/(6*alpha_crouzeix**2)],
        ],
        [(1+alpha_crouzeix)/2,   1/2,   (1-alpha_crouzeix)/2],
    ),
    
    "crouzeix_2s": (
        [
            [1/2 + 3**0.5 / 6, 0],
            [-(3**0.5 / 3), 1/2 + 3**0.5 / 6]
        ],
        [
            [1/2, 1/2],
        ],
        [1/2 + 3**0.5 / 6, 1/2 - 3**0.5 / 6],
    ),
    "verner_13s": ( #verner9. some values are missing, need to revise
        [
            [],
        ],
        [
            [],
        ],
        [
            0.03462,
            0.09702435063878045,
            0.14553652595817068,
            0.561,
            0.22900791159048503,
            0.544992088409515,
            0.645,
            0.48375,
            0.06757,
            0.25,
            0.6590650618730999,
            0.8206,
            0.9012,
        ]
    ),
    "verner_robust_16s": (
        [
            [],
            [0.04],
            [-0.01988527319182291, 0.11637263332969652],
            [0.0361827600517026, 0, 0.10854828015510781],
            [2.272114264290177, 0, -8.526886447976398, 6.830772183686221],
            [0.050943855353893744, 0, 0, 0.1755865049809071, 0.007022961270757467],
            [0.1424783668683285, 0, 0, -0.3541799434668684, 0.07595315450295101, 0.6765157656337123],
            [0.07111111111111111, 0, 0, 0, 0, 0.3279909287605898, 0.24089796012829906],
            [0.07125, 0, 0, 0, 0, 0.32688424515752457, 0.11561575484247544, -0.03375],
            [0.0482267732246581, 0, 0, 0, 0, 0.039485599804954, 0.10588511619346581, -0.021520063204743093, -0.10453742601833482],
            [-0.026091134357549235, 0, 0, 0, 0, 0.03333333333333333, -0.1652504006638105, 0.03434664118368617, 0.1595758283215209, 0.21408573218281934],
            [-0.03628423396255658, 0, 0, 0, 0, -1.0961675974272087, 0.1826035504321331, 0.07082254444170683, -0.02313647018482431, 0.2711204726320933, 1.3081337494229808],
            [-0.5074635056416975, 0, 0, 0, 0, -6.631342198657237, -0.2527480100908801, -0.49526123800360955, 0.2932525545253887, 1.440108693768281, 6.237934498647056, 0.7270192054526988],
            [0.6130118256955932, 0, 0, 0, 0, 9.088803891640463, -0.40737881562934486, 1.7907333894903747, 0.714927166761755, -1.4385808578417227, -8.26332931206474, -1.537570570808865, 0.34538328275648716],
            [-1.2116979103438739, 0, 0, 0, 0, -19.055818715595954, 1.263060675389875, -6.913916969178458, -0.6764622665094981, 3.367860445026608, 18.00675164312591, 6.83882892679428, -1.0315164519219504, 0.4129106232130623],
            [2.1573890074940536, 0, 0, 0, 0, 23.807122198095804, 0.8862779249216555, 13.139130397598764, -2.604415709287715, -5.193859949783872, -20.412340711541507, -12.300856252505723, 1.5215530950085394],
        ],
        [
            0.014588852784055396, 0, 0, 0, 0, 0, 0, 0.0020241978878893325, 0.21780470845697167,
            0.12748953408543898, 0.2244617745463132, 0.1787254491259903, 0.07594344758096556,
            0.12948458791975614, 0.029477447612619417, 0
        ],
        [
            0, 0.04, 0.09648736013787361, 0.1447310402068104, 0.576, 0.2272326564618766,
            0.5407673435381234, 0.64, 0.48, 0.06754, 0.25, 0.6770920153543243, 0.8115,
            0.906, 1, 1
        ],
    ),

    "dormand-prince_13s": (
        [
            [],
            [1/18],
            [1/48, 1/16],
            [1/32, 0, 3/32],
            [5/16, 0, -75/64, 75/64],
            [3/80, 0, 0, 3/16, 3/20],
            [29443841/614563906, 0, 0, 77736538/692538347, -28693883/1125000000, 23124283/1800000000],
            [16016141/946692911, 0, 0, 61564180/158732637, 22789713/633445777, 545815736/2771057229, -180193667/1043307555],
            [39632708/573591083, 0, 0, -433636366/683701615, -421739975/2616292301, 100302831/723423059, 790204164/839813087, 800635310/3783071287],
            [246121993/1340847787, 0, 0, -37695042795/15268766246, -309121744/1061227803, -12992083/490766935, 6005943493/2108947869, 393006217/1396673457, 123872331/1001029789],
            [-1028468189/846180014, 0, 0, 8478235783/508512852, 1311729495/1432422823, -10304129995/1701304382, -48777925059/3047939560, 15336726248/1032824649, -45442868181/3398467696, 3065993473/597172653],
            [185892177/718116043, 0, 0, -3185094517/667107341, -477755414/1098053517, -703635378/230739211, 5731566787/1027545527, 5232866602/850066563, -4093664535/808688257, 3962137247/1805957418, 65686358/487910083],
            [403863854/491063109, 0, 0, -5068492393/434740067, -411421997/543043805, 652783627/914296604, 11173962825/925320556, -13158990841/6184727034, 3936647629/1978049680, -160528059/685178525, 248638103/1413531060],
        ],
        [
            [14005451/335480064, 0, 0, 0, 0, -59238493/1068277825, 181606767/758867731, 561292985/797845732, -1041891430/1371343529, 760417239/1151165299, 118820643/751138087, -528747749/2220607170, 1/4],
        ],
        [0, 1/18, 1/12, 1/8, 5/16, 3/8, 59/400, 93/200, 5490023248 / 9719169821, 13/20, 1201146811 / 1299019798, 1, 1],
    ),
    "dormand-prince_6s": (
        [
            [],
            [1/5],
            [3/40, 9/40],
            [44/45, -56/15, 32/9],
            [19372/6561, -25360/2187, 64448/6561, -212/729],
            [9017/3168, -355/33, 46732/5247, 49/176, -5103/18656],
        ],
        [
            [35/384, 0, 500/1113, 125/192, -2187/6784, 11/84],
        ],
        [0, 1/5, 3/10, 4/5, 8/9, 1],
    ),
    "bogacki-shampine_7s": ( #5th order
        [
            [],
            [1/6],
            [2/27, 4/27],
            [183/1372, -162/343, 1053/1372],
            [68/297, -4/11, 42/143, 1960/3861],
            [597/22528, 81/352, 63099/585728, 58653/366080, 4617/20480],
            [174197/959244, -30942/79937, 8152137/19744439, 666106/1039181, -29421/29068, 482048/414219],
        ],
        [
            [587/8064, 0, 4440339/15491840, 24353/124800, 387/44800, 2152/5985, 7267/94080],
        ],
        [0, 1/6, 2/9, 3/7, 2/3, 3/4, 1] 
    ),
    "bogacki-shampine_4s": ( #5th order
        [
            [],
            [1/2],
            [0, 3/4],
            [2/9, 1/3, 4/9],
        ],
        [
            [2/9, 1/3, 4/9, 0],
        ],
        [0, 1/2, 3/4, 1] 
    ),
    "tsi_7s": ( #5th order 
        [
            [],
            [0.161],
            [-0.008480655492356989, 0.335480655492357],
            [2.8971530571054935, -6.359448489975075, 4.3622954328695815],
            [5.325864828439257, -11.748883564062828, 7.4955393428898365, -0.09249506636175525],
            [5.86145544294642, -12.92096931784711, 8.159367898576159, -0.071584973281401, -0.02826905039406838],
            [0.09646076681806523, 0.01, 0.4798896504144996, 1.379008574103742, -3.290069515436081, 2.324710524099774],
        ],
        [
            [0.09646076681806523, 0.01, 0.4798896504144996, 1.379008574103742, -3.290069515436081, 2.324710524099774, 0.0],
        ],
        [0.0, 0.161, 0.327, 0.9, 0.9800255409045097, 1.0, 1.0],
    ),
    "rk6_7s": ( #5th order
        [
            [],
            [1/3],
            [0, 2/3],
            [1/12, 1/3, -1/12],
            [-1/16, 9/8, -3/16, -3/8],
            [0, 9/8, -3/8, -3/4, 1/2],
            [9/44, -9/11, 63/44, 18/11, 0, -16/11],
        ],
        [
            [11/120, 0, 27/40, 27/40, -4/15, -4/15, 11/120],
        ],
        [0, 1/3, 2/3, 1/3, 1/2, 1/2, 1],
    ),
    "rk5_7s": ( #5th order
        [
            [],
            [1/5],
            [3/40, 9/40],
            [44/45, -56/15, 32/9],
            [19372/6561, -25360/2187, 64448/6561, 212/729], #flipped 212 sign
            [-9017/3168, -355/33, 46732/5247, 49/176, -5103/18656],
            [35/384, 0, 500/1113, 125/192, -2187/6784, 11/84],
        ],
        [
            [5179/57600, 0, 7571/16695, 393/640, -92097/339200, 187/2100, 1/40],
        ],
        [0, 1/5, 3/10, 4/5, 8/9, 1, 1],
    ),
    "ssprk4_4s": ( #https://link.springer.com/article/10.1007/s41980-022-00731-x
        [
            [],
            [1/2],
            [1/2, 1/2],
            [1/6, 1/6, 1/6],
        ],
        [
            [1/6, 1/6, 1/6, 1/2],
        ],
        [0, 1/2, 1, 1/2],
    ),
    "rk4_4s": (
        [
            [],
            [1/2],
            [0, 1/2],
            [0, 0, 1],
        ],
        [
            [1/6, 1/3, 1/3, 1/6],
        ],
        [0, 1/2, 1/2, 1],
    ),
    "rk38_4s": (
        [
            [],
            [1/3],
            [-1/3, 1],
            [1, -1, 1],
        ],
        [
            [1/8, 3/8, 3/8, 1/8],
        ],
        [0, 1/3, 2/3, 1],
    ),
    "ralston_4s": (
        [
            [],
            [2/5],
            [(-2889+1428 * 5**0.5)/1024,   (3785-1620 * 5**0.5)/1024],
            [(-3365+2094 * 5**0.5)/6040,   (-975-3046 * 5**0.5)/2552,  (467040+203968*5**0.5)/240845],
        ],
        [
            [(263+24*5**0.5)/1812, (125-1000*5**0.5)/3828, (3426304+1661952*5**0.5)/5924787, (30-4*5**0.5)/123],
        ],
        [0, 2/5, (14-3 * 5**0.5)/16, 1],
    ),
    "heun_3s": (
        [
            [],
            [1/3],
            [0, 2/3],
        ],
        [
            [1/4, 0, 3/4],
        ],
        [0, 1/3, 2/3],
    ),
    "kutta_3s": (
        [
            [],
            [1/2],
            [-1, 2],
        ],
        [
            [1/6, 2/3, 1/6],
        ],
        [0, 1/2, 1],
    ),
    "ralston_3s": (
        [
            [],
            [1/2],
            [0, 3/4],
        ],
        [
            [2/9, 1/3, 4/9],
        ],
        [0, 1/2, 3/4],
    ),
    "houwen-wray_3s": (
        [
            [],
            [8/15],
            [1/4, 5/12],
        ],
        [
            [1/4, 0, 3/4],
        ],
        [0, 8/15, 2/3],
    ),
    "ssprk3_3s": (
        [
            [],
            [1],
            [1/4, 1/4],
        ],
        [
            [1/6, 1/6, 2/3],
        ],
        [0, 1, 1/2],
    ),
    "midpoint_2s": (
        [
            [],
            [1/2],
        ],
        [
            [0, 1],
        ],
        [0, 1/2],
    ),
    "heun_2s": (
        [
            [],
            [1],
        ],
        [
            [1/2, 1/2],
        ],
        [0, 1],
    ),
    "ralston_2s": (
        [
            [],
            [2/3],
        ],
        [
            [1/4, 3/4],
        ],
        [0, 2/3],
    ),
    "euler": (
        [
            [],
        ],
        [
            [1],
        ],
        [0],
    ),
}



def get_rk_methods_beta(rk_type, h, c1=0.0, c2=0.5, c3=1.0, h_prev=None, step=0, sigmas=None, sigma=None, sigma_next=None, sigma_down=None, extra_options=None):
    FSAL = False
    multistep_stages = 0
    hybrid_stages = 0
    u, v = None, None
    
    multistep_initial_sampler = get_extra_options_kv("multistep_initial_sampler", "", extra_options)
    multistep_extra_initial_steps = int(get_extra_options_kv("multistep_extra_initial_steps", "1", extra_options))
    
    #if RK_Method_Beta.is_exponential(rk_type): 
    if rk_type.startswith(("res", "dpmpp", "ddim", "pec", "etdrk", "lawson")): 
        h_no_eta = -torch.log(sigma_next/sigma)
        h_prev1_no_eta = -torch.log(sigmas[step]/sigmas[step-1]) if step >= 1 else None
        h_prev2_no_eta = -torch.log(sigmas[step]/sigmas[step-2]) if step >= 2 else None
        h_prev3_no_eta = -torch.log(sigmas[step]/sigmas[step-3]) if step >= 3 else None
        h_prev4_no_eta = -torch.log(sigmas[step]/sigmas[step-4]) if step >= 4 else None

    else:
        h_no_eta = sigma_next - sigma
        h_prev1_no_eta = sigmas[step] - sigmas[step-1] if step >= 1 else None
        h_prev2_no_eta = sigmas[step] - sigmas[step-2] if step >= 2 else None
        h_prev3_no_eta = sigmas[step] - sigmas[step-3] if step >= 3 else None
        h_prev4_no_eta = sigmas[step] - sigmas[step-4] if step >= 4 else None
        
    if type(c1) == torch.Tensor:
        c1 = c1.item()
    if type(c2) == torch.Tensor:
        c2 = c2.item()
    if type(c3) == torch.Tensor:
        c3 = c3.item()

    if c1 == -1:
        c1 = random.uniform(0, 1)
    if c2 == -1:
        c2 = random.uniform(0, 1)
    if c3 == -1:
        c3 = random.uniform(0, 1)
        
    if rk_type[:4] == "deis": 
        order = int(rk_type[-2])
        if step < order + multistep_extra_initial_steps:
            if order == 4:
                rk_type = "res_4s_strehmel_weiner"
                rk_type = multistep_initial_sampler if multistep_initial_sampler else rk_type
                order = 3
            elif order == 3:
                rk_type = "res_3s"
                rk_type = multistep_initial_sampler if multistep_initial_sampler else rk_type
            elif order == 2:
                rk_type = "res_2s"
                rk_type = multistep_initial_sampler if multistep_initial_sampler else rk_type
        else:
            rk_type = "deis"
            multistep_stages = order-1
    
    if rk_type[-2:] == "2m": #multistep method
        rk_type = rk_type[:-2] + "2s"
        #if h_prev is not None and step >= 1: 
        if step >= 1 + multistep_extra_initial_steps:
            multistep_stages = 1
            c2 = (-h_prev1_no_eta / h_no_eta).item()
        else:
            rk_type = multistep_initial_sampler if multistep_initial_sampler else rk_type
        if rk_type.startswith("abnorsett"):
            rk_type = "res_2s"
            rk_type = multistep_initial_sampler if multistep_initial_sampler else rk_type
            
    if rk_type[-2:] == "3m": #multistep method
        rk_type = rk_type[:-2] + "3s"
        #if h_prev2 is not None and step >= 2: 
        if step >= 2 + multistep_extra_initial_steps:
            multistep_stages = 2

            c2 = (-h_prev1_no_eta / h_no_eta).item()
            c3 = (-h_prev2_no_eta / h_no_eta).item()      
        else:
            rk_type = multistep_initial_sampler if multistep_initial_sampler else rk_type 
        if rk_type.startswith("abnorsett"):
            rk_type = "res_3s"
            rk_type = multistep_initial_sampler if multistep_initial_sampler else rk_type
            
    if rk_type[-2:] == "4m": #multistep method
        rk_type = rk_type[:-2] + "4s"
        #if h_prev2 is not None and step >= 2: 
        if step >= 3 + multistep_extra_initial_steps:
            multistep_stages = 3

            c2 = (-h_prev1_no_eta / h_no_eta).item()
            c3 = (-h_prev2_no_eta / h_no_eta).item()
            # WOULD NEED A C4 (POW) TO IMPLEMENT RES_4M IF IT EXISTED
        else:
            rk_type = multistep_initial_sampler if multistep_initial_sampler else rk_type
        if rk_type == "res_4s":
            rk_type = "res_4s_strehmel_weiner"
            rk_type = multistep_initial_sampler if multistep_initial_sampler else rk_type
        if rk_type.startswith("abnorsett"):
            rk_type = "res_4s_strehmel_weiner"
            rk_type = multistep_initial_sampler if multistep_initial_sampler else rk_type
            
    if rk_type[-3] == "h" and rk_type[-1] == "s": #hybrid method 
        if step < int(rk_type[-4]) + multistep_extra_initial_steps:
            rk_type = "res_" + rk_type[-2:]
            rk_type = multistep_initial_sampler if multistep_initial_sampler else rk_type
        else:
            hybrid_stages = int(rk_type[-4])  #+1 adjustment needed?
        if rk_type == "res_4s":
            rk_type = "res_4s_strehmel_weiner"
            rk_type = multistep_initial_sampler if multistep_initial_sampler else rk_type
        if rk_type == "res_1s":
            rk_type = "res_2s"
            rk_type = multistep_initial_sampler if multistep_initial_sampler else rk_type

    if rk_type in rk_coeff:
        a, b, ci = copy.deepcopy(rk_coeff[rk_type])
        
        a = [row + [0] * (len(ci) - len(row)) for row in a]

    match rk_type:
        case "deis": 
            coeff_list = get_deis_coeff_list(sigmas, multistep_stages+1, deis_mode="rhoab")
            coeff_list = [[elem / h for elem in inner_list] for inner_list in coeff_list]
            if multistep_stages == 1:
                b1, b2 = coeff_list[step]
                a = [
                        [0, 0],
                        [0, 0],
                ]
                b = [
                        [b1, b2],
                ]
                ci = [0, 0]
            if multistep_stages == 2:
                b1, b2, b3 = coeff_list[step]
                a = [
                        [0, 0, 0],
                        [0, 0, 0],
                        [0, 0, 0],
                ]
                b = [
                        [b1, b2, b3],
                ]
                ci = [0, 0, 0]
            if multistep_stages == 3:
                b1, b2, b3, b4 = coeff_list[step]
                a = [
                        [0, 0, 0, 0],
                        [0, 0, 0, 0],
                        [0, 0, 0, 0],
                        [0, 0, 0, 0],
                ]
                b = [
                    [b1, b2, b3, b4],
                ]
                ci = [0, 0, 0, 0]
            if multistep_stages > 0:
                for i in range(len(b[0])): 
                    b[0][i] *= ((sigma_down - sigma) / (sigma_next - sigma))

        case "dormand-prince_6s":
            FSAL = True

        case "ddim":
            b1 = phi(1, -h)
            a = [
                    [0],
            ]
            b = [
                    [b1],
            ]
            ci = [0]

        case "res_2s":
            c2 = float(get_extra_options_kv("c2", str(c2), extra_options))

            ci = [0, c2]
            φ = Phi(h, ci)
            
            a2_1 = c2 * φ(1,2)
            b2 = φ(2)/c2
            b1 = φ(1) - b2

            a = [
                    [0,0],
                    [a2_1, 0],
            ]
            b = [
                    [b1, b2],
            ]

        case "res_2s_rkmk2e":

            ci = [0, 1]
            φ = Phi(h, ci)
            
            b2 = φ(2)

            a = [
                    [0,0],
                    [0, 0],
            ]
            b = [
                    [0, b2],
            ]

            gen_first_col_exp(a, b, ci, φ)



        case "abnorsett2_1h2s":

            c1, c2 = 0, 1
            ci = [c1, c2]
            φ = Phi(h, ci)

            b1 = φ(1) #+ φ(2)

            a = [
                    [0, 0],
                    [0, 0],
            ]
            b = [
                    [0, 0],
            ]

            if extra_options_flag("h_prev_h_h_no_eta", extra_options):
                φ1 = Phi(h_prev1_no_eta * h/h_no_eta, ci)
            elif extra_options_flag("h_only", extra_options):
                φ1 = Phi(h, ci)
            else:
                φ1 = Phi(h_prev1_no_eta, ci)

            u1 = -φ1(2)
            v1 = -φ1(2)

            u = [
                    [0, 0],
                    [u1, 0],
            ]
            v = [
                    [v1, 0],
            ]

            gen_first_col_exp_uv(a, b, ci, u, v, φ) 



        case "abnorsett_2m":

            c1, c2 = 0, 1
            ci = [c1, c2]
            φ = Phi(h, ci)

            a = [
                    [0, 0],
                    [0, 0],
            ]
            b = [
                    [0, -φ(2)],
            ]

            gen_first_col_exp(a, b, ci, φ) 


        case "abnorsett_3m":

            c1, c2, c3 = 0, 0, 1
            ci = [c1, c2, c3]
            φ = Phi(h, ci)

            a = [
                    [0, 0, 0],
                    [0, 0, 0],
                    [0, 0, 0],
            ]
            b = [
                    [0, -2*φ(2) - 2*φ(3), (1/2)*φ(2) + φ(3)],
            ]

            gen_first_col_exp(a, b, ci, φ) 



        case "abnorsett_4m":

            c1, c2, c3, c4 = 0, 0, 0, 1
            ci = [c1, c2, c3, c4]
            φ = Phi(h, ci)

            a = [
                    [0, 0, 0, 0],
                    [0, 0, 0, 0],
                    [0, 0, 0, 0],
                    [0, 0, 0, 0],
            ]
            b = [
                    [0, 
                     -3*φ(2) - 5*φ(3) - 3*φ(4),
                     (3/2)*φ(2) + 4*φ(3) + 3*φ(4),
                     (-1/3)*φ(2) - φ(3) - φ(4),
                     ],
            ]

            gen_first_col_exp(a, b, ci, φ) 


        case "abnorsett3_2h2s":
            
            c1,c2 = 0,1
            ci = [c1, c2]
            φ = Phi(h, ci)
            
            b2 = 0

            a = [
                    [0, 0],
                    [0, 0],
            ]
            b = [
                    [0, 0],
            ]
            
            if extra_options_flag("h_prev_h_h_no_eta", extra_options):
                φ1 = Phi(h_prev1_no_eta * h/h_no_eta, ci)
                φ2 = Phi(h_prev2_no_eta * h/h_no_eta, ci)
            elif extra_options_flag("h_only", extra_options):
                φ1 = Phi(h, ci)
                φ2 = Phi(h, ci)
            else:
                φ1 = Phi(h_prev1_no_eta, ci)
                φ2 = Phi(h_prev2_no_eta, ci)
                
            u2_1 = -2*φ1(2) - 2*φ1(3)
            u2_2 = (1/2)*φ2(2) + φ2(3)
            
            v1 = u2_1 # -φ1(2) + φ1(3) + 3*φ1(4)
            v2 = u2_2 # (1/6)*φ2(2) - φ2(4)
            
            u = [
                    [   0,    0],
                    [u2_1, u2_2],
            ]
            v = [
                    [v1, v2],
            ]
            
            gen_first_col_exp_uv(a, b, ci, u, v, φ)
            


        case "pec423_2h2s":
            
            c1,c2 = 0,1
            ci = [c1, c2]
            φ = Phi(h, ci)
            
            b2 = (1/3)*φ(2) + φ(3) + φ(4)

            a = [
                    [0, 0],
                    [0, 0],
            ]
            b = [
                    [0, b2],
            ]
            
            if extra_options_flag("h_prev_h_h_no_eta", extra_options):
                φ1 = Phi(h_prev1_no_eta * h/h_no_eta, ci)
                φ2 = Phi(h_prev2_no_eta * h/h_no_eta, ci)
            elif extra_options_flag("h_only", extra_options):
                φ1 = Phi(h, ci)
                φ2 = Phi(h, ci)
            else:
                φ1 = Phi(h_prev1_no_eta, ci)
                φ2 = Phi(h_prev2_no_eta, ci)
                
            u2_1 = -2*φ1(2) - 2*φ1(3)
            u2_2 = (1/2)*φ2(2) + φ2(3)
            
            v1 = -φ1(2) + φ1(3) + 3*φ1(4)
            v2 = (1/6)*φ2(2) - φ2(4)
            
            u = [
                    [   0,    0],
                    [u2_1, u2_2],
            ]
            v = [
                    [v1, v2],
            ]
            
            gen_first_col_exp_uv(a, b, ci, u, v, φ)
            



        case "pec433_2h3s":
            
            c1,c2,c3 = 0, 1, 1
            ci = [c1,c2,c3]
            φ = Phi(h, ci)
            
            a3_2 = (1/3)*φ(2) + φ(3) + φ(4)
            
            b2 = 0
            b3 = (1/3)*φ(2) + φ(3) + φ(4)

            a = [
                    [0,    0, 0],
                    [0,    0, 0],
                    [0, a3_2, 0],
            ]
            b = [
                    [0, b2, b3],
            ]
            
            if extra_options_flag("h_prev_h_h_no_eta", extra_options):
                φ1 = Phi(h_prev1_no_eta * h/h_no_eta, ci)
                φ2 = Phi(h_prev2_no_eta * h/h_no_eta, ci)
            elif extra_options_flag("h_only", extra_options):
                φ1 = Phi(h, ci)
                φ2 = Phi(h, ci)
            else:
                φ1 = Phi(h_prev1_no_eta, ci)
                φ2 = Phi(h_prev2_no_eta, ci)
                
            u2_1 = -2*φ1(2) - 2*φ1(3)
            u3_1 = -φ1(2) + φ1(3) + 3*φ1(4)
            v1 = -φ1(2) + φ1(3) + 3*φ1(4)
            
            u2_2 = (1/2)*φ2(2) + φ2(3)
            u3_2 = (1/6)*φ2(2) - φ2(4)
            v2 = (1/6)*φ2(2) - φ2(4)

            
            u = [
                    [   0,    0, 0],
                    [u2_1, u2_2, 0],
                    [u3_1, u3_2, 0],
            ]
            v = [
                    [v1, v2, 0],
            ]
            
            gen_first_col_exp_uv(a, b, ci, u, v, φ)


            
        case "res_3s":
            c2 = float(get_extra_options_kv("c2", str(c2), extra_options))
            c3 = float(get_extra_options_kv("c3", str(c3), extra_options))
            
            gamma = calculate_gamma(c2, c3)
            a2_1 = c2 * phi(1, -h*c2)
            a3_2 = gamma * c2 * phi(2, -h*c2) + (c3 ** 2 / c2) * phi(2, -h*c3) #phi_2_c3_h  # a32 from k2 to k3
            a3_1 = c3 * phi(1, -h*c3) - a3_2 # a31 from k1 to k3
            b3 = (1 / (gamma * c2 + c3)) * phi(2, -h)      
            b2 = gamma * b3  #simplified version of: b2 = (gamma / (gamma * c2 + c3)) * phi_2_h  
            b1 = phi(1, -h) - b2 - b3     
            
            a = [
                    [0, 0, 0],
                    [a2_1, 0, 0],
                    [a3_1, a3_2, 0],
            ]
            b = [
                    [b1, b2, b3],
            ]
            ci = [c1, c2, c3]
            
        case "res_3s_alt":
            c2 = 1/3
            c2 = float(get_extra_options_kv("c2", str(c2), extra_options))
            
            c1,c2,c3 = 0, c2, 2/3
            ci = [c1,c2,c3]
            φ = Phi(h, ci)
            
            a = [
                    [0, 0,                   0],
                    [0, 0,                   0],
                    [0, (4/(9*c2)) * φ(2,3), 0],
            ]
            b = [
                    [0, 0, (1/c3)*φ(2)],
            ]
            
            a, b = gen_first_col_exp(a,b,ci,φ)
            
        case "res_3s_strehmel_weiner": # weak 4th order, Krogstad
            c2 = 1/2
            c2 = float(get_extra_options_kv("c2", str(c2), extra_options))

            ci = [0,c2,1]
            φ = Phi(h, ci)
            
            a = [
                    [0, 0, 0],
                    [0, 0, 0],
                    [0, (1/c2) * φ(2,3), 0],
            ]
            b = [
                    [0, 
                     0,
                     φ(2)],
            ]
            
            a, b = gen_first_col_exp(a,b,ci,φ)
            
            
        case "res_3s_cox_matthews": # Cox & Matthews; known as ETD3RK
            c2 = 1/2 # must be 1/2
            ci = [0,c2,1]
            φ = Phi(h, ci)
            
            a = [
                    [0, 0, 0],
                    [0, 0, 0],
                    [0, (1/c2) * φ(1,3), 0],  # paper said 2 * φ(1,3), but this is the same and more consistent with res_3s_strehmel_weiner
            ]
            b = [
                    [0, 
                     -8*φ(3) + 4*φ(2),
                     4*φ(3) - φ(2)],
            ]
            
            a, b = gen_first_col_exp(a,b,ci,φ)
            
        case "res_3s_lie": # Lie; known as ETD2CF3
            c1,c2,c3 = 0, 1/3, 2/3
            ci = [c1,c2,c3]
            φ = Phi(h, ci)
            
            a = [
                    [0, 0, 0],
                    [0, 0, 0],
                    [0, (4/3)*φ(2,3), 0],  # paper said 2 * φ(1,3), but this is the same and more consistent with res_3s_strehmel_weiner
            ]
            b = [
                    [0, 
                     6*φ(2) - 18*φ(3),
                     (-3/2)*φ(2) + 9*φ(3)],
            ]
            
            a, b = gen_first_col_exp(a,b,ci,φ)
        
        
        case "res_4s_cox_matthews": # weak 4th order, Cox & Matthews; unresolved issue, see below
            c1,c2,c3,c4 = 0, 1/2, 1/2, 1
            ci = [c1,c2,c3,c4]
            φ = Phi(h, ci)
            
            a2_1 = c2 * φ(1,2)
            a3_2 = c3 * φ(1,3)
            a4_1 = (1/2) * φ(1,3) * (φ(0,3) - 1) # φ(0,3) == torch.exp(-h*c3)
            a4_3 = φ(1,3)

            b1 = φ(1) - 3*φ(2) + 4*φ(3)

            b2 = 2*φ(2) - 4*φ(3)
            b3 = 2*φ(2) - 4*φ(3)
            b4 = 4*φ(3) - φ(2)

            a = [
                    [0,    0,0,0],
                    [a2_1, 0,0,0],
                    [0, a3_2,0,0],
                    [a4_1, 0, a4_3,0],
            ]
            b = [
                    [b1, b2, b3, b4],
            ]
            
            
        case "res_4s_cfree4": # weak 4th order, Cox & Matthews; unresolved issue, see below
            c1,c2,c3,c4 = 0, 1/2, 1/2, 1
            ci = [c1,c2,c3,c4]
            φ = Phi(h, ci)
            
            a2_1 = c2 * φ(1,2)
            a3_2 = c3 * φ(1,2)
            a4_1 = (1/2) * φ(1,2) * (φ(0,2) - 1) # φ(0,3) == torch.exp(-h*c3)
            a4_3 = φ(1,2)

            b1 = (1/2)*φ(1) - (1/3)*φ(1,2)

            b2 = (1/3)*φ(1)
            b3 = (1/3)*φ(1)
            b4 = -(1/6)*φ(1) + (1/3)*φ(1,2)

            a = [
                    [0,    0,0,0],
                    [a2_1, 0,0,0],
                    [0, a3_2,0,0],
                    [a4_1, 0, a4_3,0],
            ]
            b = [
                    [b1, b2, b3, b4],
            ]

        case "res_4s_friedli": # https://ora.ox.ac.uk/objects/uuid:cc001282-4285-4ca2-ad06-31787b540c61/files/m611df1a355ca243beb09824b70e5e774
            c1,c2,c3,c4 = 0, 1/2, 1/2, 1
            ci = [c1,c2,c3,c4]
            φ = Phi(h, ci)
            
            a3_2 = 2*φ(2,2)
            a4_2 = -(26/25)*φ(1) +  (2/25)*φ(2)
            a4_3 =  (26/25)*φ(1) + (48/25)*φ(2)


            b2 = 0
            b3 = 4*φ(2) - 8*φ(3)
            b4 =  -φ(2) + 4*φ(3)

            a = [
                    [0, 0,0,0],
                    [0, 0,0,0],
                    [0, a3_2,0,0],
                    [0, a4_2, a4_3,0],
            ]
            b = [
                    [0, b2, b3, b4],
            ]

            a, b = gen_first_col_exp(a,b,ci,φ)

        case "res_4s_munthe-kaas": # unstable RKMK4t
            c1,c2,c3,c4 = 0, 1/2, 1/2, 1
            ci = [c1,c2,c3,c4]
            φ = Phi(h, ci)

            a = [
                    [0, 0,      0,        0],
                    [c2*φ(1,2), 0,      0,        0],
                    [(h/8)*φ(1,2), (1/2)*(1-h/4)*φ(1,2), 0,        0],
                    [0, 0,      φ(1), 0],
            ]
            b = [
                    [(1/6)*φ(1)*(1+h/2),
                     (1/3)*φ(1),
                     (1/3)*φ(1),
                     (1/6)*φ(1)*(1-h/2)],
            ]

        case "res_4s_krogstad": # weak 4th order, Krogstad
            c1,c2,c3,c4 = 0, 1/2, 1/2, 1
            ci = [c1,c2,c3,c4]
            φ = Phi(h, ci)
            
            a = [
                    [0, 0,      0,        0],
                    [0, 0,      0,        0],
                    [0, φ(2,3), 0,        0],
                    [0, 0,      2*φ(2,4), 0],
            ]
            b = [
                    [0, 
                     2*φ(2) - 4*φ(3),
                     2*φ(2) - 4*φ(3),
                     -φ(2)  + 4*φ(3)],
            ]
            
            #a = [row + [0] * (len(ci) - len(row)) for row in a]
            a, b = gen_first_col_exp(a,b,ci,φ)
            
        case "res_4s_minchev": # https://ora.ox.ac.uk/objects/uuid:cc001282-4285-4ca2-ad06-31787b540c61/files/m611df1a355ca243beb09824b70e5e774
            c1,c2,c3,c4 = 0, 1/2, 1/2, 1
            ci = [c1,c2,c3,c4]
            φ = Phi(h, ci)
            
            a3_2 = (4/25)*φ(1,2) + (24/25)*φ(2,2)
            a4_2 = (21/5)*φ(2) - (108/5)*φ(3)
            a4_3 = (1/20)*φ(1) - (33/10)*φ(2) + (123/5)*φ(3)


            b2 = -(1/10)*φ(1) +  (1/5)*φ(2) - 4*φ(3) + 12*φ(4)
            b3 =  (1/30)*φ(1) + (23/5)*φ(2) - 8*φ(3) -  4*φ(4)
            b4 =  (1/30)*φ(1) -  (7/5)*φ(2) + 6*φ(3) -  4*φ(4)

            a = [
                    [0, 0,0,0],
                    [0, 0,0,0],
                    [0, a3_2,0,0],
                    [0, 0, a4_3,0],
            ]
            b = [
                    [0, b2, b3, b4],
            ]

            a, b = gen_first_col_exp(a,b,ci,φ)
            
        case "res_4s_strehmel_weiner": # weak 4th order, Strehmel & Weiner
            c1,c2,c3,c4 = 0, 1/2, 1/2, 1
            ci = [c1,c2,c3,c4]
            φ = Phi(h, ci)
            
            a = [
                    [0, 0,         0,        0],
                    [0, 0,         0,        0],
                    [0, c3*φ(2,3), 0,        0],
                    [0, -2*φ(2,4), 4*φ(2,4), 0],
            ]
            b = [
                    [0, 
                     0,
                     4*φ(2) - 8*φ(3), 
                     -φ(2) +  4*φ(3)],
            ]
            
            a, b = gen_first_col_exp(a,b,ci,φ)
            
        case "lawson2a_2s": # based on midpoint rule, stiff order 1 https://cds.cern.ch/record/848126/files/cer-002531460.pdf
            c1,c2 = 0,1/2
            ci = [c1, c2]
            φ = Phi(h, ci)
            
            a2_1 = c2 * φ(0,2)
            b2 = φ(0,2)
            b1 = 0

            a = [
                    [0,0],
                    [a2_1, 0],
            ]
            b = [
                    [b1, b2],
            ]

        case "lawson2b_2s": # based on trapezoidal rule, stiff order 1 https://cds.cern.ch/record/848126/files/cer-002531460.pdf
            c1,c2 = 0,1
            ci = [c1, c2]
            φ = Phi(h, ci)
            
            a2_1 = φ(0)
            b2 = 1/2
            b1 = (1/2)*φ(0)

            a = [
                    [0,0],
                    [a2_1, 0],
            ]
            b = [
                    [b1, b2],
            ]


        case "lawson4_4s": 
            c1,c2,c3,c4 = 0, 1/2, 1/2, 1
            ci = [c1,c2,c3,c4]
            φ = Phi(h, ci)
            
            a2_1 = c2 * φ(0,2)
            a3_2 = 1/2
            a4_3 = φ(0,2)
            
            b1 = (1/6) * φ(0)
            b2 = (1/3) * φ(0,2)
            b3 = (1/3) * φ(0,2)
            b4 = 1/6

            a = [
                    [0,    0,    0,    0],
                    [a2_1, 0,    0,    0],
                    [0,    a3_2, 0,    0],
                    [0,    0,    a4_3, 0],
            ]
            b = [
                    [b1,b2,b3,b4],
            ]

        case "lawson41-gen_4s": # GenLawson4 https://ora.ox.ac.uk/objects/uuid:cc001282-4285-4ca2-ad06-31787b540c61/files/m611df1a355ca243beb09824b70e5e774
            c1,c2,c3,c4 = 0, 1/2, 1/2, 1
            ci = [c1,c2,c3,c4]
            φ = Phi(h, ci)


            a3_2 = 1/2
            a4_3 = φ(0,2)
            
            b2 = (1/3) * φ(0,2)
            b3 = (1/3) * φ(0,2)
            b4 = 1/6

            a = [
                    [0, 0,        0, 0],
                    [0, 0,          0,        0],
                    [0, a3_2, 0,        0],
                    [0, 0, a4_3, 0],
            ]
            b = [
                    [0,
                     b2,
                     b3,
                     b4,],
            ]

            a, b = gen_first_col_exp(a,b,ci,φ)

        case "lawson41-gen-mod_4s": # GenLawson4 https://ora.ox.ac.uk/objects/uuid:cc001282-4285-4ca2-ad06-31787b540c61/files/m611df1a355ca243beb09824b70e5e774
            c1,c2,c3,c4 = 0, 1/2, 1/2, 1
            ci = [c1,c2,c3,c4]
            φ = Phi(h, ci)


            a3_2 = 1/2
            a4_3 = φ(0,2)
            
            b2 = (1/3) * φ(0,2)
            b3 = (1/3) * φ(0,2)
            b4 = φ(2) - (1/3)*φ(0,2)

            a = [
                    [0, 0,        0, 0],
                    [0, 0,          0,        0],
                    [0, a3_2, 0,        0],
                    [0, 0, a4_3, 0],
            ]
            b = [
                    [0,
                     b2,
                     b3,
                     b4,],
            ]

            a, b = gen_first_col_exp(a,b,ci,φ)



        case "lawson42-gen-mod_1h4s": # GenLawson4 https://ora.ox.ac.uk/objects/uuid:cc001282-4285-4ca2-ad06-31787b540c61/files/m611df1a355ca243beb09824b70e5e774
            c1,c2,c3,c4 = 0, 1/2, 1/2, 1
            ci = [c1,c2,c3,c4]
            φ = Phi(h, ci)

            a3_2 = 1/2
            a4_3 = φ(0,2)
            
            b2 = (1/3) * φ(0,2)
            b3 = (1/3) * φ(0,2)
            b4 = (1/2)*φ(2) + φ(3) - (1/4)*φ(0,2)

            a = [
                    [0, 0,    0, 0],
                    [0, 0,    0, 0],
                    [0, a3_2, 0, 0],
                    [0, 0, a4_3, 0],
            ]
            b = [
                    [0, b2, b3, b4,],
            ]

            if extra_options_flag("h_prev_h_h_no_eta", extra_options):
                φ1 = Phi(h_prev1_no_eta * h/h_no_eta, ci)
            elif extra_options_flag("h_only", extra_options):
                φ1 = Phi(h, ci)
            else:
                φ1 = Phi(h_prev1_no_eta, ci)

            u2_1 = -φ1(2,2)
            u3_1 = -φ1(2,2) + 1/4
            u4_1 = -φ1(2) + (1/2)*φ1(0,2)
            v1 = -(1/2)*φ1(2) + φ1(3) + (1/12)*φ1(0,2)

            u = [
                    [   0, 0, 0, 0],
                    [u2_1, 0, 0, 0],
                    [u3_1, 0, 0, 0],
                    [u4_1, 0, 0, 0],
            ]
            v = [
                    [v1, 0, 0, 0,],
            ]

            a, b = gen_first_col_exp_uv(a,b,ci,u,v,φ)



        case "lawson43-gen-mod_2h4s": # GenLawson4 https://ora.ox.ac.uk/objects/uuid:cc001282-4285-4ca2-ad06-31787b540c61/files/m611df1a355ca243beb09824b70e5e774
            c1,c2,c3,c4 = 0, 1/2, 1/2, 1
            ci = [c1,c2,c3,c4]
            φ = Phi(h, ci)

            a3_2 = 1/2
            a4_3 = φ(0,2)
            
            b3 = b2 = (1/3) * a4_3
            b4 = (1/3)*φ(2) + φ(3) + φ(4) - (5/24)*φ(0,2)

            a = [
                    [0, 0,    0, 0],
                    [0, 0,    0, 0],
                    [0, a3_2, 0, 0],
                    [0, 0, a4_3, 0],
            ]
            b = [
                    [0, b2, b3, b4,],
            ]

            if extra_options_flag("h_prev_h_h_no_eta", extra_options):
                φ1 = Phi(h_prev1_no_eta * h/h_no_eta, ci)
                φ2 = Phi(h_prev2_no_eta * h/h_no_eta, ci)
            elif extra_options_flag("h_only", extra_options):
                φ1 = Phi(h, ci)
                φ2 = Phi(h, ci)
            else:
                φ1 = Phi(h_prev1_no_eta, ci)
                φ2 = Phi(h_prev2_no_eta, ci)

            u2_1 = -2*φ1(2,2) - 2*φ1(3,2)
            u3_1 = -2*φ1(2,2) - 2*φ1(3,2) + 5/8
            u4_1 = -2*φ1(2) - 2*φ1(3) + (5/4)*φ1(0,2)
            v1 = -φ1(2) + φ1(3) + 3*φ1(4) + (5/24)*φ1(0,2)
            
            u2_2 = -(1/2)*φ2(2,2) + φ2(3,2)
            u3_2 = (1/2)*φ2(2,2) + φ2(3,2) - 3/16
            u4_2 = (1/2)*φ2(2) + φ2(3) - (3/8)*φ2(0,2)
            v2 = (1/6)*φ2(2) - φ2(4) - (1/24)*φ2(0,2)
            
            u = [
                    [   0,    0, 0, 0],
                    [u2_1, u2_2, 0, 0],
                    [u3_1, u3_2, 0, 0],
                    [u4_1, u4_2, 0, 0],
            ]
            v = [
                    [v1, v2, 0, 0,],
            ]

            a, b = gen_first_col_exp_uv(a,b,ci,u,v,φ)


        case "lawson44-gen-mod_3h4s": # GenLawson4 https://ora.ox.ac.uk/objects/uuid:cc001282-4285-4ca2-ad06-31787b540c61/files/m611df1a355ca243beb09824b70e5e774
            c1,c2,c3,c4 = 0, 1/2, 1/2, 1
            ci = [c1,c2,c3,c4]
            φ = Phi(h, ci)

            a3_2 = 1/2
            a4_3 = φ(0,2)
            
            b3 = b2 = (1/3) * a4_3
            b4 = (1/4)*φ(2) + (11/12)*φ(3) + (3/2)*φ(4) + φ(5) - (35/192)*φ(0,2)

            a = [
                    [0, 0,    0, 0],
                    [0, 0,    0, 0],
                    [0, a3_2, 0, 0],
                    [0, 0, a4_3, 0],
            ]
            b = [
                    [0, b2, b3, b4,],
            ]

            if extra_options_flag("h_prev_h_h_no_eta", extra_options):
                φ1 = Phi(h_prev1_no_eta * h/h_no_eta, ci)
                φ2 = Phi(h_prev2_no_eta * h/h_no_eta, ci)
                φ3 = Phi(h_prev3_no_eta * h/h_no_eta, ci)
            elif extra_options_flag("h_only", extra_options):
                φ1 = Phi(h, ci)
                φ2 = Phi(h, ci)
                φ3 = Phi(h, ci)
            else:
                φ1 = Phi(h_prev1_no_eta, ci)
                φ2 = Phi(h_prev2_no_eta, ci)
                φ3 = Phi(h_prev3_no_eta, ci)
                
            u2_1 = -3*φ1(2,2) - 5*φ1(3,2) - 3*φ1(4,2)
            u3_1 = u2_1 + 35/32
            u4_1 = -3*φ1(2) - 5*φ1(3) - 3*φ1(4) + (35/16)*φ1(0,2)
            v1 = -(3/2)*φ1(2) + (1/2)*φ1(3) + 6*φ1(4) + 6*φ1(5) + (35/96)*φ1(0,2)
            
            u2_2 = (3/2)*φ2(2,2) + 4*φ2(3,2) + 3*φ2(4,2)
            u3_2 = u2_2 - 21/32
            u4_2 = (3/2)*φ2(2) + 4*φ2(3) + 3*φ2(4) - (21/16)*φ2(0,2)
            v2 = (1/2)*φ2(2) + (1/3)*φ2(3) - 3*φ2(4) - 4*φ2(5) - (7/48)*φ2(0,2)
            
            u2_3 = (-1/3)*φ3(2,2) - φ3(3,2) - φ3(4,2)
            u3_3 = u2_3 + 5/32
            u4_3 = -(1/3)*φ3(2) - φ3(3) - φ3(4) + (5/16)*φ3(0,2)
            v3 = -(1/12)*φ3(2) - (1/12)*φ3(3) + (1/2)*φ3(4) + φ3(5) + (5/192)*φ3(0,2)
            
            u = [
                    [   0,    0,    0, 0],
                    [u2_1, u2_2, u2_3, 0],
                    [u3_1, u3_2, u3_3, 0],
                    [u4_1, u4_2, u4_3, 0],
            ]
            v = [
                    [v1, v2, v3, 0,],
            ]

            a, b = gen_first_col_exp_uv(a,b,ci,u,v,φ)



        case "lawson45-gen-mod_4h4s": # GenLawson4 https://ora.ox.ac.uk/objects/uuid:cc001282-4285-4ca2-ad06-31787b540c61/files/m611df1a355ca243beb09824b70e5e774
            c1,c2,c3,c4 = 0, 1/2, 1/2, 1
            ci = [c1,c2,c3,c4]
            φ = Phi(h, ci)

            a3_2 = 1/2
            a4_3 = φ(0,2)
            
            b2 = (1/3) * φ(0,2)
            b3 = (1/3) * φ(0,2)
            b4 = (12/59)*φ(2) + (50/59)*φ(3) + (105/59)*φ(4) + (120/59)*φ(5) - (60/59)*φ(6) - (157/944)*φ(0,2)

            a = [
                    [0, 0,    0, 0],
                    [0, 0,    0, 0],
                    [0, a3_2, 0, 0],
                    [0, 0, a4_3, 0],
            ]
            b = [
                    [0, b2, b3, b4,],
            ]

            if extra_options_flag("h_prev_h_h_no_eta", extra_options):
                φ1 = Phi(h_prev1_no_eta * h/h_no_eta, ci)
                φ2 = Phi(h_prev2_no_eta * h/h_no_eta, ci)
                φ3 = Phi(h_prev3_no_eta * h/h_no_eta, ci)
                φ4 = Phi(h_prev4_no_eta * h/h_no_eta, ci)
            elif extra_options_flag("h_only", extra_options):
                φ1 = Phi(h, ci)
                φ2 = Phi(h, ci)
                φ3 = Phi(h, ci)
                φ4 = Phi(h, ci)
            else:
                φ1 = Phi(h_prev1_no_eta, ci)
                φ2 = Phi(h_prev2_no_eta, ci)
                φ3 = Phi(h_prev3_no_eta, ci)
                φ4 = Phi(h_prev4_no_eta, ci)
                
            u2_1 = -4*φ1(2,2) - (26/3)*φ1(3,2) - 9*φ1(4,2) - 4*φ1(5,2)
            u3_1 = u2_1 + 105/64
            u4_1 = -4*φ1(2) - (26/3)*φ1(3) - 9*φ1(4) - 4*φ1(5) + (105/32)*φ1(0,2)
            v1 = -(116/59)*φ1(2) -  (34/177)*φ1(3) + (519/59)*φ1(4) + (964/59)*φ1(5) - (600/59)*φ1(6) +   (495/944)*φ1(0,2)
            
            u2_2 = 3*φ2(2,2) + (19/2)*φ2(3,2) + 12*φ2(4,2) + 6*φ2(5,2)
            u3_2 = u2_2 - 189/128
            u4_2 = 3*φ2(2) + (19/2)*φ2(3) + 12*φ2(4) + 6*φ2(5) - (189/64)*φ2(0,2)
            v2 =  (57/59)*φ2(2) + (121/118)*φ2(3) - (342/59)*φ2(4) - (846/59)*φ2(5) + (600/59)*φ2(6) -  (577/1888)*φ2(0,2)
            
            u2_3 = -(4/3)*φ3(2,2) - (14/3)*φ3(3,2) - 7*φ3(4,2) - 4*φ3(5,2)
            u3_3 = u2_3 + 45/64
            u4_3 = -(4/3)*φ3(2) - (14/3)*φ3(3) - 7*φ3(4) - 4*φ3(5) +(45/32)*φ3(0,2)
            v3 = -(56/177)*φ3(2) -  (76/177)*φ3(3) + (112/59)*φ3(4) + (364/59)*φ3(5) - (300/59)*φ3(6) +    (25/236)*φ3(0,2)
            
            u2_4 = (1/4)*φ4(2,2) + (88/96)*φ4(3,2) + (3/2)*φ4(4,2) + φ4(5,2)
            u3_4 = u2_4 - 35/256
            u4_4 = (1/4)*φ4(2) + (11/12)*φ4(3) + (3/2)*φ4(4) + φ4(5) - (35/128)*φ4(0,2)
            v4 =  (11/236)*φ4(2) +  (49/708)*φ4(3) - (33/118)*φ4(4) -  (61/59)*φ4(5) + ( 60/59)*φ4(6) - (181/11328)*φ4(0,2)

            u = [
                    [   0,    0,    0,    0],
                    [u2_1, u2_2, u2_3, u2_4],
                    [u3_1, u3_2, u3_3, u3_4],
                    [u4_1, u4_2, u4_3, u4_4],
            ]
            v = [
                    [v1, v2, v3, v4,],
            ]

            a, b = gen_first_col_exp_uv(a,b,ci,u,v,φ)



        case "etdrk2_2s": # https://arxiv.org/pdf/2402.15142v1
            c1,c2 = 0, 1
            ci = [c1,c2]
            φ = Phi(h, ci)   
                     
            a = [
                    [0, 0],
                    [φ(1), 0],
            ]
            b = [
                    [φ(1)-φ(2), φ(2)],
            ]

        case "etdrk3_a_3s": # https://arxiv.org/pdf/2402.15142v1
            c1,c2,c3 = 0, 1, 2/3
            ci = [c1,c2,c3]
            φ = Phi(h, ci)   
            
            a2_1 = c2*φ(1)
            a3_2 = (4/9)*φ(2,3)
            a3_1 = c3*φ(1,3) - a3_2
            
            b2 = φ(2) - (1/2)*φ(1)
            b3 = (3/4) * φ(1)
            b1 = φ(1) - b2 - b3 
                     
            a = [
                    [0, 0, 0],
                    [a2_1, 0, 0],
                    [a3_1, a3_2, 0 ]
            ]
            b = [
                    [b1, b2, b3],
            ]

        case "etdrk3_b_3s": # https://arxiv.org/pdf/2402.15142v1
            c1,c2,c3 = 0, 4/9, 2/3
            ci = [c1,c2,c3]
            φ = Phi(h, ci)   
            
            a2_1 = c2*φ(1,2)
            a3_2 = φ(2,3)
            a3_1 = c3*φ(1,3) - a3_2
            
            b2 = 0
            b3 = (3/2) * φ(2)
            b1 = φ(1) - b2 - b3 
                     
            a = [
                    [0, 0, 0],
                    [a2_1, 0, 0],
                    [a3_1, a3_2, 0 ]
            ]
            b = [
                    [b1, b2, b3],
            ]

        case "etdrk4_4s": # https://ora.ox.ac.uk/objects/uuid:cc001282-4285-4ca2-ad06-31787b540c61/files/m611df1a355ca243beb09824b70e5e774
            c1,c2,c3,c4 = 0, 1/2, 1/2, 1
            ci = [c1,c2,c3,c4]
            φ = Phi(h, ci)
            
            a3_2 =   φ(1,2)
            a4_3 = 2*φ(1,2)

            b2 = 2*φ(2) - 4*φ(3)
            b3 = 2*φ(2) - 4*φ(3)
            b4 =  -φ(2) + 4*φ(3)

            a = [
                    [0, 0,0,0],
                    [0, 0,0,0],
                    [0, a3_2,0,0],
                    [0, 0, a4_3,0],
            ]
            b = [
                    [0, b2, b3, b4],
            ]

            a, b = gen_first_col_exp(a,b,ci,φ)

            
        case "dpmpp_2s":
            c2 = float(get_extra_options_kv("c2", str(c2), extra_options))
            
            a2_1 =         c2   * phi(1, -h*c2)
            b1 = (1 - 1/(2*c2)) * phi(1, -h)
            b2 =     (1/(2*c2)) * phi(1, -h)

            a = [
                    [0, 0],
                    [a2_1, 0],
            ]
            b = [
                    [b1, b2],
            ]
            ci = [0, c2]
            
        case "dpmpp_sde_2s":
            c2 = 1.0 #hardcoded to 1.0 to more closely emulate the configuration for k-diffusion's implementation
            a2_1 =         c2   * phi(1, -h*c2)
            b1 = (1 - 1/(2*c2)) * phi(1, -h)
            b2 =     (1/(2*c2)) * phi(1, -h)

            a = [
                    [0, 0],
                    [a2_1, 0],
            ]
            b = [
                    [b1, b2],
            ]
            ci = [0, c2]

        case "dpmpp_3s":
            c2 = float(get_extra_options_kv("c2", str(c2), extra_options))
            c3 = float(get_extra_options_kv("c3", str(c3), extra_options))
            
            a2_1 = c2 * phi(1, -h*c2)
            a3_2 = (c3**2 / c2) * phi(2, -h*c3)
            a3_1 = c3 * phi(1, -h*c3) - a3_2
            b2 = 0
            b3 = (1/c3) * phi(2, -h)
            b1 = phi(1, -h) - b2 - b3

            a = [
                    [0, 0, 0],
                    [a2_1, 0, 0],
                    [a3_1, a3_2, 0],  
            ]
            b = [
                    [b1, b2, b3],
            ]
            ci = [0, c2, c3]
            
        case "res_5s": #4th order
                
            c1, c2, c3, c4, c5 = 0, 1/2, 1/2, 1, 1/2
            
            a2_1 = c2 * phi(1, -h * c2)
            
            a3_2 = phi(2, -h * c3)
            a3_1 = c3 * phi(1, -h * c3) - a3_2
            #a3_1 = c3 * phi(1, -h * c3) - phi(2, -h * c3)

            a4_2 = a4_3 = phi(2, -h * c4)
            a4_1 = c4 * phi(1, -h * c4) - a4_2 - a4_3
            #a4_1 = phi(1, -h * c4) - 2 * phi(2, -h * c4)
            
            a5_2 = a5_3 = 0.5 * phi(2, -h * c5) - phi(3, -h * c4) + 0.25 * phi(2, -h * c4) - 0.5 * phi(3, -h * c5)
            a5_4 = 0.25 * phi(2, -h * c5) - a5_2
            a5_1 = c5 * phi(1, -h * c5) - a5_2 - a5_3 - a5_4
                    
            b2 = b3 = 0
            b4 = -phi(2, -h) + 4*phi(3, -h)
            b5 = 4 * phi(2, -h) - 8 * phi(3, -h)
            #b1 = phi(1, -h) - 3 * phi(2, -h) + 4 * phi(3, -h)
            b1 = phi(1,-h) - b2 - b3 - b4 - b5

            a = [
                    [0, 0, 0, 0, 0],
                    [a2_1, 0, 0, 0, 0],
                    [a3_1, a3_2, 0, 0, 0],
                    [a4_1, a4_2, a4_3, 0, 0],
                    [a5_1, a5_2, a5_3, a5_4, 0],
            ]
            b = [
                    [b1, b2, b3, b4, b5],
            ]
            ci = [0., 0.5, 0.5, 1., 0.5]
            
        case "res_6s": #4th order
                
            c1, c2, c3, c4, c5, c6 = 0, 1/2, 1/2, 1/3, 1/3, 5/6
            ci = [c1, c2, c3, c4, c5, c6]
            φ = Phi(h, ci)
            
            a2_1 = c2 * φ(1,2)
            
            a3_1 = 0
            a3_2 = (c3**2 / c2) * φ(2,3)
            
            a4_1 = 0
            a4_2 = (c4**2 / c2) * φ(2,4)
            a4_3 = (c4**2 * φ(2,4) - a4_2 * c2) / c3
            
            a5_1 = 0
            a5_2 = 0 #zero
            a5_3 = (-c4 * c5**2 * φ(2,5) + 2*c5**3 * φ(3,5))   /   (c3 * (c3 - c4))
            a5_4 = (-c3 * c5**2 * φ(2,5) + 2*c5**3 * φ(3,5))   /   (c4 * (c4 - c3))
            
            a6_1 = 0
            a6_2 = 0 #zero
            a6_3 = (-c4 * c6**2 * φ(2,6) + 2*c6**3 * φ(3,6))   /   (c3 * (c3 - c4))
            a6_4 = (-c3 * c6**2 * φ(2,6) + 2*c6**3 * φ(3,6))   /   (c4 * (c4 - c3))
            a6_5 = (c6**2 * φ(2,6) - a6_3*c3 - a6_4*c4)   /   c5
            #a6_5_alt = (2*c6**3 * φ(3,6) - a6_3*c3**2 - a6_4*c4**2)   /   c5**2
                    
            b1 = 0
            b2 = 0
            b3 = 0
            b4 = 0
            b5 = (-c6*φ(2) + 2*φ(3)) / (c5 * (c5 - c6))
            b6 = (-c5*φ(2) + 2*φ(3)) / (c6 * (c6 - c5))

            a = [
                    [0, 0, 0, 0, 0, 0],
                    [0, 0, 0, 0, 0, 0],
                    [0, a3_2, 0, 0, 0, 0],
                    [0, a4_2, a4_3, 0, 0, 0],
                    [0, a5_2, a5_3, a5_4, 0, 0],
                    [0, a6_2, a6_3, a6_4, a6_5, 0],
            ]
            b = [
                    [0, b2, b3, b4, b5, b6],
            ]
             
            for i in range(len(ci)): 
                a[i][0] = ci[i] * φ(1,i+1) - sum(a[i])
            for i in range(len(b)): 
                b[i][0] =         φ(1)     - sum(b[i])

        case "res_8s": # this is not EXPRK5S8 https://ora.ox.ac.uk/objects/uuid:cc001282-4285-4ca2-ad06-31787b540c61/files/m611df1a355ca243beb09824b70e5e774
                
            c1, c2, c3, c4, c5, c6, c7, c8 = 0, 1/2, 1/2, 1/4,    1/2, 1/5, 2/3, 1
            ci = [c1, c2, c3, c4, c5, c6, c7, c8]
            φ = Phi(h, ci, analytic_solution=True)
            
            a3_2 = (1/2) * φ(2,3)
            
            a4_3 = (1/8) * φ(2,4)

            a5_3 = (-1/2) * φ(2,5) + 2 * φ(3,5)
            a5_4 =      2 * φ(2,5) - 4 * φ(3,5)
            
            a6_4 = (8/25) * φ(2,6) - (32/125) * φ(3,6)
            a6_5 = (2/25) * φ(2,6) -  (1/2)   * a6_4
            
            a7_4 = (-125/162)  * a6_4
            a7_5 =  (125/1944) * a6_4 -  (16/27) * φ(2,7) + (320/81) * φ(3,7)
            a7_6 = (3125/3888) * a6_4 + (100/27) * φ(2,7) - (800/81) * φ(3,7)
            
            Φ = (5/32)*a6_4 - (1/28)*φ(2,6) + (36/175)*φ(2,7) - (48/25)*φ(3,7) + (6/175)*φ(4,6) + (192/35)*φ(4,7) + 6*φ(4,8)
            
            a8_5 =  (208/3)*φ(3,8) -  (16/3) *φ(2,8) -      40*Φ
            a8_6 = (-250/3)*φ(3,8) + (250/21)*φ(2,8) + (250/7)*Φ
            a8_7 =      -27*φ(3,8) +  (27/14)*φ(2,8) + (135/7)*Φ
            
            b6 = (125/14)*φ(2) - (625/14)*φ(3) + (1125/14)*φ(4)
            b7 = (-27/14)*φ(2) + (162/7) *φ(3) -  (405/7) *φ(4)
            b8 =   (1/2) *φ(2) -  (13/2) *φ(3) +   (45/2) *φ(4)
            
            a2_1 = c2*φ(1,2) 
            a3_1 = c3*φ(1,3) - a3_2
            a4_1 = c4*φ(1,4) - a4_3
            a5_1 = c5*φ(1,5) - a5_3 - a5_4 
            a6_1 = c6*φ(1,6) - a6_4 - a6_5
            a7_1 = c7*φ(1,7) - a7_4 - a7_5 - a7_6
            a8_1 = c8*φ(1,8) - a8_5 - a8_6 - a8_7 
            b1   =    φ(1)   - b6 - b7 - b8
            
            a = [
                    [0,    0, 0, 0, 0, 0, 0, 0],
                    [a2_1, 0, 0, 0, 0, 0, 0, 0],
                    
                    [a3_1, a3_2, 0, 0, 0, 0, 0, 0],
                    [a4_1, 0, a4_3, 0, 0, 0, 0, 0],
                    
                    [a5_1, 0, a5_3, a5_4, 0, 0, 0, 0],
                    [a6_1, 0, 0, a6_4, a6_5, 0, 0, 0],
                    
                    [a7_1 , 0, 0, a7_4, a7_5, a7_6, 0,    0],
                    [a8_1 , 0, 0, 0,    a8_5, a8_6, a8_7, 0],
            ]
            b = [
                    [b1,   0, 0, 0, 0, b6, b7, b8],
            ]
             
            a = [
                    [0, 0, 0, 0, 0, 0, 0, 0],
                    [0, 0, 0, 0, 0, 0, 0, 0],
                    
                    [0, a3_2, 0, 0, 0, 0, 0, 0],
                    [0, 0, a4_3, 0, 0, 0, 0, 0],
                    
                    [0, 0, a5_3, a5_4, 0, 0, 0, 0],
                    [0, 0, 0, a6_4, a6_5, 0, 0, 0],
                    
                    [0 , 0, 0, a7_4, a7_5, a7_6, 0,    0],
                    [0 , 0, 0, 0,    a8_5, a8_6, a8_7, 0],
            ]
            b = [
                    [0,   0, 0, 0, 0, b6, b7, b8],
            ]
             
            for i in range(len(a)): 
                a[i][0] = ci[i] * φ(1,i+1) - sum(a[i])
            for i in range(len(b)): 
                b[i][0] =         φ(1)     - sum(b[i])



        case "res_8s_alt": # this is EXPRK5S8 https://ora.ox.ac.uk/objects/uuid:cc001282-4285-4ca2-ad06-31787b540c61/files/m611df1a355ca243beb09824b70e5e774
                
            c1, c2, c3, c4, c5, c6, c7, c8 = 0, 1/2, 1/2, 1/4,    1/2, 1/5, 2/3, 1
            ci = [c1, c2, c3, c4, c5, c6, c7, c8]
            φ = Phi(h, ci, analytic_solution=True)
            
            a3_2 = 2*φ(2,2)
            
            a4_3 = 2*φ(2,4)

            a5_3 = 2*φ(2,2) + 16*φ(3,2)
            a5_4 = 8*φ(2,2) - 32*φ(3,2)
            
            a6_4 =  8*φ(2,6) - 32*φ(3,6)
            a6_5 = -2*φ(2,6) + 16*φ(3,6)
            
            a7_4 = (-125/162)  * a6_4
            a7_5 =  (125/1944) * a6_4 -  (4/3) * φ(2,7) +  (40/3)*φ(3,7)
            a7_6 = (3125/3888) * a6_4 + (25/3) * φ(2,7) - (100/3)*φ(3,7)
            
            Φ = (5/32)*a6_4 - (25/28)*φ(2,6) + (81/175)*φ(2,7) - (162/25)*φ(3,7) + (150/7)*φ(4,6) + (972/35)*φ(4,7) + 6*φ(4)
            
            a8_5 =  -(16/3)*φ(2) + (203/3)*φ(3)  -    40*Φ
            a8_6 = (250/21)*φ(2) - (250/3)*φ(3) + (250/7)*Φ
            a8_7 =  (27/14)*φ(2) +      27*φ(3) + (135/7)*Φ
            
            b6 = (125/14)*φ(2) - (625/14)*φ(3) + (1125/14)*φ(4)
            b7 = (-27/14)*φ(2) + (162/7) *φ(3) -  (405/7) *φ(4)
            b8 =   (1/2) *φ(2) -  (13/2) *φ(3) +   (45/2) *φ(4)
            
             
            a = [
                    [0, 0, 0, 0, 0, 0, 0, 0],
                    [0, 0, 0, 0, 0, 0, 0, 0],
                    
                    [0, a3_2, 0, 0, 0, 0, 0, 0],
                    [0, 0, a4_3, 0, 0, 0, 0, 0],
                    
                    [0, 0, a5_3, a5_4, 0, 0, 0, 0],
                    [0, 0, 0, a6_4, a6_5, 0, 0, 0],
                    
                    [0 , 0, 0, a7_4, a7_5, a7_6, 0,    0],
                    [0 , 0, 0, 0,    a8_5, a8_6, a8_7, 0],
            ]
            b = [
                    [0,   0, 0, 0, 0, b6, b7, b8],
            ]

            a, b = gen_first_col_exp(a,b,ci,φ)



        case "res_10s":
                
            c1, c2, c3, c4, c5, c6, c7, c8, c9, c10 = 0, 1/2, 1/2, 1/3, 1/2,     1/3, 1/4, 3/10, 3/4, 1
            ci = [c1, c2, c3, c4, c5, c6, c7, c8, c9, c10]
            φ = Phi(h, ci, analytic_solution=False)        
                
            a3_2 = (c3**2 / c2) * φ(2,3)
            a4_2 = (c4**2 / c2) * φ(2,4)
                        
            b8 =  (c9*c10*φ(2) - 2*(c9+c10)*φ(3) + 6*φ(4))   /   (c8 * (c8-c9) * (c8-c10))
            b9 =  (c8*c10*φ(2) - 2*(c8+c10)*φ(3) + 6*φ(4))   /   (c9 * (c9-c8) * (c9-c10))
            
            b10 = (c8*c9*φ(2)  - 2*(c8+c9) *φ(3) + 6*φ(4))   /   (c10 * (c10-c8) * (c10-c9))
            
            a = [
                    [0, 0, 0, 0, 0,      0, 0, 0, 0, 0],
                    [0, 0, 0, 0, 0,      0, 0, 0, 0, 0],
                    [0, a3_2, 0, 0, 0,      0, 0, 0, 0, 0],
                    [0, a4_2, 0, 0, 0,      0, 0, 0, 0, 0],
                    [0, 0, 0, 0, 0,      0, 0, 0, 0, 0],
                    
                    [0, 0, 0, 0, 0,      0, 0, 0, 0, 0],
                    [0, 0, 0, 0, 0,      0, 0, 0, 0, 0],
                    [0, 0, 0, 0, 0,      0, 0, 0, 0, 0],
                    [0, 0, 0, 0, 0,      0, 0, 0, 0, 0],
                    [0, 0, 0, 0, 0,      0, 0, 0, 0, 0],
            ]
            b = [
                    [0, 0, 0, 0, 0,      0, 0, b8, b9, b10],
            ]
            
            # a5_3, a5_4
            # a6_3, a6_4
            # a7_3, a7_4
            for i in range(5, 8): # i=5,6,7   j,k ∈ {3, 4}, j != k
                jk = [(3, 4), (4, 3)]
                jk = list(permutations([3, 4], 2)) 
                for j,k in jk:
                    a[i-1][j-1] = (-ci[i-1]**2 * ci[k-1] * φ(2,i)    +   2*ci[i-1]**3 * φ(3,i))   /   (ci[j-1] * (ci[j-1] - ci[k-1]))
                
            for i in range(8, 11): # i=8,9,10   j,k,l ∈ {5, 6, 7}, j != k != l      [    (5, 6, 7), (5, 7, 6),    (6, 5, 7), (6, 7, 5),    (7, 5, 6), (7, 6, 5)]    6 total coeff
                jkl = list(permutations([5, 6, 7], 3)) 
                for j,k,l in jkl:
                    a[i-1][j-1] = (ci[i-1]**2 * ci[k-1] * ci[l-1] * φ(2,i)   -   2*ci[i-1]**3 * (ci[k-1] + ci[l-1]) * φ(3,i)   +   6*ci[i-1]**4 * φ(4,i))    /    (ci[j-1] * (ci[j-1] - ci[k-1]) * (ci[j-1] - ci[l-1]))

            for i in range(len(a)): 
                a[i][0] = ci[i] * φ(1,i+1) - sum(a[i])
            for i in range(len(b)): 
                b[i][0] =         φ(1)     - sum(b[i])



        case "res_15s":
                
            c1,c2,c3,c4,c5,c6,c7,c8,c9,c10,c11,c12,c13,c14,c15 = 0, 1/2, 1/2, 1/3, 1/2,    1/5, 1/4, 18/25, 1/3, 3/10,    1/6, 90/103, 1/3, 3/10, 1/5
            c1 = 0
            c2 = c3 = c5 = 1/2
            c4 = c9 = c13 = 1/3
            c6 = c15 = 1/5
            c7 = 1/4
            c8 = 18/25
            c10 = c14 = 3/10
            c11 = 1/6
            c12 = 90/103
            c15 = 1/5
            ci = [c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, c11, c12, c13, c14, c15]
            φ = Phi(h, ci, analytic_solution=False)
            
            a = [[0 for _ in range(15)] for _ in range(15)]
            b = [[0 for _ in range(15)]]

            for i in range(3, 5): # i=3,4     j=2
                j=2
                a[i-1][j-1] = (ci[i-1]**2 / ci[j-1]) * φ(j,i)
            
            
            for i in range(5, 8): # i=5,6,7   j,k ∈ {3, 4}, j != k
                jk = list(permutations([3, 4], 2)) 
                for j,k in jk:
                    a[i-1][j-1] = (-ci[i-1]**2 * ci[k-1] * φ(2,i)    +   2*ci[i-1]**3 * φ(3,i))   /   prod_diff(ci[j-1], ci[k-1])

            for i in range(8, 12): # i=8,9,10,11  j,k,l ∈ {5, 6, 7}, j != k != l      [    (5, 6, 7), (5, 7, 6),    (6, 5, 7), (6, 7, 5),    (7, 5, 6), (7, 6, 5)]    6 total coeff
                jkl = list(permutations([5, 6, 7], 3)) 
                for j,k,l in jkl:
                    a[i-1][j-1] = (ci[i-1]**2 * ci[k-1] * ci[l-1] * φ(2,i)   -   2*ci[i-1]**3 * (ci[k-1] + ci[l-1]) * φ(3,i)   +   6*ci[i-1]**4 * φ(4,i))    /    (ci[j-1] * (ci[j-1] - ci[k-1]) * (ci[j-1] - ci[l-1]))

            for i in range(12,16): # i=12,13,14,15
                jkld = list(permutations([8,9,10,11], 4)) 
                for j,k,l,d in jkld:
                    numerator = -ci[i-1]**2  *  ci[d-1]*ci[k-1]*ci[l-1]  *  φ(2,i)     +     2*ci[i-1]**3  *  (ci[d-1]*ci[k-1] + ci[d-1]*ci[l-1] + ci[k-1]*ci[l-1])  *  φ(3,i)     -     6*ci[i-1]**4  *  (ci[d-1] + ci[k-1] + ci[l-1])  *  φ(4,i)     +     24*ci[i-1]**5  *  φ(5,i)
                    a[i-1][j-1] = numerator / prod_diff(ci[j-1], ci[k-1], ci[l-1], ci[d-1])

            """ijkl = list(permutations([12,13,14,15], 4)) 
            for i,j,k,l in ijkl:
                #numerator = -ci[j-1]*ci[k-1]*ci[l-1]*φ(2)   +   2*(ci[j-1]*ci[k-1]   +   ci[j-1]*ci[l-1]   +   ci[k-1]*ci[l-1])*φ(3)   -   6*(ci[j-1] + ci[k-1]   +   ci[l-1])*φ(4)   +   24*φ(5)
                #b[0][i-1] = numerator / prod_diff(ci[i-1], ci[j-1], ci[k-1], ci[l-1])
                for jjj in range (2, 6): # 2,3,4,5
                    b[0][i-1] += mu_numerator(jjj, ci[j-1], ci[i-1], ci[k-1], ci[l-1]) * φ(jjj) 
                b[0][i-1] /= prod_diff(ci[i-1], ci[j-1], ci[k-1], ci[l-1])"""
                    
            ijkl = list(permutations([12,13,14,15], 4)) 
            for i,j,k,l in ijkl:
                numerator = 0
                for jjj in range(2, 6):  # 2, 3, 4, 5
                    numerator += mu_numerator(jjj, ci[j-1], ci[i-1], ci[k-1], ci[l-1]) * φ(jjj)
                #print(i,j,k,l)

                b[0][i-1] = numerator / prod_diff(ci[i-1], ci[j-1], ci[k-1], ci[l-1])
             
             
            ijkl = list(permutations([12, 13, 14, 15], 4))
            selected_permutations = {} 
            sign = 1  

            for i in range(12, 16):
                results = []
                for j, k, l, d in ijkl:
                    if i != j and i != k and i != l and i != d:
                        numerator = 0
                        for jjj in range(2, 6):  # 2, 3, 4, 5
                            numerator += mu_numerator(jjj, ci[j-1], ci[i-1], ci[k-1], ci[l-1]) * φ(jjj)
                        theta_value = numerator / prod_diff(ci[i-1], ci[j-1], ci[k-1], ci[l-1])
                        results.append((theta_value, (i, j, k, l, d)))

                results.sort(key=lambda x: abs(x[0]))

                for theta_value, permutation in results:
                    if sign == 1 and theta_value > 0:
                        selected_permutations[i] = (theta_value, permutation)
                        sign *= -1  
                        break
                    elif sign == -1 and theta_value < 0:  
                        selected_permutations[i] = (theta_value, permutation)
                        sign *= -1 
                        break

            for i in range(12, 16):
                if i in selected_permutations:
                    theta_value, (i, j, k, l, d) = selected_permutations[i]
                    b[0][i-1] = theta_value  
                    
            for i in selected_permutations:
                theta_value, permutation = selected_permutations[i]
                print(f"i={i}")
                print(f"  Selected Theta: {theta_value:.6f}, Permutation: {permutation}")
             
             
             
            for i in range(len(a)): 
                a[i][0] = ci[i] * φ(1,i+1) - sum(a[i])
            for i in range(len(b)): 
                b[i][0] =         φ(1)     - sum(b[i])
            
            

        case "res_16s": # 6th order without weakened order conditions
                
            c1 = 0
            c2 = c3 = c5 = c8 = c12 = 1/2
            c4 = c11 = c15 = 1/3
            c6 = c9 = c13 = 1/5
            c7 = c10 = c14 = 1/4
            c16 = 1
            ci = [c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, c11, c12, c13, c14, c15, c16]
            φ = Phi(h, ci, analytic_solution=True)
            
            a3_2 = (1/2) * φ(2,3)

            a = [[0 for _ in range(16)] for _ in range(16)]
            b = [[0 for _ in range(16)]]

            for i in range(3, 5): # i=3,4     j=2
                j=2
                a[i-1][j-1] = (ci[i-1]**2 / ci[j-1]) * φ(j,i)
            
            for i in range(5, 8): # i=5,6,7   j,k ∈ {3, 4}, j != k
                jk = list(permutations([3, 4], 2)) 
                for j,k in jk:
                    a[i-1][j-1] = (-ci[i-1]**2 * ci[k-1] * φ(2,i)    +   2*ci[i-1]**3 * φ(3,i))   /   prod_diff(ci[j-1], ci[k-1])
                    
            for i in range(8, 12): # i=8,9,10,11  j,k,l ∈ {5, 6, 7}, j != k != l      [    (5, 6, 7), (5, 7, 6),    (6, 5, 7), (6, 7, 5),    (7, 5, 6), (7, 6, 5)]    6 total coeff
                jkl = list(permutations([5, 6, 7], 3)) 
                for j,k,l in jkl:
                    a[i-1][j-1] = (ci[i-1]**2 * ci[k-1] * ci[l-1] * φ(2,i)   -   2*ci[i-1]**3 * (ci[k-1] + ci[l-1]) * φ(3,i)   +   6*ci[i-1]**4 * φ(4,i))    /    (ci[j-1] * (ci[j-1] - ci[k-1]) * (ci[j-1] - ci[l-1]))

            for i in range(12,17): # i=12,13,14,15,16
                jkld = list(permutations([8,9,10,11], 4)) 
                for j,k,l,d in jkld:
                    numerator = -ci[i-1]**2  *  ci[d-1]*ci[k-1]*ci[l-1]  *  φ(2,i)     +     2*ci[i-1]**3  *  (ci[d-1]*ci[k-1] + ci[d-1]*ci[l-1] + ci[k-1]*ci[l-1])  *  φ(3,i)     -     6*ci[i-1]**4  *  (ci[d-1] + ci[k-1] + ci[l-1])  *  φ(4,i)     +     24*ci[i-1]**5  *  φ(5,i)
                    a[i-1][j-1] = numerator / prod_diff(ci[j-1], ci[k-1], ci[l-1], ci[d-1])
                     
            """ijdkl = list(permutations([12,13,14,15,16], 5)) 
            for i,j,d,k,l in ijdkl:
                #numerator = -ci[j-1]*ci[k-1]*ci[l-1]*φ(2)   +   2*(ci[j-1]*ci[k-1]   +   ci[j-1]*ci[l-1]   +   ci[k-1]*ci[l-1])*φ(3)   -   6*(ci[j-1] + ci[k-1]   +   ci[l-1])*φ(4)   +   24*φ(5)
                b[0][i-1] = theta(2, ci[d-1], ci[i-1], ci[k-1], ci[j-1], ci[l-1]) * φ(2)   +  theta(3, ci[d-1], ci[i-1], ci[k-1], ci[j-1], ci[l-1])*φ(3)   +   theta(4, ci[d-1], ci[i-1], ci[k-1], ci[j-1], ci[l-1])*φ(4)   +   theta(5, ci[d-1], ci[i-1], ci[k-1], ci[j-1], ci[l-1])*φ(5)    +    theta(6, ci[d-1], ci[i-1], ci[k-1], ci[j-1], ci[l-1]) * φ(6)
                #b[0][i-1] = numerator / prod_diff(ci[i-1], ci[j-1], ci[k-1], ci[l-1])"""
                    
                
            ijdkl = list(permutations([12,13,14,15,16], 5)) 
            for i,j,d,k,l in ijdkl:
                #numerator = -ci[j-1]*ci[k-1]*ci[l-1]*φ(2)   +   2*(ci[j-1]*ci[k-1]   +   ci[j-1]*ci[l-1]   +   ci[k-1]*ci[l-1])*φ(3)   -   6*(ci[j-1] + ci[k-1]   +   ci[l-1])*φ(4)   +   24*φ(5)
                #numerator = theta_numerator(2, ci[d-1], ci[i-1], ci[k-1], ci[j-1], ci[l-1]) * φ(2)   +  theta_numerator(3, ci[d-1], ci[i-1], ci[k-1], ci[j-1], ci[l-1])*φ(3)   +   theta_numerator(4, ci[d-1], ci[i-1], ci[k-1], ci[j-1], ci[l-1])*φ(4)   +   theta_numerator(5, ci[d-1], ci[i-1], ci[k-1], ci[j-1], ci[l-1])*φ(5)    +    theta_numerator(6, ci[d-1], ci[i-1], ci[k-1], ci[j-1], ci[l-1]) * φ(6)
                #b[0][i-1] = numerator / (ci[i-1] *, ci[d-1], ci[j-1], ci[k-1], ci[l-1])
                #b[0][i-1] = numerator / denominator(ci[i-1], ci[d-1], ci[j-1], ci[k-1], ci[l-1])
                b[0][i-1] = theta(2, ci[d-1], ci[i-1], ci[k-1], ci[j-1], ci[l-1]) * φ(2)   +  theta(3, ci[d-1], ci[i-1], ci[k-1], ci[j-1], ci[l-1])*φ(3)   +   theta(4, ci[d-1], ci[i-1], ci[k-1], ci[j-1], ci[l-1])*φ(4)   +   theta(5, ci[d-1], ci[i-1], ci[k-1], ci[j-1], ci[l-1])*φ(5)    +    theta(6, ci[d-1], ci[i-1], ci[k-1], ci[j-1], ci[l-1]) * φ(6)

            
            ijdkl = list(permutations([12,13,14,15,16], 5)) 
            for i,j,d,k,l in ijdkl:
                numerator = 0
                for jjj in range(2, 7):  # 2, 3, 4, 5, 6
                    numerator += theta_numerator(jjj, ci[d-1], ci[i-1], ci[k-1], ci[j-1], ci[l-1]) * φ(jjj)
                #print(i,j,d,k,l)
                b[0][i-1] = numerator / (ci[i-1] *   (ci[i-1] - ci[k-1])   *   (ci[i-1] - ci[j-1]   *   (ci[i-1] - ci[d-1])   *   (ci[i-1] - ci[l-1])))

                
            for i in range(len(a)): 
                a[i][0] = ci[i] * φ(1,i+1) - sum(a[i])
            for i in range(len(b)): 
                b[i][0] =         φ(1)     - sum(b[i])
            
            
            

            
        case "irk_exp_diag_2s":
            c1 = 1/3
            c2 = 2/3
            c1 = float(get_extra_options_kv("c1", str(c1), extra_options))
            c2 = float(get_extra_options_kv("c2", str(c2), extra_options))
            
            lam = (1 - torch.exp(-c1 * h)) / h
            a2_1 = ( torch.exp(c2*h) - torch.exp(c1*h))    /    (h * torch.exp(2*c1*h))
            b1 =  (1 + c2*h + torch.exp(h) * (-1 + h - c2*h)) / ((c1-c2) * h**2 * torch.exp(c1*h))
            b2 = -(1 + c1*h - torch.exp(h) * ( 1 - h + c1*h)) / ((c1-c2) * h**2 * torch.exp(c2*h))

            a = [
                    [lam, 0],
                    [a2_1, lam],
            ]
            b = [
                    [b1, b2],
            ]
            ci = [c1, c2]

    ci = ci[:]
    #if rk_type.startswith("lob") == False:
    ci.append(1)
        
    return a, b, u, v, ci, multistep_stages, hybrid_stages, FSAL



def gen_first_col_exp(a, b, c, φ):
    for i in range(len(c)): 
        a[i][0] = c[i] * φ(1,i+1) - sum(a[i])
    for i in range(len(b)): 
        b[i][0] =        φ(1)     - sum(b[i])
    return a, b

def gen_first_col_exp_uv(a, b, c, u, v, φ):
    for i in range(len(c)): 
        a[i][0] = c[i] * φ(1,i+1) - sum(a[i]) - sum(u[i])
    for i in range(len(b)): 
        b[i][0] =        φ(1)     - sum(b[i]) - sum(v[i])
    return a, b

def rho(j, ci, ck, cl):
    if j == 2:
        numerator = ck*cl
    if j == 3:
        numerator = (-2 * (ck + cl))
    if j == 4:
        numerator = 6
    return numerator / denominator(ci, ck, cl)
    
    
def mu(j, cd, ci, ck, cl):
    if j == 2:
        numerator = -cd * ck * cl
    if j == 3:
        numerator = 2 * (cd * ck + cd * cl + ck * cl)
    if j == 4:
        numerator = -6 * (cd + ck + cl)
    if j == 5:
        numerator = 24
    return numerator / denominator(ci, cd, ck, cl)

def mu_numerator(j, cd, ci, ck, cl):
    if j == 2:
        numerator = -cd * ck * cl
    if j == 3:
        numerator = 2 * (cd * ck + cd * cl + ck * cl)
    if j == 4:
        numerator = -6 * (cd + ck + cl)
    if j == 5:
        numerator = 24
    return numerator #/ denominator(ci, cd, ck, cl)



def theta_numerator(j, cd, ci, ck, cj, cl):
    if j == 2:
        numerator = -cj * cd * ck * cl
    if j == 3:
        numerator = 2 * (cj * ck * cd + cj*ck*cl + ck*cd*cl + cd*cl*cj)
    if j == 4:
        numerator = -6*(cj*ck + cj*cd + cj*cl + ck*cd + ck*cl + cd*cl)
    if j == 5:
        numerator = 24 * (cj + ck + cl + cd)
    if j == 6:
        numerator = -120
    return numerator # / denominator(ci, cj, ck, cl, cd)


def theta(j, cd, ci, ck, cj, cl):
    if j == 2:
        numerator = -cj * cd * ck * cl
    if j == 3:
        numerator = 2 * (cj * ck * cd + cj*ck*cl + ck*cd*cl + cd*cl*cj)
    if j == 4:
        numerator = -6*(cj*ck + cj*cd + cj*cl + ck*cd + ck*cl + cd*cl)
    if j == 5:
        numerator = 24 * (cj + ck + cl + cd)
    if j == 6:
        numerator = -120
    return numerator / ( ci * (ci - cj) * (ci - ck) * (ci - cl) * (ci - cd))
    return numerator / denominator(ci, cj, ck, cl, cd)


def prod_diff(cj, ck, cl=None, cd=None, cblah=None):
    if cl is None and cd is None:
        return cj * (cj - ck)
    if cd is None:
        return cj * (cj - ck) * (cj - cl)
    else:
        return cj * (cj - ck) * (cj - cl) * (cj - cd)

def denominator(ci, *args):
    result = ci 
    for arg in args:
        result *= (ci - arg)
    return result



def check_condition_4_2(nodes):

    c12, c13, c14, c15 = nodes

    term_1 = (1 / 5) * (c12 + c13 + c14 + c15)
    term_2 = (1 / 4) * (c12 * c13 + c12 * c14 + c12 * c15 + c13 * c14 + c13 * c15 + c14 * c15)
    term_3 = (1 / 3) * (c12 * c13 * c14 + c12 * c13 * c15 + c12 * c14 * c15 + c13 * c14 * c15)
    term_4 = (1 / 2) * (c12 * c13 * c14 * c15)

    result = term_1 - term_2 + term_3 - term_4

    return abs(result - (1 / 6)) < 1e-6  

