
import math
def dac(topic_dict, value_dict):
    username = topic_dict['username']
    meas_type = topic_dict['meas_type']
    break_bool = False
    
    if meas_type == 'SingleMeasurement':
        U_DS = value_dict['U_DS']
        U_GS = value_dict['U_GS']
        A = 300/2 * (U_GS-1.7)
        I_D = A * (1-math.e**(-(U_GS-1.7)*U_DS))
        if I_D > 0.1:
            break_bool = True
        return_dict =  {'U_DS': U_DS, 'U_GS': U_GS, 'I_D': I_D, 'break_bool': break_bool}
    elif meas_type == 'Drain-Source-Sweep':
        start = value_dict['U_DS'][0]
        stop = value_dict['U_DS'][1] + value_dict['U_DS'][2] # damit stop value inklusiv ist
        step = value_dict['U_DS'][2]
        U_DS_list = [start + i * step for i in range(int((stop-start)/step))]
        U_GS = value_dict['U_GS']
        A = 300/2 * (U_GS-1.7)
        I_D_list = [A * (1-math.e**(-(U_GS-1.7)*U_DS)) for U_DS in U_DS_list]
        if max(I_D_list) > 0.1:
            break_bool = True
        U_GS_list = [U_GS for i in range(len(U_DS_list))]
        return_dict =  {'U_DS': U_DS_list, 'U_GS': U_GS_list, 'I_D': I_D_list, 'break_bool': break_bool}
    elif meas_type == 'Gate-Source-Sweep':
        start = value_dict['U_GS'][0]
        stop = value_dict['U_GS'][1] + value_dict['U_GS'][2]
        step = value_dict['U_GS'][2]
        U_GS_list = [start + i * step for i in range(int((stop-start)/step))]
        U_DS = value_dict['U_DS']
        A = 0.2
        I_D_list = [A * (1-math.e**(-(U_GS-1.7)*U_DS)) if (A * (1-math.e**(-(U_GS-1.7)*U_DS))) >= 0 else 0 for U_GS in U_GS_list]
        if max(I_D_list) > 0.1:
            break_bool = True
        U_DS_list = [U_DS for i in range(len(U_GS_list))]
        return_dict =  {'U_DS': U_DS_list, 'U_GS': U_GS_list, 'I_D': I_D_list, 'break_bool': break_bool}
    elif meas_type == 'CombinedSweep':
        U_GS_return = []
        U_DS_return = []
        I_D_return = []
        start_gs = value_dict['U_GS'][0]
        stop_gs = value_dict['U_GS'][1] + value_dict['U_GS'][2]
        step_gs = value_dict['U_GS'][2]
        
        start_ds = value_dict['U_DS'][0]
        stop_ds = value_dict['U_DS'][1] + value_dict['U_DS'][2] # damit stop value inklusiv ist
        step_ds = value_dict['U_DS'][2]
        
        U_GS_list = [start_gs + i * step_gs for i in range(int((stop_gs-start_gs)/step_gs))]
        U_DS_list = [start_ds + i * step_ds for i in range(int((stop_ds-start_ds)/step_ds))]
        for U_GS in U_GS_list:
            A = 300/2 * (U_GS-1.7)
            I_D_list = [A * (1-math.e**(-(U_GS-1.7)*U_DS)) if (A * (1-math.e**(-(U_GS-1.7)*U_DS))) >= 0 else 0 for U_DS in U_DS_list]
            if max(I_D_list) > 0.1:
                break_bool = True
            I_D_return.append(I_D_list)
            del(I_D_list)
        for i in range(len(I_D_return)):
            U_GS_return.append(U_GS_list)
            U_DS_return.append(U_DS_list)
        return_dict = {'U_DS': U_DS_return, 'U_GS': U_GS_return, 'I_D': I_D_return, 'break_bool': break_bool}
    else:
        return 'unknown measurement type'
    return return_dict
