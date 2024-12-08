import torch
import copy
import math

from .extra_samplers_helpers import get_deis_coeff_list
from .phi_functions import *



RK_SAMPLER_NAMES = ["none",
                    "res_2m",
                    "res_3m",
                    "res_2s", 
                    "res_3s",
                    "res_5s",
                    "res_6s",
                    "res_8s",


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
                    
                    "midpoint_2s",
                    "heun_2s", 
                    "heun_3s", 
                    
                    "houwen-wray_3s",
                    "kutta_3s", 
                    "ssprk3_3s",
                    
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


IRK_SAMPLER_NAMES = ["none",
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
                    "lobatto_iiib_2s",
                    "lobatto_iiib_3s",
                    "lobatto_iiic_2s",
                    "lobatto_iiic_3s",
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
                    
                    "irk_exp_diag_2s",
                    "use_explicit", 
                    ]



alpha_crouzeix = (2/(3**0.5)) * math.cos(math.pi / 18)

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


def get_rk_methods(rk_type, h, c1=0.0, c2=0.5, c3=1.0, h_prev=None, h_prev2=None, stepcount=0, sigmas=None, sigma=None, sigma_next=None, sigma_down=None):
    FSAL = False
    multistep_stages = 0
    
    if rk_type[:4] == "deis": 
        order = int(rk_type[-2])
        if stepcount < order:
            if order == 4:
                rk_type = "res_3s"
                order = 3
            elif order == 3:
                rk_type = "res_3s"
            elif order == 2:
                rk_type = "res_2s"
        else:
            rk_type = "deis"
            multistep_stages = order-1

    
    if rk_type[-2:] == "2m": #multistep method
        if h_prev is not None: 
            multistep_stages = 1
            c2 = -h_prev / h
            rk_type = rk_type[:-2] + "2s"
        else:
            rk_type = rk_type[:-2] + "2s"
            
    if rk_type[-2:] == "3m": #multistep method
        if h_prev2 is not None: 
            multistep_stages = 2
            c2 = -h_prev2 / h_prev
            c3 = -h_prev / h
            rk_type = rk_type[:-2] + "3s"
        else:
            rk_type = rk_type[:-2] + "3s"
    
    if rk_type in rk_coeff:
        a, b, ci = copy.deepcopy(rk_coeff[rk_type])
        a = [row + [0] * (len(ci) - len(row)) for row in a]

    match rk_type:
        case "deis": 
            coeff_list = get_deis_coeff_list(sigmas, multistep_stages+1, deis_mode="rhoab")
            coeff_list = [[elem / h for elem in inner_list] for inner_list in coeff_list]
            if multistep_stages == 1:
                b1, b2 = coeff_list[stepcount]
                a = [
                        [0, 0],
                        [0, 0],
                ]
                b = [
                        [b1, b2],
                ]
                ci = [0, 0]
            if multistep_stages == 2:
                b1, b2, b3 = coeff_list[stepcount]
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
                b1, b2, b3, b4 = coeff_list[stepcount]
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
            a2_1 = c2 * phi(1, -h*c2)
            b1 =        phi(1, -h) - phi(2, -h)/c2
            b2 =        phi(2, -h)/c2

            φ = Phi(h, [0, 1/2])
            
            a2_1 = c2 * φ(1,2)
            b1 = φ(1) - φ(2)/c2
            b2 = φ(2)/c2

            a = [
                    [0,0],
                    [a2_1, 0],
            ]
            b = [
                    [b1, b2],
            ]
            ci = [0, c2]
            
        case "res_3s":
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

        case "dpmpp_2s":
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
            a6_5_alt = (2*c6**3 * φ(3,6) - a6_3*c3**2 - a6_4*c4**2)   /   c5**2
            print("a6_5 - a6_5_alt: ", a6_5, a6_5_alt, a6_5 - a6_5_alt)
                    
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

        case "res_8s":
                
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
                    [0,    0, 0, 0, 0, 0, 0, 0],
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
             
            for i in range(len(ci)): 
                a[i][0] = ci[i] * φ(1,i+1) - sum(a[i])
            for i in range(len(b)): 
                b[i][0] =         φ(1)     - sum(b[i])
            
        case "irk_exp_diag_2s":
            lam = (1 - torch.exp(-c1 * h)) / h
            a2_1 = ( torch.exp(c2*h) - torch.exp(c1*h))    /    (h * torch.exp(2*c1*h))
            b1 = (1 + c2*h + torch.exp(h) * (-1 + h - c2 *h))   /   (  (c1-c2) * h**2 * torch.exp(c1*h))
            b2 = -(1 + c1*h - torch.exp(h) * (1-h+c1*h)) /  (   (c1-c2) * h**2 * torch.exp(c2*h))

            a = [
                    [lam, 0],
                    [a2_1, lam],
            ]
            b = [
                    [b1, b2],
            ]
            ci = [c1, c2]


    ci = ci[:]
    if rk_type.startswith("lob") == False:
        ci.append(1)
    return a, b, ci, multistep_stages, FSAL

