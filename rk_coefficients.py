import torch
import copy
import math

from .extra_samplers_helpers import get_deis_coeff_list
from .phi_functions import *

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
    
    
    "dormand-prince_13s": (
        [
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [1/18, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [1/48, 1/16, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [1/32, 0, 3/32, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [5/16, 0, -75/64, 75/64, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [3/80, 0, 0, 3/16, 3/20, 0, 0, 0, 0, 0, 0, 0, 0],
            [29443841/614563906, 0, 0, 77736538/692538347, -28693883/1125000000, 23124283/1800000000, 0, 0, 0, 0, 0, 0, 0],
            [16016141/946692911, 0, 0, 61564180/158732637, 22789713/633445777, 545815736/2771057229, -180193667/1043307555, 0, 0, 0, 0, 0, 0],
            [39632708/573591083, 0, 0, -433636366/683701615, -421739975/2616292301, 100302831/723423059, 790204164/839813087, 800635310/3783071287, 0, 0, 0, 0, 0],
            [246121993/1340847787, 0, 0, -37695042795/15268766246, -309121744/1061227803, -12992083/490766935, 6005943493/2108947869, 393006217/1396673457, 123872331/1001029789, 0, 0, 0, 0],
            [-1028468189/846180014, 0, 0, 8478235783/508512852, 1311729495/1432422823, -10304129995/1701304382, -48777925059/3047939560, 15336726248/1032824649, -45442868181/3398467696, 3065993473/597172653, 0, 0, 0],
            [185892177/718116043, 0, 0, -3185094517/667107341, -477755414/1098053517, -703635378/230739211, 5731566787/1027545527, 5232866602/850066563, -4093664535/808688257, 3962137247/1805957418, 65686358/487910083, 0, 0],
            [403863854/491063109, 0, 0, -5068492393/434740067, -411421997/543043805, 652783627/914296604, 11173962825/925320556, -13158990841/6184727034, 3936647629/1978049680, -160528059/685178525, 248638103/1413531060, 0, 0],
        ],
        [
            [14005451/335480064, 0, 0, 0, 0, -59238493/1068277825, 181606767/758867731, 561292985/797845732, -1041891430/1371343529, 760417239/1151165299, 118820643/751138087, -528747749/2220607170, 1/4],
        ],
        [0, 1/18, 1/12, 1/8, 5/16, 3/8, 59/400, 93/200, 5490023248 / 9719169821, 13/20, 1201146811 / 1299019798, 1, 1],
    ),
    "dormand-prince_6s": (
        [
            [0, 0, 0, 0, 0, 0],
            [1/5, 0, 0, 0, 0, 0],
            [3/40, 9/40, 0, 0, 0, 0],
            [44/45, -56/15, 32/9, 0, 0, 0],
            [19372/6561, -25360/2187, 64448/6561, -212/729, 0, 0],
            [9017/3168, -355/33, 46732/5247, 49/176, -5103/18656, 0],
        ],
        [
            [35/384, 0, 500/1113, 125/192, -2187/6784, 11/84],
        ],
        [0, 1/5, 3/10, 4/5, 8/9, 1],
    ),
    "bogacki-shampine_7s": ( #5th order
        [
            [0, 0, 0, 0, 0, 0, 0],
            [1/6, 0, 0, 0, 0, 0, 0],
            [2/27, 4/27, 0, 0, 0, 0, 0],
            [183/1372, -162/343, 1053/1372, 0, 0, 0, 0],
            [68/297, -4/11, 42/143, 1960/3861, 0, 0, 0],
            [597/22528, 81/352, 63099/585728, 58653/366080, 4617/20480, 0, 0],
            [174197/959244, -30942/79937, 8152137/19744439, 666106/1039181, -29421/29068, 482048/414219, 0],
        ],
        [
            [587/8064, 0, 4440339/15491840, 24353/124800, 387/44800, 2152/5985, 7267/94080],
        ],
        [0, 1/6, 2/9, 3/7, 2/3, 3/4, 1] 
    ),
    "rk4_4s": (
        [
            [0, 0, 0, 0],
            [1/2, 0, 0, 0],
            [0, 1/2, 0, 0],
            [0, 0, 1, 0],
        ],
        [
            [1/6, 1/3, 1/3, 1/6],
        ],
        [0, 1/2, 1/2, 1],
    ),
    "rk38_4s": (
        [
            [0, 0, 0, 0],
            [1/3, 0, 0, 0],
            [-1/3, 1, 0, 0],
            [1, -1, 1, 0],
        ],
        [
            [1/8, 3/8, 3/8, 1/8],
        ],
        [0, 1/3, 2/3, 1],
    ),
    "ralston_4s": (
        [
            [0, 0, 0, 0],
            [2/5, 0, 0, 0],
            [(-2889+1428 * 5**0.5)/1024,   (3785-1620 * 5**0.5)/1024,  0, 0],
            [(-3365+2094 * 5**0.5)/6040,   (-975-3046 * 5**0.5)/2552,  (467040+203968*5**0.5)/240845, 0],
        ],
        [
            [(263+24*5**0.5)/1812, (125-1000*5**0.5)/3828, (3426304+1661952*5**0.5)/5924787, (30-4*5**0.5)/123],
        ],
        [0, 2/5, (14-3 * 5**0.5)/16, 1],
    ),
    "heun_3s": (
        [
            [0, 0, 0],
            [1/3, 0, 0],
            [0, 2/3, 0],
        ],
        [
            [1/4, 0, 3/4],
        ],
        [0, 1/3, 2/3],
    ),
    "kutta_3s": (
        [
            [0, 0, 0],
            [1/2, 0, 0],
            [-1, 2, 0],
        ],
        [
            [1/6, 2/3, 1/6],
        ],
        [0, 1/2, 1],
    ),
    "ralston_3s": (
        [
            [0, 0, 0],
            [1/2, 0, 0],
            [0, 3/4, 0],
        ],
        [
            [2/9, 1/3, 4/9],
        ],
        [0, 1/2, 3/4],
    ),
    "houwen-wray_3s": (
        [
            [0, 0, 0],
            [8/15, 0, 0],
            [1/4, 5/12, 0],
        ],
        [
            [1/4, 0, 3/4],
        ],
        [0, 8/15, 2/3],
    ),
    "ssprk3_3s": (
        [
            [0, 0, 0],
            [1, 0, 0],
            [1/4, 1/4, 0],
        ],
        [
            [1/6, 1/6, 2/3],
        ],
        [0, 1, 1/2],
    ),
    "midpoint_2s": (
        [
            [0, 0],
            [1/2, 0],
        ],
        [
            [0, 1],
        ],
        [0, 1/2],
    ),
    "heun_2s": (
        [
            [0, 0],
            [1, 0],
        ],
        [
            [1/2, 1/2],
        ],
        [0, 1],
    ),
    "ralston_2s": (
        [
            [0, 0],
            [2/3, 0],
        ],
        [
            [1/4, 3/4],
        ],
        [0, 2/3],
    ),
    "euler": (
        [
            [0],
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
            
        case "res_5s":
                
            c1, c2, c3, c4, c5 = 0., 0.5, 0.5, 1., 0.5
            
            a2_1 = 0.5 * phi(1, -h * c2)
            
            a3_1 = 0.5 * phi(1, -h * c3) - phi(2, -h * c3)
            a3_2 = phi(2, -h * c3)
            
            a4_1 = phi(1, -h * c4) - 2 * phi(2, -h * c4)
            a4_2 = a4_3 = phi(2, -h * c4)
            
            a5_2 = a5_3 = 0.5 * phi(2, -h * c5) - phi(3, -h * c4) + 0.25 * phi(2, -h * c4) - 0.5 * phi(3, -h * c5)
            a5_4 = 0.25 * phi(2, -h * c5) - a5_2
            a5_1 = 0.5 * phi(1, -h * c5) - 2 * a5_2 - a5_4
                    
            b1 = phi(1, -h) - 3 * phi(2, -h) + 4 * phi(3, -h)
            b2 = b3 = 0
            b4 = -phi(2, -h) + 4*phi(3, -h)
            b5 = 4 * phi(2, -h) - 8 * phi(3, -h)

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

