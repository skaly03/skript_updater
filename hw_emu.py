import math

def calc_current(U_GS, U_DS, U_th=1.7, beta=0.25):
    """
    calculates the current for a realistic measurement
    """
    if U_GS <= U_th:
        return 0.0
    V_ov = U_GS - U_th
    if U_DS < V_ov:
        return beta * (V_ov * U_DS - 0.5 * U_DS**2)
    else:
        return 0.5 * beta * V_ov**2

def dac(topic_dict, value_dict):
    """
    emulation of MOSFET transistors
    """
    username = topic_dict['username']
    meas_type = topic_dict['meas_type']
    break_bool = False

    if meas_type == 'SingleMeasurement':
        U_DS = value_dict['U_DS']
        U_GS = value_dict['U_GS']
        I_D = calc_current(U_GS, U_DS)
        if I_D > 0.1:
            break_bool = True
        return {'U_DS': U_DS, 'U_GS': U_GS, 'I_D': I_D, 'break_bool': break_bool}

    elif meas_type == 'Drain-Source-Sweep':
        start, stop, step = value_dict['U_DS']
        stop += step
        U_DS_list = [start + i * step for i in range(int((stop - start) / step))]
        U_GS = value_dict['U_GS']
        I_D_list = [calc_current(U_GS, U_DS) for U_DS in U_DS_list]
        if max(I_D_list) > 0.1:
            break_bool = True
        U_GS_list = [U_GS] * len(U_DS_list)
        return {'U_DS': U_DS_list, 'U_GS': U_GS_list, 'I_D': I_D_list, 'break_bool': break_bool}

    elif meas_type == 'Gate-Source-Sweep':
        start, stop, step = value_dict['U_GS']
        stop += step
        U_GS_list = [start + i * step for i in range(int((stop - start) / step))]
        U_DS = value_dict['U_DS']
        I_D_list = [calc_current(U_GS, U_DS) for U_GS in U_GS_list]
        if max(I_D_list) > 0.1:
            break_bool = True
        U_DS_list = [U_DS] * len(U_GS_list)
        return {'U_DS': U_DS_list, 'U_GS': U_GS_list, 'I_D': I_D_list, 'break_bool': break_bool}

    elif meas_type == 'CombinedSweep':
        start_gs, stop_gs, step_gs = value_dict['U_GS']
        stop_gs += step_gs
        start_ds, stop_ds, step_ds = value_dict['U_DS']
        stop_ds += step_ds

        U_GS_list = [start_gs + i * step_gs for i in range(int((stop_gs - start_gs) / step_gs))]
        U_DS_list = [start_ds + i * step_ds for i in range(int((stop_ds - start_ds) / step_ds))]

        I_D_return = []
        for U_GS in U_GS_list:
            I_D_row = [calc_current(U_GS, U_DS) for U_DS in U_DS_list]
            if max(I_D_row) > 0.1:
                break_bool = True
            I_D_return.append(I_D_row)

        U_GS_return = [[U_GS for U_GS in U_GS_list] for _ in U_GS_list]
        U_DS_return = [[u_ds for u_ds in U_DS_list] for _ in U_GS_list]

        return {'U_DS': U_DS_return, 'U_GS': U_GS_return, 'I_D': I_D_return, 'break_bool': break_bool}

    else:
        return 'unknown measurement type'
